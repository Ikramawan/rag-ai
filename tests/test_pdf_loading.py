import pytest

from app.document_loader import load_document


def test_pdf_preserves_text_and_page_order(tmp_path, make_pdf):
    path = make_pdf(
        tmp_path / "synthetic.pdf",
        [
            ["Synthetic guide. Prerequisite: approved account."],
            [],
            ["Step 1: enable MFA.", "Step 2: connect to the VPN."],
        ],
    )
    text = load_document(path)
    expected = ["approved account", "Step 1: enable MFA", "Step 2: connect"]
    positions = [text.index(phrase) for phrase in expected]
    assert positions == sorted(positions)


@pytest.mark.parametrize("kind", ["malformed", "encrypted", "textless"])
def test_unsupported_pdf_reports_clear_error(tmp_path, make_pdf, kind):
    path = tmp_path / "unsupported.pdf"
    if kind == "malformed":
        path.write_bytes(b"Not a PDF")
        reason = "Invalid PDF file"
    elif kind == "encrypted":
        make_pdf(path, [["Synthetic protected content."]], password="test-password")
        reason = "Encrypted PDFs are not supported"
    else:
        make_pdf(path, [[]])
        reason = "No readable text found in PDF; scanned PDFs may require OCR"
    with pytest.raises(ValueError, match=reason):
        load_document(path)
