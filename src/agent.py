"""The learning copilot agent.

    from agent import Copilot
    copilot = Copilot()
    copilot.ask("what is RAG?")            # -> {"answer": ..., "citations": [...]}
    copilot.ask("explain that more simply") # memory makes "that" resolve

`ask()` returns exactly the shape frozen in docs/SCHEMA.md, so the Streamlit app can
swap its mock fixture for a Copilot with no other change.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.memory import ConversationSummaryBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from schemas import CHAT_MODEL, REFUSAL_MARKERS, build_response
from tools import CitationCollector, SearchScope, SourceLog, make_tools

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL = CHAT_MODEL

# The default summariser rewrites the conversation as flowing prose, and prose is where
# the useful details die. Measured on a real nine-turn conversation, its output kept
# "week 4 day 3" but contained no lesson id and no timestamp at all — it wrote the
# phrase "at specific timestamps" in place of the numbers.
#
# This version asks for a bullet list and names the two things that must survive
# verbatim. It is a genuine improvement over the default, but it is still a prompt, so
# it is a best effort: `SourceLog` is the guarantee, and it is kept in code precisely
# because a model cannot be relied on to preserve exact digits.
SUMMARY_PROMPT = ChatPromptTemplate.from_template(
    """Condense the conversation below into a compact bulleted record.

Rules:
- One bullet per topic discussed, newest last.
- Copy lesson ids (like w7d2) and timestamps (like 12:28) EXACTLY as they appear. \
Never replace a number with a description of it, and never write "at specific \
timestamps" or similar.
- Keep what the student asked and what they were told. Drop pleasantries.
- If the existing summary already has a bullet for a topic, update it rather than \
adding a second one.

Existing summary:
{summary}

New lines of conversation:
{new_lines}

Updated summary:"""
)

SYSTEM_PROMPT = """You are the AI Learning Copilot for an Ironhack AI Engineering \
bootcamp. You answer questions using ONLY what was said in the recorded lessons.

You have seven tools. Pick ONE per turn based on what the student is actually asking for:

- search_course_material — a factual lookup ("what is X", "how does X work").
- find_notebooks — the student wants a NOTEBOOK, the code, or a demo file.
- find_timestamp — WHERE/WHEN something was covered, not what it means.
- explain_concept — the student explicitly asks you to explain/teach something, usually \
wanting a simpler or more intuitive framing than a plain lookup.
- generate_quiz — the student asks to be quizzed or tested.
- lesson_index — "what did we cover in week X" / "what lessons exist" — a table of \
contents question, not a concept question.
- recall_sources — the student refers BACK to something you already cited ("that \
timestamp you gave me", "the video from before", "which lesson was that again"). Use \
this instead of searching again: search returns what ranks best now, not what you \
actually showed them earlier.

How to answer:
- Pass the student's FULL question to the tool, close to their own wording. Never \
shorten it to a keyword or an acronym. The tools embed what you send and compare it \
against lecture transcripts, where a lone term matches almost anything: searching \
"CLIP" returns the LangChain recap, searching "How does CLIP work?" returns the CLIP \
lesson. If a search comes back about the wrong topic, your query was too short — \
re-send the fuller question rather than concluding it was not covered.
- Always call a tool before answering a question about course content. Never answer \
from your own knowledge of the subject, even when you are confident. The student wants \
to know what THEIR instructor said, not what is generally true.
- Call at most one tool per turn. Only call a second if the first came back empty or \
was clearly about the wrong thing.
- EXCEPTION — simplification follow-ups: if the student asks you to simplify, clarify, \
or re-explain something you already covered THIS CONVERSATION, do NOT call any tool, \
including explain_concept. Re-explain from what is already in the conversation instead. \
    Example — turn 1: "What is a vector database?" -> you call search_course_material, \
    answer with citations. Turn 2: "explain that more simply" -> you call NO tool at \
    all, you just rephrase your own previous answer using an analogy.
- If a tool returns NO_RESULTS, OR the results it did return are clearly not actually \
about what was asked, say plainly that it was not covered. Do not fall back on general \
knowledge and do not apologise at length. Use almost exactly this template, translated \
to the student's language: "That wasn't covered in the course." (Spanish example: \
"Eso no fue cubierto en el curso.") Using this near-exact wording matters — it is how \
the citations get cleaned up afterwards.
- For compound or mixed questions, evaluate EACH part of the student's question against \
the tool results. Answer only the parts that are supported by the course material. If \
one part is supported and another is not, answer the supported part normally and say \
plainly that the unsupported part was not covered in the course. NEVER fill an \
unsupported part using your own general knowledge, even if you know the answer. Every \
factual claim in your answer must be supported by the tool results or by information \
already established from course material earlier in this conversation.
- generate_quiz's output is already formatted for the student — relay it as returned, \
do not compress it into prose.
- NEVER call the same tool with the same (or near-identical) arguments twice. If a \
result looks wrong or irrelevant, that IS your answer: the topic was not covered. \
Retrying the same search will return the same thing again.

