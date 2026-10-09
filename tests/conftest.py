import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)


@pytest.fixture
def make_pdf():
    """Write small, genuine PDFs with synthetic ASCII text, without a renderer dependency."""

    def write_pdf(path, pages, *, password=None):
        writer = PdfWriter()
        for lines in pages:
            page = writer.add_blank_page(width=612, height=792)
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
            )
            commands = ["BT /F1 12 Tf 50 740 Td 16 TL"]
            for line in lines:
                escaped = (
                    line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                )
                commands.append(f"({escaped}) Tj T*")
            commands.append("ET")
            stream = DecodedStreamObject()
            stream.set_data("\n".join(commands).encode("ascii"))
            page[NameObject("/Contents")] = stream
        if password is not None:
            writer.encrypt(password)
        writer.write(path)
        writer.close()
        return path

    return write_pdf
