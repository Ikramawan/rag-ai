from pathlib import Path

import requests
import streamlit as st

from app.answer_question import answer
from app.document_loader import SUPPORTED_EXTENSIONS
from app.index_documents import main as rebuild_index
from app.url_documents import SNAPSHOT_SUFFIX, fetch_page, save_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"

st.set_page_config(page_title="Local RAG Assistant", page_icon="📚")
st.title("Local RAG Assistant")
st.caption("Answers from your locally indexed documents.")
st.info("Use synthetic, public or sanitised documents for this prototype.")

with st.sidebar:
    st.header("Documents")
    st.caption(
        "PDF uploads support text-based documents. Scanned PDFs require OCR; "
        "image-only content is not extracted. Encrypted PDFs are unsupported. "
        "Complex layouts and tables may extract imperfectly."
    )

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

    st.subheader("Documentation URL")
    st.caption(
        "Import one public HTML documentation page. Review the extracted text "
        "before saving. Linked pages, attachments and sign-in pages are not supported."
    )
    documentation_url = st.text_input("Public documentation URL")
    if st.button("Fetch preview", disabled=not documentation_url.strip()):
        st.session_state.pop("url_preview", None)
        try:
            with st.spinner("Fetching documentation…"):
                snapshot = fetch_page(documentation_url)
        except (requests.RequestException, OSError, ValueError) as exc:
            st.error(f"URL import failed: {exc}")
        else:
            st.session_state.url_preview = (documentation_url, snapshot)

    preview = st.session_state.get("url_preview")
    if preview and preview[0] == documentation_url:
        snapshot = preview[1]
        st.text(f"Fetched: {snapshot['fetched_at']}")
        st.text(f"Page: {snapshot['resolved_url']}")
        with st.expander("Extracted documentation", expanded=True):
            st.text(snapshot["text"])
        if st.button("Save URL snapshot"):
            try:
                save_snapshot(snapshot, DOCUMENTS_DIR)
            except FileExistsError:
                st.error(
                    "This URL is already saved. Existing content was not overwritten."
                )
            except (OSError, ValueError) as exc:
                st.error(f"Saving URL snapshot failed: {exc}")
            else:
                st.success("Saved documentation snapshot.")
                st.warning("Rebuild the index to include this page.")
                st.session_state.pop("url_preview", None)

    if st.button("Rebuild index"):
        with st.status("Processing documents", expanded=True) as rebuild_status:
            try:
                report = rebuild_index(
                    progress=lambda message: rebuild_status.update(label=message)
                )
            except (requests.RequestException, OSError, ValueError, KeyError) as exc:
                rebuild_status.update(label="Index rebuild failed", state="error")
                st.error(f"Index rebuild failed: {exc}")
                report = None
            else:
                rebuild_status.update(
                    label="Index ready", state="complete", expanded=False
                )
        if report is not None:
            st.success(
                f"Indexed {len(report['loaded'])} documents "
                f"into {report['chunk_count']} chunks."
            )
            with st.expander("Passed index checks"):
                for check in report["validation"]["checks"]:
                    st.text(check)
                st.caption(
                    "These checks validate index integrity, not answer accuracy."
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
            and (
                path.suffix.lower() in SUPPORTED_EXTENSIONS
                or path.name.endswith(SNAPSHOT_SUFFIX)
            )
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
