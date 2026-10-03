import json
import sys
from pathlib import Path

import numpy as np
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = PROJECT_ROOT / "data" / "index"


def search(question: str, top_k: int = 3) -> list[dict]:
    if not question.strip() or top_k < 1:
        raise ValueError("Provide a question and a positive top_k.")

    metadata = json.loads(
        (INDEX_DIR / "chunks.json").read_text(encoding="utf-8")
    )
    chunks = metadata["chunks"]
    vectors = np.load(INDEX_DIR / "vectors.npy", allow_pickle=False)

    if (
        vectors.ndim != 2
        or vectors.shape[0] != len(chunks)
        or not chunks
        or not np.isfinite(vectors).all()
    ):
        raise ValueError("Invalid index. Rebuild it.")

    response = requests.post(
        "http://localhost:11434/api/embed",
        json={
            "model": metadata["embedding_model"],
            "input": f"search_query: {question}",
            "truncate": False,
        },
        timeout=120,
    )
    response.raise_for_status()

    query = np.asarray(
        response.json()["embeddings"][0], dtype=np.float32
    )

    if query.shape != (vectors.shape[1],) or not np.isfinite(query).all():
        raise ValueError("Query embedding does not match the index.")

    vector_norms = np.linalg.norm(vectors, axis=1)
    query_norm = np.linalg.norm(query)

    if query_norm == 0 or np.any(vector_norms == 0):
        raise ValueError("Cannot compare zero-length vectors.")

    scores = (vectors @ query) / (vector_norms * query_norm)
    positions = np.argsort(-scores)[:top_k]

    return [
        {**chunks[int(position)], "score": float(scores[position])}
        for position in positions
    ]


def main() -> None:
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit(
            'Usage: python -m app.search_documents "your question"'
        )

    for result in search(question):
        print(f"\nSource: {result['source']}")
        print(f"Chunk: {result['chunk_id']}")
        print(f"Similarity: {result['score']:.3f}")
        print(result["text"])


if __name__ == "__main__":
    main()