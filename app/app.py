"""Streamlit app for the Ironhack AI Course Copilot.

The UI talks directly to the real Copilot agent and keeps one Copilot
instance in Streamlit session state so conversational memory survives reruns.
"""

from __future__ import annotations

import json
import random
import re
import sys
from io import BytesIO
from pathlib import Path

import streamlit as st

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

# Allow the Streamlit app to import the project modules from src/.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent import Copilot  # noqa: E402
from retrieval import search_with_scores  # noqa: E402
from tools import RELEVANCE_CUTOFF  # noqa: E402


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
        border: 1px solid #B9BEF5;
        border-radius: 12px;
        background: #EDEBFE;
    }

    /* The syllabus is reference material, not conversation, so it gets the violet end
       of the palette — clear of the indigo answers and the cyan questions either side
       of it. Streamlit tags every expander identically, so it is matched on the app's
       own marker span. The nested week expanders inside are deliberately left alone:
       tinting those too would flatten the panel back into one block of colour. */
    .stExpander:has(.vc-syllabus) > details {
        background: #EDE7FE !important;
        border: 1px solid #A78BFA !important;
        border-left: 4px solid #7C3AED !important;
        border-radius: 14px !important;
    }
    .stExpander:has(.vc-syllabus) > details > summary {
        font-weight: 700;
        color: #3B1E7A;
    }
    .stExpander:has(.vc-syllabus) .stExpander > details {
        background: #FFFFFF;
        border: 1px solid #C4B5FD;
        border-radius: 10px;
    }
    .vc-syllabus { display: none; }
    .stElementContainer:has(.vc-syllabus) { display: none; }

    /* The syllabus download. .stDownloadButton is a separate class from .stButton, so
       it inherits none of the starter-question styling — without this it renders as a
       plain grey pill on the violet panel. */
    .stDownloadButton > button {
        background: #FFFFFF;
        border: 1px solid #A78BFA;
        border-radius: 10px;
        color: #3B1E7A;
        font-weight: 600;
        padding: 0.3rem 0.8rem;
    }
    .stDownloadButton > button:hover {
        border-color: #7C3AED;
        background: #F6F2FF;
        color: #3B1E7A;
    }

    /* ---------------------------------------------------------------- sidebar */

    /* The same iridescent gradient as the hero, one step down in lightness. The
       first version was washed out to near-white, which made the hero look like the
       only coloured thing on the page. This keeps the hero dominant while the
       sidebar still reads as the same palette rather than as grey furniture.
       Stops chosen so text at #1E1B4B stays above 9:1 on every one of them. */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #D6CEFD 0%, #C6CFFB 45%, #B2E7F6 100%);
        border-right: 1px solid #9AA2F0;
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
        border-bottom: 3px solid;
        border-image: linear-gradient(90deg, #6366F1, #22D3EE) 1;
    }

    /* Field labels — smaller, uppercase, so they stop competing with the titles. */
    section[data-testid="stSidebar"] label p {
        font-size: 0.74rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: #322B7C !important;
    }

    /* Dropdowns and text inputs: white on the tinted panel so they read as controls,
       not as text. The deeper panel behind them does most of the separating now. */
    section[data-testid="stSidebar"] [data-baseweb="select"] > div,
    section[data-testid="stSidebar"] [data-baseweb="input"],
    section[data-testid="stSidebar"] .stTextInput input {
        background: #FFFFFF;
        border: 1px solid #8E97EE;
        border-radius: 10px;
    }

    /* The helper captions under each control. */
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
    section[data-testid="stSidebar"] small {
        color: #443C93 !important;
    }

    /* The credit line at the very bottom. Smaller than a caption on purpose — it has to
       be readable but must not compete with the controls above it. */
    section[data-testid="stSidebar"] .vc-credit {
        font-size: 0.68rem;
        line-height: 1.45;
        color: #4C43A8;
    }
    section[data-testid="stSidebar"] .vc-credit b {
        color: #322B7C;
    }

    /* Streamlit's default divider is a hard grey line; soften it into the palette. */
    section[data-testid="stSidebar"] hr {
        border-color: #9AA2F0;
        opacity: 0.9;
    }

    /* "Generate quiz" is the one action the sidebar exists for, so it wears the hero
       gradient. Everything else in there stays a white card — two loud buttons would
       tell the student nothing about which one to press. Streamlit renamed the button
       attribute across versions, so both selectors are listed. */
    section[data-testid="stSidebar"] button[kind="primary"],
    section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
        background: linear-gradient(115deg, #c4b5fd 0%, #818cf8 55%, #67e8f9 100%) !important;
        border: none !important;
        color: #10102E !important;
        font-weight: 700 !important;
        text-align: center !important;
        box-shadow: 0 6px 16px -8px rgba(79, 70, 229, 0.7);
    }
    section[data-testid="stSidebar"] button[kind="primary"]:hover,
    section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover {
        filter: brightness(1.07);
        color: #10102E !important;
    }

    /* ------------------------------------------------------------- chat + misc */

    /* Assistant bubble — the violet/indigo end of the palette, with an indigo bar
       down the edge. The bar does more work than the fill: two pale fills a few
       percent apart are hard to tell apart while scrolling, a 4px saturated edge
       is not. */
    .stChatMessage {
        background: #DFE2FE;
        border: 1px solid #A9AFF3;
        border-left: 4px solid #6366F1;
        border-radius: 14px;
    }

    /* The student's own turn gets the cyan end, so the two speakers are told apart
       by colour and not only by avatar.

       Matched on the app's own marker span, not on Streamlit's DOM. The obvious
       selector — `:has([data-testid="stChatMessageAvatarUser"])` — matches nothing
       here, because passing a custom `avatar=` replaces that element. It failed
       silently: every bubble simply took the assistant fill. */
    .vc-user-turn { display: none; }
    .stChatMessage .stElementContainer:has(.vc-user-turn) { display: none; }

    .stChatMessage:has(.vc-user-turn) {
        background: #CBEDF9;
        border-color: #6BC5DF;
        border-left-color: #0E9BBE;
    }

    /* Text shade follows the bubble it sits in: deep indigo for the copilot's
       answers, deep teal for the student's question. Both are dark enough to read
       (11:1 and 10:1 on their own fills) — the difference is hue and weight, not
       one of them being faded out. Streamlit paints markdown on inner nodes, so the
       colour has to be set there; setting it on .stChatMessage alone does nothing. */
    .stChatMessage [data-testid="stMarkdownContainer"],
    .stChatMessage [data-testid="stMarkdownContainer"] p,
    .stChatMessage [data-testid="stMarkdownContainer"] li,
    .stChatMessage [data-testid="stMarkdownContainer"] strong {
        color: #221C5E;
    }
    .stChatMessage:has(.vc-user-turn) [data-testid="stMarkdownContainer"],
    .stChatMessage:has(.vc-user-turn) [data-testid="stMarkdownContainer"] p,
    .stChatMessage:has(.vc-user-turn) [data-testid="stMarkdownContainer"] li,
    .stChatMessage:has(.vc-user-turn) [data-testid="stMarkdownContainer"] strong {
        color: #0A3D4C;
        font-weight: 600;
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

# Streamlit puts no role on the chat message element — `data-testid` is `stChatMessage`
# for both speakers, and passing `avatar=` removes the one testid that used to give the
# user's turn away. The only real difference left in the DOM is a hashed emotion class,
# which changes between Streamlit versions.
#
# So the app marks its own turns: an invisible span goes inside every student message and
# the CSS styles the bubble around it with `:has()`. Its element container is hidden with
# `display: none`, which removes it from the flex layout entirely — `visibility: hidden`
# would leave the vertical block's gap behind as a blank line above the question.
USER_TURN_MARKER = '<span class="vc-user-turn"></span>'

# Same trick for the syllabus panel — see the CSS block for why it needs its own colour.
SYLLABUS_MARKER = '<span class="vc-syllabus"></span>'

LESSONS_PATH = ROOT_DIR / "data" / "lessons.json"

# Built by scripts/build_syllabus_pdf.py and committed. The app only reads it.
# ReportLab is pinned as a deploy dependency because Study Notes PDFs are
# generated at runtime.
SYLLABUS_PDF_PATH = ROOT_DIR / "app" / "assets" / "ironhack-ai-syllabus.pdf"

# Loom's public watch URL. The agent emits /embed/ links for the inline players;
# the syllabus links out instead, so it wants the share form.
LOOM_SHARE = "https://www.loom.com/share"

# The team repo, not a personal fork — this is what the sidebar credit links to.
REPO_URL = "https://github.com/AI-Learning-Copilot/ironhack-final-project"


@st.cache_data
def load_lessons() -> dict:
    """The course calendar, generated from the recording metadata."""
    with LESSONS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


@st.cache_data
def load_syllabus_pdf(mtime: float) -> bytes:
    """Read once per server, not once per rerun — st.download_button wants the bytes in
    hand on every render, and the file is static.

    `mtime` is only there to key the cache: rebuilding the PDF while the dev server is
    up otherwise keeps serving the previous bytes until a restart.
    """
    return SYLLABUS_PDF_PATH.read_bytes()


SYLLABUS_LESSONS = load_lessons()

# One theme per week. Hand-written, because nothing in data/lessons.json can produce it:
# that file carries per-day titles, and a week's five titles concatenated run to several
# hundred characters. "Week 4" alone tells a student nothing about whether their question
# belongs there; "Week 4 · NLP & embeddings" does.
#
# Checked against every session title in lessons.json, not guessed from the week number.
# Three of these were wrong on the first pass and are worth recording so they do not get
# "simplified" back:
#
#   w3  "Deep learning" hid that half the week is computer vision — image preprocessing,
#       feature extraction and CNNs are two of its four days.
#   w5  "LLMs & APIs" dropped databases entirely. w5d1 is three SQLite sessions: CRUD,
#       table relationships and joins. A student looking for SQL could not find the week
#       it was taught in.
#   w8  "Multimodal AI" covered one of the week's two days. The other is NLP evaluation
#       metrics.
WEEK_THEMES = {
    1: "Python & data",
    2: "Machine learning",
    3: "Deep learning & vision",
    4: "NLP & embeddings",
    5: "Databases & LLM APIs",
    6: "Deployment",
    7: "LangChain & RAG",
    8: "Multimodal & evaluation",
}

def load_study_note(lesson_id: str) -> str | None:
    """Load generated Study Notes for a lesson, if available."""
    notes_path = ROOT_DIR / "summaries" / f"{lesson_id}.md"

    if not notes_path.exists():
        return None

    return notes_path.read_text(encoding="utf-8")

def study_notes_to_pdf(
    markdown: str,
    lesson_id: str,
    lesson_title: str,
) -> bytes:
    """Convert Study Notes Markdown into a polished downloadable PDF."""

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.8 * cm,
        leftMargin=1.8 * cm,
        topMargin=2.0 * cm,
        bottomMargin=1.8 * cm,
        title=f"Study Notes — {lesson_id.upper()}",
        author="Ironhack AI Course Copilot",
    )

    styles = getSampleStyleSheet()

    # -----------------------------------------------------------------------
    # Styles
    # -----------------------------------------------------------------------

    brand_style = ParagraphStyle(
        "StudyNotesBrand",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
        textColor="#6366F1",
        spaceAfter=8,
    )

    title_style = ParagraphStyle(
        "StudyNotesTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor="#1E1B4B",
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        "StudyNotesSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor="#4B5563",
        spaceAfter=18,
    )

    heading_style = ParagraphStyle(
        "StudyNotesHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor="#4338CA",
        spaceBefore=14,
        spaceAfter=7,
    )

    subheading_style = ParagraphStyle(
        "StudyNotesSubheading",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor="#312E81",
        spaceBefore=10,
        spaceAfter=5,
    )

    body_style = ParagraphStyle(
        "StudyNotesBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor="#1F2937",
        spaceAfter=6,
    )

    bullet_style = ParagraphStyle(
        "StudyNotesBullet",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-8,
        spaceAfter=4,
    )

    numbered_style = ParagraphStyle(
        "StudyNotesNumbered",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=0,
        spaceAfter=4,
    )

    source_style = ParagraphStyle(
        "StudyNotesSource",
        parent=body_style,
        fontSize=8.5,
        leading=12,
        leftIndent=12,
        firstLineIndent=-8,
        textColor="#374151",
        spaceAfter=4,
    )

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------

    def draw_footer(canvas, document) -> None:
        canvas.saveState()

        width, _ = A4

        canvas.setStrokeColor("#D1D5DB")
        canvas.setLineWidth(0.5)
        canvas.line(
            document.leftMargin,
            1.15 * cm,
            width - document.rightMargin,
            1.15 * cm,
        )

        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor("#6B7280")

        canvas.drawString(
            document.leftMargin,
            0.75 * cm,
            f"Ironhack AI Course Copilot · {lesson_id.upper()}",
        )

        canvas.drawRightString(
            width - document.rightMargin,
            0.75 * cm,
            f"Page {document.page}",
        )

        canvas.restoreState()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def markdown_inline_to_reportlab(text: str) -> str:
        """Convert the small subset of Markdown used by Study Notes."""

        # Escape ampersands first.
        text = text.replace("&", "&amp;")

        # Convert Markdown links:
        # [label](https://example.com)
        text = re.sub(
            r"\[([^\]]+)\]\((https?://[^)]+)\)",
            r'<link href="\2" color="#4F46E5"><u>\1</u></link>',
            text,
        )

        # Bold
        text = re.sub(
            r"\*\*(.+?)\*\*",
            r"<b>\1</b>",
            text,
        )

        # Inline code
        text = re.sub(
            r"`(.+?)`",
            r'<font name="Courier">\1</font>',
            text,
        )

        # Italic
        text = re.sub(
            r"(?<!\*)\*([^*]+)\*(?!\*)",
            r"<i>\1</i>",
            text,
        )

        return text

    # -----------------------------------------------------------------------
    # Build document
    # -----------------------------------------------------------------------

    story = []

    # Brand
    story.append(
        Paragraph(
            "IRONHACK AI ENGINEERING",
            brand_style,
        )
    )

    # Title
    story.append(
        Paragraph(
            f"{lesson_id.upper()} — {lesson_title}",
            title_style,
        )
    )

    # Subtitle
    story.append(
        Paragraph(
            "Study notes generated from the indexed Ironhack AI Engineering "
            "course recordings and notebooks.",
            subtitle_style,
        )
    )

    # Remove generated Markdown title and blockquote because the PDF
    # has its own designed header.
    content = re.sub(
        r"^# .*\n+",
        "",
        markdown,
        count=1,
    )

    content = re.sub(
        r"^> .*\n+",
        "",
        content,
        count=1,
        flags=re.MULTILINE,
    )

    in_sources = False
    source_category = ""

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if not line:
            story.append(Spacer(1, 3))
            continue

        # ---------------------------------------------------------------
        # Main headings
        # ---------------------------------------------------------------

        if line.startswith("## "):
            text = line[3:].strip()

            if text.lower() == "sources":
                in_sources = True

            story.append(
                Paragraph(
                    markdown_inline_to_reportlab(text),
                    heading_style,
                )
            )
            continue

        # ---------------------------------------------------------------
        # Subheadings
        # ---------------------------------------------------------------

        if line.startswith("### "):
            text = line[4:].strip()

            if in_sources:
                source_category = text

            story.append(
                Paragraph(
                    markdown_inline_to_reportlab(text),
                    subheading_style,
                )
            )
            continue

        # ---------------------------------------------------------------
        # Sources
        # ---------------------------------------------------------------

        if in_sources and line.startswith("- "):
            text = line[2:].strip()

            story.append(
                Paragraph(
                    f"• {markdown_inline_to_reportlab(text)}",
                    source_style,
                )
            )
            continue

        # ---------------------------------------------------------------
        # Bullets
        # ---------------------------------------------------------------

        if line.startswith("- "):
            text = line[2:].strip()

            story.append(
                Paragraph(
                    f"• {markdown_inline_to_reportlab(text)}",
                    bullet_style,
                )
            )
            continue

        # ---------------------------------------------------------------
        # Numbered lists
        # ---------------------------------------------------------------

        numbered_match = re.match(
            r"^(\d+)\.\s+(.+)",
            line,
        )

        if numbered_match:
            number = numbered_match.group(1)
            text = numbered_match.group(2)

            story.append(
                Paragraph(
                    f"{number}. {markdown_inline_to_reportlab(text)}",
                    numbered_style,
                )
            )
            continue

        # ---------------------------------------------------------------
        # Normal paragraph
        # ---------------------------------------------------------------

        story.append(
            Paragraph(
                markdown_inline_to_reportlab(line),
                body_style,
            )
        )

    doc.build(
        story,
        onFirstPage=draw_footer,
        onLaterPages=draw_footer,
    )

    return buffer.getvalue()

