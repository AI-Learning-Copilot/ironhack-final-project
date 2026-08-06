"""Streamlit app for the Ironhack AI Course Copilot.

The UI talks directly to the real Copilot agent and keeps one Copilot
instance in Streamlit session state so conversational memory survives reruns.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

# Allow the Streamlit app to import the project modules from src/.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent import Copilot  # noqa: E402


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Ironhack AI Course Copilot",
    page_icon="🎓",
    layout="centered",
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "copilot" not in st.session_state:
    st.session_state.copilot = Copilot()

if "messages" not in st.session_state:
    st.session_state.messages = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def render_citation(citation: dict) -> None:
    """Render one citation using metadata prepared by the backend."""
    source_type = citation.get("source_type", "")
    label = citation.get("label", "Course source")
    url = citation.get("url", "")

    if source_type == "video":
        st.markdown("**🎥 Lecture video**")

        if url:
            st.markdown(f"[{label}]({url})")

            # Loom URLs produced by the backend already use /embed/ and
            # include the timestamp query parameter, so the player opens
            # directly at the cited point in the lecture.
            if "loom.com/embed/" in url:
                st.iframe(
                    url,
                    height=360,
                )
        else:
            st.write(label)

    elif source_type == "notebook":
        st.markdown("**📓 Course notebook**")

        if url:
            st.markdown(f"[{label}]({url})")
        else:
            st.write(label)

    else:
        st.markdown("**🔗 Course source**")

        if url:
            st.markdown(f"[{label}]({url})")
        else:
            st.write(label)


def render_response(response: dict) -> None:
    """Render one Copilot response and its citations."""
    st.markdown(response.get("answer", "No answer returned."))

    citations = response.get("citations", [])

    if citations:
        with st.expander(f"Sources ({len(citations)})", expanded=True):
            for citation in citations:
                with st.container(border=True):
                    render_citation(citation)


def reset_conversation() -> None:
    """Clear both the visible chat and the agent's conversation memory."""
    if "copilot" in st.session_state:
        st.session_state.copilot.reset()

    st.session_state.messages = []


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Course Copilot")

    st.write(
        "Answers are grounded in the Ironhack AI Engineering "
        "course recordings."
    )

    if st.button("New conversation", use_container_width=True):
        reset_conversation()
        st.rerun()


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.title("🎓 Ironhack AI Course Copilot")

st.write(
    "Ask a question about the AI Engineering course and get an answer "
    "grounded in the recorded lessons."
)


# Render previous conversation turns.
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_response(message["response"])
        else:
            st.markdown(message["content"])


# Chat input stays at the bottom of the conversation.
question = st.chat_input(
    "Ask something about the course..."
)


if question:
    # Save and immediately display the student's question.
    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    with st.chat_message("user"):
        st.markdown(question)

    # Ask the real RAG agent.
    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching the course material..."):
                response = st.session_state.copilot.ask(question)

            render_response(response)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "response": response,
                }
            )

        except Exception as exc:
            st.error(
                "The Course Copilot could not answer this question. "
                "Please try again."
            )

            # Useful during local MVP development without exposing the
            # traceback or secrets in the normal interface.
            with st.expander("Technical details"):
                st.code(f"{type(exc).__name__}: {exc}")
                