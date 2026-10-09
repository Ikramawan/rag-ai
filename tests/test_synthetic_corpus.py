from types import SimpleNamespace

import pytest
from pypdf import PdfReader

from app import index_documents
from app.document_loader import load_document
from app.index_validation import load_index
from scripts import generate_synthetic_corpus as corpus


def test_generated_corpus_has_extractable_notice_and_representative_evidence(tmp_path):
    paths = corpus.generate(tmp_path / "documents")
    assert len(paths) == 22
    assert {path.suffix for path in paths} == {".md", ".txt", ".html", ".docx", ".pdf"}
    for path in paths:
        assert corpus.NOTICE in load_document(path)
    expected = {
        "incident-handoff.docx": "Impact | Affected service and user group",
        "storage-access.docx": "Report reader | Read approved reports | 30 days",
        "harbor-roles.html": "Viewer | Read release records | Application owner",
        "backup-retention.html": "Daily snapshot | 14 days | Data platform team",
        "deployment-prerequisites.pdf": "reviewed rollback criteria",
        "diagnostic-redaction.pdf": "MFA recovery codes",
        "release-evidence.md": "16. Wait for explicit approval",
    }
    for filename, evidence in expected.items():
        assert evidence in " ".join(
            load_document(tmp_path / "documents" / filename).split()
        )
    assert len(load_document(tmp_path / "documents" / "release-evidence.md")) > 3600
    with PdfReader(tmp_path / "documents" / "diagnostic-redaction.pdf") as pdf:
        assert len(pdf.pages) == 2
        assert "MFA recovery codes" in " ".join(pdf.pages[0].extract_text().split())
        assert "confirm receipt" in " ".join(pdf.pages[1].extract_text().split())


def test_collision_aborts_without_creating_or_overwriting_documents(tmp_path):
    original = tmp_path / "gcp-labels.md"
    original.write_bytes(b"User-owned document")
    unrelated = tmp_path / "user-notes.txt"
    unrelated.write_bytes(b"User notes")
    with pytest.raises(FileExistsError):
        corpus.generate(tmp_path)
    assert original.read_bytes() == b"User-owned document"
    assert unrelated.read_bytes() == b"User notes"
    assert set(tmp_path.iterdir()) == {original, unrelated}


def test_failed_publication_rolls_back_only_new_files(tmp_path, monkeypatch):
    output = tmp_path / "documents"
    output.mkdir()
    existing = output / "user-notes.txt"
    existing.write_bytes(b"Keep me")
    original_link = corpus.os.link
    calls = 0

    def fail_later(source, target):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("Simulated publication failure")
        original_link(source, target)

    monkeypatch.setattr(corpus.os, "link", fail_later)
    with pytest.raises(OSError, match="Simulated publication failure"):
        corpus.generate(output)
    assert list(output.iterdir()) == [existing]
    assert existing.read_bytes() == b"Keep me"


def test_entire_generated_corpus_indexes_with_complete_source_coverage(
    tmp_path, monkeypatch
):
    documents = tmp_path / "documents"
    index_dir = tmp_path / "index"
    paths = corpus.generate(documents)
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", documents)
    monkeypatch.setattr(index_documents, "INDEX_DIR", index_dir)

    def fake_post(url, *, json, timeout):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"embeddings": [[1.0, 2.0] for _ in json["input"]]},
        )

    monkeypatch.setattr(index_documents.requests, "post", fake_post)
    report = index_documents.main()
    metadata, vectors, _ = load_index(
        index_dir / "index.npz", expected_sources=[path.name for path in paths]
    )
    assert report["validation"]["document_count"] == 22
    assert vectors.shape == (report["chunk_count"], 2)
    assert (
        sum(chunk["source"] == "release-evidence.md" for chunk in metadata["chunks"])
        > 2
    )
    assert any(
        "Report reader | Read approved reports | 30 days" in chunk["text"]
        for chunk in metadata["chunks"]
    )
