# NaijaCodex
### Nigerian Regulatory Intelligence Platform

> *Ask anything about Nigerian law. Get cited, sourced answers in seconds.*

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-FF6B6B?style=flat-square)
![Pinecone](https://img.shields.io/badge/Pinecone-Vector_DB-00B0FF?style=flat-square)
![Groq](https://img.shields.io/badge/Groq-llama--3.3--70b-F55036?style=flat-square)
![Gradio](https://img.shields.io/badge/Gradio-4.44-FF7C00?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-22C55E?style=flat-square)

</div>

---

## What Is This?

**NaijaCodex** is a production-grade **Retrieval-Augmented Generation (RAG)** system built specifically for Nigerian regulatory intelligence. It ingests official documents from Nigeria's top regulatory bodies, embeds them into a semantic vector store, and answers compliance questions with **zero hallucination** — every answer is grounded in cited source documents.

No guessing. No fabrication. Just law.

---

## The Problem It Solves

Nigerian compliance professionals, fintech founders, and legal practitioners face a fragmented regulatory landscape:

- CBN circulars buried in PDFs across dozens of web pages
- SEC rules updated without notice
- NDPC data protection obligations spread across 100+ page documents
- No unified interface to query across agencies simultaneously

**NaijaCodex fixes this.** One query. All agencies. Sourced answers.

---

## Regulatory Coverage

| Agency | Full Name | Documents Covered |
|--------|-----------|-------------------|
|**CBN** | Central Bank of Nigeria | Open Banking Policy, Cybersecurity Framework, Consumer Protection |
|**SEC** | Securities and Exchange Commission | Investment Rules, Capital Market Regulations, AML/CFT |
|**NDPC** | Nigeria Data Protection Commission | NDPA 2023, Data Subject Rights, Breach Notification |
|**NRS** | Nigeria Revenue Service | Tax Filing Obligations, Penalties, Compliance |
|**NITDA** | National IT Development Agency | NDPR, IT Service Provider Rules, Digital Economy Policy |

---

## Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        User Query                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Gradio UI  (app.py)                            │
│   Dark theme · Collapsible sidebar · Session history             │
│   Casual conversation bypass · 40s timeout protection            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
   Casual message?              Regulatory query?
   (greetings, small talk)      (CBN, SEC, NDPC...)
              │                         │
              ▼                         ▼
   Direct LLM reply           LangGraph Agentic Pipeline
   (no Pinecone)                        │
                               ┌────────┴─────────┐
                               ▼                   ▼
                        Query Analyser      Agency Detector
                               │
                               ▼
                        Retrieval Agent
                        (Pinecone · top_k=8)
                        (BAAI/bge-small-en-v1.5)
                               │
                               ▼
                        Conflict Detector
                        (cross-agency checks)
                               │
                               ▼
                        Confidence Guard
                        (blocks low-confidence)
                               │
                               ▼
                        Answer Synthesiser
                        (Groq · llama-3.3-70b)
                               │
                               ▼
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
UI                  Gradio 4.44 (dark Grok-style theme)
LLM                 Groq API — llama-3.3-70b-versatile
Embeddings          BAAI/bge-small-en-v1.5 (384-dim)
Vector Store        Pinecone (855+ chunks, cosine similarity)
Orchestration       LangGraph 0.2 (5-node agentic pipeline)
Chunking            Custom NigerianLegalChunker
PDF Processing      pypdf + custom OCR processor
Background Watcher  Custom scraper (SEC: 57 docs detected)
Runtime             Python 3.11 · CPU-only · Ubuntu 24
```

---

## Project Structure
```
naijacodex/
├── app.py                          # Gradio UI — main entry point
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
│   ├── watcher/
│   │   └── watcher.py              # Background regulatory scraper
│   └── evaluation/
├── data/
│   ├── raw/                        # Source PDFs and text files
│   ├── processed/                  # Chunked documents (JSON)
│   └── watcher_registry.json       # Ingestion history
└── tests/
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
# Clone the repo
git clone https://github.com/jamesdanas/naijacodex.git
cd naijacodex

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
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
python app.py
```

Open `http://localhost:7860` in your browser.

---

## Key Features

### Zero-Hallucination Answers
Every answer is grounded in retrieved document chunks. If sufficient sources are not found, the system returns a transparent "I don't know" with recommended actions — never a fabricated answer.

### Multi-Agency Query Routing
The query analyser automatically detects which regulatory agencies are relevant and routes retrieval accordingly — CBN for banking, NDPC for data protection, SEC for capital markets.

### Conflict Detection
When multiple agencies have overlapping or contradictory rules, NaijaCodex flags the conflict explicitly so the user is aware of the regulatory tension.

### Conversational Awareness
Non-regulatory messages bypass Pinecone entirely for natural, fast conversation without regulatory boilerplate.

### Live Watcher Service
A background scraper monitors CBN, SEC, NDPC, and NITDA websites for new documents and automatically ingests them into Pinecone every 24 hours.
```bash
# Run watcher manually
python src/watcher/watcher.py --once

# Run as background service every 12 hours
python src/watcher/watcher.py --hours 12
```

---

## RAG Pipeline Performance

| Metric | Value |
|--------|-------|
| Vector store chunks | 855+ |
| Agencies covered | 5 (CBN, SEC, NDPC, NRS, NITDA) |
| Chunks per query | 8 (top-k retrieval) |
| Avg retrieval score | 0.75–0.82 (cosine) |
| LLM | llama-3.3-70b-versatile via Groq |
| Avg latency | 3–8 seconds |
| Timeout protection | 40 second hard limit |

---

## Build Log
```
Day 1  Legal document chunker, OCR processor, metadata extractor
Day 2  Embedding pipeline, Pinecone vector store, 855-chunk ingestion
Day 3  Zero-hallucination system prompt, citation builder, answer generator
Day 4  LangGraph 5-node agentic pipeline, conflict detector, dedup fix
Day 5  Grok-style Gradio UI, collapsible sidebar, casual conversation layer
Day 6  Background watcher service, SEC auto-ingestion (57 docs detected)
Day 7  RAGAS evaluation, README, deployment notes
```

---

## Limitations

- **CBN website** — PDFs are JavaScript-rendered; watcher gets 0 links from CBN. Selenium would fix this.
- **Session persistence** — History lives in memory only. Restart wipes all sessions.
- **NRS coverage** — Thin document coverage compared to CBN and SEC.
- **CPU-only** — GPU would reduce embedding latency significantly.

---

## License

MIT License

---

## Built By

**James Danas** — AI/ML Engineer

> *"The law should be accessible to everyone, not just those who can afford a lawyer."*

---

<div align="center">
  <sub>Built with 🇳🇬 pride · Powered by Groq · Pinecone · LangGraph · Gradio</sub>
</div>

## Documents Ingested (not tracked in git)

| File | Agency | Source |
|------|--------|--------|
| `data/documents/CBN/cbn_consumer_protection.pdf` | CBN | CBN website |
| `data/documents/CBN/cbn_cybersecurity_framework.pdf` | CBN | CBN website |
| `data/documents/CBN/cbn_open_banking_policy.pdf` | CBN | CBN website |
| `data/documents/CBN/NEW-CBN-LICENCING-REQUIREMENTS-FOR-PAYMENT-SERVICES.pdf` | CBN | Detail Commercial Solicitors / CBN circular May 2021 |
| `data/documents/CBN/REGULATORY_FRAMEWORK_FOR_MOBILE_PAYMENTS_SERVICES_IN_NIGERIA.pdf` | CBN | CBN website |

All documents are ingested into Pinecone index `naijacodex`. Re-ingest using `src/watcher/watcher.py DocumentIngester`.