def week_label(week: int) -> str:
    """"Week 4 · NLP & embeddings" — falls back to the bare number if a week is added
    to the corpus before it gets a theme here."""
    theme = WEEK_THEMES.get(week)
    return f"Week {week} · {theme}" if theme else f"Week {week}"

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

def pick_quiz_topic(scope_lesson: str, scope_week: int | None) -> str | None:
    """A real topic to quiz on, drawn from the lessons inside the current scope.

    Used when the student leaves the topic box empty. Two things this has to survive:

    1. A blank topic must not be turned into a sentence. Sending "the main concepts
       covered in the course" to the embedder is a sentence ABOUT topics, not a topic —
       it lands nearest the generic intro talk, so every quiz came out of week 1.

    2. Not every fragment of a lesson title is a topic. w6d5's entire title is
       "Group2B · Group2A" — project presentation day, no teaching content — and a
       random pick from it produced "Quiz me on Group2A", which then refused.

    So candidates are shuffled and each is checked against the index before use. The
    first one that actually retrieves course material within the scope wins. Returns
    None when the scope holds nothing quizzable, which is a real answer for a week of
    presentations.
    """
    # Presentation days are titled by group, not by topic — w6d5 is "Group2B · Group2A".
    # Those fragments cannot be filtered by checking the index, because the sessions
    # WERE recorded, so "Group2A" happily retrieves its own transcript. They have to be
    # recognised by shape.
    #
    # A word-count rule was the obvious alternative and is wrong: of the 115 title
    # fragments in the course, only five are single words, and three of those
    # (NumPy, Pandas, Streaming) are real topics.
    not_a_topic = re.compile(r"^(group|team|grupo|equipo)\s*\d*[a-z]?$", re.IGNORECASE)

    candidates: list[str] = []

    for lesson_id, lesson in SYLLABUS_LESSONS.items():
        if scope_lesson and lesson_id != scope_lesson:
            continue
        if scope_week and not lesson_id.startswith(f"w{scope_week}d"):
            continue
        candidates.extend(
            part.strip()
            for part in lesson["title"].split(" · ")
            if part.strip() and not not_a_topic.match(part.strip())
        )

    random.shuffle(candidates)

    for candidate in candidates[:8]:
        hits = search_with_scores(
            candidate,
            k=1,
            lesson_id=scope_lesson or None,
            week=scope_week,
        )
        if hits and hits[0][1] <= RELEVANCE_CUTOFF:
            return candidate

    return None


