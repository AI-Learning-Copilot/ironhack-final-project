"""Build the Chroma index.

Run as a script:

    python src/embeddings.py --dev     # 5 topic-spanning lessons, for agent development
    python src/embeddings.py --full    # all 120 recordings, the one we ship

Why two indexes: the full build is the artefact we commit and deploy, but waiting for it
blocks agent work. The dev index takes about a minute and is enough to develop C4/C5
against. Only the full index is committed — see .gitignore.

Embeddings use dimensions=512 rather than the default 1536. At 1536 the persisted index
would be roughly 75 MB and GitHub warns at 50 MB per file; at 512 it is a fraction of
that with no measurable retrieval loss at this corpus size.
"""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from chunking import chunk_all
from ingestion import DEV_LESSONS, load_all
from notebooks import chunk_all_notebooks
from schemas import COLLECTION_NAME, EMBED_DIMENSIONS, EMBED_MODEL

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_INDEX = REPO_ROOT / "index" / "dev"
FULL_INDEX = REPO_ROOT / "index" / "full"

load_dotenv(REPO_ROOT / ".env")


def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=EMBED_MODEL, dimensions=EMBED_DIMENSIONS)


def build_index(chunks: list[dict], persist_dir: Path, batch_size: int = 256) -> Chroma:
    """Embed chunks and persist them. Replaces whatever was there before.

    Rebuilding from scratch rather than upserting keeps the index a pure function of the
    transcripts — no stale chunks surviving a change to the chunker or the jargon table.
    """
    if persist_dir.exists():
        shutil.rmtree(persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(persist_dir),
    )

    started = time.time()
    for offset in range(0, len(chunks), batch_size):
        batch = chunks[offset : offset + batch_size]
        store.add_texts(
            texts=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
        done = min(offset + batch_size, len(chunks))
        print(f"  embedded {done:>5,}/{len(chunks):,}", end="\r", flush=True)

    elapsed = time.time() - started
    print(
        f"\n  {len(chunks):,} chunks · {elapsed:.0f}s · "
        f"{_size_mb(persist_dir):.1f} MB · {persist_dir}"
    )
    return store


def _size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


# DO NOT prune `embeddings_queue` to save space.
#
# It looks like a free ~25% win: the table is Chroma's write-ahead log and holds a second
# copy of every embedding, and deleting it + VACUUM took the dev index from 9.6 MB to
# 6.4 MB. It also appears to work, because the Chroma object still in memory keeps the
# HNSW graph loaded and keeps answering queries.
#
# In a fresh process it returns ZERO results. `collection.count()` still reports 726 and
# data_level0.bin is still 2.1 MB, but the segment's sequence tracking is tied to that
# queue, so the graph never loads. An index that reports the right size and silently
# retrieves nothing is the worst possible failure here — it would look fine locally and
# return "I don't know" to every question in the deployed app.
#
# If the index size becomes a real problem, reduce EMBED_DIMENSIONS instead.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dev", action="store_true", help=f"only {', '.join(DEV_LESSONS)}")
    group.add_argument("--full", action="store_true", help="all 120 recordings")
    parser.add_argument("--no-notebooks", action="store_true",
                        help="video only, for comparing retrieval with and without")
    args = parser.parse_args()

    if args.dev:
        recordings = load_all(lessons=DEV_LESSONS)
        target = DEV_INDEX
    else:
        recordings = load_all()
        target = FULL_INDEX

    chunks = chunk_all(recordings)
    print(f"{len(recordings)} recordings -> {len(chunks):,} video chunks")

    # Notebooks go into the SAME collection, discriminated by source_type. That is the
    # whole point of the single-collection decision: one question can return both the
    # minute of the recording and the notebook cell that demonstrates it.
    if not args.no_notebooks:
        notebook_chunks = chunk_all_notebooks()
        print(f"{len({c['metadata']['notebook'] for c in notebook_chunks})} notebooks "
              f"-> {len(notebook_chunks):,} notebook chunks")
        chunks += notebook_chunks

    print(f"total {len(chunks):,} chunks")
    build_index(chunks, target)


if __name__ == "__main__":
    main()
