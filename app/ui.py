from pathlib import Path

import requests
import streamlit as st

from app.answer_question import answer
from app.document_loader import SUPPORTED_EXTENSIONS
from app.index_documents import main as rebuild_index

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"

st.set_page_config(page_title="Local RAG Assistant", page_icon="📚")
st.title("Local RAG Assistant")
st.caption("Answers from your locally indexed documents.")
st.info("Use synthetic, public or sanitised documents for this prototype.")

with st.sidebar:
    st.header("Documents")

    uploads = st.file_uploader(
        "Choose documents",
        type=sorted(extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS),
        accept_multiple_files=True,
    )

    if st.button("Save uploaded documents", disabled=not uploads):
        DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

        # Validate the whole selection before saving.
        names = [Path(upload.name).name for upload in uploads]

        if len(names) != len(set(names)):
            st.error("Duplicate filenames selected. Rename them first.")
        elif any(
            not name
            or name in {".", ".."}
            or name.startswith("~$")
            or Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS
            for name in names
        ):
            st.error("An uploaded filename is invalid or unsupported.")
        elif any((DOCUMENTS_DIR / name).exists() for name in names):
            st.error("A filename already exists. Rename the upload first.")
        else:
            try:
                for upload, name in zip(uploads, names, strict=True):
                    with (DOCUMENTS_DIR / name).open("xb") as destination:
                        destination.write(upload.getvalue())
            except OSError as exc:
                st.error(f"Saving failed; some files may have saved: {exc}")
            else:
                st.success(f"Saved {len(uploads)} documents.")
                st.warning("Rebuild the index to include these documents.")

    if st.button("Rebuild index"):
        try:
            with st.spinner("Reading documents and creating embeddings…"):
                report = rebuild_index()
        except (requests.RequestException, OSError, ValueError, KeyError) as exc:
            st.error(f"Index rebuild failed: {exc}")
        else:
            st.success(
                f"Indexed {len(report['loaded'])} documents "
                f"into {report['chunk_count']} chunks."
            )

            with st.expander("Loaded documents"):
                for source in report["loaded"]:
                    st.text(source)

            if report["skipped"]:
                st.warning(f"Skipped {len(report['skipped'])} unsupported files.")
                with st.expander("Skipped files"):
                    for source in report["skipped"]:
                        st.text(source)

    files = (
        sorted(
            path.relative_to(DOCUMENTS_DIR).as_posix()
            for path in DOCUMENTS_DIR.rglob("*")
            if path.is_file()
            and not path.name.startswith("~$")
            and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if DOCUMENTS_DIR.exists()
        else []
    )

    st.caption(f"{len(files)} supported files on disk; not necessarily indexed.")
    for filename in files:
        st.text(filename)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if question := st.chat_input("Ask about your documents"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching documents and generating an answer…"):
                result = answer(question)
        except (requests.RequestException, OSError, ValueError, KeyError) as exc:
            st.error(f"Could not answer: {exc}")
        else:
            st.markdown(result)
            st.session_state.messages.append({"role": "assistant", "content": result})
