"""PDF rendering, lifted out of `app/app.py` unchanged.

`study_notes_to_pdf` never imported streamlit — it is markdown in, bytes out — so it was
already reusable and only its location made it Streamlit's. Moving it here lets the HTTP
API serve the same PDF the download button produces, from the same code, rather than a
second implementation that drifts.

The function body below is byte-identical to the version that was in `app/app.py`. If it
needs changing, change it here: `app.py` now imports it.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

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

ROOT_DIR = Path(__file__).resolve().parents[1]
SYLLABUS_PDF_PATH = ROOT_DIR / "app" / "assets" / "ironhack-ai-syllabus.pdf"


def syllabus_pdf_bytes() -> bytes | None:
    """The pre-built syllabus PDF, or None if it was never generated.

    Static file, no rendering. `app.py` wraps this in `st.cache_data` keyed on mtime so a
    rebuild during a dev session is picked up; the HTTP layer has no such problem.
    """
    if not SYLLABUS_PDF_PATH.is_file():
        return None
    return SYLLABUS_PDF_PATH.read_bytes()


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