How to write:
- Answer in the SAME LANGUAGE the student used. The recordings are in English; translate \
your explanation, never the quotes.
- Refer to lessons the way the transcript does: "in week 7 day 2". Do NOT write out URLs, \
timestamps, or markdown links — those are attached automatically, and anything you type \
by hand will be wrong.
-- Be direct and concrete. Prefer the instructor's own terminology, framing, and examples
over a textbook definition. When the retrieved course material uses a specific technical
term for an important concept, preserve that terminology in the answer rather than
replacing it with a generic synonym. For key technical concepts, explicitly use the
technical terms that appear in the retrieved material when they are relevant to the
question."""


class Copilot:
    """One conversation. Hold on to the instance — the memory lives in it."""

    def __init__(self, model: str = MODEL, verbose: bool = False) -> None:
        self.collector = CitationCollector()
        # The UI narrows this before a turn; empty means the whole course. Held on the
        # Copilot so every tool built below shares the same instance.
        self.scope = SearchScope()
        # Exact ids and timestamps for everything cited this conversation, held outside
        # the LLM's memory so summarisation cannot destroy them.
        self.sources = SourceLog()
        llm = ChatOpenAI(
            model=model,
            temperature=0,
        )
        # Same llm instance reused inside explain_concept/generate_quiz — one model
        # client per Copilot, not two.
        self.tools = make_tools(
            self.collector, llm=llm, scope=self.scope, sources=self.sources
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder("chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ]
        )

        # Summary-buffer rather than a plain buffer: lecture answers are long, and a
        # raw transcript of the conversation would eat the context window within a few
        # turns. This keeps recent turns verbatim and summarises what falls out.
        self.memory = ConversationSummaryBufferMemory(
            llm=llm,
            # 2000, up from 800. Measured: at 800 the buffer overflows on turn 6, and
            # compression destroys exactly what students ask for — lesson ids and
            # timestamps do not survive it, only the prose "week 4 day 3" does.
            #
            # The cost of holding more is small and known. The buffer is resent on every
            # model call, so a full 2000-token buffer adds ~$0.0003 per call against a
            # measured ~$0.0008 per question. That buys roughly turn 6 to turn 15 before
            # anything is lost at all.
            #
            # Not unlimited: an uncapped transcript would grow
            # the per-call bill without bound and eventually crowd out the retrieved
            # course material, which is the part that makes the answer correct.
            max_token_limit=2000,
            prompt=SUMMARY_PROMPT,
            memory_key="chat_history",
            input_key="input",
            output_key="output",
            return_messages=True,
        )

        self.executor = AgentExecutor(
            agent=create_openai_tools_agent(llm, self.tools, prompt),
            tools=self.tools,
            memory=self.memory,
            # Without a cap the agent will occasionally search five times for one
            # question, which triples latency for no gain in answer quality.
            max_iterations=4,
            early_stopping_method="force",
            verbose=verbose,
            return_intermediate_steps=True,
        )

    # LangChain's own message when max_iterations is hit — not a real answer, must
    # never reach the student verbatim and must never carry citations. Seen when a
    # borderline query (e.g. "quantum" scoring close to "quantization") leaves the model
    # unable to settle on either a real answer or a clean refusal within the iteration cap.
    _ITERATION_LIMIT_MESSAGE = "agent stopped due to"

    def ask(self, question: str) -> dict:
        """Answer one question. Returns the frozen {answer, citations} shape."""
        self.collector.reset()
        result = self.executor.invoke({"input": question})
        answer = result["output"]
        lowered = answer.lower()

        if self._ITERATION_LIMIT_MESSAGE in lowered:
            return build_response(self._not_covered(), [])

        # If the model says it wasn't covered, we show no sources — whatever the
        # retriever thought. A distance threshold alone cannot catch this: "quantum
        # error correction" scores 1.04 against the QLoRA and Quantization lessons,
        # because the embeddings see "quantum" and "quantization" as near neighbours.
        # Drop citations only for a full refusal. A mixed question may contain a
        # supported answer plus an explicit refusal for the unsupported part; in
        # that case the citations for the supported material must remain visible.
        is_refusal = any(marker in lowered for marker in REFUSAL_MARKERS)

        if is_refusal:
            short_answer = answer.strip().lower()

            # Full refusals are deliberately short ("That wasn't covered in the
            # course."). Longer answers containing a refusal marker are partial
            # refusals and may still have valid course-grounded content.
            if len(short_answer.split()) <= 20:
                # A refusal under a scope means "not in THIS lesson", which is a very
                # different fact from "not in the course" — the student picked the
                # filter and deserves to know the filter is why. Rewrite the model's
                # generic wording rather than trying to prompt it into the distinction,
                # which is unreliable and would also have to survive translation.
                if self.scope.active:
                    return build_response(self._not_covered(), [])
                return build_response(answer, [])

        response = build_response(answer, self.collector.metadatas)
        # Log after build_response, not from the raw collector: this stores exactly the
        # citations the student was shown, deduplicated and labelled the same way. A
        # refusal reaches one of the returns above and is never logged, so "the video
        # you mentioned" can never resolve to something we declined to cite.
        self.sources.record(question, response["citations"])
        return response

    def _not_covered(self) -> str:
        """The refusal wording, which depends on whether a scope narrowed the search."""
        if self.scope.active:
            return (
                f"That wasn't covered in {self.scope.label()}. "
                f"It may still be covered elsewhere in the course — "
                f"turn the lesson filter off to search all 8 weeks."
            )
        return "That wasn't covered in the course."

    def tools_used(self, result: dict | None = None) -> list[str]:
        """Names of the tools called on the last turn — used by the memory demo."""
        steps = (result or {}).get("intermediate_steps", [])
        return [action.tool for action, _ in steps]

    def reset(self) -> None:
        self.memory.clear()
        self.collector.reset()
        # Otherwise "the video you mentioned earlier" would resolve to the previous
        # conversation after the student pressed New conversation.
        self.sources.clear()


if __name__ == "__main__":
    import sys

    copilot = Copilot(verbose="-v" in sys.argv)
    questions = [a for a in sys.argv[1:] if not a.startswith("-")] or [
        "what is RAG?",
        "explain that more simply",
        "where was cosine similarity covered?",
    ]
    for question in questions:
        print(f"\n--- {question}")
        response = copilot.ask(question)
        print(response["answer"])
        for citation in response["citations"]:
            print(f"    {citation['label']}\n    {citation['url']}")
