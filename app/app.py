"""Streamlit app for the Ironhack AI Course Copilot.

The UI talks directly to the real Copilot agent and keeps one Copilot
instance in Streamlit session state so conversational memory survives reruns.
"""

from __future__ import annotations

import json
import random
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
# Theme — "Vapor Chrome"
# ---------------------------------------------------------------------------
#
# Colours live in .streamlit/config.toml (Streamlit reads those itself).
# Everything below is what config.toml cannot express: web fonts, the header
# gradient, and the citation card styling.
#
# Palette: #c4b5fd violet · #818cf8 indigo · #67e8f9 cyan · #a5f3fc ice

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@600;700&family=Manrope:wght@400;500;600&display=swap');

    html, body, [class*="st-"], .stMarkdown, .stChatInput textarea {
        font-family: 'Manrope', system-ui, sans-serif;
    }
    h1, h2, h3, h4 {
        font-family: 'Sora', system-ui, sans-serif;
        letter-spacing: -0.02em;
    }

    /* Streamlit draws its icons as ligatures in a Material icon font. The rule above
       matches those spans too and renders them as literal words such as
       "keyboard_double_arrow_left". Hand the icon font back. */
    [class*="material-icons"], [data-testid="stIconMaterial"], .material-icons,
    span[data-testid^="stIcon"], .material-symbols-rounded {
        font-family: 'Material Symbols Rounded', 'Material Icons' !important;
    }

    /* Hero — the iridescent band the whole palette exists for. */
    .vc-hero {
        background: linear-gradient(115deg, #c4b5fd 0%, #818cf8 38%, #67e8f9 78%, #a5f3fc 100%);
        border-radius: 16px;
        padding: 0.95rem 1.3rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 22px -12px rgba(129, 140, 248, 0.55);
    }
    .vc-hero h1 {
        margin: 0;
        font-size: 1.45rem;
        color: #10102E;
    }
    .vc-hero p {
        margin: 0.2rem 0 0;
        font-size: 0.87rem;
        color: #241F5A;
    }
    .vc-stats {
        margin-top: 0.6rem;
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
    }
    .vc-stats span {
        background: rgba(255, 255, 255, 0.72);
        border-radius: 999px;
        padding: 0.2rem 0.7rem;
        font-size: 0.78rem;
        font-weight: 600;
        color: #241F5A;
        white-space: nowrap;
    }

    /* Citations sit in a tinted card so sources read as one group, not loose text. */
    .stChatMessage [data-testid="stExpander"] details {
        border: 1px solid #DCDDFB;
        border-radius: 12px;
        background: #F7F6FF;
    }

    /* ---------------------------------------------------------------- sidebar */

    /* The same iridescent wash as the hero, dialled right down so it reads as a
       tinted panel rather than a second hero competing with the first. */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #EDE9FE 0%, #E7ECFE 45%, #E0F5FC 100%);
        border-right: 1px solid #D7D9FA;
    }

    /* Section titles: Sora, indigo, with a gradient rule underneath so
       "Browse the course" and "Answer language" read as real section headers. */
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        font-family: 'Sora', system-ui, sans-serif !important;
        color: #1E1B4B;
        font-size: 1.02rem;
        letter-spacing: -0.01em;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid;
        border-image: linear-gradient(90deg, #818cf8, #67e8f9) 1;
    }

    /* Field labels — smaller, uppercase, so they stop competing with the titles. */
    section[data-testid="stSidebar"] label p {
        font-size: 0.74rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #4C43A8 !important;
    }

    /* Dropdowns: white on the tinted panel so they read as controls, not text. */
    section[data-testid="stSidebar"] [data-baseweb="select"] > div {
        background: #FFFFFF;
        border: 1px solid #C9CDF7;
        border-radius: 10px;
    }

    /* The helper captions under each control. */
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
    section[data-testid="stSidebar"] small {
        color: #5B54A6 !important;
    }

    /* Streamlit's default divider is a hard grey line; soften it into the palette. */
    section[data-testid="stSidebar"] hr {
        border-color: #CFD3F7;
        opacity: 0.8;
    }

    /* ------------------------------------------------------------- chat + misc */

    /* Assistant and user bubbles, tinted rather than Streamlit grey. */
    .stChatMessage {
        background: #E8EAFE;
        border: 1px solid #C9CDF7;
        border-radius: 14px;
    }

    /* The student's own turn gets the cyan end of the palette, so the two
       speakers are told apart by colour and not only by avatar. */
    .stChatMessage:has([data-testid="stChatMessageAvatarUser"]) {
        background: #DDF3FB;
        border-color: #A9DFF0;
    }

    /* Starter question buttons — white cards on the tinted page, indigo on hover. */
    .stButton > button {
        background: #FFFFFF;
        border: 1px solid #C9CDF7;
        border-radius: 12px;
        color: #2A2470;
        font-weight: 600;
        text-align: left;
        padding: 0.55rem 0.85rem;
    }
    .stButton > button:hover {
        border-color: #818cf8;
        background: #F3F2FF;
        color: #1E1B4B;
    }

    /* Chat input picks up the palette instead of the default red focus ring. */
    .stChatInput textarea:focus {
        border-color: #818cf8 !important;
        box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.28) !important;
    }

    /* Links across the app in the palette indigo, not Streamlit red. */
    a, a:visited {
        color: #4F46E5 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

# Custom avatars. Streamlit's defaults are red/orange icons, the only colours on
# screen that sit outside the palette.
AVATARS = {"user": "🧑‍🎓", "assistant": "🎓"}

LESSONS_PATH = ROOT_DIR / "data" / "lessons.json"

# Loom's public watch URL. The agent emits /embed/ links for the inline players;
# the syllabus links out instead, so it wants the share form.
LOOM_SHARE = "https://www.loom.com/share"


@st.cache_data
def load_lessons() -> dict:
    """The course calendar, generated from the recording metadata."""
    with LESSONS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


SYLLABUS_LESSONS = load_lessons()

# Streamlit keeps session state across reruns, including a Copilot built by an older
# version of the module. Bump this whenever Copilot gains state the app relies on, so a
# live session rebuilds instead of failing on a missing attribute.
COPILOT_VERSION = 2

if (
    "copilot" not in st.session_state
    or st.session_state.get("copilot_version") != COPILOT_VERSION
):
    st.session_state.copilot = Copilot()
    st.session_state.copilot_version = COPILOT_VERSION

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
                    height=190,
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

    IMPORTANT: This format is a frozen cross-file contract documented in
    para-leer/SCHEMA.md. If the quiz generator format changes in src/tools.py,
    this parser must be reviewed at the same time.

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
            if current_options and current_answer:
                save_current_question()

            quiz_started = True
            current_question_lines = [
                question_match.group(1).strip()
            ]
            continue

        if quiz_started:
            if not current_options:
                current_question_lines.append(
                    _strip_markdown(line)
                )
        else:
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
        # Keep retrieval untouched, but avoid overwhelming the UI with
        # five large source players after every answer.
        #
        # citations arrive most-relevant-first: retrieval returns nearest-first by
        # embedding distance and build_response() preserves that order while
        # deduplicating. So the first three are the closest matches, and everything
        # after them is still relevant, just further away.
        visible_citations = citations[:3]
        extra_citations = citations[3:]

        source_label = f"Sources ({len(visible_citations)} shown)"

        if extra_citations:
            source_label = (
                f"Sources ({len(visible_citations)} shown, "
                f"{len(extra_citations)} more below)"
            )

        with st.expander(
            source_label,
            expanded=True,
        ):
            columns = st.columns(len(visible_citations))

            for column, citation in zip(
                columns,
                visible_citations,
            ):
                with column:
                    with st.container(border=True):
                        render_citation(citation)

            # Everything past the top three is listed as a plain link rather than a
            # player. A student who wants the other passages can still reach them,
            # and the answer does not turn into a wall of embedded videos.
            if extra_citations:
                st.markdown("")
                st.caption("Other relevant sources")

                for citation in extra_citations:
                    icon = "🎥" if citation.get("source_type") == "video" else "📓"
                    label = citation.get("label", "Course source")
                    url = citation.get("url", "")

                    if url:
                        st.markdown(f"{icon} [{label}]({url})")
                    else:
                        st.markdown(f"{icon} {label}")


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
    # No title or strapline here on purpose. The hero at the top of the main
    # column already carries the product name and what it does; repeating it in
    # the sidebar said the same thing twice in two different styles. The sidebar
    # is controls only.

    # -----------------------------------------------------------------------
    # Course browser
    # -----------------------------------------------------------------------

    st.subheader("🎯 Scope")

    lessons_path = ROOT_DIR / "data" / "lessons.json"

    with lessons_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        lessons = json.load(file)

    # Build available week numbers from IDs such as w7d2.
    weeks = sorted(
        {
            int(lesson_id.split("d")[0][1:])
            for lesson_id in lessons
        }
    )

    selected_week = st.selectbox(
        "Week",
        weeks,
        format_func=lambda week: f"Week {week}",
    )

    # Only show lesson days belonging to the selected week.
    week_lessons = {
        lesson_id: lesson
        for lesson_id, lesson in lessons.items()
        if lesson_id.startswith(f"w{selected_week}d")
    }

    lesson_ids = sorted(
        week_lessons,
        key=lambda lesson_id: int(
            lesson_id.split("d")[1]
        ),
    )

    def lesson_label(lesson_id: str) -> str:
        """Create a compact label for the lesson selectbox."""
        day = lesson_id.split("d")[1]
        title = week_lessons[lesson_id]["title"]

        # Use the first topic so long lesson titles do not overwhelm
        # the sidebar selectbox.
        first_topic = title.split(" · ")[0]

        if len(first_topic) > 45:
            first_topic = first_topic[:42] + "..."

        return f"Day {day} — {first_topic}"

    selected_lesson_id = st.selectbox(
        "Lesson",
        lesson_ids,
        format_func=lesson_label,
    )

    selected_lesson = week_lessons[
        selected_lesson_id
    ]

    # Show the complete contents of the selected lesson underneath.
    st.caption(
        selected_lesson["title"]
    )

    # This used to be display-only: you picked a lesson and nothing happened. The
    # syllabus in the main column lists lessons better, so these controls earn their
    # place by narrowing what the copilot can see — the one thing a list cannot do.
    #
    # The scope is set on the Copilot rather than written into the question, so every
    # tool shares it. That is what makes "quiz me on week 7" mean a quiz built from
    # week 7's material and not a whole-course quiz that mentions week 7.
    scope_choice = st.radio(
        "Answers come from",
        ["Whole course", f"Week {selected_week}", selected_lesson_id],
        key="scope_choice",
        help=(
            "Narrows every tool, not just search. A quiz scoped to a week is "
            "written only from that week's material."
        ),
    )

    if scope_choice == "Whole course":
        st.session_state.scope_week = None
        st.session_state.scope_lesson = ""
    elif scope_choice.startswith("Week"):
        st.session_state.scope_week = selected_week
        st.session_state.scope_lesson = ""
    else:
        st.session_state.scope_week = None
        st.session_state.scope_lesson = selected_lesson_id

    st.divider()

    # -----------------------------------------------------------------------
    # Quiz builder
    # -----------------------------------------------------------------------
    #
    # The quiz is the clearest use of the scope above, so it lives next to it: pick
    # how much of the course to be tested on, optionally narrow to a topic, generate.
    # Leaving the topic blank quizzes on whatever the chosen scope covers, which is
    # the point of scoping by week.

    st.subheader("📝 Quiz me")

    quiz_topic = st.text_input(
        "Topic (optional)",
        key="quiz_topic",
        placeholder="e.g. embeddings",
        help="Leave blank to be quizzed on whatever the scope above covers.",
    )

    quiz_count = st.slider(
        "Questions",
        min_value=3,
        max_value=5,
        value=3,
        key="quiz_count",
    )

    scope_words = {
        "Whole course": "the course",
        f"Week {selected_week}": f"week {selected_week}",
    }.get(scope_choice, f"lesson {selected_lesson_id}")

    if st.button(
        f"Generate quiz · {scope_words}",
        use_container_width=True,
        key="quiz_button",
    ):
        topic = quiz_topic.strip()

        if not topic:
            # A blank topic used to send the literal phrase "the main concepts covered
            # in the course" to the embedder. That is not a topic — it is a sentence
            # about topics, and it lands nearest the generic intro/overview talk, which
            # is week 1. Every whole-course quiz came out of week 1.
            #
            # Instead, pick a real lesson from whatever is in scope and quiz on that.
            # Random, so pressing the button twice covers different ground.
            candidates = [
                lesson
                for lesson_id, lesson in SYLLABUS_LESSONS.items()
                if (
                    not st.session_state.scope_lesson
                    or lesson_id == st.session_state.scope_lesson
                )
                and (
                    not st.session_state.scope_week
                    or lesson_id.startswith(f"w{st.session_state.scope_week}d")
                )
            ]

            if candidates:
                chosen = random.choice(candidates)
                # Lesson titles are several topics joined by " · "; one is a better
                # quiz seed than the whole string.
                topic = random.choice(chosen["title"].split(" · ")).strip()
            else:
                topic = f"the main concepts covered in {scope_words}"

        st.session_state.pending_question = (
            f"Quiz me on {topic}. Give me {quiz_count} questions."
        )
        st.rerun()

    st.divider()

    # -----------------------------------------------------------------------
    # Answer language
    # -----------------------------------------------------------------------

    st.subheader("🌐 Answer language")

    language = st.selectbox(
        "Language",
        [
            "Auto — match my question",
            "English",
            "Español",
        ],
        label_visibility="collapsed",
    )

    st.caption(
        "Auto answers in the same language as your question."
    )

    st.divider()

    if st.button(
        "New conversation",
        use_container_width=True,
    ):
        reset_conversation()
        st.rerun()


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div class="vc-hero">
      <h1>🎓 Ironhack AI Course Copilot</h1>
      <p>Ask anything from the bootcamp. Every answer is grounded in the recorded
      lessons and plays the video at the exact second it was explained.</p>
      <div class="vc-stats">
        <span>120 teaching recordings</span>
        <span>91 hours</span>
        <span>32 lesson days</span>
        <span>English &amp; Español</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Full syllabus
# ---------------------------------------------------------------------------
#
# The sidebar browser answers "show me one lesson". This answers "what does the
# course actually contain?" — the whole 8 weeks at once, which is the question a
# student has before they know what to ask.
#
# Collapsed by default so it costs one line when nobody wants it. Everything is
# read from data/lessons.json, which is generated from the recording metadata, so
# it cannot drift from what is actually indexed.


def render_syllabus(lessons: dict) -> None:
    """The whole course, grouped by week, with a link per recording."""
    by_week: dict[int, list[str]] = {}

    for lesson_id in sorted(lessons):
        week = int(lesson_id.split("d")[0].lstrip("w"))
        by_week.setdefault(week, []).append(lesson_id)

    total_recordings = sum(
        len(lessons[lesson_id].get("recordings", []))
        for lesson_id in lessons
    )
    total_hours = sum(
        recording.get("duration_seconds", 0)
        for lesson_id in lessons
        for recording in lessons[lesson_id].get("recordings", [])
    ) / 3600

    st.caption(
        f"{len(lessons)} lesson days · {total_recordings} recordings · "
        f"{total_hours:.0f} hours. Every one is searchable above."
    )

    for week in sorted(by_week):
        with st.expander(f"Week {week}"):
            for lesson_id in by_week[week]:
                lesson = lessons[lesson_id]
                recordings = lesson.get("recordings", [])

                day_minutes = sum(
                    r.get("duration_seconds", 0) for r in recordings
                ) / 60

                st.markdown(
                    f"**{lesson_id}** · {lesson.get('title', '')} "
                    f"<span style='color:#6B63B5'>· {day_minutes:.0f} min</span>",
                    unsafe_allow_html=True,
                )

                for recording in recordings:
                    minutes = recording.get("duration_seconds", 0) / 60
                    title = recording.get("title", "Untitled")
                    loom_id = recording.get("loom_id", "")
                    url = f"{LOOM_SHARE}/{loom_id}"

                    if loom_id:
                        st.markdown(
                            f"&nbsp;&nbsp;🎥 [{title}]({url}) · {minutes:.0f} min",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"&nbsp;&nbsp;🎥 {title} · {minutes:.0f} min")

                st.markdown("")


with st.expander("🗂️ Full course syllabus — all 8 weeks"):
    render_syllabus(SYLLABUS_LESSONS)


# ---------------------------------------------------------------------------
# Starter questions
# ---------------------------------------------------------------------------
#
# Shown only on an empty conversation. Two jobs: they fill what would otherwise
# be a blank page, and they let the app be demoed by clicking rather than typing,
# which removes the risk of a typo in front of an audience.
#
# Each one exercises a different capability, so clicking through them left to
# right is a complete demo.

STARTERS = [
    ("📍 Where was cosine similarity covered?", "Where was cosine similarity covered?"),
    ("📓 Show me the code for chunking with LangChain", "Show me the code for splitting documents into chunks with LangChain."),
    ("📝 Quiz me on RAG", "Quiz me on RAG"),
    ("🌍 ¿Cómo funciona RAG?", "¿Cómo funciona RAG?"),
]

# A starter click has to survive the rerun, so it is staged in session state and
# picked up next to st.chat_input() exactly like a typed question.
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

if not st.session_state.messages:
    st.caption("Try one of these:")

    for row_start in range(0, len(STARTERS), 2):
        for column, (label, prompt) in zip(
            st.columns(2),
            STARTERS[row_start:row_start + 2],
        ):
            with column:
                if st.button(
                    label,
                    key=f"starter_{row_start}_{label}",
                    use_container_width=True,
                ):
                    st.session_state.pending_question = prompt
                    st.rerun()


# ---------------------------------------------------------------------------
# Render previous conversation turns
# ---------------------------------------------------------------------------

for message_index, message in enumerate(
    st.session_state.messages
):
    with st.chat_message(message["role"], avatar=AVATARS[message["role"]]):
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

# A starter button click behaves exactly like a typed question from here on.
if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None


if question:
    # Save and immediately display the student's question.
    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(question)

        scope_note = st.session_state.get("scope_lesson") or (
            f"week {st.session_state.scope_week}"
            if st.session_state.get("scope_week")
            else ""
        )

        if scope_note:
            st.caption(f"🔒 scoped to {scope_note}")

    # Ask the real RAG agent.
    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        try:
            with st.spinner(
                "Searching the course material..."
            ):
                # Keep Auto's existing behaviour. For an explicitly selected
                # language, add an internal instruction without changing the
                # student's visible question in the chat.
                if language == "English":
                    agent_question = (
                        f"{question}\n\n"
                        "Answer in English."
                    )
                elif language == "Español":
                    agent_question = (
                        f"{question}\n\n"
                        "Responde en español."
                    )
                else:
                    agent_question = question

                # The scope is set on the agent, not written into the question. A
                # prompt instruction only reaches whichever tool the model happens to
                # pick; setting it here narrows every tool, so a quiz scoped to a week
                # is written from that week's material too.
                st.session_state.copilot.scope.set(
                    lesson_id=st.session_state.get("scope_lesson", ""),
                    week=st.session_state.get("scope_week"),
                )

                response = (
                    st.session_state.copilot.ask(agent_question)
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