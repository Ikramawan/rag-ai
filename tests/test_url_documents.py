import socket
from unittest.mock import MagicMock

import pytest
import requests

from app import url_documents


@pytest.fixture
def http(monkeypatch):
    session = MagicMock()
    session.__enter__.return_value = session
    monkeypatch.setattr(url_documents.requests, "Session", lambda: session)
    monkeypatch.setattr(
        url_documents.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    return session


def response(
    body=b"<main><h1>Synthetic guide</h1><p>Enable MFA.</p></main>",
    *,
    status=200,
    headers=None,
):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.headers = {"Content-Type": "text/html", **(headers or {})}
    result.iter_content.return_value = iter([body])
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError("HTTP failure")
    return result


def test_fetch_extracts_documentation_and_records_origin(http):
    http.get.return_value = response(
        b"<nav>Menu</nav><main><p>Synthetic guide</p>"
        b"<table><tr><th>Task</th><th>Requirement</th></tr>"
        b"<tr><td>VPN</td><td>MFA</td></tr></table></main><footer>Footer</footer>"
    )
    snapshot = url_documents.fetch_page("https://docs.example.com/guide#section")
    assert snapshot["source_url"] == "https://docs.example.com/guide"
    assert snapshot["resolved_url"] == snapshot["source_url"]
    assert "Task | Requirement\nVPN | MFA" in snapshot["text"]
    assert "Menu" not in snapshot["text"]
    assert "Footer" not in snapshot["text"]
    assert url_documents.validate_snapshot(snapshot) == snapshot
    assert http.trust_env is False
    assert http.get.call_count == 1  # Linked pages are not crawled.


def test_relative_redirect_records_both_urls(http):
    http.get.side_effect = [
        response(status=302, headers={"Location": "/new"}),
        response(),
    ]
    snapshot = url_documents.fetch_page("https://docs.example.com/old")
    assert snapshot["source_url"].endswith("/old")
    assert snapshot["resolved_url"] == "https://docs.example.com/new"
    assert http.get.call_count == 2


def test_login_form_is_rejected(http):
    http.get.return_value = response(b'<main>Sign in<input type="password"></main>')
    with pytest.raises(ValueError, match="Sign-in pages"):
        url_documents.fetch_page("https://docs.example.com/guide")


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/doc",
        "ftp://example.com/doc",
        "https://user:pass@example.com",
        "http://example.com:11434",
        "https://example.com/bad path",
    ],
)
def test_invalid_urls_never_reach_http(http, url):
    with pytest.raises(ValueError):
        url_documents.fetch_page(url)
    http.get.assert_not_called()


def test_private_redirect_is_rejected_before_following(http, monkeypatch):
    http.get.return_value = response(
        status=302, headers={"Location": "http://127.0.0.1/"}
    )
    monkeypatch.setattr(
        url_documents.socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", 80),
            )
        ],
    )
    with pytest.raises(ValueError, match="Only public"):
        url_documents.fetch_page("https://docs.example.com/guide")
    assert http.get.call_count == 1


@pytest.mark.parametrize(
    "kind", ["non_html", "empty", "oversized", "redirect_loop", "http_error", "timeout"]
)
def test_fetch_failures_are_reported(http, monkeypatch, kind):
    if kind == "non_html":
        http.get.return_value = response(headers={"Content-Type": "application/pdf"})
    elif kind == "empty":
        http.get.return_value = response(b"<main><script>Ignored</script></main>")
    elif kind == "oversized":
        monkeypatch.setattr(url_documents, "MAX_BYTES", 20)
        http.get.return_value = response(b"x" * 21)
    elif kind == "redirect_loop":
        http.get.side_effect = [
            response(status=302, headers={"Location": "/loop"}) for _ in range(4)
        ]
    elif kind == "http_error":
        http.get.return_value = response(status=403)
    else:
        http.get.side_effect = requests.Timeout("Timed out")
    with pytest.raises((ValueError, requests.RequestException)):
        url_documents.fetch_page("https://docs.example.com/guide")


def test_snapshot_roundtrip_and_duplicate_does_not_overwrite(tmp_path, http):
    http.get.return_value = response()
    snapshot = url_documents.fetch_page("https://docs.example.com/guide")
    path = url_documents.save_snapshot(snapshot, tmp_path)
    original_bytes = path.read_bytes()
    assert url_documents.load_snapshot(path) == snapshot
    with pytest.raises(FileExistsError):
        url_documents.save_snapshot({**snapshot, "text": "Changed text"}, tmp_path)
    assert path.read_bytes() == original_bytes
    assert list(path.parent.iterdir()) == [path]


def test_failed_snapshot_publication_leaves_no_partial_file(
    tmp_path, http, monkeypatch
):
    http.get.return_value = response()
    snapshot = url_documents.fetch_page("https://docs.example.com/guide")

    def fail_link(*args):
        raise OSError("Simulated publication failure")

    monkeypatch.setattr(url_documents.os, "link", fail_link)
    with pytest.raises(OSError, match="Simulated publication failure"):
        url_documents.save_snapshot(snapshot, tmp_path)
    assert list((tmp_path / "url-imports").iterdir()) == []
