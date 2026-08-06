# 🎓 Ironhack AI Course Copilot

An AI learning assistant built for the **Ironhack AI Engineering Bootcamp**.

The Course Copilot uses **Retrieval-Augmented Generation (RAG)** to answer questions using the actual course material, including lecture recordings and notebooks.

Instead of searching through hours of recordings, students can ask questions and receive grounded answers with links to the relevant lessons and timestamps.

## ✨ Features

- 💬 Ask questions about the AI Engineering course
- 🔎 Search across **120 teaching recordings**
- 📓 Retrieve information from course notebooks
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

## 🛠️ Tech Stack

- **Python 3.11**
- **LangChain**
- **OpenAI**
- **Chroma**
- **Streamlit**
- **Tiktoken**
- **Pandas / NumPy**

## 🧪 Evaluation

The project includes an automated evaluation suite covering:

- Course content questions
- Lesson and timestamp retrieval
- Spanish questions
- Unsupported questions
- Conversational follow-ups
- Notebook retrieval

**Current result: 30 / 30 evaluation cases passing.**

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

## 👥 Team

Built by **Casilda and Felipe** as the final project for the **Ironhack AI Engineering Bootcamp**.