import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from app import index_documents


@pytest.mark.parametrize("valid_vectors", [True, False])
def test_rebuild_ui_reports_validation_success_or_failure(
    tmp_path, monkeypatch, valid_vectors
):
    documents = tmp_path / "documents"
    index_dir = tmp_path / "index"
    documents.mkdir()
    index_dir.mkdir()
    (documents / "sample.txt").write_text("Synthetic evidence.", encoding="utf-8")
    active_index = index_dir / "index.npz"
    previous_metadata = {
        "embedding_model": "nomic-embed-text",
        "chunks": [
            {"source": "old.txt", "chunk_id": "old.txt:0:0", "text": "Old evidence"}
        ],
    }
    np.savez_compressed(
        active_index,
        vectors=np.array([[1.0, 2.0]]),
        metadata=np.asarray(json.dumps(previous_metadata)),
    )
    previous_bytes = active_index.read_bytes()
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"embeddings": [[1.0, 2.0] if valid_vectors else [0.0, 0.0]]},
    )
    monkeypatch.setattr(
        index_documents.requests, "post", lambda *args, **kwargs: response
    )

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app/ui.py").run()
    next(
        button for button in app.button if button.label == "Rebuild index"
    ).click().run()
    assert not app.exception
    if valid_vectors:
        assert any(
            "Indexed 1 documents into 1 chunks" in item.value for item in app.success
        )
        assert any(
            "Every loaded document is represented" == item.value for item in app.text
        )
        assert any("not answer accuracy" in item.value for item in app.caption)
        assert active_index.read_bytes() != previous_bytes
        assert not app.error
    else:
        assert any(
            "Candidate index validation failed" in item.value for item in app.error
        )
        assert not app.success
        assert active_index.read_bytes() == previous_bytes
    assert list(index_dir.iterdir()) == [active_index]
