"""Structural checks shared by index publication and retrieval."""

import json
import re
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile

import numpy as np

from app.url_documents import SNAPSHOT_SUFFIX, validate_snapshot


def validate_index(
    metadata: dict, vectors: np.ndarray, *, expected_sources=None
) -> dict:
    if (
        not isinstance(metadata, dict)
        or not isinstance(metadata.get("embedding_model"), str)
        or not metadata["embedding_model"].strip()
    ):
        raise ValueError("Index embedding model is missing.")
    chunks = metadata.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("Index must contain chunks.")
    if (
        vectors.ndim != 2
        or vectors.shape[0] != len(chunks)
        or vectors.shape[1] == 0
        or vectors.dtype.kind not in "iuf"
        or not np.isfinite(vectors).all()
    ):
        raise ValueError("Index vectors are invalid or do not match the chunks.")
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        norms = np.linalg.norm(vectors, axis=1)
    if not np.isfinite(norms).all() or np.any(norms == 0):
        raise ValueError("Index contains unusable vector norms.")

    identifiers = set()
    sources = set()
    for chunk in chunks:
        if not isinstance(chunk, dict) or any(
            not isinstance(chunk.get(key), str) or not chunk[key].strip()
            for key in ("source", "chunk_id", "text")
        ):
            raise ValueError("Index chunk fields are missing or empty.")
        source = chunk["source"]
        path = PurePosixPath(source)
        if path.is_absolute() or ".." in path.parts or "\\" in source:
            raise ValueError("Index sources must be relative document paths.")
        if not re.fullmatch(re.escape(source) + r":\d+:\d+", chunk["chunk_id"]):
            raise ValueError("Chunk ID does not identify its source.")
        if chunk["chunk_id"] in identifiers:
            raise ValueError("Index contains duplicate chunk IDs.")
        if (
            chunk["text"].startswith("Document:")
            and not chunk["text"].partition("\n\n")[2].strip()
        ):
            raise ValueError("Index chunk contains a document label without evidence.")
        identifiers.add(chunk["chunk_id"])
        sources.add(source)
        provenance = ("source_url", "resolved_url", "fetched_at")
        if source.endswith(SNAPSHOT_SUFFIX) or any(key in chunk for key in provenance):
            validate_snapshot(
                {
                    "version": 1,
                    "text": chunk["text"],
                    **{key: chunk.get(key) for key in provenance},
                }
            )

    if expected_sources is not None and sources != set(expected_sources):
        raise ValueError("Index source coverage does not match the loaded documents.")
    return {
        "document_count": len(sources),
        "chunk_count": len(chunks),
        "dimensions": vectors.shape[1],
        "checks": [
            "Vectors match chunks and have finite, nonzero norms",
            "Chunk IDs are unique and identify nonempty source evidence",
            "URL provenance is complete where required",
        ],
    }


def load_index(path: Path, *, expected_sources=None) -> tuple[dict, np.ndarray, dict]:
    try:
        with np.load(path, allow_pickle=False) as index:
            serialized = index["metadata"]
            if serialized.shape != () or serialized.dtype.kind != "U":
                raise ValueError("Index metadata must be a scalar JSON string.")
            metadata = json.loads(serialized.item())
            vectors = index["vectors"]
        report = validate_index(metadata, vectors, expected_sources=expected_sources)
    except (OSError, ValueError, KeyError, TypeError, EOFError, BadZipFile) as exc:
        raise ValueError(f"Invalid index: {exc}") from exc
    report["checks"].insert(0, "Saved index archive is readable")
    if expected_sources is not None:
        report["checks"].append("Every loaded document is represented")
    return metadata, vectors, report
