import json
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import numpy as np
import pytest

from app import index_documents


@pytest.mark.parametrize(
    ("invalid_file", "failure_kind", "expected_reason"),
    [
        ("empty.txt", "empty", "No readable text"),
        ("invalid.docx", "non_zip", "Invalid DOCX file"),
        ("missing-part.docx", "missing_part", "Invalid DOCX file"),
        ("invalid-xml.docx", "invalid_xml", "Invalid DOCX file"),
    ],
)
def test_invalid_document_aborts_rebuild_and_preserves_index(
    tmp_path, monkeypatch, invalid_file, failure_kind, expected_reason
):
    documents_dir = tmp_path / "documents"
    index_dir = tmp_path / "index"
    documents_dir.mkdir()
    index_dir.mkdir()
    (documents_dir / "a-valid.md").write_text(
        "# Valid document\n\nSynthetic example content.", encoding="utf-8"
    )
    nested_dir = documents_dir / "nested"
    nested_dir.mkdir()
    invalid_path = nested_dir / invalid_file
    if failure_kind == "empty":
        invalid_path.write_text(" \n\t", encoding="utf-8")
    elif failure_kind == "non_zip":
        invalid_path.write_bytes(b"This is not a DOCX archive.")
    else:
        with ZipFile(invalid_path, "w") as archive:
            if failure_kind == "missing_part":
                archive.writestr("unrelated.txt", "Missing required DOCX parts.")
            else:
                archive.writestr("[Content_Types].xml", "<broken")

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
    post = Mock(side_effect=AssertionError("Embedding must not start"))
    monkeypatch.setattr(index_documents.requests, "post", post)

    with pytest.raises(ValueError) as failure:
        index_documents.main()

    message = str(failure.value)
    assert f"nested/{invalid_file}" in message
    assert expected_reason in message
    assert "No new index was published" in message
    assert "any existing index is unchanged" in message
    post.assert_not_called()
    assert active_index.read_bytes() == original_bytes
    assert list(index_dir.iterdir()) == [active_index]

    with np.load(active_index, allow_pickle=False) as saved:
        assert json.loads(saved["metadata"].item()) == previous_metadata
        np.testing.assert_array_equal(saved["vectors"], previous_vectors)


def test_html_table_evidence_survives_ingestion_and_chunking(tmp_path, monkeypatch):
    documents_dir = tmp_path / "documents"
    nested_dir = documents_dir / "support"
    index_dir = tmp_path / "index"
    nested_dir.mkdir(parents=True)
    trailing_procedure = "".join(
        f"<p>Step {number}: record the synthetic diagnostic observation.</p>"
        for number in range(100)
    )
    (nested_dir / "synthetic-targets.html").write_text(
        """<html><body><main>
<h1>Synthetic response targets</h1>
<p>Synthetic policy for ingestion tests only.</p>
<table>
<tr><th>Priority</th><th>Initial response target</th></tr>
<tr><td>P1</td><td>15 minutes</td></tr>
<tr><td>P2</td><td>1 business hour</td></tr>
</table>
<p>Diagnostic procedure follows.</p>
"""
        + trailing_procedure
        + "</main></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)

    def fake_post(url, *, json, timeout):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"embeddings": [[1.0, 2.0] for _ in json["input"]]},
        )

    monkeypatch.setattr(index_documents.requests, "post", fake_post)

    report = index_documents.main()
    assert report["loaded"] == ["support/synthetic-targets.html"]
    assert report["chunk_count"] > 1

    with np.load(index_dir / "index.npz", allow_pickle=False) as saved:
        chunks = json.loads(saved["metadata"].item())["chunks"]

    table_evidence = (
        "Priority | Initial response target\nP1 | 15 minutes\nP2 | 1 business hour"
    )
    evidence_chunks = [chunk for chunk in chunks if table_evidence in chunk["text"]]
    assert evidence_chunks, "No saved chunk contains the table header and both rows"
    for chunk in evidence_chunks:
        assert chunk["source"] == "support/synthetic-targets.html"
        assert chunk["chunk_id"].startswith("support/synthetic-targets.html:")


def test_html_table_answer_retains_header_across_chunk_boundary(tmp_path, monkeypatch):
    documents_dir = tmp_path / "documents"
    index_dir = tmp_path / "index"
    documents_dir.mkdir()
    preamble = "Synthetic diagnostic context. " * 48
    intervening_rows = "".join(
        f"<tr><td>Example {number}</td><td>"
        "Synthetic response target pending review by the example support team."
        "</td></tr>"
        for number in range(8)
    )
    (documents_dir / "boundary-table.html").write_text(
        f"<main><p>{preamble}</p><table>"
        "<tr><th>Priority</th><th>Initial response target</th></tr>"
        + intervening_rows
        + "<tr><td>P2</td><td>1 business hour</td></tr>"
        "</table><p>End of synthetic policy.</p></main>",
        encoding="utf-8",
    )
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)

    def fake_post(url, *, json, timeout):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"embeddings": [[1.0, 2.0] for _ in json["input"]]},
        )

    monkeypatch.setattr(index_documents.requests, "post", fake_post)
    index_documents.main()

    with np.load(index_dir / "index.npz", allow_pickle=False) as saved:
        chunks = json.loads(saved["metadata"].item())["chunks"]

    answer_chunks = [
        chunk for chunk in chunks if "P2 | 1 business hour" in chunk["text"]
    ]
    assert answer_chunks, "The answer row was lost during ingestion"
    assert any(
        "Priority | Initial response target" in chunk["text"] for chunk in chunks
    )
    assert any(
        "Priority | Initial response target" in chunk["text"] for chunk in answer_chunks
    ), "The answer row survives, but no answer chunk retains its table header"
