# RegNaija
### Nigerian Regulatory Intelligence Platform

> *Ask anything about Nigerian law. Get cited, sourced answers in seconds.*

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-FF6B6B?style=flat-square)
![Pinecone](https://img.shields.io/badge/Pinecone-Vector_DB-00B0FF?style=flat-square)
![Groq](https://img.shields.io/badge/Groq-llama--3.3--70b-F55036?style=flat-square)
![Streamlit](https://img.shields.io/badge/Streamlit-1.x-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![RAGAS](https://img.shields.io/badge/RAGAS-Precision_1.000-22C55E?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-22C55E?style=flat-square)

</div>

---

## What Is This?

**RegNaija** is a production-grade **Retrieval-Augmented Generation (RAG)** system built specifically for Nigerian regulatory intelligence. It ingests official documents from Nigeria's top regulatory bodies, embeds them into a semantic vector store, and answers compliance questions with **zero hallucination** — every answer is grounded in cited source documents.

No guessing. No fabrication. Just law.

---

## The Problem It Solves

Nigerian compliance professionals, fintech founders, and legal practitioners face a fragmented regulatory landscape:

- CBN circulars buried in PDFs across dozens of web pages
- SEC rules updated without notice
- NDPC data protection obligations spread across 100+ page documents
- No unified interface to query across agencies simultaneously

**RegNaija fixes this.** One query. All agencies. Sourced answers.

---

## Evaluation Results (RAGAS)

Evaluated against a 10-question golden test set covering all 5 agencies. Judge: `llama-3.1-8b-instant`.

| Metric | Score |
|--------|-------|
| **Context Precision** | **1.000** — every retrieved chunk was relevant |
| **Context Recall** | **0.789** — strong coverage of expected answer content |
| **Overall Average** | **0.895** |
| Questions flagged | **0 / 10** |

> Faithfulness metric excluded — requires a 70b judge model for reliable NLI reasoning.

---

## Regulatory Coverage

| Agency | Full Name | Documents Covered |
|--------|-----------|-------------------|
| **CBN** | Central Bank of Nigeria | Open Banking Policy, Cybersecurity Framework, Consumer Protection, PSP Licensing, Mobile Payments |
| **SEC** | Securities and Exchange Commission | Investments and Securities Act 2007 |
| **NDPC** | Nigeria Data Protection Commission | Nigeria Data Protection Act 2023 |
| **NRS** | Nigeria Revenue Service | Nigeria Tax Act 2025 |
| **NITDA** | National IT Development Agency | NDPR, IT Service Provider Overview |

---

## System Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        User Query                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────────┐
│                  Streamlit UI  (streamlit_app.py)               │
│   Chat interface · Session history · Source citations           │
│   Casual conversation bypass · Confidence display               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              V                         V
     Casual message?              Regulatory query?
     (greetings, small talk)      (CBN, SEC, NDPC...)
              │                         │
              V                         V
     Direct LLM reply           LangGraph Agentic Pipeline
     (no Pinecone)                      │
                               ┌────────┴─────────┐
                               V                  V 
                        Query Analyser      Agency Detector
                               │
                               V
                        Retrieval Agent
                        (Pinecone · top_k=8)
                        (BAAI/bge-small-en-v1.5)
                               │
                               V
                        Conflict Detector
                        (cross-agency checks)
                               │
                               V
                        Confidence Guard
                        (blocks low-confidence)
                               │
                               V
                        Answer Synthesiser
                        (Groq · llama-3.3-70b)
                               │
                               V
                    ┌──────────────────────┐
                    │  Cited Answer        │
                    │  + Source Documents  │
                    │  + Confidence Level  │
                    │  + Latency Metadata  │
                    └──────────────────────┘
```

---

## Tech Stack
```
Layer               Technology
──────────────────────────────────────────────────────
UI                  Streamlit (chat interface)
LLM                 Groq API — llama-3.3-70b-versatile
Embeddings          BAAI/bge-small-en-v1.5 (384-dim)
Vector Store        Pinecone (1,297 chunks, cosine similarity)
Orchestration       LangGraph 0.2 (5-node agentic pipeline)
Chunking            Custom NigerianLegalChunker
PDF Processing      pypdf + custom OCR processor
Background Watcher  Custom scraper (SEC: 57 docs detected)
Evaluation          RAGAS 0.2.6 (two-phase cached eval)
Runtime             Python 3.11 · CPU-only · Ubuntu 24
```

---

## Project Structure
```
regnaija/
├── streamlit_app.py                # Streamlit UI — main entry point
├── eval_cache.json                 # Cached pipeline answers (10 questions)
├── ragas_results.json              # Full per-question scores
├── ragas_summary.txt               # Human-readable eval summary
├── src/
│   ├── ingestion/
│   │   ├── legal_chunker.py        # Nigerian legal document chunker
│   │   ├── metadata_extractor.py   # Agency/date/section metadata
│   │   └── ocr_processor.py        # PDF text extraction
│   ├── retrieval/
│   │   ├── embedder.py             # BAAI/bge-small-en-v1.5 wrapper
│   │   └── vector_store.py         # Pinecone upsert/search interface
│   ├── generation/
│   │   ├── answer_generator.py     # Groq LLM answer synthesis
│   │   ├── citation_builder.py     # Source citation formatter
│   │   └── system_prompt.py        # Zero-hallucination system prompt
│   ├── graph/
│   │   ├── nodes.py                # LangGraph node definitions
│   │   ├── rag_graph.py            # Pipeline graph assembly
│   │   └── state.py                # TypedDict state schema
│   └── watcher/
│       └── watcher.py              # Background regulatory scraper
├── data/
│   ├── documents/CBN/              # CBN source PDFs
│   └── watcher_registry.json       # Ingestion history
└── tests/
    ├── eval_generate.py                # RAGAS Phase 1 — generate & cache answers
    └── eval_score.py                   # RAGAS Phase 2 — score cached answers
```

---

## Getting Started

### Prerequisites
```bash
Python 3.11+
Pinecone account (free tier works)
Groq API key (free tier works)
```

### Installation
```bash
git clone https://github.com/jamesdanas/regnaija.git
cd regnaija
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment Setup

Create a `.env` file in the project root:
```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENV=your_pinecone_environment
GROQ_API_KEY=your_groq_api_key
LLM_MODEL=llama-3.3-70b-versatile
EMBED_MODEL=BAAI/bge-small-en-v1.5
PINECONE_INDEX=naijacodex
```

### Run the App
```bash
streamlit run streamlit_app.py
```

Open `http://localhost:8501` in your browser.

---

## Key Features

### Zero-Hallucination Answers
Every answer is grounded in retrieved document chunks. If sufficient sources are not found, the system returns a transparent "I don't know" with recommended actions — never a fabricated answer.

### Multi-Agency Query Routing
The query analyser automatically detects which regulatory agencies are relevant and routes retrieval accordingly — CBN for banking, NDPC for data protection, SEC for capital markets, etc.

### Conflict Detection
When multiple agencies have overlapping or contradictory rules, RegNaija flags the conflict explicitly so the user is aware of the regulatory tension.

### Conversational Awareness
Non-regulatory messages bypass Pinecone entirely for natural, fast conversation without regulatory boilerplate.

### Live Watcher Service
A background scraper monitors CBN, SEC, NDPC, and NITDA websites for new documents and automatically ingests them into Pinecone.
```bash
python src/watcher/watcher.py --once        # Run once
python src/watcher/watcher.py --hours 12    # Run every 12 hours
```

### Two-Phase RAGAS Evaluation
Evaluation is decoupled into generation and scoring phases to work within free-tier token limits.
```bash
LLM_MODEL=llama-3.1-8b-instant python eval_generate.py   # Cache answers
python eval_score.py                                       # Score with RAGAS
```

---

## RAG Pipeline Performance

| Metric | Value |
|--------|-------|
| Vector store chunks | 1,297 |
| Agencies covered | 5 (CBN, SEC, NDPC, NRS, NITDA) |
| Chunks per query | 8 (top-k retrieval) |
| Avg retrieval score | 0.75–0.84 (cosine) |
| LLM | llama-3.3-70b-versatile via Groq |
| Avg latency | 3–22 seconds |
| RAGAS Context Precision | 1.000 |
| RAGAS Context Recall | 0.789 |
| RAGAS Overall Average | 0.895 |

---

## Build Log
```
Day 1  Legal document chunker, OCR processor, metadata extractor
Day 2  Embedding pipeline, Pinecone vector store, 855-chunk ingestion
Day 3  Zero-hallucination system prompt, citation builder, answer generator
Day 4  LangGraph 5-node agentic pipeline, conflict detector, dedup fix
Day 5  Streamlit UI, session history, casual conversation layer
Day 6  Background watcher service, SEC auto-ingestion (57 docs detected)
Day 7  Two-phase RAGAS evaluation framework, CBN PSP licensing doc ingested
Day 8  README polish, eval results published, deployment prep
```

---

## Limitations

- **CBN website** — PDFs are JavaScript-rendered; watcher gets 0 links from CBN directly. Selenium would fix this.
- **Session persistence** — History lives in memory only; restart wipes all sessions.
- **NRS coverage** — Thin document coverage compared to CBN and SEC.
- **CPU-only** — GPU would reduce embedding latency significantly.
- **Faithfulness metric** — Requires a 70b judge model; excluded from current eval due to free-tier token limits.

---

## Documents Ingested

| File | Agency | Source |
|------|--------|--------|
| `cbn_consumer_protection.pdf` | CBN | CBN website |
| `cbn_cybersecurity_framework.pdf` | CBN | CBN website |
| `cbn_open_banking_policy.pdf` | CBN | CBN website |
| `NEW-CBN-LICENCING-REQUIREMENTS-FOR-PAYMENT-SERVICES.pdf` | CBN | Detail Commercial Solicitors / CBN circular May 2021 |
| `REGULATORY_FRAMEWORK_FOR_MOBILE_PAYMENTS_SERVICES_IN_NIGERIA.pdf` | CBN | CBN website |
| Nigeria Data Protection Act 2023 | NDPC | NDPC website |
| Investments and Securities Act 2007 | SEC | SEC website |
| Nigeria Tax Act 2025 | NRS | NRS website |
| NITDA Overview and NDPR | NITDA | NITDA website |

All documents ingested into Pinecone index `regnaija`.

---

## License

MIT License

---

## Built By

**James Danas** — AI/ML Engineer

> *"The law should be accessible to everyone, not just those who can afford a lawyer."*

---

<div align="center">
  <sub>Powered by Groq · Pinecone · LangGraph · Streamlit</sub>
</div>
