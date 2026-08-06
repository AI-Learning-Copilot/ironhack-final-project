"""Streamlit app for the Ironhack AI Course Copilot.

The UI talks directly to the real Copilot agent and keeps one Copilot
instance in Streamlit session state so conversational memory survives reruns.
"""

from __future__ import annotations

import re
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
# Citation helpers
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


# ---------------------------------------------------------------------------
# Quiz parsing helpers
# ---------------------------------------------------------------------------

def _strip_markdown(text: str) -> str:
    """Remove simple Markdown wrappers used by the quiz generator."""
    cleaned = text.strip()
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    return cleaned.strip()


def _is_answer_line(line: str) -> bool:
    """Detect quiz answer lines, including Markdown-formatted answers."""
    cleaned = _strip_markdown(line)
    return cleaned.lower().startswith("answer:")


def _extract_answer_letter(line: str) -> str | None:
    """Extract A, B, C, or D from an Answer: line."""
    cleaned = _strip_markdown(line)

    match = re.search(
        r"answer\s*:\s*([A-D])",
        cleaned,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).upper()

    return None


def _is_option_line(line: str) -> bool:
    """Return True when a line looks like A) ..., B) ..., etc."""
    cleaned = _strip_markdown(line)

    return bool(
        re.match(
            r"^[A-D][\)\.\:]\s*.+",
            cleaned,
            flags=re.IGNORECASE,
        )
    )


