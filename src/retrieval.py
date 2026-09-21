"""Similarity search over the Chroma index.

This is the layer the agent's tools sit on. It returns LangChain `Document`s whose
metadata is exactly the frozen schema, so `build_citation()` works on anything that
comes out of here.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from embeddings import DEV_INDEX, FULL_INDEX, get_embeddings
from schemas import COLLECTION_NAME
from reranking import rerank_results

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def get_store(persist_dir: Path | None = None) -> Chroma:
    """Open an index for reading.

    Defaults to the full index, falling back to the dev index.

    Cached: without this, every call opened a fresh Chroma client AND a fresh
    embeddings client — a single quiz click runs up to 8 searches, so that was up to
    16 unnecessary client constructions for what should be one persistent connection.
    """

    if persist_dir is None:
        if FULL_INDEX.exists():
            persist_dir = FULL_INDEX
        else:
            persist_dir = DEV_INDEX
            # Silent here meant production would quietly answer "not covered" for 27
            # of the course's 32 lessons — the dev index only has 5. This must never
            # happen in production; it's expected only for local agent development.
            logger.warning(
                "FULL INDEX NOT FOUND at %s — falling back to the 5-lesson DEV INDEX "
                "at %s. Questions about the other 27 lessons will incorrectly answer "
                "'not covered'. Build the full index: python src/embeddings.py --full",
                FULL_INDEX,
                DEV_INDEX,
            )

    if not Path(persist_dir).exists():
        raise FileNotFoundError(
            f"no index at {persist_dir}. "
            "Build one: python src/embeddings.py --dev"
        )

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(persist_dir),
    )


def search(
    query: str,
    k: int = 5,
    *,
    source_type: str | None = None,
    lesson_id: str | None = None,
    store: Chroma | None = None,
) -> list[Document]:
    """Top-k chunks for a query, optionally filtered."""

    store = store or get_store()

    clauses = []

    if source_type:
        clauses.append({"source_type": source_type})

    if lesson_id:
        clauses.append({"lesson_id": lesson_id})

    where = None

    if len(clauses) == 1:
        where = clauses[0]
    elif clauses:
        where = {"$and": clauses}

    return store.similarity_search(
        query,
        k=k,
        filter=where,
    )


def search_with_scores(
    query: str,
    k: int = 5,
    store: Chroma | None = None,
    *,
    source_type: str | None = None,
    lesson_id: str | None = None,
    week: int | None = None,
):
    """Same as search(), but also returns Chroma distances.

    Supports filtering by source type, lesson and week.

    Retrieval fetches extra candidates, applies a lightweight reranker,
    and returns the final Top-k results.
    """

    store = store or get_store()

    clauses = []

    if source_type:
        clauses.append({"source_type": source_type})

    if lesson_id:
        clauses.append({"lesson_id": lesson_id})

    if week is not None:
        clauses.append({"week": week})

    where = None

    if len(clauses) == 1:
        where = clauses[0]
    elif clauses:
        where = {"$and": clauses}

    # Retrieve more candidates than requested
    results = store.similarity_search_with_score(
        query,
        k=max(k * 2, 10),
        filter=where,
    )

    # Apply reranking
    results = rerank_results(
        question=query,
        results=results,
    )

    # Return only the requested number of results
    return results[:k]


if __name__ == "__main__":
    import sys

    from schemas import build_citation

    query = (
        " ".join(sys.argv[1:])
        or "what is RAG and why do we need it"
    )

    print(f"query: {query!r}\n")

    for doc, score in search_with_scores(
        query,
        k=5,
    ):
        citation = build_citation(doc.metadata)

        print(f"[{score:.3f}] {citation['label']}")
        print(f"    {citation['url']}")
        print(f"    {doc.page_content[:120].strip()}...\n")