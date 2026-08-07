"""Build the downloadable course syllabus — one continuous page.

    python scripts/build_syllabus_pdf.py

Writes ``app/assets/ironhack-ai-syllabus.pdf``, which is **committed to the repo** and
served by the app as a static download.

Build time, not run time — the same split as the Chroma index. Generating the PDF on
every download would put reportlab on the deployed app's dependency list to produce a
file that never changes between commits. So reportlab is deliberately **not** in
requirements.txt; it is only needed by whoever regenerates the PDF:

    pip install -r scripts/requirements-syllabus-pdf.txt

**One page, not A4.** The page is A4 width and as tall as the content needs — the whole
syllabus scrolls in one go, with no page breaks splitting a week in half and no
half-empty final page. The height is measured from the laid-out flowables before the
document is created; see `measure_story`. The build asserts a single page at the end, so
a content change that breaks the measurement fails loudly instead of quietly producing
two.

Content comes from data/lessons.json (structure, durations) and
data/lesson_summaries.json (one readable sentence per day).

**No Loom links here, on purpose.** The recordings are Ironhack's material and the app is
what gates access to them; a PDF travels. The syllabus describes what was taught, and the
app is where you click through to the video.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
LESSONS_PATH = ROOT / "data" / "lessons.json"
SUMMARIES_PATH = ROOT / "data" / "lesson_summaries.json"
OUT_PATH = ROOT / "app" / "assets" / "ironhack-ai-syllabus.pdf"

APP_URL = "https://ai-learning-copilot-ironhack-final-project.streamlit.app/"
APP_SHORT = "ai-learning-copilot-ironhack-final-project.streamlit.app"
REPO_URL = "https://github.com/AI-Learning-Copilot/ironhack-final-project"
REPO_SHORT = "github.com/AI-Learning-Copilot/ironhack-final-project"
PROFILES = [
    ("Casilda Gil de Santivañes Finat", "https://github.com/Casildagsf"),
    ("Felipe Martignon", "https://github.com/Martigol2"),
]

# Kept in step with WEEK_THEMES in app/app.py. Duplicated rather than imported: importing
# app.py would execute the whole Streamlit script, load the Chroma index and build a
# Copilot, just to read a dict of eight strings.
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

# Vapor Chrome — the app's palette, not the blue of the reference layout.
VIOLET = colors.HexColor("#c4b5fd")
INDIGO = colors.HexColor("#818cf8")
CYAN = colors.HexColor("#67e8f9")
ICE = colors.HexColor("#a5f3fc")

ACCENT = colors.HexColor("#7C3AED")   # deep violet — the app's syllabus panel
LINK = colors.HexColor("#4F46E5")     # the app's link indigo
INK = colors.HexColor("#1E1B4B")      # the app's text colour
INK_SOFT = colors.HexColor("#5B54A6")
PANEL = colors.HexColor("#EDE7FE")    # the app's syllabus panel fill
RULE = colors.HexColor("#D9D2FA")
RULE_STRONG = colors.HexColor("#B9A9F7")

# Notebook and chunk counts come from the build, not from lessons.json, so they are the
# only figures typed in. Frozen 2026-08-07 after the notebook rebuild.
NOTEBOOKS_TOTAL = 64
NOTEBOOKS_MAPPED = 40
NOTEBOOKS_EXTRA = 24
CHUNKS_TOTAL = "6,037"

PAGE_WIDTH = A4[0]
SIDE_MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * SIDE_MARGIN
HEAD_HEIGHT = 20 * mm      # gradient band + running head above the frame
FOOT_HEIGHT = 16 * mm      # rule + link line below the frame


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
#
# Helvetica throughout. The app's Sora/Manrope are Google web fonts loaded over the
# network; embedding them would mean committing .ttf files for a one-page handout. The
# palette carries the family resemblance instead.
#
# Every style has spaceBefore/spaceAfter left at zero and vertical rhythm comes from
# explicit Spacers. That is what makes the page height measurable: a style-driven space
# is applied by the frame at layout time and would not show up in `measure_story`.

TITLE = ParagraphStyle(
    "title", fontName="Helvetica-Bold", fontSize=27, leading=30, textColor=INK,
)
EYEBROW = ParagraphStyle(
    "eyebrow", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
    textColor=ACCENT,
)
LEAD = ParagraphStyle(
    "lead", fontName="Helvetica", fontSize=10, leading=15.5, textColor=INK,
)
SECTION = ParagraphStyle(
    "section", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK,
)
WEEK_HEAD = ParagraphStyle(
    "weekhead", fontName="Helvetica-BoldOblique", fontSize=11.5, leading=14,
    textColor=ACCENT,
)
DAY_TAG = ParagraphStyle(
    "daytag", fontName="Helvetica-Bold", fontSize=8, leading=13, textColor=ACCENT,
)
DAY_TEXT = ParagraphStyle(
    "daytext", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK,
)
DAY_MIN = ParagraphStyle(
    "daymin", fontName="Helvetica", fontSize=8, leading=13, textColor=INK_SOFT,
    alignment=TA_RIGHT,
)
BODY = ParagraphStyle(
    "body", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK,
)
BODY_KEY = ParagraphStyle(
    "bodykey", fontName="Helvetica-Bold", fontSize=9.5, leading=13.5, textColor=INK,
)
LINKS = ParagraphStyle(
    "links", fontName="Helvetica", fontSize=9.5, leading=16, textColor=INK,
)
CAPTION = ParagraphStyle(
    "caption", fontName="Helvetica", fontSize=9, leading=13, textColor=INK_SOFT,
)
STAT_NUM = ParagraphStyle(
    "statnum", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=ACCENT,
    alignment=TA_CENTER,
)
STAT_LABEL = ParagraphStyle(
    "statlabel", fontName="Helvetica", fontSize=6.8, leading=8.6, textColor=INK_SOFT,
    alignment=TA_CENTER,
)
TABLE_HEAD = ParagraphStyle(
    "tablehead", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=INK,
)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def clean(text: str) -> str:
    """Drop characters the built-in Helvetica cannot draw, and escape the markup ones.

    One lesson title carries a 📌 (w2d3). Helvetica has no glyph for it, so reportlab
    drew a black box. Accented Latin is kept — "Santivañes" has to survive — as are the
    dashes and middots; only what sits above Latin Extended is removed.
    """
    kept = "".join(
        char for char in text if ord(char) < 0x2000 or char in "·—–…"
    )
    return kept.replace("&", "&amp;").replace("<", "&lt;").strip(" ·")


def load_course() -> dict[int, list[dict]]:
    """lessons.json grouped by week, days in order, each carrying its summary sentence."""
    lessons = json.loads(LESSONS_PATH.read_text(encoding="utf-8"))
    summaries = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))

    missing = []
    weeks: dict[int, list[dict]] = {}

    for lesson_id, lesson in lessons.items():
        week = int(lesson_id.split("d")[0].lstrip("w"))
        summary = summaries.get(lesson_id)

        if not summary:
            # Fall back to the raw title rather than printing a blank row.
            missing.append(lesson_id)
            summary = lesson.get("title", "")

        weeks.setdefault(week, []).append({**lesson, "summary": summary})

    for week in weeks:
        weeks[week].sort(key=lambda day: int(day["lesson_id"].split("d")[1]))

    if missing:
        print(
            f"warning: no sentence in lesson_summaries.json for {', '.join(missing)} "
            f"— used the raw title instead",
            file=sys.stderr,
        )

    return dict(sorted(weeks.items()))


def totals(weeks: dict[int, list[dict]]) -> tuple[int, int, float]:
    days = [day for week_days in weeks.values() for day in week_days]
    recordings = sum(len(day.get("recordings", [])) for day in days)
    hours = sum(day.get("duration_seconds", 0) for day in days) / 3600
    return len(days), recordings, hours


# ---------------------------------------------------------------------------
# Page furniture — drawn once, since there is only one page
# ---------------------------------------------------------------------------


def draw_furniture(canvas, doc) -> None:
    height = doc.pagesize[1]

    canvas.saveState()

    # The app's hero gradient, reduced to a band across the top edge. The reference
    # layout has no gradient; this is the one place the palette is allowed to be loud,
    # so a printed page still reads as the same product as the app.
    canvas.linearGradient(
        0, height - 5, PAGE_WIDTH, height,
        (VIOLET, INDIGO, CYAN, ICE), (0.0, 0.38, 0.78, 1.0), extend=True,
    )
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, PAGE_WIDTH, height - 5, stroke=0, fill=1)

    # Running head.
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(INK_SOFT)
    canvas.drawString(SIDE_MARGIN, height - 14 * mm, "IRONHACK AI ENGINEERING")
    canvas.drawRightString(
        PAGE_WIDTH - SIDE_MARGIN, height - 14 * mm, "COURSE SYLLABUS · 8 WEEKS"
    )
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(
        SIDE_MARGIN, height - 16.5 * mm, PAGE_WIDTH - SIDE_MARGIN, height - 16.5 * mm
    )

    # Footer.
    canvas.line(SIDE_MARGIN, 11 * mm, PAGE_WIDTH - SIDE_MARGIN, 11 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(INK_SOFT)
    canvas.drawString(SIDE_MARGIN, 7 * mm, f"Searchable in full at {APP_SHORT}")
    canvas.drawRightString(PAGE_WIDTH - SIDE_MARGIN, 7 * mm, f"Source: {REPO_SHORT}")

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Flowables
# ---------------------------------------------------------------------------


def overview_table(weeks: dict[int, list[dict]]) -> Table:
    header = [Paragraph(label, TABLE_HEAD) for label in
              ("Week", "Theme", "Days", "Sessions", "Hours")]
    rows = [header]

    for week, days in weeks.items():
        recordings = sum(len(day.get("recordings", [])) for day in days)
        hours = sum(day.get("duration_seconds", 0) for day in days) / 3600
        rows.append([
            str(week),
            WEEK_THEMES.get(week, ""),
            str(len(days)),
            str(recordings),
            f"{hours:.0f}",
        ])

    table = Table(
        rows,
        colWidths=[18 * mm, 76 * mm, 20 * mm, 26 * mm, 24 * mm],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PANEL),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 8),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
    ]))
    return table


def stat_card(number: str, label: str, width: float) -> Table:
    card = Table(
        [[Paragraph(number, STAT_NUM)], [Paragraph(label, STAT_LABEL)]],
        colWidths=[width],
    )
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("ROUNDEDCORNERS", [5, 5, 5, 5]),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return card


def stats_strip(weeks: dict[int, list[dict]]) -> Table:
    """The corpus, as five cards. Days, recordings and hours are counted from
    lessons.json rather than typed, so the handout cannot drift from the index."""
    day_count, recordings, hours = totals(weeks)

    figures = [
        (str(day_count), "lesson days"),
        (str(recordings), "recordings"),
        (f"{hours:.0f}", "hours of teaching"),
        (str(NOTEBOOKS_TOTAL), f"notebooks ({NOTEBOOKS_MAPPED} + {NOTEBOOKS_EXTRA} extra)"),
        (CHUNKS_TOTAL, "indexed passages"),
    ]

    gap = 3 * mm
    cell_width = CONTENT_WIDTH / 5
    card_width = cell_width - gap

    container = Table(
        [[stat_card(number, label, card_width) for number, label in figures]],
        colWidths=[cell_width] * 5,
        hAlign="LEFT",
    )
    container.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), gap),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return container


def how_to_use() -> Table:
    """Three things a student cannot guess from the interface."""
    items = [
        (
            "Ask in your own language",
            "Answers come back in the language you asked in — the material stays "
            "English underneath. Spanish questions match English lessons.",
        ),
        (
            "Every answer names its source",
            "Lesson day, notebook cell, and the recording cued to the second. If the "
            "copilot says a topic was not covered, that is a real answer, not a "
            "failure — nothing was invented to fill the gap.",
        ),
        (
            "Quiz yourself before an assessment",
            "Pick a week or a single day and the questions are written from that "
            "material only.",
        ),
    ]

    rows = [
        [Paragraph(heading, BODY_KEY), Paragraph(text, BODY)]
        for heading, text in items
    ]

    table = Table(rows, colWidths=[52 * mm, CONTENT_WIDTH - 52 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]))
    return table


def qr_drawing(url: str, size_mm: float = 26) -> Drawing:
    """QR generated by reportlab itself — no external service, no image file, and it
    stays vector so it survives printing at any size."""
    side = size_mm * mm
    widget = qr.QrCodeWidget(url, barLevel="M")
    bounds = widget.getBounds()
    scale = side / (bounds[2] - bounds[0])

    drawing = Drawing(side, side, transform=[scale, 0, 0, scale, 0, 0])
    drawing.add(widget)
    return drawing


def links_block() -> Table:
    profile_links = " · ".join(
        f'<a href="{url}" color="#4F46E5">{clean(name)}</a>' for name, url in PROFILES
    )

    text = Paragraph(
        f'<b>Ask the copilot</b> — '
        f'<a href="{APP_URL}" color="#4F46E5">{APP_SHORT}</a><br/>'
        f'<b>Source code</b> — '
        f'<a href="{REPO_URL}" color="#4F46E5">{REPO_SHORT}</a><br/>'
        f'<b>Built by</b> — {profile_links}',
        LINKS,
    )

    qr_cell = Table(
        [[qr_drawing(APP_URL)], [Paragraph("Scan to open", STAT_LABEL)]],
        colWidths=[26 * mm],
    )
    qr_cell.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    # The QR column is wider than the QR and the code is centred in it, so the gap to
    # the box edge matches the text's inset on the left. The first version right-aligned
    # a 30 mm code in a 36 mm column with 12 pt of padding, which left the code almost
    # touching the border while the text side had a comfortable margin.
    inset = 14
    qr_column = 40 * mm

    table = Table(
        [[text, qr_cell]],
        colWidths=[CONTENT_WIDTH - qr_column, qr_column],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE_STRONG),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("LEFTPADDING", (0, 0), (0, 0), inset),
        ("RIGHTPADDING", (0, 0), (0, 0), 6),
        ("LEFTPADDING", (1, 0), (1, 0), 0),
        ("RIGHTPADDING", (1, 0), (1, 0), inset),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return table


def week_block(week: int, days: list[dict]) -> list:
    """Heading with a rule under it, then one row per day."""
    heading = Table(
        [[Paragraph(f"Week {week} · {WEEK_THEMES.get(week, '')}", WEEK_HEAD)]],
        colWidths=[CONTENT_WIDTH],
        hAlign="LEFT",
    )
    heading.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.8, RULE_STRONG),
    ]))

    rows = []
    for day in days:
        lesson_id = day["lesson_id"]
        day_number = lesson_id.split("d")[1]
        minutes = day.get("duration_seconds", 0) / 60
        rows.append([
            Paragraph(f"D{day_number}", DAY_TAG),
            Paragraph(clean(day["summary"]), DAY_TEXT),
            Paragraph(f"{minutes:.0f} min", DAY_MIN),
        ])

    table = Table(
        rows,
        colWidths=[14 * mm, CONTENT_WIDTH - 14 * mm - 20 * mm, 20 * mm],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]))

    return [heading, Spacer(1, 2 * mm), table]


# ---------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------


def build_story(weeks: dict[int, list[dict]]) -> list:
    story: list = [
        Paragraph("Ironhack AI Engineering", TITLE),
        Spacer(1, 2 * mm),
        Paragraph("COURSE SYLLABUS · 8 WEEKS", EYEBROW),
        Spacer(1, 6 * mm),
        Paragraph(
            "Everything below was taught live and recorded. The AI Learning Copilot "
            "searches all of it — transcripts and course notebooks together — and "
            "answers with the lesson, the notebook cell, and the recording cued to the "
            "second the topic was explained.",
            LEAD,
        ),
        Spacer(1, 8 * mm),

        Paragraph("The eight weeks", SECTION),
        Spacer(1, 3 * mm),
        overview_table(weeks),
        Spacer(1, 9 * mm),

        Paragraph("What the copilot searches", SECTION),
        Spacer(1, 3 * mm),
        stats_strip(weeks),
        Spacer(1, 9 * mm),

        Paragraph("How to use it", SECTION),
        Spacer(1, 2 * mm),
        how_to_use(),
        Spacer(1, 9 * mm),

        Paragraph("Where to find it", SECTION),
        Spacer(1, 3 * mm),
        links_block(),
        Spacer(1, 11 * mm),

        Paragraph("Week by week", SECTION),
        Spacer(1, 1.5 * mm),
        Paragraph(
            "Every session below is indexed and searchable in the copilot.", CAPTION
        ),
        Spacer(1, 6 * mm),
    ]

    for index, (week, days) in enumerate(weeks.items()):
        story.extend(week_block(week, days))
        if index < len(weeks) - 1:
            story.append(Spacer(1, 7 * mm))

    return story


def measure_story(story: list) -> float:
    """Total laid-out height of the story at CONTENT_WIDTH.

    This is why the styles carry no spaceBefore/spaceAfter: those are applied by the
    frame during layout and never appear in `wrap()`, so a style-driven gap would make
    the measured height too small and push the last week onto a second page.

    The flowables are consumed by measuring — `build_story` is called again afterwards
    for the real document rather than reusing these.
    """
    return sum(item.wrap(CONTENT_WIDTH, 1_000_000)[1] for item in story)


def build() -> Path:
    weeks = load_course()

    content_height = measure_story(build_story(weeks))
    # 4pt of slack absorbs rounding in the table row heights. Any more and a blank strip
    # appears above the footer; any less and the last row can tip onto page two.
    page_height = HEAD_HEIGHT + content_height + FOOT_HEIGHT + 4

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(
        str(OUT_PATH),
        pagesize=(PAGE_WIDTH, page_height),
        title="Ironhack AI Engineering — Course Syllabus",
        author="AI Learning Copilot",
        subject="8-week AI Engineering bootcamp syllabus",
    )
    doc.addPageTemplates([
        PageTemplate(
            id="single",
            frames=[Frame(
                SIDE_MARGIN, FOOT_HEIGHT,
                CONTENT_WIDTH, page_height - HEAD_HEIGHT - FOOT_HEIGHT,
                id="body",
                leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            )],
            onPage=draw_furniture,
        )
    ])

    doc.build(build_story(weeks))

    pages = count_pages(OUT_PATH)
    if pages != 1:
        raise SystemExit(
            f"expected a single continuous page, got {pages}. The height measurement "
            f"is out of step with the layout — check for a style with spaceBefore or "
            f"spaceAfter set."
        )

    return OUT_PATH


def count_pages(path: Path) -> int:
    """pypdf is already pinned in requirements.txt for the ingestion side, so the check
    costs no new dependency."""
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)


if __name__ == "__main__":
    output = build()
    size_kb = output.stat().st_size / 1024
    print(f"wrote {output.relative_to(ROOT)} ({size_kb:.0f} KB, one continuous page)")