def external_link(label: str, url: str) -> str:
    """A link that opens in a new tab.

    Streamlit's markdown links navigate the current tab. On Streamlit Cloud the app
    runs inside an iframe, so following a Loom or GitHub link replaces the copilot and
    the student loses their conversation — memory included, since it lives in the
    session. Every link here points off-site, so every one of them opens in a new tab.

    rel="noopener noreferrer" because target="_blank" otherwise hands the opened page a
    handle on this one via window.opener.

    `target="_blank"` is the only lever available here, and it is genuinely in the DOM —
    checked in the running app, with nothing calling preventDefault on the click. Do not
    try to reinforce it with `onclick="window.open(...)"`: Streamlit's sanitizer strips
    event-handler attributes out of `unsafe_allow_html` markup, so the attribute simply
    never reaches the page. `st.link_button` is no stronger — it emits the same anchor.
    The only way to run real JS is `st.components.v1.html`, which puts the content in
    its own iframe.
    """
    return (
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
    )


def render_citation(citation: dict) -> None:
    """Render one citation using metadata prepared by the backend."""
    source_type = citation.get("source_type", "")
    label = citation.get("label", "Course source")
    url = citation.get("url", "")

    if source_type == "video":
        st.markdown("**🎥 Lecture video**")

        if url:
            # The text link and the inline player want different Loom URLs. The backend
            # emits /embed/, which is what the iframe below needs, but opening /embed/
            # as a page of its own gives the bare player with none of Loom's chrome —
            # no title, no transcript, no captions menu. /share/ is the watch page, and
            # it honours the same ?t= timestamp.
            st.markdown(
                external_link(label, url.replace("/embed/", "/share/")),
                unsafe_allow_html=True,
            )

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
            st.markdown(external_link(label, url), unsafe_allow_html=True)
        else:
            st.write(label)

    else:
        st.markdown("**🔗 Course source**")

        if url:
            st.markdown(external_link(label, url), unsafe_allow_html=True)
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
            # A new question can be returned in several formats by the LLM.
            # Examples:
            # 1. What is RAG?
            # 2) What is an embedding?
            # --- Question 2: What is an embedding?
            # ### Question 3: What is an embedding?
            # Question 4
            # What is an embedding?

            cleaned_line = _strip_markdown(line)

            # Format: "Question 4"
            # The actual question may be on the following line.
            question_header_match = re.match(
                r"^(?:[-*]+\s*)?"
                r"(?:#{1,6}\s*)?"
                r"question\s+\d+\s*:?\s*$",
                cleaned_line,
                flags=re.IGNORECASE,
            )

            if question_header_match:
                if current_options and current_answer:
                    save_current_question()

                quiz_started = True
                current_question_lines = []
                continue

            # Format: "Question 2: What is..."
            # Also handles "--- Question 2: ..." and "### Question 2: ..."
            question_match = re.match(
                r"^(?:[-*]+\s*)?"
                r"(?:#{1,6}\s*)?"
                r"question\s+\d+\s*:\s*(.+)",
                cleaned_line,
                flags=re.IGNORECASE,
            )

            # Format: "2. What is..." or "2) What is..."
            if not question_match:
                question_match = re.match(
                    r"^\s*\d+[\.\)]\s*(.+)",
                    cleaned_line,
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
    sources_expander: bool = True,
) -> None:
    """Render one Copilot response and its citations.

    `sources_expander=False` renders the sources without their own expander. Older
    answers in the history are themselves collapsed into an expander, and Streamlit
    cannot nest one inside another — it raises rather than degrading.
    """
    import contextlib
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

        # Collapsed by default. Each video citation embeds a Loom player, so an open
        # sources block pushed the answer itself off the screen — the student had to
        # scroll past three videos to read what they asked for.
        sources_box = (
            st.expander(source_label, expanded=False)
            if sources_expander
            else contextlib.nullcontext()
        )

        if not sources_expander:
            st.caption(source_label)

        with sources_box:
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
                        # Same /embed/ to /share/ swap as the cards above — these are
                        # links only, never players, so they always want the watch page.
                        st.markdown(
                            f"{icon} " + external_link(
                                label, url.replace("/embed/", "/share/")
                            ),
                            unsafe_allow_html=True,
                        )
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

    st.subheader("📝 Quiz me")

    # One section, not two. Scope used to be its own block that also narrowed ordinary
    # chat answers, which meant two controls doing overlapping jobs and no obvious
    # reason to touch either. The quiz is where narrowing genuinely matters — revising
    # week 5 means being tested on week 5 — so the scope lives here and applies to the
    # quiz only. Chat always searches the whole course.

    quiz_topic = st.text_input(
        "Topic (optional)",
        key="quiz_topic",
        placeholder="e.g. embeddings",
        help="Leave blank to be quizzed on whatever the scope below covers.",
    )

    quiz_scope = st.radio(
        "Quiz me on",
        ["Whole course", "A week", "A specific day"],
        key="quiz_scope",
    )

    scope_week = None
    scope_lesson = ""
    scope_words = "the whole course"

    if quiz_scope != "Whole course":
        weeks = sorted(
            {int(lesson_id.split("d")[0][1:]) for lesson_id in SYLLABUS_LESSONS}
        )
        selected_week = st.selectbox(
            "Week",
            weeks,
            format_func=week_label,
            key="quiz_week",
        )
        scope_week = selected_week
        # Number only. The theme is already on the dropdown right above the button, and
        # repeating it here wrapped "Generate quiz · week 1 · Python & data" onto two
        # lines in the sidebar's width.
        scope_words = f"week {selected_week}"

    if quiz_scope == "A specific day":
        week_lessons = {
            lesson_id: lesson
            for lesson_id, lesson in SYLLABUS_LESSONS.items()
            if lesson_id.startswith(f"w{scope_week}d")
        }
        lesson_ids = sorted(
            week_lessons, key=lambda lesson_id: int(lesson_id.split("d")[1])
        )

        def lesson_label(lesson_id: str) -> str:
            """Compact label — full lesson titles are several topics long."""
            day = lesson_id.split("d")[1]
            first_topic = week_lessons[lesson_id]["title"].split(" · ")[0]
            if len(first_topic) > 40:
                first_topic = first_topic[:37] + "..."
            return f"Day {day} — {first_topic}"

        selected_lesson_id = st.selectbox(
            "Day",
            lesson_ids,
            format_func=lesson_label,
            key="quiz_lesson",
        )
        scope_lesson = selected_lesson_id
        scope_week = None
        scope_words = f"lesson {selected_lesson_id}"

        st.caption(week_lessons[selected_lesson_id]["title"])

    quiz_count = st.slider("Questions", min_value=3, max_value=5, value=3, key="quiz_count")

    if st.button(
        f"Generate quiz · {scope_words}",
        use_container_width=True,
        key="quiz_button",
        type="primary",
    ):
        topic = quiz_topic.strip() or pick_quiz_topic(scope_lesson, scope_week)

        if not topic:
            st.warning(
                f"There is no teaching material indexed for {scope_words} — it is "
                "project presentations. Pick another week, or type a topic."
            )
        else:
            # The scope applies to this one turn only, so an ordinary follow-up
            # question afterwards is not silently still filtered.
            st.session_state.pending_scope = (scope_lesson, scope_week)
            st.session_state.pending_question = (
                f"Quiz me on {topic}. Give me {quiz_count} questions."
            )
            st.rerun()

    st.divider()

    if st.button(
        "New conversation",
        use_container_width=True,
    ):
        reset_conversation()
        st.rerun()

    st.divider()

    # Language sits last on purpose. It is set once at the start of a session and then
    # left alone, unlike the quiz controls above it, which are touched every time. A
    # preference that is rarely changed should not sit between the student and the
    # control they came for.
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

    # Attribution, last thing in the sidebar. Two separate credits and they should not be
    # confused: the teaching material is Ironhack's, the software around it is ours. The
    # app answers only from that material, so saying whose it is belongs on the screen
    # rather than in the README alone.
    st.markdown(
        f'<div class="vc-credit">'
        f"The material in this app — recordings and notebooks — is from the "
        f"<b>Ironhack AI Engineering bootcamp</b> and belongs to Ironhack. "
        f"The copilot itself is our final project for that bootcamp; the code is on "
        f"{external_link('GitHub', REPO_URL)}."
        f"</div>",
        unsafe_allow_html=True,
    )


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
        <!-- 90, not 91. lessons.json totals 89.78 h across the 120 recordings; the
             syllabus panel computes the same figure and printed 90 next to a hero
             saying 91. -->
        <span>90 hours</span>
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

    # Guarded: a fresh clone that has not run scripts/build_syllabus_pdf.py still starts,
    # it just has no download button.
    if SYLLABUS_PDF_PATH.exists():
        st.download_button(
            "⬇️  Syllabus PDF",
            data=load_syllabus_pdf(SYLLABUS_PDF_PATH.stat().st_mtime),
            file_name="ironhack-ai-syllabus.pdf",
            mime="application/pdf",
            help="One continuous page: the eight weeks, every lesson day, and a QR "
                 "code back to this app.",
        )

    for week in sorted(by_week):
        with st.expander(week_label(week)):
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

                # Study Notes are available only for lessons that already have
                # generated notes in summaries/.
                notes_path = ROOT_DIR / "summaries" / f"{lesson_id}.md"

                if notes_path.exists():
                    if st.button(
                        "📚 Study Notes",
                        key=f"study_notes_{lesson_id}",
                    ):
                        st.session_state["study_notes_lesson"] = lesson_id
                        st.rerun()

                for recording in recordings:
                    minutes = recording.get("duration_seconds", 0) / 60
                    title = recording.get("title", "Untitled")
                    loom_id = recording.get("loom_id", "")
                    url = f"{LOOM_SHARE}/{loom_id}"

                    if loom_id:
                        st.markdown(
                            "&nbsp;&nbsp;🎥 "
                            + external_link(title, url)
                            + f" · {minutes:.0f} min",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"&nbsp;&nbsp;🎥 {title} · {minutes:.0f} min")

                st.markdown("")


