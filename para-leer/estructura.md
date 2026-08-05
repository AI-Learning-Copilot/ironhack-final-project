ironhack-final-project/
│
├── .venv/                       # Local virtual environment
│
├── app/
│   └── app.py                   # Streamlit application
│
├── data/
│   ├── raw/                     # Original transcripts / VTT / TXT
│   │
│   └── processed/               # Cleaned/parsed transcripts
│
├── notebooks/
│   └── experiments.ipynb        # Experiments only
│
├── src/
│   ├── ingestion.py             # Zoom/Loom transcript loading
│   ├── chunking.py              # Transcript → chunks
│   ├── embeddings.py            # Embedding generation
│   ├── retrieval.py             # Vector DB similarity search
│   ├── rag.py                   # RAG pipeline
│   │
│   ├── agent.py                 # LangGraph agent
│   ├── tools.py                 # Agent tools
│   ├── memory.py                # Conversation memory
│   │
│   ├── summarization.py         # BONUS
│   └── translation.py           # BONUS
│
├── evaluation/
│   ├── evaluation.py            # LangSmith evaluation
│   └── test_questions.json      # Evaluation dataset
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_chunking.py
│   ├── test_retrieval.py
│   └── test_rag.py
│
├── para-leer/
│   ├── PLAN.md
│   └── README-sync.md
│
├── .env                         # API keys — NEVER GitHub
├── .gitignore
├── README.md
└── requirements.txt