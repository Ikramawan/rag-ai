import json
from pathlib import Path

import numpy as np
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
INDEX_DIR = PROJECT_ROOT / "data" / "index"
MODEL = "nomic-embed-text"


def main() -> None:
    chunks = []

    for path in sorted(DOCUMENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")

        # For this first sample, split at second-level headings.
        sections = text.split("\n## ")
        title = sections[0].splitlines()[0].removeprefix("# ").strip()

        for position, section in enumerate(sections):
            if position > 0:
                section = "## " + section

            if section.strip():
                chunks.append(
                    {
                        "source": path.name,
                        "chunk_id": f"{path.name}:{position}",
                        "text": f"Document: {title}\n\n{section.strip()}",
                    }
                )

    if not chunks:
        raise ValueError("No non-empty Markdown documents found.")

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
