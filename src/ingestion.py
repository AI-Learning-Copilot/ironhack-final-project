"""Load Loom transcripts (.vtt) and lesson metadata (.info.json) into cues.

This module produces `Cue(start_seconds, text)` lists per recording. `chunking.py` turns
those into chunks.

Two things happen here that are easy to overlook and expensive to skip:

1. Speaker tags (`<v 0>...</v>`) are stripped. They appear once per file and would
   otherwise end up inside chunk text and get embedded.
2. Auto-caption mistakes on course vocabulary are corrected. This is not cosmetic —
   "RAC" appears 61 times in this corpus against 17 for "RAG", so without the fix a
   student asking about RAG misses roughly four fifths of the material on it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import webvtt

CAPTIONS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "captions"

# Auto-caption errors on course vocabulary. Applied case-insensitively, whole words only.
# Counts are from the real corpus as of 2026-08-05.
#
# Add to this whenever you spot a new one — it is the cheapest retrieval win available.
JARGON_FIXES: dict[str, str] = {
    r"\bRAC\b": "RAG",                 # 61 occurrences, vs 17 spelled correctly
    r"\blang chain\b": "LangChain",    # 5
    r"\bline chain\b": "LangChain",    # 2
    r"\bkarma\b": "Chroma",            # 3 — only ever appears in a vector-db context here
    r"\bhugging face\b": "HuggingFace",
    r"\bnum py\b": "NumPy",
    r"\bpie torch\b": "PyTorch",
    r"\bjupiter\b": "Jupyter",
}

_SPEAKER_TAG = re.compile(r"</?v[^>]*>")
_WHITESPACE = re.compile(r"\s+")
_FILENAME = re.compile(r"^(?P<lesson_id>w\d+d\d+)__(?P<loom_id>[0-9a-f]{32})$")

# --- classmate anonymisation (task C1b) -------------------------------------
#
# The repo is public and the committed index stores chunk text, so classroom
# conversation directed at named people would be published. Those people never agreed
# to that.
#
# We scrub DIRECT ADDRESS, not names. A global find-and-replace on a roster would
# corrupt the teaching content, because the instructor uses the same first names as
# examples:
#
#   "x will have the value Alice"          <- Python loop demo, must survive
#   "those numbers, Alice, Bob, Charlie"   <- list example, must survive
#   "Thanks, Kriti. You were writing to me" <- real classmate, must go
#
# Matching on the greeting/thanks that precedes a name separates the two cleanly, and
# leaves anything used as data or as an example untouched.
# The greeting is case-insensitive; the NAME deliberately is not. Making the whole
# pattern case-insensitive would match ordinary words — "thanks for", "sorry but" —
# and quietly delete real text.
_ADDRESS = re.compile(
    r"\b((?i:hi|hey|hello|thanks|thank you|sorry|bye|bye-bye|welcome back|good morning|"
    r"good afternoon|good evening|see you|congrats|congratulations|exactly|correct|"
    r"perfect|absolutely|indeed))([,\s]+)([A-Z][a-z]{2,14})\b"
)

# "Antonio, David, Kriti, you can use breakout room two" — a roster read aloud.
_ROSTER = re.compile(
    r"\b([A-Z][a-z]{2,14}(?:\s*,\s*[A-Z][a-z]{2,14}){1,6})\s*,\s*(you|please)\b"
)

ANON = "[student]"


@dataclass(frozen=True)
class Cue:
    start_seconds: int
    text: str


@dataclass(frozen=True)
class Recording:
    lesson_id: str
    loom_id: str
    title: str          # "RAG II - Indexing"
    segment: str        # "b"
    transcript_source: str
    cues: list[Cue]

    @property
    def duration_seconds(self) -> int:
        return self.cues[-1].start_seconds if self.cues else 0


def anonymise(text: str) -> str:
    """Replace names used as direct address. Names used as data are left alone."""
    text = _ADDRESS.sub(lambda m: f"{m.group(1)}{m.group(2)}{ANON}", text)
    return _ROSTER.sub(lambda m: f"{ANON}, {m.group(2)}", text)


def clean_text(text: str) -> str:
    """Strip speaker tags, collapse whitespace, fix jargon, anonymise classmates."""
    text = _SPEAKER_TAG.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    for pattern, replacement in JARGON_FIXES.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return anonymise(text)


def timestamp_to_seconds(stamp: str) -> int:
    """'00:14:32.570' -> 872. Floors, so a citation never points past the moment."""
    hours, minutes, seconds = stamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(float(seconds))


def parse_title(raw_title: str) -> tuple[str, str]:
    """'AI 2026.06 - w7d2 - b - RAG II - Indexing' -> ('RAG II - Indexing', 'b').

    The topic itself contains ' - ', which is why we rejoin the tail rather than taking
    a fixed field.
    """
    parts = [p.strip() for p in raw_title.split(" - ")]
    if len(parts) < 4:
        return raw_title.strip(), ""
    return " - ".join(parts[3:]), parts[2]


def load_recording(vtt_path: Path) -> Recording:
    """One .vtt plus its sibling .info.json -> a Recording."""
    stem = vtt_path.name.removesuffix(".en.vtt")
    match = _FILENAME.match(stem)
    if not match:
        raise ValueError(f"unexpected caption filename: {vtt_path.name}")

    info_path = vtt_path.with_name(f"{stem}.info.json")
    raw_title = json.loads(info_path.read_text())["title"] if info_path.exists() else stem
    title, segment = parse_title(raw_title)

    cues: list[Cue] = []
    for caption in webvtt.read(str(vtt_path)):
        text = clean_text(caption.text)
        if text:
            cues.append(Cue(timestamp_to_seconds(caption.start), text))

    return Recording(
        lesson_id=match["lesson_id"],
        loom_id=match["loom_id"],
        title=title,
        segment=segment,
        transcript_source="loom",
        cues=cues,
    )


# The dev index (task C1c). Deliberately NOT "the first five lessons" — week 1 is Python
# basics, which tells us nothing about whether retrieval works on the material we will
# actually demo. These five span the topics a student is most likely to ask about, and
# include two that are easy to confuse (w4d3 embeddings vs w7d2 RAG) so we can see
# whether the retriever picks the right one.
DEV_LESSONS = ("w1d4", "w4d3", "w7d1", "w7d2", "w8d1")


def load_all(
    captions_dir: Path = CAPTIONS_DIR,
    limit_lessons: int | None = None,
    lessons: tuple[str, ...] | list[str] | None = None,
) -> list[Recording]:
    """Every recording that has captions, sorted by lesson then segment.

    `lessons` selects specific lesson days — pass `DEV_LESSONS` for the dev index.
    `limit_lessons` takes the first N lesson days instead.
    """
    paths = sorted(captions_dir.glob("*.en.vtt"))
    if not paths:
        raise FileNotFoundError(
            f"no captions in {captions_dir}. Run: bash data/raw/fetch_captions.sh"
        )

    recordings = [load_recording(p) for p in paths]
    recordings.sort(key=lambda r: (r.lesson_id, r.segment))

    if lessons is not None:
        wanted = set(lessons)
        missing = wanted - {r.lesson_id for r in recordings}
        if missing:
            raise ValueError(f"no captions for lesson(s): {sorted(missing)}")
        recordings = [r for r in recordings if r.lesson_id in wanted]
    elif limit_lessons is not None:
        keep = sorted({r.lesson_id for r in recordings})[:limit_lessons]
        recordings = [r for r in recordings if r.lesson_id in keep]
    return recordings


def build_lessons_index(recordings: list[Recording]) -> dict:
    """Task C2: lessons.json, derived from the Loom titles rather than typed by hand."""
    lessons: dict[str, dict] = {}
    for r in recordings:
        lesson = lessons.setdefault(
            r.lesson_id, {"lesson_id": r.lesson_id, "recordings": []}
        )
        lesson["recordings"].append(
            {
                "loom_id": r.loom_id,
                "segment": r.segment,
                "title": r.title,
                "duration_seconds": r.duration_seconds,
                "cues": len(r.cues),
            }
        )
    for lesson in lessons.values():
        lesson["title"] = " · ".join(r["title"] for r in lesson["recordings"])
        lesson["duration_seconds"] = sum(r["duration_seconds"] for r in lesson["recordings"])
    return lessons


if __name__ == "__main__":
    recordings = load_all()
    total_cues = sum(len(r.cues) for r in recordings)
    hours = sum(r.duration_seconds for r in recordings) / 3600
    print(f"{len(recordings)} recordings · {total_cues:,} cues · {hours:.1f} hours")
    for r in recordings[:4]:
        print(f"  {r.lesson_id} {r.segment} · {r.title[:46]:<46} {len(r.cues):>4} cues")
