from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

SUPPORTED_EXTENSIONS = {".md", ".txt", ".docx", ".html", ".htm"}


def load_document(path: Path) -> str:
    extension = path.suffix.lower()

    if extension in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8")

    elif extension == ".docx":
        document = Document(path)
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

    elif extension in {".html", ".htm"}:
        soup = BeautifulSoup(path.read_bytes(), "html.parser")

        for element in soup(["script", "style", "nav", "footer"]):
            element.decompose()

        # Prefer the page's main content when available.
        content = soup.find("main") or soup.find("article") or soup
        text = content.get_text(separator="\n", strip=True)

    else:
        raise ValueError(f"Unsupported document format: {extension}")

    if not text.strip():
        raise ValueError(f"No readable text found in {path.name}")

    return text
