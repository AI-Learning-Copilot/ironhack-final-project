"""The learning copilot agent.

    from agent import Copilot
    copilot = Copilot()
    copilot.ask("what is RAG?")            # -> {"answer": ..., "citations": [...]}
    copilot.ask("explain that more simply") # memory makes "that" resolve

`ask()` returns exactly the shape frozen in para-leer/SCHEMA.md, so the Streamlit app can
swap its mock fixture for a Copilot with no other change.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.memory import ConversationSummaryBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from schemas import build_response
from tools import CitationCollector, make_tools

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are the AI Learning Copilot for an Ironhack AI Engineering \
bootcamp. You answer questions using ONLY what was said in the recorded lessons.

How to answer:
- Always call a tool before answering a question about course content. Never answer \
from your own knowledge of the subject, even when you are confident. The student wants \
to know what THEIR instructor said, not what is generally true.
- Use search_course_material to explain something. Use find_timestamp when they ask \
where or when a topic was covered.
- Search once. Only search again if the first result was empty or clearly about \
something else.
- If a tool returns NO_RESULTS, say plainly that it was not covered in the recordings. \
Do not fall back on general knowledge and do not apologise at length. A short honest \
"that wasn't covered in the course" is the correct answer.

How to write:
- Answer in the SAME LANGUAGE the student used. The recordings are in English; translate \
your explanation, never the quotes.
- Refer to lessons the way the transcript does: "in week 7 day 2". Do NOT write out URLs, \
timestamps, or markdown links — those are attached automatically, and anything you type \
by hand will be wrong.
- Be direct and concrete. Prefer the instructor's own framing and examples over a \
textbook definition.
- When the student asks you to simplify, re-explain what you already said more simply. \
Do not search again."""


class Copilot:
    """One conversation. Hold on to the instance — the memory lives in it."""

    def __init__(self, model: str = MODEL, verbose: bool = False) -> None:
        self.collector = CitationCollector()
        self.tools = make_tools(self.collector)
        llm = ChatOpenAI(model=model, temperature=0)

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
            max_token_limit=800,
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

    # If the model says it wasn't covered, we show no sources — whatever the retriever
    # thought. A distance threshold alone cannot catch this: "quantum error correction"
    # scores 1.04 against the QLoRA and Quantization lessons, because the embeddings see
    # "quantum" and "quantization" as near neighbours. The agent refused correctly and
    # the UI still rendered five confident-looking videos underneath the refusal.
    REFUSAL_MARKERS = (
        "wasn't covered", "was not covered", "not covered", "does not cover",
        "do not cover", "not appear", "no está", "no fue cubierto",
    )

    def ask(self, question: str) -> dict:
        """Answer one question. Returns the frozen {answer, citations} shape."""
        self.collector.reset()
        result = self.executor.invoke({"input": question})
        answer = result["output"]

        lowered = answer.lower()
        if any(marker in lowered for marker in self.REFUSAL_MARKERS):
            return build_response(answer, [])
        return build_response(answer, self.collector.metadatas)

    def tools_used(self, result: dict | None = None) -> list[str]:
        """Names of the tools called on the last turn — used by the memory demo."""
        steps = (result or {}).get("intermediate_steps", [])
        return [action.tool for action, _ in steps]

    def reset(self) -> None:
        self.memory.clear()
        self.collector.reset()


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
