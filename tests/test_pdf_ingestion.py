import json
from types import SimpleNamespace

import numpy as np

from app import index_documents


def test_pdf_text_survives_indexing_with_source_metadata(
    tmp_path, monkeypatch, make_pdf
):
    documents_dir = tmp_path / "documents"
    source_dir = documents_dir / "guides"
    index_dir = tmp_path / "index"
    source_dir.mkdir(parents=True)
    pages = [
        ["Synthetic VPN guide. Prerequisite: approved account and MFA."],
        [
            f"Step {number}: collect synthetic diagnostic item {number}."
            for number in range(40)
        ],
        ["Final step: contact the synthetic network support team."],
    ]
    make_pdf(source_dir / "synthetic-vpn.pdf", pages)
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)
    embedded_inputs = []

    def fake_post(url, *, json, timeout):
        embedded_inputs.extend(json["input"])
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"embeddings": [[1.0, 2.0] for _ in json["input"]]},
        )

    monkeypatch.setattr(index_documents.requests, "post", fake_post)
    report = index_documents.main()
    assert report["loaded"] == ["guides/synthetic-vpn.pdf"]
    assert report["skipped"] == []
    assert report["chunk_count"] > 1

    with np.load(index_dir / "index.npz", allow_pickle=False) as saved:
        metadata = json.loads(saved["metadata"].item())
        chunks = metadata["chunks"]
        assert saved["vectors"].shape == (len(chunks), 2)
    assert metadata["embedding_model"] == index_documents.MODEL
    assert len(chunks) == report["chunk_count"]
    assert all(chunk["source"] == "guides/synthetic-vpn.pdf" for chunk in chunks)
    assert all(
        chunk["chunk_id"].startswith("guides/synthetic-vpn.pdf:") for chunk in chunks
    )
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
    for line in (line for page in pages for line in page):
        assert any(line in chunk["text"] for chunk in chunks)
        assert any(line in text for text in embedded_inputs)
