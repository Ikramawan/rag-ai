import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from app import index_documents, search_documents
from app.index_validation import load_index, validate_index


@pytest.fixture
def metadata():
    return {
        "embedding_model": "nomic-embed-text",
        "chunks": [
            {
                "source": "sample.txt",
                "chunk_id": "sample.txt:0:0",
                "text": "Document: sample\n\nSynthetic evidence.",
            }
        ],
    }


@pytest.mark.parametrize(
    "defect",
    [
        "zero",
        "nonfinite",
        "zero_dimensions",
        "wrong_count",
        "empty_text",
        "label_only",
        "duplicate_id",
        "wrong_source_id",
        "invalid_path",
        "missing_url_provenance",
        "missing_model",
    ],
)
def test_invalid_index_is_rejected(metadata, defect):
    vectors = np.array([[1.0, 2.0]], dtype=np.float32)
    chunk = metadata["chunks"][0]
    if defect == "zero":
        vectors[:] = 0
    elif defect == "nonfinite":
        vectors[0, 0] = np.nan
    elif defect == "zero_dimensions":
        vectors = np.empty((1, 0))
    elif defect == "wrong_count":
        vectors = np.ones((2, 2))
    elif defect == "empty_text":
        chunk["text"] = " "
    elif defect == "label_only":
        chunk["text"] = "Document: sample\n\n"
    elif defect == "duplicate_id":
        metadata["chunks"].append(copy.deepcopy(chunk))
        vectors = np.ones((2, 2))
    elif defect == "wrong_source_id":
        chunk["chunk_id"] = "another.txt:0:0"
    elif defect == "invalid_path":
        chunk["source"] = "../sample.txt"
    elif defect == "missing_url_provenance":
        chunk["source_url"] = "https://docs.example.com/guide"
    else:
        metadata.pop("embedding_model")
    with pytest.raises(ValueError):
        validate_index(metadata, vectors)


def test_loaded_document_coverage_is_required(metadata):
    with pytest.raises(ValueError, match="source coverage"):
        validate_index(
            metadata, np.ones((1, 2)), expected_sources=["sample.txt", "missing.txt"]
        )


@pytest.mark.parametrize(
    "defect",
    [
        "corrupt_archive",
        "empty_archive",
        "zero_vectors",
        "duplicate_ids",
        "changed_content",
        "changed_vectors",
    ],
)
def test_failed_candidate_validation_preserves_active_index(
    tmp_path, monkeypatch, metadata, defect
):
    documents = tmp_path / "documents"
    index_dir = tmp_path / "index"
    documents.mkdir()
    index_dir.mkdir()
    (documents / "sample.txt").write_text("New synthetic evidence.", encoding="utf-8")
    active_index = index_dir / "index.npz"
    original_save = np.savez_compressed
    original_save(
        active_index,
        vectors=np.array([[1.0, 2.0]], dtype=np.float32),
        metadata=np.asarray(json.dumps(metadata)),
    )
    original_bytes = active_index.read_bytes()
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)
    monkeypatch.setattr(
        index_documents,
        "split_text",
        lambda text: ["First new evidence.", "Second new evidence."],
    )
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"embeddings": [[3.0, 4.0], [5.0, 6.0]]},
    )
    monkeypatch.setattr(
        index_documents.requests, "post", lambda *args, **kwargs: response
    )

    def damage_candidate(destination, *, vectors, metadata):
        if defect == "corrupt_archive":
            destination.write(b"Not an archive")
            return
        if defect == "empty_archive":
            return
        saved_metadata = json.loads(metadata.item())
        vectors = vectors.copy()
        if defect == "zero_vectors":
            vectors[0] = 0
        elif defect == "duplicate_ids":
            saved_metadata["chunks"][1]["chunk_id"] = saved_metadata["chunks"][0][
                "chunk_id"
            ]
        elif defect == "changed_content":
            saved_metadata["chunks"][0]["text"] = (
                "Document: sample\n\nUnexpected evidence."
            )
        elif defect == "changed_vectors":
            vectors = vectors[::-1]
        original_save(
            destination,
            vectors=vectors,
            metadata=np.asarray(json.dumps(saved_metadata)),
        )

    monkeypatch.setattr(index_documents.np, "savez_compressed", damage_candidate)
    stages = []
    with pytest.raises(ValueError, match="Candidate index validation failed"):
        index_documents.main(progress=stages.append)
    assert "Validating candidate index" in stages
    assert "Publishing validated index" not in stages
    assert active_index.read_bytes() == original_bytes
    assert list(index_dir.iterdir()) == [active_index]
    saved_metadata, saved_vectors, _ = load_index(active_index)
    assert saved_metadata == metadata
    np.testing.assert_array_equal(saved_vectors, [[1.0, 2.0]])


def test_valid_candidate_replaces_index_and_reports_checks(tmp_path, monkeypatch):
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "sample.txt").write_text("Synthetic evidence.", encoding="utf-8")
    index_dir = tmp_path / "index"
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)
    response = SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"embeddings": [[1.0, 2.0]]}
    )
    monkeypatch.setattr(
        index_documents.requests, "post", lambda *args, **kwargs: response
    )
    stages = []
    report = index_documents.main(progress=stages.append)
    assert stages == [
        "Processing documents",
        "Validating candidate index",
        "Publishing validated index",
    ]
    assert report["validation"]["document_count"] == 1
    assert report["validation"]["dimensions"] == 2
    assert "Every loaded document is represented" in report["validation"]["checks"]
    assert list(index_dir.iterdir()) == [index_dir / "index.npz"]
    load_index(index_dir / "index.npz")


def test_search_rejects_invalid_index_before_request(tmp_path, monkeypatch, metadata):
    np.savez_compressed(
        tmp_path / "index.npz",
        vectors=np.zeros((1, 2)),
        metadata=np.asarray(json.dumps(metadata)),
    )
    monkeypatch.setattr(search_documents, "INDEX_DIR", tmp_path)

    def fail_request(*args, **kwargs):
        pytest.fail("An invalid index should not reach Ollama")

    monkeypatch.setattr(search_documents.requests, "post", fail_request)
    with pytest.raises(ValueError, match="unusable vector norms"):
        search_documents.search("Synthetic evidence")
