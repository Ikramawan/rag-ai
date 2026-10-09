import json
import re
import sys
from pathlib import Path

import numpy as np
import requests
from rank_bm25 import BM25Okapi

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = PROJECT_ROOT / "data" / "index"

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "should",
    "the",
    "their",
    "this",
    "to",
    "we",
    "what",
    "when",
    "where",
    "which",
    "with",
    "you",
    "your",
}


def tokenize(text: str) -> list[str]:
    return [
        token for token in re.findall(r"\w+", text.lower()) if token not in STOP_WORDS
    ]


def combine_rankings(
    semantic_scores: np.ndarray,
    keyword_scores: np.ndarray,
    top_k: int,
) -> list[int]:
    candidate_count = min(len(semantic_scores), max(10, top_k))
    combined = {}

    semantic_order = np.argsort(-semantic_scores)[:candidate_count]
    keyword_order = [
        position
        for position in np.argsort(-keyword_scores)
        if keyword_scores[position] > 0
    ][:candidate_count]

    for ranking in (semantic_order, keyword_order):
        for rank, position in enumerate(ranking, start=1):
            position = int(position)
            combined[position] = combined.get(position, 0.0) + 1.0 / (60 + rank)

    return sorted(
        combined,
        key=lambda position: combined[position],
        reverse=True,
    )[:top_k]


def search(question: str, top_k: int = 3) -> list[dict]:
    if not question.strip() or top_k < 1:
        raise ValueError("Provide a question and a positive top_k.")

    with np.load(INDEX_DIR / "index.npz", allow_pickle=False) as index:
        metadata = json.loads(index["metadata"].item())
        vectors = index["vectors"]

    chunks = metadata["chunks"]

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

    query = np.asarray(response.json()["embeddings"][0], dtype=np.float32)

    if query.shape != (vectors.shape[1],) or not np.isfinite(query).all():
        raise ValueError("Query embedding does not match the index.")

    vector_norms = np.linalg.norm(vectors, axis=1)
    query_norm = np.linalg.norm(query)

    if query_norm == 0 or np.any(vector_norms == 0):
        raise ValueError("Cannot compare zero-length vectors.")

    scores = (vectors @ query) / (vector_norms * query_norm)

    corpus = [tokenize(chunk["text"]) for chunk in chunks]
    bm25 = BM25Okapi(corpus)
    keyword_scores = bm25.get_scores(tokenize(question))

    positions = combine_rankings(scores, keyword_scores, top_k)

    return [
        {
            **chunks[position],
            "score": float(scores[position]),
            "keyword_score": float(keyword_scores[position]),
        }
        for position in positions
    ]


def main() -> None:
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit('Usage: python -m app.search_documents "your question"')

    for result in search(question):
        print(f"\nSource: {result.get('source_url', result['source'])}")
        print(f"Chunk: {result['chunk_id']}")
        print(f"Similarity: {result['score']:.3f}")
        print(f"Keyword score: {result['keyword_score']:.3f}")
        print(result["text"])


if __name__ == "__main__":
    main()
