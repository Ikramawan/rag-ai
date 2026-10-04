import json
from pathlib import Path

import numpy as np
import requests

from app.chunking import split_text
from app.document_loader import SUPPORTED_EXTENSIONS, load_document

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
INDEX_DIR = PROJECT_ROOT / "data" / "index"
MODEL = "nomic-embed-text"


def main() -> None:
    chunks = []

    for path in sorted(DOCUMENTS_DIR.rglob("*")):
        if not path.is_file() or path.name.startswith("~$"):
            continue

        source = path.relative_to(DOCUMENTS_DIR).as_posix()

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"Skipped unsupported file: {source}")
            continue

        text = load_document(path)
        sections = text.split("\n## ")
        title = path.stem

        for position, section in enumerate(sections):
            if position > 0:
                section = "## " + section

            for part, chunk in enumerate(split_text(section)):
                chunks.append(
                    {
                        "source": source,
                        "chunk_id": f"{source}:{position}:{part}",
                        "text": f"Document: {title}\n\n{chunk}",
                    }
                )

        print(f"Loaded: {source}")

    if not chunks:
        raise ValueError("No readable supported documents found.")

    response = requests.post(
        "http://localhost:11434/api/embed",
        json={
            "model": MODEL,
            "input": [f"search_document: {chunk['text']}" for chunk in chunks],
            "truncate": False,
        },
        timeout=180,
    )
    response.raise_for_status()

    vectors = np.asarray(response.json()["embeddings"], dtype=np.float32)

    if (
        vectors.ndim != 2
        or vectors.shape[0] != len(chunks)
        or vectors.shape[1] == 0
        or not np.isfinite(vectors).all()
    ):
        raise ValueError("Invalid embedding response.")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_DIR / "vectors.npy", vectors)
    (INDEX_DIR / "chunks.json").write_text(
        json.dumps(
            {"embedding_model": MODEL, "chunks": chunks},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Indexed {len(chunks)} chunks.")
    print(f"Vector shape: {vectors.shape}")


if __name__ == "__main__":
    main()
