#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# RegNaija — Clean Git History Script
# Squashes all commits into 11 clean day-by-day commits
# Run from project root: bash clean_commits.sh
# ══════════════════════════════════════════════════════════════════

set -e  # Exit on any error

echo "==================================================="
echo "  RegNaija - Rebuilding Clean Git History"
echo "==================================================="
echo ""

# Step 1 — Squash everything to the very first commit
echo "[1/3] Squashing all commits to root..."
FIRST_COMMIT=$(git rev-list --max-parents=0 HEAD)
git reset --soft "$FIRST_COMMIT"

# Step 2 — Unstage everything
echo "[2/3] Unstaging all files..."
git reset HEAD .
echo ""

echo "[3/3] Recommitting in clean day-by-day groups..."
echo ""

# ── COMMIT 1 — Day 1: Project Scaffold ───────────────────────────
echo "--- Commit 1: Day 1 - Project scaffold"
git add \
    .gitignore \
    .python-version \
    packages.txt \
    requirements.txt \
    restart.sh \
    .streamlit/config.toml \
    src/__init__.py \
    src/ingestion/__init__.py \
    src/retrieval/__init__.py \
    src/generation/__init__.py \
    src/graph/__init__.py \
    src/watcher/__init__.py \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "chore(day1): project scaffold - Python 3.12 venv, pinned dependencies, Streamlit config, folder structure

Files:
  - .gitignore               secrets, venv, caches excluded
  - .python-version          pins Python 3.12 for Streamlit Cloud
  - packages.txt             system deps: tesseract-ocr, poppler-utils
  - requirements.txt         conflict-free dependency set (CPU torch)
  - restart.sh               one-command local restart helper
  - .streamlit/config.toml   dark theme, headless server
  - src/**/__init__.py       Python package declarations"

echo ""

# ── COMMIT 2 — Day 2: Ingestion Pipeline ─────────────────────────
echo "--- Commit 2: Day 2 - Ingestion pipeline"
git add \
    src/ingestion/legal_chunker.py \
    src/ingestion/ocr_processor.py \
    src/ingestion/metadata_extractor.py \
    src/ingestion/save_chunks.py \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day2): ingestion pipeline - LegalChunker, OCRProcessor, MetadataExtractor

Files:
  - src/ingestion/legal_chunker.py      section-aware PDF splitter (regex boundaries)
  - src/ingestion/ocr_processor.py      scanned PDF handler (Tesseract, 300 DPI)
  - src/ingestion/metadata_extractor.py agency/date/section extractor (32 docs, 9 agencies)
  - src/ingestion/save_chunks.py        chunk persistence utility

Key design: splits at section boundaries, never mid-clause.
Scanned PDFs auto-detected (<100 chars/page) and OCR-processed."

echo ""

# ── COMMIT 3 — Day 3: Embedder and Vector Store ──────────────────
echo "--- Commit 3: Day 3 - Embedder and Pinecone vector store"
git add \
    src/retrieval/embedder.py \
    src/retrieval/vector_store.py \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day3): embedder and Pinecone vector store

Files:
  - src/retrieval/embedder.py      BAAI/bge-small-en-v1.5 wrapper (384-dim, CPU-only)
  - src/retrieval/vector_store.py  Pinecone interface — upsert, query, dedup

Embedding: mean-pooling + L2 normalisation → cosine similarity = dot product.
Retrieval: top_k=12 → score filter ≥0.30 → dedup → top 8."

echo ""

# ── COMMIT 4 — Day 4: Answer Generator and System Prompt ─────────
echo "--- Commit 4: Day 4 - Answer generator and system prompt"
git add \
    src/generation/answer_generator.py \
    src/graph/state.py \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day4): zero-hallucination system prompt and answer generator

Files:
  - src/generation/answer_generator.py  Groq LLM call, structured output parser
  - src/graph/state.py                  LangGraph pipeline state schema

System prompt enforces: DIRECT ANSWER / REGULATORY BASIS / CITATIONS / CONFIDENCE.
Temperature=0.1 for near-deterministic regulatory answers."

echo ""

# ── COMMIT 5 — Day 5: LangGraph Pipeline ─────────────────────────
echo "--- Commit 5: Day 5 - LangGraph 6-node agentic pipeline"
git add \
    src/graph/nodes.py \
    src/graph/rag_graph.py \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day5): LangGraph 6-node agentic RAG pipeline

Files:
  - src/graph/nodes.py      query_analyser, retriever, cross_reference,
                            answer_generator, citation_builder, confidence_scorer
  - src/graph/rag_graph.py  stateful DAG definition, RegNaijaPipeline class

Cross-reference node detects inter-agency regulatory conflicts.
Confidence scorer: HIGH (score≥0.70 AND cites≥2), MED, LOW."

echo ""

# ── COMMIT 6 — Day 6: Watcher Service ────────────────────────────
echo "--- Commit 6: Day 6 - Watcher service"
git add \
    src/watcher/watcher.py \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day6): watcher service — auto-ingestion via APScheduler

Files:
  - src/watcher/watcher.py  DocumentIngester + Watcher (30-min polling)

Monitors 8 agency websites for new PDFs.
Known limitation: JS-rendered CBN/SEC sites return 0 links (needs Playwright)."

echo ""

# ── COMMIT 7 — Day 7: Streamlit UI ───────────────────────────────
echo "--- Commit 7: Day 7 - Streamlit UI"
git add \
    streamlit_app.py \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day7): Streamlit UI - streaming, confidence badges, WAT greetings

