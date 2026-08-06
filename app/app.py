"""Streamlit shell for the Ironhack AI Course Copilot.

F3 intentionally runs against tests/fixtures/mock_response.json.
The real Copilot agent will be connected during C7.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
MOCK_RESPONSE_PATH = ROOT_DIR / "tests" / "fixtures" / "mock_response.json"


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Ironhack AI Course Copilot",
    page_icon="🎓",
    layout="centered",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_mock_response() -> dict:
    """Load the frozen response fixture used while building the F3 UI."""
    with MOCK_RESPONSE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def render_citation(citation: dict) -> None:
    """Render one citation without making the UI calculate citation data."""
    source_type = citation.get("source_type", "")
    label = citation.get("label", "Course source")
    url = citation.get("url", "")

    if source_type == "video":
        icon = "🎥"
        source_name = "Lecture video"
    elif source_type == "notebook":
        icon = "📓"
        source_name = "Course notebook"
    else:
        icon = "🔗"
        source_name = "Course source"

    st.markdown(f"**{icon} {source_name}**")
    st.markdown(f"[{label}]({url})")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.title("🎓 Ironhack AI Course Copilot")

st.write(
    "Ask a question about the AI Engineering course and get an answer "
    "grounded in the course material."
)

question = st.text_input(
    "What would you like to know?",
    placeholder="Example: What is indexing in a RAG pipeline?",
)

ask_clicked = st.button(
    "Ask Copilot",
    type="primary",
    use_container_width=True,
)

if ask_clicked:
    if not question.strip():
        st.warning("Please enter a question first.")

    else:
        # F3 uses the frozen fixture.
        # C7 will replace this with the real Copilot().ask(question) call.
        response = load_mock_response()

        st.divider()

        st.subheader("Answer")
        st.markdown(response["answer"])

        citations = response.get("citations", [])

        if citations:
            st.subheader("Sources")

            for citation in citations:
                with st.container(border=True):
                    render_citation(citation)