with st.expander("🗂️ Full course syllabus — all 8 weeks"):
    # Same marker trick as the student's chat turn: Streamlit gives every expander the
    # same testid, so the syllabus is told apart by a span the app puts inside it.
    st.markdown(SYLLABUS_MARKER, unsafe_allow_html=True)
    render_syllabus(SYLLABUS_LESSONS)

# ---------------------------------------------------------------------------
# Study Notes viewer
# ---------------------------------------------------------------------------

selected_notes_lesson = st.session_state.get("study_notes_lesson")

if selected_notes_lesson:
    notes = load_study_note(selected_notes_lesson)

    if notes:
        lesson = SYLLABUS_LESSONS.get(
            selected_notes_lesson,
            {},
        )

        lesson_title = lesson.get(
            "title",
            selected_notes_lesson.upper(),
        )

        st.markdown("---")

        st.subheader(
            f"📚 Study Notes — {selected_notes_lesson.upper()}"
        )

        if lesson_title:
            st.caption(lesson_title)

        # The Markdown file already contains its own H1 title.
        # Remove it because the app displays the title above.
        notes_body = re.sub(
            r"^# .*\n+",
            "",
            notes,
            count=1,
        )

        st.markdown(notes_body)

        pdf_data = study_notes_to_pdf(
            markdown=notes,
            lesson_id=selected_notes_lesson,
            lesson_title=lesson_title,
        )

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                "⬇️ Download Study Notes PDF",
                data=pdf_data,
                file_name=f"{selected_notes_lesson}_study_notes.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        with col2:
            if st.button(
                "✕ Close Study Notes",
                key="close_study_notes",
                use_container_width=True,
            ):
                st.session_state.pop(
                    "study_notes_lesson",
                    None,
                )
                st.rerun()

    else:
        st.warning(
            f"Study Notes for {selected_notes_lesson.upper()} "
            "could not be found."
        )


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

