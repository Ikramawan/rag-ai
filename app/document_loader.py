from pathlib import Path
from zipfile import BadZipFile

from bs4 import BeautifulSoup
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx", ".html", ".htm", ".pdf"}


def load_document(path: Path) -> str:
    extension = path.suffix.lower()

    if extension in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8")

    elif extension == ".docx":
        try:
            document = Document(path)
        except (PackageNotFoundError, BadZipFile, KeyError, XMLSyntaxError) as exc:
            raise ValueError(f"Invalid DOCX file: {exc}") from exc
        blocks = []

        # Keep paragraphs and tables in their document order.
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                content = block.text.strip()
                style = block.style.name if block.style else ""

                if content and style.startswith("Heading "):
                    level = style.removeprefix("Heading ")
                    if level.isdigit():
                        content = f"{'#' * min(int(level), 6)} {content}"

                if content:
                    blocks.append(content)

            elif isinstance(block, Table):
                rows = [
                    " | ".join(
                        cell.text.strip().replace("\n", " / ") for cell in row.cells
                    )
                    for row in block.rows
                ]
                blocks.append("\n".join(rows))

        text = "\n\n".join(blocks)

    elif extension == ".pdf":
        try:
            with PdfReader(path, strict=True) as document:
                if document.is_encrypted:
                    raise ValueError("Encrypted PDFs are not supported.")
                pages = [(page.extract_text() or "").strip() for page in document.pages]
        except (PyPdfError, KeyError, TypeError) as exc:
            raise ValueError(f"Invalid PDF file: {exc}") from exc

        text = "\n\n".join(pages)
        if not text.strip():
            raise ValueError(
                "No readable text found in PDF; scanned PDFs may require OCR."
            )

    elif extension in {".html", ".htm"}:
        text = extract_html(path.read_bytes())

    else:
        raise ValueError(f"Unsupported document format: {extension}")

    if not text.strip():
        raise ValueError(f"No readable text found in {path.name}")

    return text


def extract_html(body: bytes) -> str:
    soup = BeautifulSoup(body, "html.parser")

    for element in soup(["script", "style", "nav", "footer"]):
        element.decompose()

    # Prefer the page's main content when available.
    content = soup.find("main") or soup.find("article") or soup

    # Keep table rows together so chunking can retain cell relationships.
    for row in reversed(content.find_all("tr")):
        cells = row.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        values = []
        for cell in cells:
            for line_break in cell.find_all("br"):
                line_break.replace_with(" / ")
            values.append(" ".join(cell.get_text(separator=" ", strip=True).split()))
        row.replace_with("\n" + " | ".join(values) + "\n")

    text = content.get_text(separator="\n", strip=True)
    if not text.strip():
        raise ValueError("No readable text found in HTML.")
    return text
