from types import SimpleNamespace

import numpy as np
import pytest

from app import index_documents


def test_failed_save_preserves_previous_index(tmp_path, monkeypatch) -> None:
    documents = tmp_path / "documents"
    index_dir = tmp_path / "index"
    documents.mkdir()
    index_dir.mkdir()

    (documents / "sample.md").write_text(
        "# Sample\n\nNew document content.",
        encoding="utf-8",
    )

    active_index = index_dir / "index.npz"
    np.savez_compressed(
        active_index,
        vectors=np.array([[1.0, 2.0]], dtype=np.float32),
        metadata=np.asarray('{"version": "old"}'),
    )
    original_bytes = active_index.read_bytes()

    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)

    fake_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"embeddings": [[3.0, 4.0]]},
    )
    monkeypatch.setattr(
        index_documents.requests,
        "post",
        lambda *args, **kwargs: fake_response,
    )

    def fail_during_save(destination, **kwargs) -> None:
        destination.write(b"incomplete index")
        raise OSError("Simulated disk write failure")

    monkeypatch.setattr(
        index_documents.np,
        "savez_compressed",
        fail_during_save,
    )

    with pytest.raises(OSError, match="Simulated disk write failure"):
        index_documents.main()

    assert active_index.read_bytes() == original_bytes
    assert list(index_dir.iterdir()) == [active_index]

    with np.load(active_index, allow_pickle=False) as saved:
        assert saved["metadata"].item() == '{"version": "old"}'
        np.testing.assert_array_equal(saved["vectors"], [[1.0, 2.0]])