# Only the newest answer stays open. Each answer carries an embedded Loom player per
# citation, so three questions deep the page is mostly video and the student has to
# scroll past everything they have already read to reach the thing they just asked.
#
# Older answers collapse into an expander showing their first line. render_response()
# normally opens its own expander for the sources, which cannot be nested inside this
# one, so it is asked to render them inline instead.

_last_assistant = max(
    (
        index
        for index, message in enumerate(st.session_state.messages)
        if message["role"] == "assistant"
    ),
    default=-1,
)


def _preview(text: str, limit: int = 110) -> str:
    """First line of an answer, for the collapsed label."""
    first_line = next(
        (line.strip() for line in text.splitlines() if line.strip()),
        "",
    )
    if len(first_line) > limit:
        first_line = first_line[: limit - 1].rstrip() + "…"
    return first_line or "Answer"


for message_index, message in enumerate(
    st.session_state.messages
):
    with st.chat_message(message["role"], avatar=AVATARS[message["role"]]):
        if message["role"] == "assistant":
            if message_index == _last_assistant:
                render_response(
                    message["response"],
                    message_id=str(message_index),
                )
            else:
                answer = message["response"].get("answer", "")
                sources = len(message["response"].get("citations", []))
                source_note = f" · {sources} sources" if sources else ""

                with st.expander(f"{_preview(answer)}{source_note}"):
                    render_response(
                        message["response"],
                        message_id=str(message_index),
                        # Already inside an expander — see render_response.
                        sources_expander=False,
                    )
        else:
            st.markdown(USER_TURN_MARKER, unsafe_allow_html=True)
            st.markdown(message["content"])

            if message.get("scope_note"):
                st.caption(f"🔒 scoped to {message['scope_note']}")


