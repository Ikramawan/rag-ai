"""Import a single public HTML page as an immutable local text snapshot."""

import hashlib
import ipaddress
import json
import os
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from app.document_loader import extract_html

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
SNAPSHOT_SUFFIX = ".url.json"


def validate_url(url: str) -> str:
    url = urldefrag(url.strip())[0]
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.port not in {None, 80, 443}
        or any(character.isspace() or ord(character) < 32 for character in url)
    ):
        raise ValueError(
            "Use a public HTTP/HTTPS URL without credentials or custom ports."
        )
    return url


def _validate_public_host(url: str) -> None:
    parts = urlsplit(url)
    try:
        addresses = socket.getaddrinfo(
            parts.hostname,
            parts.port or (443 if parts.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("Could not resolve the documentation host.") from exc
    if not addresses or any(
        not ipaddress.ip_address(address[4][0]).is_global for address in addresses
    ):
        raise ValueError("Only public documentation hosts are supported.")


def fetch_page(url: str) -> dict:
    original_url = validate_url(url)
    current_url = original_url
    with requests.Session() as session:
        # Public imports must not pick up local account credentials or proxies.
        session.trust_env = False
        for redirect in range(MAX_REDIRECTS + 1):
            _validate_public_host(current_url)
            with session.get(
                current_url,
                stream=True,
                allow_redirects=False,
                timeout=(5, 15),
                headers={
                    "User-Agent": "Local-RAG-Assistant/1.0",
                    "Accept": "text/html",
                },
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location or redirect == MAX_REDIRECTS:
                        raise ValueError(
                            "Missing redirect target or too many redirects."
                        )
                    current_url = validate_url(urljoin(current_url, location))
                    continue
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError(
                        "The documentation page did not return usable content."
                    )
                media_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .lower()
                    .strip()
                )
                if media_type not in {"text/html", "application/xhtml+xml"}:
                    raise ValueError("Only HTML documentation pages are supported.")
                body = bytearray()
                for part in response.iter_content(chunk_size=16 * 1024):
                    body.extend(part)
                    if len(body) > MAX_BYTES:
                        raise ValueError("Documentation page exceeds the 2 MiB limit.")
                if BeautifulSoup(bytes(body), "html.parser").find(
                    "input", attrs={"type": "password"}
                ):
                    raise ValueError(
                        "Sign-in pages are not documentation; use a public page."
                    )
                text = extract_html(bytes(body))
                return {
                    "version": 1,
                    "source_url": original_url,
                    "resolved_url": current_url,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "text": text,
                }
    raise ValueError("Could not fetch documentation page.")


def validate_snapshot(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        raise ValueError("Invalid URL snapshot version.")
    for key in ("source_url", "resolved_url", "fetched_at", "text"):
        if not isinstance(snapshot.get(key), str) or not snapshot[key].strip():
            raise ValueError(f"Invalid URL snapshot field: {key}")
    validate_url(snapshot["source_url"])
    validate_url(snapshot["resolved_url"])
    if datetime.fromisoformat(snapshot["fetched_at"]).tzinfo is None:
        raise ValueError("URL snapshot fetch time must include a timezone.")
    return snapshot


def load_snapshot(path: Path) -> dict:
    return validate_snapshot(json.loads(path.read_text(encoding="utf-8")))


def save_snapshot(snapshot: dict, documents_dir: Path) -> Path:
    validate_snapshot(snapshot)
    directory = documents_dir / "url-imports"
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(snapshot["source_url"].encode()).hexdigest()
    destination = directory / f"{digest}{SNAPSHOT_SUFFIX}"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(snapshot, temporary, ensure_ascii=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        # Publish the complete file atomically, refusing to overwrite an import.
        os.link(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return destination
