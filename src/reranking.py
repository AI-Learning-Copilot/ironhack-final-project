from __future__ import annotations

import re


def tokenize(text: str) -> set[str]:
    """
    Lowercase tokenization used for simple keyword matching.
    """

    return set(
        re.findall(
            r"[a-zA-Z0-9_]+",
            text.lower(),
        )
    )


def rerank_results(
    question: str,
    results: list,
):
    """
    Re-rank Chroma search results using lightweight heuristics.
    """

    question_tokens = tokenize(question)

    scored = []

    for doc, distance in results:

        metadata = doc.metadata

        score = -distance

        # ---------------------------------------------------
        # Notebook bonus
        # ---------------------------------------------------

        if metadata.get("source_type") == "notebook":
            score += 0.05


        # ---------------------------------------------------
        # Heading bonus
        # ---------------------------------------------------

        heading = metadata.get("heading", "")

        if heading:

            heading_tokens = tokenize(heading)

            overlap = len(
                question_tokens & heading_tokens
            )

            score += overlap * 0.05



        # ---------------------------------------------------
        # Keep EVERY result
        # ---------------------------------------------------

        scored.append(
            (
                score,
                doc,
                distance,
            )
        )

    scored.sort(
        reverse=True,
        key=lambda x: x[0],
    )

    return [
        (doc, distance)
        for _, doc, distance in scored
    ]