# ---------------------------------------------------------------------------
# Memory nudge
# ---------------------------------------------------------------------------
#
# ConversationSummaryBufferMemory keeps recent turns verbatim inside a token budget and
# compresses whatever falls out into a running prose summary.
#
# This used to fire on a turn count of 3, from an early estimate. Measured on the real
# agent over a nine-turn conversation, compression actually starts at **turn 6** — the
# buffer holds 173, 248, 396, 547 and 618 tokens over the first five turns and only then
# overflows. The nudge was warning students three turns before anything had happened.
#
# The count was the wrong thing to watch anyway: the budget is tokens, so a conversation
# of short refusals lasts twice as long as one of long explanations. `moving_summary_buffer`
# is empty until the memory genuinely compresses something, so ask the memory instead of
# guessing from turn numbers. Exact, and it cannot drift again.
#
# What compression costs, measured on the summary text it produced: weeks survive as
# prose ("week 4 day 3"), but machine-readable lesson ids and exact timestamps do not —
# a regex for `w\dd\d` and for `\d+:\d\d` both return nothing, and the summariser writes
# the phrase "at specific timestamps" in place of the numbers. So "which week was that?"
# keeps working and "go back to that minute you gave me" cannot.

_memory_has_summarised = bool(
    getattr(st.session_state.copilot.memory, "moving_summary_buffer", "")
)