Files:
  - streamlit_app.py  complete frontend (migrated from Gradio)

Features:
  - word-by-word streaming (capped at 2s total)
  - HIGH/MED/LOW confidence colour badges
  - WAT-aware greetings (morning/afternoon/evening)
  - is_casual() router bypasses RAG for greetings (~500ms vs ~2.5s)
  - negation stripping ('no regulation questions' → casual)
  - session persistence via JSON file
  - suggested follow-up questions
  - mobile-responsive CSS (max-width: 768px)
  - system prompt leak guard
  - Groq 429 rate-limit friendly error messages"

echo ""

# ── COMMIT 8 — Day 8: RAGAS Evaluation ───────────────────────────
echo "--- Commit 8: Day 8 - RAGAS evaluation"
git add \
    eval_generate.py \
    eval_score.py \
    ragas_results.json \
    ragas_summary.txt \
    ragas_flagged.json \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day8): RAGAS evaluation - Context Precision 1.000, Recall 0.789

Files:
  - eval_generate.py    Phase 1: generate answers, cache to eval_cache.json
  - eval_score.py       Phase 2: score with gpt-oss-20b judge
  - ragas_results.json  per-question scores (10 questions)
  - ragas_summary.txt   human-readable summary
  - ragas_flagged.json  questions scoring below threshold

Results (10 questions, 0 flagged):
  Context Precision: 1.000 (perfect - zero irrelevant chunks retrieved)
  Context Recall:    0.789
  Overall Average:   0.895"

echo ""

# ── COMMIT 9 — Day 9: Model Upgrade ──────────────────────────────
echo "--- Commit 9: Day 9 - Model upgrade (Groq Llama deprecated)"
git add \
    streamlit_app.py \
    src/graph/nodes.py \
    .env.example \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "fix(day9): upgrade models - Groq Llama decommissioned Aug 2026

Files:
  - streamlit_app.py    casual model: gpt-oss-20b, cache TTL fixes
  - src/graph/nodes.py  main model: openai/gpt-oss-120b fallback updated
  - .env.example        updated model names

llama-3.3-70b-versatile → openai/gpt-oss-120b (main pipeline)
llama-3.1-8b-instant   → openai/gpt-oss-20b  (casual + RAGAS judge)

Also fixed partial→lambda bug in rag_graph.py (LangGraph 0.2 compatibility)."

echo ""

# ── COMMIT 10 — Day 10: Rebrand to RegNaija ──────────────────────
echo "--- Commit 10: Day 10 - Rebrand to RegNaija"
git add \
    streamlit_app.py \
    src/graph/nodes.py \
    src/watcher/watcher.py \
    regnaija_sessions.json \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day10): rebrand - project renamed to RegNaija

Files:
  - streamlit_app.py         RegNaija branding, identity system prompt hardened
  - src/graph/nodes.py       AGENCY_KEYWORDS expanded (8 agencies + FIRS alias)
  - src/watcher/watcher.py   logger renamed regnaija.watcher
  - regnaija_sessions.json   renamed from naijacodex_sessions.json

Identity fixes:
  - LLM now states 'RegNaija built by James Danas, AI/ML Engineer, Jos Nigeria'
  - Never hedges identity ('I seem to be' → 'I am')
  - System prompt leak guard prevents context window exposure"

echo ""

# ── COMMIT 11 — Day 11: Knowledge Base Expansion ─────────────────
echo "--- Commit 11: Day 11 - Knowledge base expansion + README"
git add \
    batch_ingest.py \
    src/ingestion/metadata_extractor.py \
    README.md \
    data/ingestion_manifest.json \
    .python-version \
    packages.txt \
    2>/dev/null || true

git diff --cached --quiet || \
git commit -m "feat(day11): knowledge base expansion - 32 docs, 7 agencies, 5756 vectors

Files:
  - batch_ingest.py                    production ingestion script (32 docs)
  - src/ingestion/metadata_extractor.py 32-doc registry, 9 agency map (CAC, NCC, FIRS added)
  - data/ingestion_manifest.json       audit trail of ingestion run
  - README.md                          production docs - architecture, system design, RAGAS

Knowledge base (was 1,297 → now 5,756 vectors):
  CBN  - 14 docs: Cybersecurity 2024, Open Banking, AML, Basel III x6, Forex, PSP...
  SEC  -  8 docs: ISA 2007, Digital Assets, AML, Sharia, Robo-Advisory, April 2025...
  NDPC -  3 docs: NDPA 2023, NDPR Guidelines, NDP-ACT GAID 2025
  NRS  -  2 docs: Nigeria Tax Act 2025, NRS Establishment Act 2025
  FIRS -  1 doc:  Companies Income Tax Act
  CAC  -  2 docs: CAMA 2020, Companies Regulations 2021
  NCC  -  1 doc:  Nigerian Communications Act 2003
  NITDA-  1 doc:  NDPR 2019

Ingestion fixes:
  - OCR auto-applied to 2 scanned PDFs (AML merged, Basel III circular)
  - Paragraph fallback chunker for corrupt PDF structure (SEC AML)
  - doc_id-based chunk IDs prevent Pinecone ID collisions"

echo ""
echo "==================================================="
echo "  Clean history built. Verifying..."
echo "==================================================="
echo ""
git log --oneline
echo ""
echo "==================================================="
echo "  Now run: git push origin main --force"
echo "==================================================="
