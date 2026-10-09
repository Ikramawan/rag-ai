import json
import os
import tempfile
from pathlib import Path

import numpy as np
import requests

from app.chunking import split_text
from app.document_loader import SUPPORTED_EXTENSIONS, load_document
from app.url_documents import SNAPSHOT_SUFFIX, load_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
INDEX_DIR = PROJECT_ROOT / "data" / "index"
MODEL = "nomic-embed-text"


def main() -> dict:
    chunks = []
    loaded = []
    skipped = []

    for path in sorted(DOCUMENTS_DIR.rglob("*")):
        if not path.is_file() or path.name.startswith("~$"):
            continue

        source = path.relative_to(DOCUMENTS_DIR).as_posix()

        is_snapshot = path.name.endswith(SNAPSHOT_SUFFIX)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS and not is_snapshot:
            print(f"Skipped unsupported file: {source}")
            skipped.append(source)
            continue

        try:
            provenance = {}
            if is_snapshot:
                snapshot = load_snapshot(path)
                text = snapshot["text"]
                provenance = {
                    key: snapshot[key]
                    for key in ("source_url", "resolved_url", "fetched_at")
                }
            else:
                text = load_document(path)
        except ValueError as exc:
            raise ValueError(
                f"Could not load document '{source}': {exc}. "
                "No new index was published; any existing index is unchanged."
            ) from exc
        sections = text.split("\n## ")
        title = provenance.get("source_url", path.stem)

        for position, section in enumerate(sections):
            if position > 0:
                section = "## " + section

            for part, chunk in enumerate(split_text(section)):
                chunks.append(
                    {
                        "source": source,
                        "chunk_id": f"{source}:{position}:{part}",
                        "text": f"Document: {title}\n\n{chunk}",
                        **provenance,
                    }
                )

        print(f"Loaded: {source}")
        loaded.append(source)

    if not chunks:
        raise ValueError("No readable supported documents found.")

    batch_size = 32
    vector_batches = []
    dimensions = None

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]

        response = requests.post(
            "http://localhost:11434/api/embed",
            json={
                "model": MODEL,
                "input": [f"search_document: {chunk['text']}" for chunk in batch],
                "truncate": False,
            },
            timeout=180,
        )
        response.raise_for_status()

        batch_vectors = np.asarray(
            response.json()["embeddings"],
            dtype=np.float32,
        )

        if (
            batch_vectors.ndim != 2
            or batch_vectors.shape[0] != len(batch)
            or batch_vectors.shape[1] == 0
            or not np.isfinite(batch_vectors).all()
        ):
            raise ValueError("Invalid embedding response.")

        if dimensions is None:
            dimensions = batch_vectors.shape[1]
        elif batch_vectors.shape[1] != dimensions:
            raise ValueError("Embedding dimensions changed between batches.")

        vector_batches.append(batch_vectors)
        print(f"Embedded {start + len(batch)}/{len(chunks)} chunks.")

    vectors = np.concatenate(vector_batches, axis=0)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    metadata = json.dumps(
        {"embedding_model": MODEL, "chunks": chunks},
        ensure_ascii=False,
    )

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=INDEX_DIR,
            suffix=".npz",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            np.savez_compressed(
                temporary,
                vectors=vectors,
                metadata=np.asarray(metadata),
            )
            temporary.flush()
            os.fsync(temporary.fileno())

        os.replace(temporary_path, INDEX_DIR / "index.npz")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    print(f"Indexed {len(chunks)} chunks.")
    print(f"Vector shape: {vectors.shape}")
    return {
        "loaded": loaded,
        "skipped": skipped,
        "chunk_count": len(chunks),
    }


if __name__ == "__main__":
    main()
