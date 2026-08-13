# 🎓 Ironhack AI Course Copilot

> An AI-powered study assistant for the Ironhack AI Engineering bootcamp. It answers questions using the course recordings and notebooks, with grounded answers and direct source references.

## Overview

The **Ironhack AI Course Copilot** is an agentic RAG application built as the final project for the Ironhack AI Engineering bootcamp.

Instead of relying only on the LLM's general knowledge, the Copilot retrieves relevant material from the bootcamp's recorded lessons and notebooks and uses it as context for generating answers.

The application supports English and Spanish and can connect answers to the relevant lesson, notebook, and video timestamp.

## ✨ Features

- 🔎 **Course-grounded Q&A** — answers are based on the bootcamp material.
- 🎥 **Timestamped citations** — jump directly to where a concept was explained.
- 📓 **Notebook references** — locate relevant implementation examples and cells.
- 🧠 **Conversation memory** — supports contextual follow-up questions.
- 📝 **Interactive quizzes** — generate and score multiple-choice quizzes from course material.
- 📚 **Study Notes** — generate structured notes and PDF exports.
- 🌐 **English & Spanish** — follows the language of the student's question.
- 🛑 **Scope protection** — refuses questions that cannot be grounded in the course.

# 🏗️ Architecture

The Copilot uses an **agentic RAG architecture**.

### Offline / Indexing

```text
Course recordings + notebooks
            ↓
        Chunking
            ↓
        Embeddings
            ↓
      Chroma vector DB
```

Course chunks are stored together with metadata such as source type, lesson, week/day, timestamps, notebook references, and text.

### Online / Query time

```text
Student
   ↓
Streamlit UI
   ↓
LangChain Copilot + Memory
   ↓
Tool layer
   ↓
Retrieval + Reranking
   ↓
Relevant course context
   ↓
LLM
   ↓
Answer + Citations
```

The agent can use tools for course search, notebook lookup, timestamp lookup, concept explanation, quiz generation, lesson indexing, and source recall.

## 🧩 RAG

Retrieval-Augmented Generation allows the Copilot to retrieve the relevant course material at query time instead of depending on the model's pretrained knowledge.

This improves:

- Grounding in the actual course.
- Traceability to original sources.
- Access to course-specific knowledge.
- Detection of unsupported questions.

## 🛠️ Technology Stack

| Component       | Technology                                         |
| --------------- | -------------------------------------------------- |
| UI              | Streamlit                                          |
| Agent           | LangChain                                          |
| LLM             | GPT-4o-mini                                        |
| Embeddings      | OpenAI embeddings                                  |
| Vector DB       | Chroma                                             |
| Retrieval       | Similarity search + metadata filtering + reranking |
| Source material | Loom recordings + Jupyter notebooks                |
| Language        | Python                                             |
| PDF generation  | ReportLab                                          |

## 📁 Project Structure

```text
ironhack-final-project/
├── app/
├── data/
├── evaluation/
├── index/
├── notebooks/
├── docs/
├── scripts/
├── src/
├── summaries/
├── tests/
├── requirements.txt
└── README.md
```

## 🚀 Run Locally

### 1. Clone and enter the repository

```bash
git clone https://github.com/AI-Learning-Copilot/ironhack-final-project.git
cd ironhack-final-project
```

### 2. Create the environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure the API key

Create `.env` in the project root:

```env
OPENAI_API_KEY=your_api_key_here
```

Never commit API keys.

### 4. Start the application

```bash
streamlit run app/app.py
```

## 🧪 Evaluation

The evaluation suite tests content questions, lesson-location queries, Spanish questions, unanswerable questions, follow-ups, and notebook/code queries.

### GPT-4o-mini Evaluation

Latest GPT-4o-mini evaluation:

```text
29/30 cases pass
SOURCE ACCURACY     27/27 (100%)
REFUSAL ACCURACY      3/3
median latency        4.2s
p95 latency           13.0s
max latency           22.0s
```

Run it with:

```bash
PYTHONPATH=src python evaluation/evaluation.py
```

### Retrieval Evaluation

The retrieval evaluation tests 84 golden questions against the course index.

```text
Questions tested : 84
Top-1 accuracy   : 84.5%
Top-3 accuracy   : 91.7%
Top-5 accuracy   : 94.0%
Average distance : 0.792
```

Run it with:

```bash
PYTHONPATH=src python scripts/evaluate_retrieval.py
```

## 🧪 LLM Experiment

The project was also tested with **NVIDIA Nemotron 3 Nano 30B A3B** as an alternative LLM.

The experiment was kept isolated on the `experiment/nemotron` branch and was not merged into `main`. The main branch continues to use **GPT-4o-mini**.

For the implementation details, configuration, and observed experiment results, see [`docs/nemotron-experiment.md`](docs/nemotron-experiment.md).


## 🎯 Design Goal

The Copilot is designed around a simple learning flow:

**Question → Grounded explanation → Source → Lesson / Notebook → Timestamp**

If the course material does not support an answer, the system should say so rather than presenting general LLM knowledge as something taught in the bootcamp.

## 👥 Project

Built as the final project for the **Ironhack AI Engineering Bootcamp**.

GitHub: https://github.com/AI-Learning-Copilot/ironhack-final-project

The course material used by the application belongs to Ironhack.

### Architecture

The canonical architecture diagram is maintained at:

```text
docs/architecture.png
```