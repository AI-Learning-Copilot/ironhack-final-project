"""Turn transcript cues into chunks ready for Chroma.

The rule that matters: **a chunk's timestamp is the start time of its first cue.** We
never split inside a cue, because a cue is the smallest unit we have a real timestamp
for — splitting one would mean guessing where in those two seconds the text fell.

Chunk size is timestamp precision. We cite the start of a chunk, so a four-minute chunk
sends the student four minutes before the answer. 1000 characters is roughly 65 seconds
of lecture speech: long enough to hold one complete idea, short enough that the citation
still lands somewhere useful.
"""

from __future__ import annotations

from ingestion import Cue, Recording
from schemas import VIDEO_CHUNK_OVERLAP, VIDEO_CHUNK_SIZE, video_chunk


def _overlap_tail(cues: list[Cue], overlap_chars: int) -> list[Cue]:
    """The last few cues of a chunk, totalling about `overlap_chars`.

    Overlap is carried as whole cues rather than characters so the next chunk still
    starts at a real timestamp.
    """
    tail: list[Cue] = []
    length = 0
    for cue in reversed(cues):
        if length >= overlap_chars:
            break
        tail.insert(0, cue)
        length += len(cue.text) + 1
    return tail


def chunk_cues(
    cues: list[Cue],
    chunk_size: int = VIDEO_CHUNK_SIZE,
    overlap: int = VIDEO_CHUNK_OVERLAP,
) -> list[tuple[int, str]]:
    """Cues -> [(start_seconds, text)], never splitting inside a cue."""
    chunks: list[tuple[int, str]] = []
    current: list[Cue] = []
    length = 0

    for cue in cues:
        # A single cue longer than the target still becomes its own chunk rather than
        # being cut — its timestamp is the only honest one we have.
        if current and length + len(cue.text) + 1 > chunk_size:
            chunks.append((current[0].start_seconds, " ".join(c.text for c in current)))
            current = _overlap_tail(current, overlap)
            length = sum(len(c.text) + 1 for c in current)

        current.append(cue)
        length += len(cue.text) + 1

    if current:
        chunks.append((current[0].start_seconds, " ".join(c.text for c in current)))
    return chunks


def contextual_header(recording: Recording) -> str:
    """A one-line topic label prepended to every chunk before embedding.

    Without this, a chunk is raw spoken transcript and nothing else, so a topic query
    has to match rambling speech rather than the subject. That fails exactly where it
    matters most: "how does CLIP work" returned w7d1 LangChain, while the lesson
    actually titled "Multimodal Search Engine with CLIP" — 99 chunks, 14 of them
    mentioning CLIP — did not appear at all, because the words "Multimodal", "Search"
    and "CLIP" existed only in metadata.

    The header is part of the embedded text on purpose. It also helps the model, which
    then sees which lesson an excerpt came from without being told separately.
    """
    return f"[{recording.lesson_id} · {recording.title}]"


def chunk_recording(recording: Recording) -> list[dict]:
    """A Recording -> chunks in the frozen schema, ready for Chroma."""
    header = contextual_header(recording)
    return [
        video_chunk(
            f"{header}\n{text}",
            lesson_id=recording.lesson_id,
            lesson_title=recording.title,
            loom_id=recording.loom_id,
            start_seconds=start,
            segment=recording.segment,
            transcript_source=recording.transcript_source,
        )
        for start, text in chunk_cues(recording.cues)
    ]


def chunk_all(recordings: list[Recording]) -> list[dict]:
    return [chunk for r in recordings for chunk in chunk_recording(r)]


if __name__ == "__main__":
    from ingestion import load_all
    from schemas import build_citation

    recordings = load_all()
    chunks = chunk_all(recordings)
    sizes = [len(c["text"]) for c in chunks]

    print(f"{len(recordings)} recordings -> {len(chunks):,} chunks")
    print(f"chars: min {min(sizes)} · median {sorted(sizes)[len(sizes)//2]} · max {max(sizes)}")

    sample = next(c for c in chunks if c["metadata"]["lesson_id"] == "w7d2")
    print("\nsample chunk")
    print(" ", build_citation(sample["metadata"])["label"])
    print(" ", build_citation(sample["metadata"])["url"])
    print(" ", sample["text"][:180].strip(), "...")
