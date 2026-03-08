"""
streamlit_app.py — NaijaCodex front-end built with Streamlit.
Features:
- Clean, modern UI with custom CSS
- Chat interface with user/assistant bubbles
- Sidebar for new chats, recent sessions, and document upload
- Dynamic follow-up question suggestions (lazy/async)
- Session persistence (local JSON — note: ephemeral on Streamlit Cloud)
"""
import re
import json
from pathlib import Path
import warnings
import sys
from collections import defaultdict
import streamlit as st
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
load_dotenv()

st.set_page_config(
    page_title="NaijaCodex",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Persistence ─────────────────────────────────────────────────────────────
SESSIONS_FILE = Path("naijacodex_sessions.json")

def load_sessions():
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_sessions(sessions_list):
    try:
        SESSIONS_FILE.write_text(
            json.dumps(sessions_list, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # Silently fail on ephemeral filesystems (Streamlit Cloud)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    :root {
        --bg: #0f0f0f;
        --chat-bg-user: linear-gradient(135deg, #1d4ed8, #3b82f6);
        --chat-bg-ai: #1e1e1e;
        --border: rgba(59, 130, 246, 0.18);
        --text: #e5e7eb;
        --muted: #9ca3af;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: var(--bg) !important;
        color: var(--text) !important;
        font-family: 'Inter', system-ui, sans-serif !important;
    }

    /* Keep header visible so sidebar toggle appears */
    header {
        visibility: visible !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }

    [data-testid="stMainMenu"],
    [data-testid="stStatusWidget"],
    [data-testid="stAppDeployButton"] { display: none !important; }

    footer { display: none !important; }

    .block-container {
        max-width: 780px !important;
        padding: 1.5rem 1.5rem 5rem !important;
        margin: 0 auto !important;
    }

    /* ── User messages — right aligned, blue gradient ── */
    div[data-testid="stChatMessage"]:has(div[data-testid="chatAvatarIcon-user"]) {
        margin-left: auto !important;
        margin-right: 0 !important;
        max-width: 68% !important;
        background: var(--chat-bg-user) !important;
        color: white !important;
        border-radius: 18px 18px 4px 18px !important;
        padding: 0.9rem 1.1rem !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.35) !important;
    }
    div[data-testid="stChatMessage"]:has(div[data-testid="chatAvatarIcon-user"])
        [data-testid="chatMessageContent"] { color: white !important; }

    /* ── Assistant messages — left aligned, dark ── */
    div[data-testid="stChatMessage"]:has(div[data-testid="chatAvatarIcon-assistant"]) {
        margin-right: auto !important;
        margin-left: 0 !important;
        max-width: 78% !important;
        background: var(--chat-bg-ai) !important;
        border: 1px solid var(--border) !important;
        border-radius: 18px 18px 18px 4px !important;
        padding: 0.9rem 1.1rem !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4) !important;
    }

    /* ── Chat input ── */
    div[data-testid="stChatInput"] {
        max-width: 780px !important;
        margin: 0 auto !important;
        padding: 0 1.5rem !important;
    }
    div[data-testid="stChatInput"] > div > div > textarea {
        border-radius: 9999px !important;
        padding: 0.85rem 1.25rem !important;
        background: #1a1a1a !important;
        border: 1px solid #333 !important;
        color: white !important;
        font-size: 15px !important;
    }

    /* ── Expander — small font for sources ── */
    [data-testid="stExpander"] { font-size: 9.5px !important; line-height: 1.4 !important; }
    [data-testid="stExpander"] p,
    [data-testid="stExpander"] a,
    [data-testid="stExpander"] div,
    [data-testid="stExpander"] li { font-size: 9.5px !important; }
    [data-testid="stExpander"] a { color: #3b82f6 !important; text-decoration: none !important; }
    [data-testid="stExpander"] a:hover { text-decoration: underline !important; }

    /* ── Metadata line ── */
    .metadata-line { font-size: 9px !important; color: #666 !important; margin-top: 8px !important; }

    /* ── Follow-up suggestion buttons ── */
    .followup-btn button {
        background: #1a1a1a !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 8px !important;
        color: #aaa !important;
        font-size: 11px !important;
        text-align: left !important;
    }
    .followup-btn button:hover {
        border-color: #3b82f6 !important;
        color: #fff !important;
    }

    /* ── Footer ── */
    .custom-footer {
        position: fixed;
        bottom: 0; left: 0; right: 0;
        height: 44px;
        background: rgba(15,15,15,0.92);
        backdrop-filter: blur(12px);
        border-top: 1px solid #222;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
        color: #aaa;
        z-index: 999;
        gap: 16px;
    }
    .custom-footer strong { color: #f87171; font-weight: 500; }
</style>

<div class="custom-footer">
    <strong>⚠️ Not legal advice</strong> • Official sources only • Built by James Danas
</div>
""", unsafe_allow_html=True)

# ── Session state ────────────────────────────────────────────────────────────
for k, v in {
    "messages":        [],
    "sessions":        load_sessions(),
    "current_index":   -1,
    "total_queries":   0,
    "total_chunks":    0,
    "pipeline_ready":  False,
    "last_question":   "",
    "last_processed":  "",
    "pending_followups": None,   # FIX 1: lazy follow-ups stored here
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Pipeline ─────────────────────────────────────────────────────────────────
@st.cache_resource
def load_pipeline():
    from src.graph.rag_graph import NaijaCodexPipeline
    return NaijaCodexPipeline()

if not st.session_state.pipeline_ready:
    with st.spinner("Loading NaijaCodex..."):
        pipeline = load_pipeline()
        st.session_state.pipeline_ready = True
else:
    pipeline = load_pipeline()

# ── Helpers ───────────────────────────────────────────────────────────────────
def is_casual(text: str) -> bool:
    return not any(s in text.lower() for s in [
        "cbn","sec","ndpc","nrs","nitda","cyber","penalty","compliance","regulation",
        "bank","tax","fintech","data protection","capital","securities","law","act",
    ])

def casual_response(question: str) -> str:
    from langchain_groq import ChatGroq
    from langchain_core.messages import SystemMessage, HumanMessage
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.7, max_tokens=150)
    return llm.invoke([
        SystemMessage(content="You are NaijaCodex, a warm Nigerian regulatory expert. "
                               "Keep greetings to 1-3 sentences and invite a compliance question."),
        HumanMessage(content=question),
    ]).content.strip()

def clean_answer(text: str) -> str:
    """Remove SOURCE tags, Citations section, and force section labels to
    bold inline (never ## headings), with response text on the next line."""
    text = re.sub(r"\[SOURCE:[^\]]+\]", "", text)
    text = re.sub(r"\*\*Citations?\*\*[\s\S]*$", "", text, flags=re.IGNORECASE)
    _LABELS = r"(Direct Answer|Regulatory Basis|Cross-Regulation Notes|Confidence|Summary)"
    # Kill any ## headings the LLM may have emitted
    text = re.sub(rf"#{1,3}\s*{_LABELS}\s*:?\s*",
                  lambda m: f"\n\n**{m.group(1).strip()}**\n",
                  text, flags=re.IGNORECASE)
    # Normalise **Label** : → bold label + newline
    text = re.sub(rf"\*\*{_LABELS}\**\s*:?\s*",
                  lambda m: f"\n\n**{m.group(1).strip()}**\n",
                  text, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def format_citations_markdown(raw_cit: str) -> str:
    """Group citations by URL and render as clickable markdown links."""
    if not raw_cit or raw_cit == "No sources found.":
        return ""
    lines = [l.strip() for l in raw_cit.strip().split("\n") if l.strip()]
    if not lines:
        return ""

    url_to_items = defaultdict(list)
    for line in lines:
        m = re.search(r'https?://\S+', line)
        if m:
            url  = m.group(0).rstrip(".,)")
            desc = line[:m.start()].strip(" ·•-[]()").strip()
            sec  = re.search(r'Section\s+[\d\.]+', desc, re.IGNORECASE)
            url_to_items[url].append(sec.group() if sec else (desc[:50] if desc else url))
        else:
            url_to_items[None].append(line)

    md = []
    for url, items in url_to_items.items():
        if url is None:
            for item in items: md.append(f"- {item}")
        elif len(items) == 1:
            md.append(f"- [{items[0]}]({url})")
        else:
            doc  = items[0].split(" Section")[0].strip()
            secs = [re.search(r'Section\s+([\d\.]+)', it, re.IGNORECASE) for it in items]
            nums = [s.group(1) for s in secs if s]
            label = f"{doc} — Sections {', '.join(nums)}" if nums else "; ".join(items)
            md.append(f"- [{label}]({url})")
    return "\n".join(md)

def generate_followups(question: str, answer: str) -> list:
    """Generate 3 follow-up questions synchronously.
    Called inside st.status() so latency is hidden behind the existing spinner."""
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.6, max_tokens=120)
        prompt = (f"User asked: {question}\nAnswer: {answer[:400]}\n"
                  "Generate exactly 3 short follow-up questions (max 12 words each). "
                  "Output one per line, no numbering, no bullet points.")
        resp = llm.invoke([
            SystemMessage(content="You are a helpful regulatory assistant."),
            HumanMessage(content=prompt),
        ]).content
        qs = [q.strip("-• 1234567890.").strip() for q in resp.split("\n") if q.strip()][:3]
        return qs if len(qs) == 3 else [
            "What are the penalties for non-compliance?",
            "How does this compare to 2022 guidelines?",
            "What is the implementation timeline for fintechs?",
        ]
    except Exception:
        return [
            "What are the penalties for non-compliance?",
            "How does this compare to 2022 guidelines?",
            "What is the implementation timeline for fintechs?",
        ]

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:8px 0;'>
      <div style='font-size:2.4rem;'>🏛️</div>
      <h1 style='margin:0;color:#e0e0e0;font-size:1.3rem;'>NaijaCodex</h1>
      <p style='color:#555;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;'>
        Regulatory Intelligence
      </p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("＋ New Chat", use_container_width=True, type="primary"):
        st.session_state.current_index   = -1
        st.session_state.messages        = []
        st.session_state.pending_followups = None
        st.rerun()

    st.divider()
    c1, c2 = st.columns(2)
    with c1: st.metric("Queries", st.session_state.total_queries)
    with c2: st.metric("Chunks",  st.session_state.total_chunks)

    st.divider()
    st.markdown("**Try These**")
    for ex in [
        "CBN cybersecurity requirements for fintechs?",
        "Data protection obligations under NDPC 2023?",
        "NRS tax filing penalties for late returns?",
        "SEC capital requirements for stockbrokers?",
        "CBN open banking API security rules?",
        "Rights of data subjects under NDPA 2023?",
    ]:
        if st.button(ex, use_container_width=True, key="pill_" + ex[:12]):
            st.session_state.last_question = ex
            st.rerun()

    st.divider()
    st.markdown("**Upload Regulatory Document**")
    st.caption("⚠️ Uploaded files are not persisted on Streamlit Cloud.")
    uploaded = st.file_uploader("PDF or TXT", type=["pdf", "txt"], key="sidebar_upload")
    if uploaded and st.button("Ingest Document", type="primary", use_container_width=True):
        with st.spinner("Ingesting..."):
            try:
                import tempfile
                suffix = Path(uploaded.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = tmp.name
                # FIX 3: guard against missing method
                if hasattr(pipeline, "ingest_document"):
                    pipeline.ingest_document(tmp_path)
                    st.success(f"✅ {uploaded.name} ingested!")
                else:
                    st.warning("Document ingestion not yet supported via UI.")
            except Exception as e:
                st.error(f"Failed: {str(e)[:120]}")

    st.divider()
    st.markdown("**Regulatory Bodies**")
    for icon, short, url in [
        ("🏦", "CBN",   "https://www.cbn.gov.ng"),
        ("📈", "SEC",   "https://home.sec.gov.ng"),
        ("🔒", "NDPC",  "https://ndpc.gov.ng"),
        ("💰", "NRS",   "https://nrs.gov.ng"),
        ("💻", "NITDA", "https://nitda.gov.ng"),
    ]:
        st.markdown(
            f'<a href="{url}" target="_blank" style="color:#ccc;text-decoration:none;">'
            f'{icon} <strong>{short}</strong> ↗</a>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("**Recent Chats**")
    # FIX 6: correct delete index — iterate with real index, no reversed()
    sessions = st.session_state.sessions
    for i in range(len(sessions) - 1, max(len(sessions) - 9, -1), -1):
        sess  = sessions[i]
        label = sess.get("title", "Chat")[:32]
        col1, col2 = st.columns([5, 1])
        with col1:
            if st.button(f"↩ {label}...", key=f"load_{i}", use_container_width=True):
                st.session_state.current_index     = i
                st.session_state.messages          = sess["messages"][:]
                st.session_state.pending_followups = None
                st.rerun()
        with col2:
            if st.button("🗑", key=f"del_{i}", help="Delete"):
                st.session_state.sessions.pop(i)
                save_sessions(st.session_state.sessions)
                if st.session_state.current_index >= len(st.session_state.sessions):
                    st.session_state.current_index = -1
                    st.session_state.messages      = []
                st.rerun()

    st.divider()
    st.markdown("""
    <div style='color:#1e1e1e;font-size:10px;text-align:center;line-height:2;'>
      Built by <strong style='color:#2a2a2a;'>James Danas</strong><br>
      v1.0 · LangGraph · Pinecone · Groq · BAAI/bge
    </div>
    """, unsafe_allow_html=True)


# ── MAIN ──────────────────────────────────────────────────────────────────────
st.markdown("""
<h1 style='text-align:center;font-size:1.8rem;margin-bottom:4px;'>🏛️ NaijaCodex</h1>
<p style='text-align:center;color:#555;font-size:12px;'>CBN · SEC · NDPC · NRS · NITDA</p>
""", unsafe_allow_html=True)

if not st.session_state.messages:
    st.markdown("""
    <div style='text-align:center;padding:80px 20px;'>
      <div style='font-size:4rem;margin-bottom:20px;'>⚖️</div>
      <h2 style='color:#444;'>Ask anything about Nigerian regulations</h2>
      <p style='color:#333;'>Powered by RAG · Citation-backed · Use sidebar for example questions</p>
    </div>
    """, unsafe_allow_html=True)

# ── Chat history ──────────────────────────────────────────────────────────────
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="🏛️" if msg["role"] == "assistant" else None):
        st.markdown(msg["content"])

        if msg["role"] == "assistant" and msg.get("meta"):
            meta    = msg["meta"]
            raw_cit = meta.get("citations", "")

            if raw_cit and raw_cit != "No sources found.":
                sources_md = format_citations_markdown(raw_cit)
                with st.expander("📎 Official Sources", expanded=False):
                    st.markdown(sources_md)

            conf     = meta.get("confidence", "MED")
            agencies = ", ".join(meta.get("agencies_searched", [])) or "N/A"
            chunks   = meta.get("chunks", 0)
            qid      = meta.get("query_id", "")
            latency  = meta.get("latency_ms", 0)
            conflict = " · ⚠️ Conflict" if meta.get("conflict") else ""
            st.markdown(
                f"<div class='metadata-line'>{qid} · {agencies} · "
                f"{chunks} chunks · {conf[:4]} · {latency}ms{conflict}</div>",
                unsafe_allow_html=True,
            )

        # Copy button
        if msg["role"] == "assistant":
            if st.button("📋 Copy", key=f"copy_{idx}"):
                full = msg["content"]
                if msg.get("meta"):
                    raw_cit = msg["meta"].get("citations", "")
                    if raw_cit and raw_cit != "No sources found.":
                        full += "\n\nSources:\n" + raw_cit
                st.markdown(
                    f"<script>navigator.clipboard.writeText({json.dumps(full)});</script>",
                    unsafe_allow_html=True,
                )
                st.toast("Copied!", icon="📋")

# ── Follow-up suggestions ─────────────────────────────────────────────────────
# Cache by message count — no LLM call on plain reruns, no stale key clashes
_msgs = st.session_state.messages
if _msgs and _msgs[-1]["role"] == "assistant" and _msgs[-1].get("meta"):
    _cache_key = f"followups_{len(_msgs)}"
    if _cache_key not in st.session_state:
        _last_q = next((m["content"] for m in reversed(_msgs) if m["role"] == "user"), "")
        st.session_state[_cache_key] = generate_followups(_last_q, _msgs[-1]["content"])
    _suggestions = st.session_state.get(_cache_key, [])
    if _suggestions:
        st.markdown("**💡 Suggested follow-ups**")
        _cols = st.columns(3)
        for _i, _sug in enumerate(_suggestions):
            with _cols[_i]:
                if st.button(_sug, key=f"sug_{len(_msgs)}_{_i}", use_container_width=True):
                    st.session_state.last_question = _sug
                    st.rerun()

# ── Chat input ────────────────────────────────────────────────────────────────
question = st.chat_input("Ask about Nigerian regulations...")

if st.session_state.get("last_question"):
    question = st.session_state.last_question
    st.session_state.last_question = ""

# FIX 2: dedup by content+turn-count, not just content string
turn_key = f"{question}_{len(st.session_state.messages)}" if question else ""

if question and turn_key != st.session_state.get("last_processed", ""):
    st.session_state.last_processed    = turn_key
    st.session_state.pending_followups = None
    st.session_state.messages.append({"role": "user", "content": question, "meta": None})

    with st.status("Searching official regulations...", expanded=True) as status:
        status.update(label="Processing...", state="running")
        try:
            if is_casual(question):
                answer = casual_response(question)
                meta   = None
            else:
                result   = pipeline.query(question)
                answer   = clean_answer(result.get("answer", ""))
                raw_cit  = result.get("citations", "")
                conf     = result.get("confidence", "MED")
                agencies = result.get("agencies_searched", [])
                chunks   = len(result.get("retrieved_docs", []))
                qid      = result.get("query_id", "")
                latency  = result.get("latency_ms", 0)
                conflict = result.get("conflicts_found", False)
                meta = {
                    "citations":         raw_cit,
                    "confidence":        conf,
                    "agencies_searched": agencies,
                    "chunks":            chunks,
                    "query_id":          qid,
                    "latency_ms":        latency,
                    "conflict":          conflict,
                }
                st.session_state.total_queries += 1
                st.session_state.total_chunks  += chunks

            status.update(label="Answer ready", state="complete")
            st.session_state.messages.append({"role": "assistant", "content": answer, "meta": meta})

            # FIX 4: note about ephemeral filesystem
            title = question[:45] + ("..." if len(question) > 45 else "")
            if st.session_state.current_index == -1:
                st.session_state.sessions.append({
                    "id": str(len(st.session_state.sessions) + 1),
                    "title": title,
                    "messages": st.session_state.messages[:],
                })
                st.session_state.current_index = len(st.session_state.sessions) - 1
            else:
                idx = st.session_state.current_index
                st.session_state.sessions[idx]["messages"] = st.session_state.messages[:]
                st.session_state.sessions[idx]["title"] = title
            save_sessions(st.session_state.sessions)

        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant", "content": f"Error: {str(e)}", "meta": None,
            })
            status.update(label="Error occurred", state="error")

    st.rerun()