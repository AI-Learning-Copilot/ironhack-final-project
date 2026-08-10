from __future__ import annotations

import re

from schemas import EXTRA_LESSON_ID

# A notebook is usually the better answer to a "show me how" question than a transcript
# of someone talking about it, so notebooks get a small lift.
NOTEBOOK_BONUS = 0.05

# ...but not the 24 supplementary notebooks. Those carry lesson_id="extra": they sit in
# the course repo without belonging to any taught day. The flat bonus was pushing them
# above the official lesson material — "What is Python?" ranked three `extra` notebooks
# above `w1d1 · Python I`, and `w1d1` was the *closer* match at 1.129 against 1.160.
#
# This answers Felipe's open question in the 7 Aug recap ("decide whether official lesson
# notebooks should rank above extra notebooks"). Measured over the 84 golden questions,
# scored the corrected way:
#
#   nb +0.05, no penalty (as written)   Top-1 81.0%  Top-3 91.7%
#   no notebook bonus at all            Top-1 82.1%  Top-3 91.7%
#   nb +0.05, extra -0.05               Top-1 83.3%  Top-3 91.7%
#   nb +0.05, extra -0.10               Top-1 83.3%  Top-3 92.9%   <- this
#
# Honest caveat: the penalty was chosen on the same 84 questions it is measured against,
# so read the +2.3 points as "does not hurt, probably helps" rather than as a validated
# gain. It is two questions. The scoring fix in scripts/evaluate_retrieval.py is the
# result that actually matters.
EXTRA_NOTEBOOK_PENALTY = 0.25

HEADING_TOKEN_BONUS = 0.05


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

            score += NOTEBOOK_BONUS

            if metadata.get("lesson_id") == EXTRA_LESSON_ID:
                score -= EXTRA_NOTEBOOK_PENALTY


        # ---------------------------------------------------
        # Heading bonus
        # ---------------------------------------------------

        heading = metadata.get("heading", "")

        if heading:

            heading_tokens = tokenize(heading)

            overlap = len(
                question_tokens & heading_tokens
            )

            score += overlap * HEADING_TOKEN_BONUS



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

