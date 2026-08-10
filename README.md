# 🎓 Ironhack AI Course Copilot

An AI learning assistant built for the **Ironhack AI Engineering Bootcamp**.

The Course Copilot uses **Retrieval-Augmented Generation (RAG)** to answer questions using the actual course material, including lecture recordings and notebooks.

Instead of searching through hours of recordings, students can ask questions and receive grounded answers with links to the relevant lessons and timestamps.

**Live:** https://ai-learning-copilot-ironhack-final-project.streamlit.app/

## ✨ Features

- 💬 Ask questions about the AI Engineering course
- 🔎 Search across **120 teaching recordings** (90 hours, 32 lesson days)
- 📓 Retrieve information from **64 course notebooks**
- 🎥 Cite lecture videos with timestamps
- 🧠 Maintain conversational memory for follow-up questions
- 🌍 Answer in English or Spanish
- 📍 Find where a topic was covered
- 📝 Generate interactive multiple-choice quizzes with scoring
- 🛡️ Refuse unsupported questions instead of relying on general model knowledge

## 🏗️ How It Works

```text
Course recordings + notebooks
            ↓
     Parsing & Chunking
            ↓
      OpenAI Embeddings
            ↓
      Chroma Vector DB
            ↓
        Retrieval
            ↓
     LangChain Agent
            ↓
 Grounded answer + citations
            ↓
      Streamlit UI
```

The knowledge base combines lecture transcripts and course notebooks in a single Chroma collection.

When a student asks a question, relevant chunks are retrieved and provided to the LLM as context. The agent then generates an answer grounded in the retrieved course material.

## 📚 What Is Indexed

| | |
|---|---|
| Teaching recordings | **120** across **32 lesson days**, **90 hours** |
| Course notebooks | **64** — 40 mapped to a lesson, 24 supplementary |
| Video chunks | 5,090 |
| Notebook chunks | 947 |
| **Total indexed passages** | **6,037** |

Notebook coverage spans weeks 1–5 and 7–8. Week 6 is deployment and project
presentations, which produced no notebooks.

The 24 supplementary notebooks are files that live in the course repository without
belonging to a taught day — Python basics, NumPy, pandas, transfer learning, LangSmith.
They are indexed and cited with an `Extra ·` prefix so a student can tell them apart from
lesson material.

**Not indexed: the Ironhack lab assignments.** The copilot searches the lectures and the
demo notebooks. Asking where a lab is will return the recording where the instructor
introduces it, not the lab itself.

The index is built once and committed. The deployed app only reads it — it never
re-embeds on boot, which keeps cold starts fast and means the index cannot be lost when
the host restarts.

## 🛠️ Tech Stack

- **Python 3.11**
- **LangChain**
- **OpenAI**
- **Chroma**
- **Streamlit**
- **Tiktoken**
- **Pandas / NumPy**

## 🧪 Evaluation

Two suites, measuring different things.

### End-to-end — does the copilot answer correctly?

30 hand-written cases run through the full agent: course content, lesson and timestamp
retrieval, Spanish questions, unsupported questions that must be refused, conversational
follow-ups, and notebook retrieval.

```
29 / 30 cases pass
Source accuracy    27 / 27  — every citation points at a lesson that really covers it
Refusal accuracy    3 / 3   — no invented answer to an out-of-scope question
Median latency      4.6s
```

**The one failure is `f01`,** and it is a wording assertion rather than a retrieval fault.
The case requires the answer to "What is RAG and why would I use it?" to contain the word
*context*; the model sometimes says *external documents* or *knowledge base* instead. It
fails roughly one run in three on unchanged code. We are reporting 29/30 rather than
re-running until it passes.

### Retrieval — does the right material come back at all?

84 golden questions with a known correct lesson and notebook, scored on whether the
correct source appears in the top 1, 3 or 5 results. No LLM involved.

```
Top-1   83.3%
Top-3   92.9%
Top-5   94.0%
```

Both suites are reproducible:

```bash
python evaluation/evaluation.py          # end-to-end
python scripts/evaluate_retrieval.py     # retrieval
```

### Honest notes on these numbers

- Retrieval uses **approximate** nearest-neighbour search (HNSW), so identical queries can
  return slightly different results between processes. Treat single-point differences as
  noise.
- The reranker's penalty for supplementary notebooks was tuned on the same 84 questions it
  is measured against. Its +2.3 points on Top-1 is two questions, and should be read as
  "does not hurt" rather than as a validated gain.
- Both suites were written by us, so they measure what we thought to test.

## 📁 Project Structure

```text
ironhack-final-project/
├── app/
│   └── app.py
├── data/
├── evaluation/
├── notebooks/
├── src/
│   ├── agent.py
│   ├── chunking.py
│   ├── embeddings.py
│   ├── ingestion.py
│   ├── notebooks.py
│   ├── retrieval.py
│   ├── schemas.py
│   └── tools.py
├── tests/
├── requirements.txt
└── README.md
```

## 🚀 Run Locally

Clone the repository:

```bash
git clone https://github.com/AI-Learning-Copilot/ironhack-final-project.git
cd ironhack-final-project
```

Create and activate the virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Add the required API configuration to `.env`, then run:

```bash
python -m streamlit run app/app.py
```

## 🎯 MVP Scope

The current MVP is a **text-based course learning assistant**.

Voice input was intentionally left outside the MVP so development could focus on reliable retrieval, grounded answers, citations, conversational memory, lesson navigation, and interactive quizzes.

Raw course transcripts are not included in the public repository.

**Conversations are held in memory and end with the session.** Nothing a student asks is
written to disk or to any database. Refreshing the page starts a new conversation. This
is a deliberate choice, not a missing feature — see Future Work.

## 🔭 Future Work

### Persistent conversations, and what they would let us learn

Today a conversation lives in the server's memory for one browser connection. It survives
clicks; it does not survive a refresh, a second tab, or the host restarting.

Making it persist is not primarily a convenience feature. The valuable part is the
**record of what students actually ask**: which topics generate the most questions, where
the copilot refuses most often, which lessons nobody ever asks about. That is feedback on
*the course*, not on the app, and we currently throw all of it away.

It is not a small change, and the interesting difficulties are not the storage:

- **It forces an identity decision.** There is no such thing as "your" conversation today.
  The moment one is stored, something must say whose it is and who may read it back. With
  an anonymous id, a conversation link becomes a capability: hold it, read it.
- **The host cannot be trusted to keep a file.** The deployment rebuilds its container on
  redeploy and sleeps when idle — the same constraint that led us to commit the Chroma
  index rather than build it at runtime. Persistence means an external database, not a
  file on disk.
- **It creates a data-protection obligation we do not currently have.** Storing nothing is
  a strong privacy position. Storing conversations means a stated retention period, a way
  to erase on request, and a conversation with Ironhack, whose material and students these
  are.

The groundwork is already in place: `SourceLog` (added to survive summarisation) is plain
serialisable data, and it is the piece that makes a restored conversation useful rather
than one whose early timestamps have already been compressed away.

### Other known gaps

- **The lab assignments are not indexed** — only the lectures and the demo notebooks.
- **Retrieval is approximate** (HNSW), so identical queries can return slightly different
  results between processes.
- **The reranker's supplementary-notebook penalty was tuned on the evaluation set it is
  measured against.** A held-out set would tell us whether the gain is real.

## 👥 Team

Built by **Casilda and Felipe** as the final project for the **Ironhack AI Engineering Bootcamp**.