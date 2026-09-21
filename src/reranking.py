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
#
# 2026-09-14: shipped value corrected from 0.25 (never one of the tuned options above)
# to 0.10. Since then, `evaluation/golden_questions.csv` gained a `split` column
# (64 tune / 20 holdout — see scripts/evaluate_retrieval.py) and the STOPWORDS filter
# below was added, so the table above is no longer reproducible as written; re-run
# `python scripts/evaluate_retrieval.py --split=tune` before tuning this again, and
# score any change against `--split=holdout` before trusting it. Full 84 measured this
# same day, after both of those changes and an index rebuild: Top-1 79.8%, Top-3 90.5%,
# Top-5 92.9% (vs the 83.3/92.9/94.0 above) — see the PR that added this note for the
# breakdown of how much of that gap is index-rebuild noise vs. the stopword fix.
EXTRA_NOTEBOOK_PENALTY = 0.10

HEADING_TOKEN_BONUS = 0.05

# Function words in both course languages (English lectures, Spanish questions). Without
# this, a heading sharing only "what is the" with the question earned the same overlap
# bonus as one sharing the actual topic — cheapening the signal the bonus exists for.
STOPWORDS = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "in", "on", "at", "to", "of", "for", "and", "or", "but", "with", "as",
        "by", "from", "that", "this", "these", "those", "it", "its", "what",
        "how", "why", "when", "where", "who", "which", "do", "does", "did",
        "can", "could", "would", "should", "will", "shall", "may", "might",
        "must", "have", "has", "had", "not", "no", "so", "if", "than", "then",
        "there", "here", "we", "you", "i", "he", "she", "they",
        "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o",
        "pero", "con", "de", "del", "en", "por", "para", "que", "qué", "cómo",
        "cuándo", "dónde", "quién", "cuál", "es", "son", "era", "eran", "ser",
        "estar", "sí", "se", "su", "sus", "lo", "le", "les", "al", "a",
    }
)


def tokenize(text: str) -> set[str]:
    """
    Lowercase tokenization used for simple keyword matching.

    Includes accented Latin letters (à-ö, ø-ÿ) so Spanish words survive whole —
    without them "explicación" split into "explicaci" + "n" at the "ó", and a Spanish
    question could never match a heading on its own real words.
    """

    return set(
        re.findall(
            r"[a-z0-9_à-öø-ÿ]+",
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
                (question_tokens - STOPWORDS) & (heading_tokens - STOPWORDS)
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