if _memory_has_summarised:
    st.caption(
        "💭 This conversation is now long enough that the earliest turns are "
        "summarised. Follow-ups on the same topic still work, and so does *\"which "
        "week was that?\"* — but the **exact timestamps** from those early answers are "
        "gone. For a new topic, or to get a precise minute back, start a "
        "**New conversation** in the sidebar."
    )


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
    pending = st.session_state.get("pending_scope") or ("", None)
    scope_note = pending[0] or (f"week {pending[1]}" if pending[1] else "")

    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
            # Stored, not recomputed: the scope is consumed when the answer is
            # generated, so re-rendering history later would otherwise lose the badge.
            "scope_note": scope_note,
        }
    )

    with st.chat_message("user", avatar=AVATARS["user"]):
        # The marker goes first and separately: the question itself is rendered without
        # unsafe_allow_html, so nothing a student types can inject markup.
        st.markdown(USER_TURN_MARKER, unsafe_allow_html=True)
        st.markdown(question)

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
                #
                # It is consumed here and cleared, so it lasts exactly one turn. A
                # follow-up typed after a week-5 quiz searches the whole course again,
                # which is what a student expects — the filter belonged to the quiz
                # they asked for, not to the conversation.
                turn_lesson, turn_week = st.session_state.pop(
                    "pending_scope", ("", None)
                )
                st.session_state.copilot.scope.set(
                    lesson_id=turn_lesson,
                    week=turn_week,
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

            # Rerun so the history re-renders with this answer as the newest one and
            # the previous one collapsed. Without it the script has already finished
            # and the older answer stays open until the student's *next* action —
            # collapsing one turn late, which looks broken. Nothing is re-asked: the
            # response is already in session state.
            st.rerun()

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