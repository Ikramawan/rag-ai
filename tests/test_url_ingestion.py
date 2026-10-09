import json
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from app import answer_question, index_documents, search_documents, url_documents


@pytest.fixture
def snapshot():
    return {
        "version": 1,
        "source_url": "https://docs.example.com/vpn",
        "resolved_url": "https://docs.example.com/guides/vpn",
        "fetched_at": "2026-10-09T12:00:00+00:00",
        "text": "Synthetic VPN guide. Obtain an approved VPN account and enable MFA.",
    }


def test_url_origin_survives_index_search_and_answer(tmp_path, monkeypatch, snapshot):
    documents_dir = tmp_path / "documents"
    index_dir = tmp_path / "index"
    path = url_documents.save_snapshot(snapshot, documents_dir)
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)
    monkeypatch.setattr(search_documents, "INDEX_DIR", index_dir)
    chat_payloads = []

    def fake_post(url, *, json, timeout):
        if url.endswith("/api/chat"):
            chat_payloads.append(json)
            payload = {
                "message": {"content": "Approved account and MFA are required [1]."}
            }
        else:
            inputs = json["input"]
            count = len(inputs) if isinstance(inputs, list) else 1
            payload = {"embeddings": [[1.0, 2.0] for _ in range(count)]}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr(index_documents.requests, "post", fake_post)
    report = index_documents.main()
    assert report["loaded"] == [path.relative_to(documents_dir).as_posix()]
    assert report["skipped"] == []
    with np.load(index_dir / "index.npz", allow_pickle=False) as saved:
        chunk = json.loads(saved["metadata"].item())["chunks"][0]
    for key in ("source_url", "resolved_url", "fetched_at"):
        assert chunk[key] == snapshot[key]
    assert snapshot["text"] in chunk["text"]
    result = search_documents.search("VPN prerequisites")[0]
    assert result["source_url"] == snapshot["source_url"]
    output = answer_question.answer("VPN prerequisites")
    assert f"[1] {snapshot['source_url']}" in output
    assert snapshot["source_url"] in chat_payloads[0]["messages"][1]["content"]


def test_invalid_snapshot_preserves_active_index(tmp_path, monkeypatch, snapshot):
    documents_dir = tmp_path / "documents"
    index_dir = tmp_path / "index"
    path = url_documents.save_snapshot(snapshot, documents_dir)
    path.write_text('{"version": 1, "text": "Missing provenance"}', encoding="utf-8")
    index_dir.mkdir()
    active_index = index_dir / "index.npz"
    metadata = {
        "embedding_model": "nomic-embed-text",
        "chunks": [
            {"source": "old.txt", "chunk_id": "old.txt:0:0", "text": "Old evidence"}
        ],
    }
    np.savez_compressed(
        active_index,
        vectors=np.array([[1.0, 2.0]]),
        metadata=np.asarray(json.dumps(metadata)),
    )
    previous_bytes = active_index.read_bytes()
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)
    post = Mock(side_effect=AssertionError("Embedding should not start"))
    monkeypatch.setattr(index_documents.requests, "post", post)
    with pytest.raises(ValueError, match="Could not load document") as failure:
        index_documents.main()
    assert "existing index is unchanged" in str(failure.value)
    post.assert_not_called()
    assert active_index.read_bytes() == previous_bytes
    with np.load(active_index, allow_pickle=False) as saved:
        assert (
            json.loads(saved["metadata"].item())["chunks"][0]["text"] == "Old evidence"
        )
    assert list(index_dir.iterdir()) == [active_index]
