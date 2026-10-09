import json
from types import SimpleNamespace

import numpy as np
import pytest
import requests

from app import index_documents


def test_embedding_batches_preserve_order(tmp_path, monkeypatch):
    documents_dir = tmp_path / "documents"
    index_dir = tmp_path / "index"
    documents_dir.mkdir()
    (documents_dir / "sample.txt").write_text("Sample", encoding="utf-8")

    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)
    monkeypatch.setattr(
        index_documents,
        "split_text",
        lambda text: [f"chunk-{number}" for number in range(65)],
    )

    batch_sizes = []

    def fake_post(url, *, json, timeout):
        inputs = json["input"]
        batch_sizes.append(len(inputs))

        # Give each chunk a distinctive vector to check its saved position.
        embeddings = [[float(text.rsplit("chunk-", 1)[1]), 1.0] for text in inputs]

        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"embeddings": embeddings},
        )

    monkeypatch.setattr(index_documents.requests, "post", fake_post)

    report = index_documents.main()

    assert batch_sizes == [32, 32, 1]
    assert report["chunk_count"] == 65

    with np.load(index_dir / "index.npz", allow_pickle=False) as saved:
        vectors = saved["vectors"]
        metadata = json.loads(saved["metadata"].item())

    assert vectors.shape == (65, 2)
    np.testing.assert_array_equal(vectors[:, 0], np.arange(65))
    np.testing.assert_array_equal(vectors[:, 1], np.ones(65))

    assert [chunk["text"] for chunk in metadata["chunks"]] == [
        f"Document: sample\n\nchunk-{number}" for number in range(65)
    ]


def test_later_embedding_batch_failure_preserves_previous_index(tmp_path, monkeypatch):
    documents_dir = tmp_path / "documents"
    index_dir = tmp_path / "index"
    documents_dir.mkdir()
    index_dir.mkdir()
    (documents_dir / "sample.txt").write_text("Sample", encoding="utf-8")

    previous_metadata = {
        "embedding_model": index_documents.MODEL,
        "chunks": [
            {
                "source": "previous.txt",
                "chunk_id": "previous.txt:0:0",
                "text": "Document: previous\n\nPreviously indexed content.",
            }
        ],
    }
    previous_vectors = np.array([[1.0, 2.0]], dtype=np.float32)
    active_index = index_dir / "index.npz"
    np.savez_compressed(
        active_index,
        vectors=previous_vectors,
        metadata=np.asarray(json.dumps(previous_metadata)),
    )
    original_bytes = active_index.read_bytes()

    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)
    monkeypatch.setattr(
        index_documents,
        "split_text",
        lambda text: [f"chunk-{number}" for number in range(65)],
    )

    batch_sizes = []

    def fail_response():
        raise requests.HTTPError("Simulated later embedding batch failure")

    def fake_post(url, *, json, timeout):
        inputs = json["input"]
        batch_sizes.append(len(inputs))
        if len(batch_sizes) > 1:
            return SimpleNamespace(raise_for_status=fail_response)

        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"embeddings": [[3.0, 4.0] for _ in inputs]},
        )

    monkeypatch.setattr(index_documents.requests, "post", fake_post)

    with pytest.raises(
        requests.HTTPError, match="Simulated later embedding batch failure"
    ):
        index_documents.main()

    assert batch_sizes == [32, 32]
    assert active_index.read_bytes() == original_bytes
    assert list(index_dir.iterdir()) == [active_index]

    with np.load(active_index, allow_pickle=False) as saved:
        assert json.loads(saved["metadata"].item()) == previous_metadata
        np.testing.assert_array_equal(saved["vectors"], previous_vectors)
