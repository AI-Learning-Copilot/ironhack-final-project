"""Similarity search over the Chroma index.

This is the layer the agent's tools sit on. It returns LangChain `Document`s whose
metadata is exactly the frozen schema, so `build_citation()` works on anything that
comes out of here.
"""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from embeddings import DEV_INDEX, FULL_INDEX, get_embeddings
from schemas import COLLECTION_NAME


def get_store(persist_dir: Path | None = None) -> Chroma:
    """Open an index for reading.

    Defaults to the full index, falling back to the dev index — so agent work runs
    against whatever exists locally without a code change.
    """
    if persist_dir is None:
        persist_dir = FULL_INDEX if FULL_INDEX.exists() else DEV_INDEX

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
    """Top-k chunks for a query, optionally filtered.

    `source_type` and `lesson_id` are what let one collection behave like
    several—the reason we did not split video and notebook chunks into
    separate collections.
    """
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

    Merge note (7 Aug): Felipe and Casilda both added filtering here on the same day —
    `source_type` from one side, `week` from the other. This is the union; dropping
    either breaks a caller. `source_type` lets a caller ask for only videos or only
    notebooks; `week` and `lesson_id` are what the UI scope control sets.

    All three filter **inside** the search rather than afterwards. Post-filtering a
    global top-k is not the same thing: the five nearest chunks across the whole corpus
    almost never share one lesson day, so filtering after the fact usually returned
    nothing at all.

    `store` stays positional — tools.py and the notebook pass it that way.
    """
    store = store or get_store()

    clauses = []

    if source_type:
        clauses.append({"source_type": source_type})

    if lesson_id:
        clauses.append({"lesson_id": lesson_id})

    if week:
        clauses.append({"week": week})

    where = None

    if len(clauses) == 1:
        where = clauses[0]
    elif clauses:
        where = {"$and": clauses}

    return store.similarity_search_with_score(
        query,
        k=k,
        filter=where,
    )


if __name__ == "__main__":
    import sys

    from schemas import build_citation

    query = " ".join(sys.argv[1:]) or "what is RAG and why do we need it"

    print(f"query: {query!r}\n")

    for doc, score in search_with_scores(query, k=5):
        citation = build_citation(doc.metadata)

        print(f"  [{score:.3f}] {citation['label']}")
        print(f"          {citation['url']}")
        print(f"          {doc.page_content[:120].strip()}...\n")
