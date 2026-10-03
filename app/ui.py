import requests
import streamlit as st

from app.answer_question import answer

st.set_page_config(page_title="Local RAG Assistant", page_icon="📚")
st.title("Local RAG Assistant")
st.caption("Answers from your locally indexed documents.")
st.info("Current documents contain fictional training procedures.")

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