def _extract_option(line: str) -> tuple[str, str] | None:
    """Turn 'A) Vector database' into ('A', 'Vector database')."""
    cleaned = _strip_markdown(line)

    match = re.match(
        r"^([A-D])[\)\.\:]\s*(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    letter = match.group(1).upper()
    text = match.group(2).strip()

    return letter, text


def parse_quiz(answer: str) -> tuple[str, list[dict]]:
    """Parse the backend quiz text into structured quiz questions.

    The backend currently returns quizzes in this form:

        Question text
        A) ...
        B) ...
        C) ...
        D) ...
        Answer: B

    This parser keeps that backend contract untouched and converts the
    response into data that Streamlit can render interactively.
    """
    lines = answer.splitlines()

    intro_lines: list[str] = []
    questions: list[dict] = []

    current_question_lines: list[str] = []
    current_options: dict[str, str] = {}
    current_answer: str | None = None

    def save_current_question() -> None:
        nonlocal current_question_lines
        nonlocal current_options
        nonlocal current_answer

        if (
            current_question_lines
            and len(current_options) >= 2
            and current_answer
        ):
            question_text = " ".join(
                line.strip()
                for line in current_question_lines
                if line.strip()
            )

            questions.append(
                {
                    "question": question_text,
                    "options": current_options.copy(),
                    "answer": current_answer,
                }
            )

        current_question_lines = []
        current_options = {}
        current_answer = None

    quiz_started = False

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            continue

        if _is_option_line(line):
            quiz_started = True

            option = _extract_option(line)

            if option:
                letter, option_text = option
                current_options[letter] = option_text

            continue

        if _is_answer_line(line):
            quiz_started = True
            current_answer = _extract_answer_letter(line)

            # The Answer line marks the end of one question.
            save_current_question()
            continue

        # A new numbered question can start after a previous question.
        # Examples:
        # 1. What is RAG?
        # 2) What is an embedding?
        question_match = re.match(
            r"^\s*\d+[\.\)]\s*(.+)",
            _strip_markdown(line),
        )

        if question_match:
            # If for any reason a previous question is still open,
            # preserve it before starting the next one.
            if current_options and current_answer:
                save_current_question()

            quiz_started = True
            current_question_lines = [
                question_match.group(1).strip()
            ]
            continue

        if quiz_started:
            # If we have not reached the options yet, this belongs to the
            # current question text.
            if not current_options:
                current_question_lines.append(
                    _strip_markdown(line)
                )
        else:
            # Text such as "Here are your quiz questions..."
            intro_lines.append(line)

    # Defensive final save in case the model omitted a trailing blank line.
    if current_question_lines and current_options and current_answer:
        save_current_question()

    intro = "\n".join(intro_lines).strip()

    return intro, questions


# ---------------------------------------------------------------------------
# Interactive quiz UI
# ---------------------------------------------------------------------------

def render_quiz(answer: str, quiz_id: str) -> None:
    """Render a real multiple-choice test with scoring."""
    intro, questions = parse_quiz(answer)

    # Fallback:
    # If the LLM ever returns an unexpected quiz format, do not break the
    # entire chat UI. Hide answer lines using the old reveal behaviour.
    if not questions:
        blocks = answer.split("\n\n")

        for block_index, block in enumerate(blocks):
            lines = block.strip().splitlines()

            if not lines:
                continue

            answer_lines = [
                line
                for line in lines
                if _is_answer_line(line)
            ]

            visible_lines = [
                line
                for line in lines
                if not _is_answer_line(line)
            ]

            if visible_lines:
                st.markdown("\n".join(visible_lines))

            for answer_index, answer_line in enumerate(answer_lines):
                with st.expander(
                    "👁️ Show answer",
                    expanded=False,
                ):
                    st.markdown(
                        f"**{_strip_markdown(answer_line)}**"
                    )

        return

    if intro:
        st.markdown(intro)

    st.markdown("### 📝 Quiz")

    st.caption(
        "Choose one answer for each question, then submit your quiz "
        "to see your score."
    )

    submitted_key = f"{quiz_id}_submitted"

    if submitted_key not in st.session_state:
        st.session_state[submitted_key] = False

    # -----------------------------------------------------------------------
    # Questions
    # -----------------------------------------------------------------------

    for index, question in enumerate(questions):
        question_number = index + 1

        st.markdown(
            f"#### Question {question_number}"
        )

        st.markdown(question["question"])

        option_letters = list(question["options"].keys())

        option_labels = [
            f"{letter}) {question['options'][letter]}"
            for letter in option_letters
        ]

        selection_key = (
            f"{quiz_id}_question_{question_number}"
        )

        selected_label = st.radio(
            "Choose your answer:",
            options=option_labels,
            index=None,
            key=selection_key,
            disabled=st.session_state[submitted_key],
            label_visibility="collapsed",
        )

        # -------------------------------------------------------------------
        # Feedback after submission
        # -------------------------------------------------------------------

        if st.session_state[submitted_key]:
            selected_letter = None

            if selected_label:
                selected_letter = selected_label[0].upper()

            correct_letter = question["answer"]

            if selected_letter == correct_letter:
                st.success("✅ Correct!")

            else:
                st.error("❌ Incorrect")

                if selected_letter:
                    selected_text = question["options"].get(
                        selected_letter,
                        "",
                    )

                    st.write(
                        f"Your answer: **{selected_letter}) "
                        f"{selected_text}**"
                    )
                else:
                    st.write("Your answer: **No answer selected**")

                correct_text = question["options"].get(
                    correct_letter,
                    "",
                )

                st.write(
                    f"Correct answer: **{correct_letter}) "
                    f"{correct_text}**"
                )

        st.divider()

    # -----------------------------------------------------------------------
    # Submit + score
    # -----------------------------------------------------------------------

    if not st.session_state[submitted_key]:
        selected_answers = []

        for index in range(len(questions)):
            question_number = index + 1
            selection_key = (
                f"{quiz_id}_question_{question_number}"
            )

            selected_answers.append(
                st.session_state.get(selection_key)
            )

        answered_count = sum(
            answer is not None
            for answer in selected_answers
        )

        st.caption(
            f"Answered: {answered_count}/{len(questions)}"
        )

        if st.button(
            "✅ Submit Quiz",
            key=f"{quiz_id}_submit",
            type="primary",
            use_container_width=True,
        ):
            if answered_count < len(questions):
                st.warning(
                    "Please answer every question before submitting."
                )
            else:
                st.session_state[submitted_key] = True
                st.rerun()

    else:
        score = 0

        for index, question in enumerate(questions):
            question_number = index + 1

            selection_key = (
                f"{quiz_id}_question_{question_number}"
            )

            selected_label = st.session_state.get(
                selection_key
            )

            if selected_label:
                selected_letter = selected_label[0].upper()

                if selected_letter == question["answer"]:
                    score += 1

        total = len(questions)
        percentage = round((score / total) * 100)

        st.markdown("### 🎯 Your score")

        st.metric(
            label="Result",
            value=f"{score} / {total}",
            delta=f"{percentage}%",
        )

        if percentage == 100:
            st.success(
                "🏆 Perfect score!"
            )
        elif percentage >= 70:
            st.success(
                "👏 Great job!"
            )
        elif percentage >= 50:
            st.info(
                "👍 Good attempt. Review the questions you missed."
            )
        else:
            st.info(
                "📚 Keep practicing. Review the course sources below "
                "and try again."
            )

        if st.button(
            "🔄 Try Again",
            key=f"{quiz_id}_retry",
            use_container_width=True,
        ):
            # Remove only this quiz's Streamlit state.
            keys_to_delete = [
                key
                for key in list(st.session_state.keys())
                if key.startswith(f"{quiz_id}_")
            ]

            for key in keys_to_delete:
                del st.session_state[key]

            st.rerun()


# ---------------------------------------------------------------------------
# Response rendering
# ---------------------------------------------------------------------------

def render_response(
    response: dict,
    message_id: str,
) -> None:
    """Render one Copilot response and its citations."""
    answer = response.get(
        "answer",
        "No answer returned.",
    )

    # Quiz responses contain explicit Answer: lines.
    is_quiz = any(
        _is_answer_line(line)
        for line in answer.splitlines()
    )

    if is_quiz:
        render_quiz(
            answer,
            quiz_id=f"quiz_{message_id}",
        )
    else:
        st.markdown(answer)

    citations = response.get("citations", [])

    if citations:
        with st.expander(
            f"Sources ({len(citations)})",
            expanded=True,
        ):
            for citation in citations:
                with st.container(border=True):
                    render_citation(citation)


# ---------------------------------------------------------------------------
# Conversation reset
# ---------------------------------------------------------------------------

def reset_conversation() -> None:
    """Clear both the visible chat and the agent's conversation memory."""
    if "copilot" in st.session_state:
        st.session_state.copilot.reset()

    st.session_state.messages = []

    # Clear interactive quiz state as well.
    quiz_keys = [
        key
        for key in list(st.session_state.keys())
        if key.startswith("quiz_")
    ]

    for key in quiz_keys:
        del st.session_state[key]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Course Copilot")

    st.write(
        "Answers are grounded in the Ironhack AI Engineering "
        "course recordings."
    )

    if st.button(
        "New conversation",
        use_container_width=True,
    ):
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


# ---------------------------------------------------------------------------
# Render previous conversation turns
# ---------------------------------------------------------------------------

for message_index, message in enumerate(
    st.session_state.messages
):
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_response(
                message["response"],
                message_id=str(message_index),
            )
        else:
            st.markdown(message["content"])


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

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
            with st.spinner(
                "Searching the course material..."
            ):
                response = (
                    st.session_state.copilot.ask(question)
                )

            # The assistant message will become the next message
            # in the conversation history.
            message_id = str(
                len(st.session_state.messages)
            )

            render_response(
                response,
                message_id=message_id,
            )

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
                st.code(
                    f"{type(exc).__name__}: {exc}"
                )