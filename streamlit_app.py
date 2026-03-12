"""
streamlit_app.py — NaijaCodex front-end built with Streamlit.
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

# ── Persistence ───────────────────────────────────────────────────────────────
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
        pass

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    :root {
        --bg: #0f0f0f;
        --chat-bg-user: linear-gradient(135deg, #1d4ed8, #3b82f6);
        --chat-bg-ai: #1e1e1e;
        --border: rgba(59, 130, 246, 0.18);
        --text: #e5e7eb;
        --muted: #9ca3af;
        --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: var(--bg) !important;
        color: var(--text) !important;
        font-family: var(--font) !important;
    }

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

    [data-testid="stExpander"] { font-size: 9.5px !important; line-height: 1.4 !important; }
    [data-testid="stExpander"] p,
    [data-testid="stExpander"] a,
    [data-testid="stExpander"] div,
    [data-testid="stExpander"] li { font-size: 9.5px !important; }
    [data-testid="stExpander"] a { color: #3b82f6 !important; text-decoration: none !important; }
    [data-testid="stExpander"] a:hover { text-decoration: underline !important; }

    .metadata-line { font-size: 9px !important; color: #666 !important; margin-top: 8px !important; }

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
    <strong>⚠️ Not legal advice</strong> &nbsp;·&nbsp; Official sources only &nbsp;·&nbsp; Built by James Danas
</div>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "messages": [],
    "sessions": load_sessions(),
    "current_index": -1,
    "total_queries": 0,
    "total_chunks": 0,
    "pipeline_ready": False,
    "last_question": "",
    "last_processed": "",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Pipeline ──────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
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
_REGULATORY_KEYWORDS = {
    "cbn","sec","ndpc","nrs","nitda","cyber","penalty","compliance","regulation",
    "bank","tax","fintech","data protection","capital","securities","law","act",
    "license","licence","circular","guideline","framework","directive","policy",
}

def is_casual(text: str) -> bool:
    t = text.lower()
    return not any(kw in t for kw in _REGULATORY_KEYWORDS)

@st.cache_data(show_spinner=False, ttl=3600)
def casual_response(question: str) -> str:
    """Cached casual reply — uses 8b model for speed."""
    from langchain_groq import ChatGroq
    from langchain_core.messages import SystemMessage, HumanMessage
    llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.7, max_tokens=120)
    return llm.invoke([
        SystemMessage(content=(
            "You are NaijaCodex, a warm Nigerian regulatory assistant. "
            "For greetings reply in 1-2 sentences and invite a compliance question."
        )),
        HumanMessage(content=question),
    ]).content.strip()

def clean_answer(text: str) -> str:
    text = re.sub(r"\[SOURCE:[^\]]+\]", "", text)
    text = re.sub(r"\*\*Citations?\*\*[\s\S]*$", "", text, flags=re.IGNORECASE)
    _LABELS = r"(Direct Answer|Regulatory Basis|Cross-Regulation Notes|Confidence|Summary)"
    text = re.sub(rf"#{1,3}\s*{_LABELS}\s*:?\s*",
                  lambda m: f"\n\n**{m.group(1).strip()}**\n",
                  text, flags=re.IGNORECASE)
    text = re.sub(rf"\*\*{_LABELS}\**\s*:?\s*",
                  lambda m: f"\n\n**{m.group(1).strip()}**\n",
                  text, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def format_citations_markdown(raw_cit: str) -> str:
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

@st.cache_data(show_spinner=False, ttl=3600)
def generate_followups(question: str, answer_snippet: str) -> list:
    """Cached follow-up suggestions — uses 8b model, cached by question+answer."""
    try:
        from langchain_groq import ChatGroq
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.5, max_tokens=100)
        prompt = (
            f"User asked: {question}\nAnswer summary: {answer_snippet[:300]}\n"
            "Generate exactly 3 short follow-up questions (max 10 words each). "
            "One per line, no numbering, no bullets."
        )
        resp = llm.invoke([
            SystemMessage(content="You are a regulatory assistant. Be concise."),
            HumanMessage(content=prompt),
        ]).content
        qs = [q.strip("-• 1234567890.").strip() for q in resp.split("\n") if q.strip()][:3]
        return qs if len(qs) == 3 else _default_followups()
    except Exception:
        return _default_followups()

def _default_followups():
    return [
        "What are the penalties for non-compliance?",
        "How does this apply to fintechs specifically?",
        "What is the implementation timeline?",
    ]

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:8px 0;'>
      <div style='font-size:2.2rem;'>🏛️</div>
      <h1 style='margin:0;color:#e0e0e0;font-size:1.3rem;'>NaijaCodex</h1>
      <p style='color:#555;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;'>
        Regulatory Intelligence
      </p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("+ New Chat", use_container_width=True, type="primary"):
        st.session_state.current_index = -1
        st.session_state.messages      = []
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
    st.markdown("**Upload Document**")
    st.caption("Not persisted on Streamlit Cloud.")
    uploaded = st.file_uploader("PDF or TXT", type=["pdf", "txt"], key="sidebar_upload")
    if uploaded and st.button("Ingest", type="primary", use_container_width=True):
        with st.spinner("Ingesting..."):
            try:
                import tempfile
                suffix = Path(uploaded.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = tmp.name
                if hasattr(pipeline, "ingest_document"):
                    pipeline.ingest_document(tmp_path)
                    st.success(f"{uploaded.name} ingested!")
                else:
                    st.warning("Ingestion not available via UI.")
            except Exception as e:
                st.error(f"Failed: {str(e)[:120]}")

    st.divider()
    st.markdown("**Regulatory Bodies**")
    for short, url in [
        ("CBN",   "https://www.cbn.gov.ng"),
        ("SEC",   "https://home.sec.gov.ng"),
        ("NDPC",  "https://ndpc.gov.ng"),
        ("NRS",   "https://nrs.gov.ng"),
        ("NITDA", "https://nitda.gov.ng"),
    ]:
        st.markdown(
            f'<a href="{url}" target="_blank" style="color:#ccc;text-decoration:none;">'
            f'<strong>{short}</strong> &nearr;</a>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("**Recent Chats**")
    sessions = st.session_state.sessions
    for i in range(len(sessions) - 1, max(len(sessions) - 9, -1), -1):
        sess  = sessions[i]
        label = sess.get("title", "Chat")[:32]
        col1, col2 = st.columns([5, 1])
        with col1:
            if st.button(f"{label}...", key=f"load_{i}", use_container_width=True):
                st.session_state.current_index = i
                st.session_state.messages = sess["messages"][:]
                st.rerun()
        with col2:
            if st.button("x", key=f"del_{i}", help="Delete"):
                st.session_state.sessions.pop(i)
                save_sessions(st.session_state.sessions)
                if st.session_state.current_index >= len(st.session_state.sessions):
                    st.session_state.current_index = -1
                    st.session_state.messages = []
                st.rerun()

    st.divider()
    st.markdown("""
    <div style='color:#333;font-size:10px;text-align:center;line-height:2;'>
      Built by <strong style='color:#444;'>James Danas</strong><br>
      v1.0 · LangGraph · Pinecone · Groq
    </div>
    """, unsafe_allow_html=True)

# ── MAIN ──────────────────────────────────────────────────────────────────────
st.markdown("""
<h1 style='text-align:center;font-size:1.8rem;margin-bottom:4px;'>NaijaCodex</h1>
<p style='text-align:center;color:#555;font-size:12px;'>CBN · SEC · NDPC · NRS · NITDA</p>
""", unsafe_allow_html=True)

if not st.session_state.messages:
    st.markdown("""
    <div style='text-align:center;padding:80px 20px;'>
      <h2 style='color:#444;'>Ask anything about Nigerian regulations</h2>
      <p style='color:#333;'>RAG-powered · Citation-backed · Use sidebar for examples</p>
    </div>
    """, unsafe_allow_html=True)

# ── Chat history ──────────────────────────────────────────────────────────────
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="🏛️" if msg["role"] == "assistant" else None):
        st.markdown(msg["content"])

        if msg["role"] == "assistant" and msg.get("meta"):
            meta     = msg["meta"]
            raw_cit  = meta.get("citations", "")

            if raw_cit and raw_cit != "No sources found.":
                sources_md = format_citations_markdown(raw_cit)
                with st.expander("Sources", expanded=False):
                    st.markdown(sources_md)

            conf     = meta.get("confidence", "MED")
            agencies = ", ".join(meta.get("agencies_searched", [])) or "N/A"
            chunks   = meta.get("chunks", 0)
            latency  = meta.get("latency_ms", 0)
            conflict = " · Conflict detected" if meta.get("conflict") else ""
            st.markdown(
                f"<div class='metadata-line'>{agencies} · {chunks} chunks · "
                f"{conf[:4]} · {latency}ms{conflict}</div>",
                unsafe_allow_html=True,
            )

# ── Follow-up suggestions ─────────────────────────────────────────────────────
_msgs = st.session_state.messages
if _msgs and _msgs[-1]["role"] == "assistant" and _msgs[-1].get("meta"):
    _cache_key = f"followups_{len(_msgs)}"
    if _cache_key not in st.session_state:
        _last_q = next((m["content"] for m in reversed(_msgs) if m["role"] == "user"), "")
        _snippet = _msgs[-1]["content"][:300]
        st.session_state[_cache_key] = generate_followups(_last_q, _snippet)
    _suggestions = st.session_state.get(_cache_key, [])
    if _suggestions:
        st.markdown("<p style='color:#555;font-size:11px;margin-bottom:4px;'>Suggested follow-ups</p>",
                    unsafe_allow_html=True)
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

turn_key = f"{question}_{len(st.session_state.messages)}" if question else ""

if question and turn_key != st.session_state.get("last_processed", ""):
    st.session_state.last_processed = turn_key
    st.session_state.messages.append({"role": "user", "content": question, "meta": None})

    with st.status("Searching regulations...", expanded=False) as status:
        try:
            if is_casual(question):
                answer = casual_response(question)
                meta   = None
            else:
                result = pipeline.query(question)
                answer = clean_answer(result.get("answer", ""))
                meta   = {
                    "citations":        result.get("citations", ""),
                    "confidence":       result.get("confidence", "MED"),
                    "agencies_searched": result.get("agencies_searched", []),
                    "chunks":           len(result.get("retrieved_docs", [])),
                    "query_id":         result.get("query_id", ""),
                    "latency_ms":       result.get("latency_ms", 0),
                    "conflict":         result.get("conflicts_found", False),
                }
                st.session_state.total_queries += 1
                st.session_state.total_chunks  += meta["chunks"]

            status.update(label="Done", state="complete")
            st.session_state.messages.append(
                {"role": "assistant", "content": answer, "meta": meta}
            )

            title = question[:45] + ("..." if len(question) > 45 else "")
            if st.session_state.current_index == -1:
                st.session_state.sessions.append({
                    "id":       str(len(st.session_state.sessions) + 1),
                    "title":    title,
                    "messages": st.session_state.messages[:],
                })
                st.session_state.current_index = len(st.session_state.sessions) - 1
            else:
                i = st.session_state.current_index
                st.session_state.sessions[i]["messages"] = st.session_state.messages[:]
                st.session_state.sessions[i]["title"]    = title
            save_sessions(st.session_state.sessions)

        except Exception as e:
            st.session_state.messages.append(
                {"role": "assistant", "content": f"Error: {str(e)}", "meta": None}
            )
            status.update(label="Error", state="error")

    st.rerun()
