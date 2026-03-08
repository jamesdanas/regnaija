"""
app.py — NaijaCodex UI
"""
import warnings
warnings.filterwarnings("ignore")
import sys
sys.path.insert(0, ".")

import gradio as gr
from dotenv import load_dotenv
load_dotenv()

from src.graph.rag_graph import NaijaCodexPipeline

print("Starting NaijaCodex...")
pipeline = NaijaCodexPipeline()
print("Ready")

EXAMPLES = [
    "CBN cybersecurity requirements for fintechs?",
    "Data protection obligations under NDPC 2023?",
    "NRS tax filing penalties for late returns?",
    "SEC capital requirements for stockbrokers?",
    "CBN open banking API security rules?",
    "Rights of data subjects under NDPA 2023?",
]

sessions = {}
session_labels = {}
current_sid = ["session_1"]
counter = [1]


def _new_sid():
    counter[0] += 1
    sid = f"session_{counter[0]}"
    current_sid[0] = sid
    return sid

def new_chat():
    _new_sid()
    return [], "", _build_sidebar_html()

def _build_sidebar_html():
    if not sessions:
        return "*No conversations yet.*"
    parts = []
    for sid in reversed(list(sessions.keys())):
        hist = sessions.get(sid, [])
        if not hist:
            continue
        label = session_labels.get(sid, hist[0][0])[:38]
        count = len(hist)
        parts.append(
            f"**{label}...**  \n"
            f"<small>{count} turn(s) · `{sid}`</small>"
        )
    return "\n\n---\n\n".join(parts) if parts else "*No conversations yet.*"

def load_session(sid_input):
    sid = sid_input.strip()
    if sid in sessions:
        return sessions[sid], f"Loaded: {sid}", _build_sidebar_html()
    return [], f"Session `{sid}` not found.", _build_sidebar_html()

def toggle_sidebar(is_open):
    new_state = not is_open
    # When open: show full sidebar content, button shows ◀
    # When closed: hide content, button shows ▶
    return (
        new_state,
        gr.update(visible=new_state),   # sidebar_col
        gr.update(value="◀" if new_state else "▶"),  # toggle btn label
    )

def _clean_answer(text):
    import re
    text = re.sub(r"\[SOURCE:[^\]]+\]", "", text)
    text = re.sub(r"\*\*Citations?\*\*[\s\S]*?(?=\*\*|\Z)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^CITATIONS[\s\S]*?(?=^\*\*|\Z)", "", text, flags=re.MULTILINE)
    def caps_to_bold(m):
        return "**" + m.group(0).title() + "**"
    text = re.sub(
        r"^(DIRECT ANSWER|REGULATORY BASIS|CROSS-REGULATION NOTES|CONFIDENCE|CITATIONS)",
        caps_to_bold, text, flags=re.MULTILINE
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

CASUAL_SYSTEM = (
    "You are NaijaCodex, a warm and professional AI assistant specialising in "
    "Nigerian regulatory and compliance law (CBN, SEC, NDPC, NRS, NITDA). "
    "For greetings and small talk, respond naturally and briefly in 1-3 sentences. "
    "Do NOT use any regulatory format or cite sources for casual messages. "
    "If the user introduces themselves, acknowledge them warmly by name. "
    "Always gently invite them to ask a compliance question."
)

CASUAL_TRIGGERS = [
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "how are you", "who are you", "what are you", "what is naijacodex",
    "thanks", "thank you", "okay", "ok", "bye", "goodbye", "great", "nice",
    "i am", "my name is", "i'm", "lol", "haha", "cool", "awesome",
    "what can you do", "help me", "what do you do",
]

def _is_casual(text: str) -> bool:
    t = text.lower().strip().rstrip("!?.,")
    words = t.split()

    # Always casual if very short and no regulatory keywords
    regulatory_signals = [
        "cbn", "sec", "ndpc", "nrs", "nitda", "bank", "tax", "regulation",
        "compliance", "license", "penalty", "fintech", "data protection",
        "capital", "securities", "requirement", "obligation", "law", "act",
        "section", "policy", "framework", "guideline", "filing",
    ]
    has_regulatory = any(sig in t for sig in regulatory_signals)
    if has_regulatory:
        return False

    # Short message — check if it contains any casual trigger
    if len(words) <= 8:
        for trigger in CASUAL_TRIGGERS:
            if trigger in t:
                return True
        # Pure short messages with no regulatory content are casual
        if len(words) <= 3:
            return True

    return False


def _casual_reply(question: str) -> str:
    from langchain_groq import ChatGroq
    from langchain_core.messages import SystemMessage, HumanMessage
    import os
    llm = ChatGroq(
        model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        temperature = 0.7,
        max_tokens = 120,
    )
    resp = llm.invoke([
        SystemMessage(content=CASUAL_SYSTEM),
        HumanMessage(content=question),
    ])
    return resp.content.strip()


REGULATORY_SIGNALS = [
    "cbn", "sec", "ndpc", "nrs", "nitda", "bank", "tax", "regulation",
    "compliance", "license", "penalty", "fintech", "data protection",
    "capital", "securities", "requirement", "obligation", "law", "act",
    "section", "policy", "framework", "guideline", "filing", "cybersecurity",
]

def _is_casual(text: str) -> bool:
    t = text.lower().strip().rstrip("!?.,")

    # If ANY regulatory keyword is present, always go to RAG
    if any(sig in t for sig in REGULATORY_SIGNALS):
        return False

    # No regulatory signal found — treat as casual regardless of length
    return True

def _casual_reply(question: str) -> str:
    from langchain_groq import ChatGroq
    from langchain_core.messages import SystemMessage, HumanMessage
    import os
    llm = ChatGroq(
        model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        temperature = 0.7,
        max_tokens = 120,
    )
    system = (
        "You are NaijaCodex, a warm and professional AI assistant specialising in "
        "Nigerian regulatory and compliance law covering CBN, SEC, NDPC, NRS, and NITDA. "
        "For greetings and small talk, respond naturally in 1-3 sentences only. "
        "If the user introduces themselves, greet them warmly by name. "
        "Never output regulatory format, citations, or sources for casual messages. "
        "Always invite them to ask a compliance question."
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=question)])
    return resp.content.strip()

def query_naijacodex(question, history):
    if not question or not question.strip():
        return history, ""
    try:
        # Handle casual messages — no Pinecone, no citations
        if _is_casual(question.strip()):
            answer = _casual_reply(question.strip())
            history = list(history or [])
            history.append((question, answer))
            sid = current_sid[0]
            if sid not in sessions:
                sessions[sid] = []
                session_labels[sid] = question
            sessions[sid].append((question, answer))
            return history, ""

        import threading
        result_holder = [None]
        error_holder = [None]
        def _run():
            try:
                result_holder[0] = pipeline.query(question.strip())
            except Exception as e:
                error_holder[0] = e
        t = threading.Thread(target=_run)
        t.start()
        t.join(timeout=40)
        if t.is_alive() or result_holder[0] is None:
            history = list(history or [])
            history.append((question, 'Sorry, that query timed out. Please try a more specific regulatory question, e.g. \'What are CBN requirements for fintechs?\' '))
            return history, ''
        if error_holder[0]:
            raise error_holder[0]
        result = result_holder[0]
        raw_ans = result.get("answer", "No answer generated.")
        raw_cit = result.get("citations", "")
        conf = result.get("confidence", "")
        agencies = ", ".join(result.get("agencies_searched", []))
        chunks = len(result.get("retrieved_docs", []))
        qid = result.get("query_id", "")
        latency = result.get("latency_ms", 0)
        conflict = result.get("conflicts_found", False)

        clean = _clean_answer(raw_ans)

        citations_block = ""
        if raw_cit and raw_cit != "No sources found.":
            lines = [
                f"<small>{l.strip()}</small>"
                for l in raw_cit.strip().split("\n") if l.strip()
            ]
            if lines:
                citations_block = (
                    "\n\n<small style='color:#444'>── Sources ──</small>\n"
                    + "\n".join(lines)
                )

        conflict_note = " · Conflict" if conflict else ""
        meta = (
            f"\n\n<small style='color:#444'>"
            f"{qid} · {agencies} · {chunks} chunks · "
            f"{conf[:4]} · {latency}ms{conflict_note}</small>"
        )

        full_answer = clean + citations_block + meta
        history = list(history or [])
        history.append((question, full_answer))

        sid = current_sid[0]
        if sid not in sessions:
            sessions[sid] = []
            session_labels[sid] = question
        sessions[sid].append((question, full_answer))

    except TimeoutError:
        history = list(history or [])
        history.append((question,
            "Sorry, that query took too long to process. "
            "Please try rephrasing it more specifically, for example: "
            "'What are CBN requirements for setting up a fintech company?'"
        ))
    except Exception as e:
        history = list(history or [])
        history.append((question, f"Error: {str(e)}"))

    return history, ""


CSS = """
body, .gradio-container {
    background: #0d0d0d !important;
    color: #e8e8e8 !important;
    font-family: Inter, sans-serif !important;
}
#toggle-col {
    background: #111 !important;
    border-right: 1px solid #1e1e1e !important;
    padding: 12px 6px !important;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
}
#sidebar-col {
    background: #111 !important;
    border-right: 1px solid #1e1e1e !important;
    padding: 16px 12px !important;
    min-height: 100vh;
}
#toggle-btn {
    background: #1a1a1a !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 8px !important;
    color: #aaa !important;
    font-size: 14px !important;
    width: 32px !important;
    min-width: 32px !important;
    height: 32px !important;
    padding: 0 !important;
}
#toggle-btn:hover { background: #252525 !important; color: #fff !important; }
#new-chat-btn {
    background: #1a1a1a !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 10px !important;
    color: #ccc !important;
    font-size: 13px !important;
    width: 100%;
    margin-bottom: 8px;
}
#new-chat-btn:hover { background: #222 !important; color: #fff !important; }
#load-btn {
    background: #1a1a1a !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 8px !important;
    color: #aaa !important;
    font-size: 12px !important;
}
#load-btn:hover { background: #222 !important; color: #fff !important; }
#session-input textarea, #session-input input {
    background: #161616 !important;
    border: 1px solid #252525 !important;
    border-radius: 8px !important;
    color: #ccc !important;
    font-size: 12px !important;
    font-family: monospace !important;
}
.pill button {
    background: #161616 !important;
    border: 1px solid #222 !important;
    border-radius: 999px !important;
    color: #999 !important;
    font-size: 11px !important;
    padding: 5px 11px !important;
}
.pill button:hover { background: #1e1e1e !important; color: #eee !important; }
#chatbot { background: #0d0d0d !important; border: none !important; }
#chatbot .message.user div {
    background: #1c1c2e !important;
    border-radius: 14px !important;
    padding: 12px 16px !important;
    font-size: 14px !important;
    max-width: 75%;
    margin-left: auto;
}
#chatbot .message.bot div {
    background: transparent !important;
    font-size: 14px !important;
    line-height: 1.75 !important;
    padding: 0 !important;
}
#chatbot small { font-size: 11px !important; color: #555 !important; }
#question-box textarea {
    background: #161616 !important;
    border: 1px solid #252525 !important;
    border-radius: 14px !important;
    color: #e8e8e8 !important;
    font-size: 14px !important;
}
#search-btn {
    background: #2563eb !important;
    border: none !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-weight: 600 !important;
}
#search-btn:hover { background: #1d4ed8 !important; }
#clear-btn {
    background: transparent !important;
    border: 1px solid #252525 !important;
    border-radius: 10px !important;
    color: #666 !important;
}
#footer { text-align: center; padding: 14px 0 4px; font-size: 11px; color: #444; }
footer { display: none !important; }
"""

with gr.Blocks(title="NaijaCodex", theme=gr.themes.Base(), css=CSS) as demo:

    sidebar_open = gr.State(True)

    with gr.Row(equal_height=True):

        #  Toggle rail — always visible 
        with gr.Column(scale=0, min_width=48, elem_id="toggle-col"):
            toggle_btn = gr.Button("◀", elem_id="toggle-btn")

        #  Sidebar content — collapsible 
        with gr.Column(scale=1, elem_id="sidebar-col", visible=True) as sidebar_col:
            new_chat_btn = gr.Button("+ New Chat", elem_id="new-chat-btn")
            gr.Markdown("---")
            gr.Markdown("**Coverage**\n\n CBN\n\n SEC\n\n NDPC\n\n NRS\n\n NITDA")
            gr.Markdown("---")
            gr.Markdown("**Load Conversation**")
            gr.Markdown("<small>Paste a session ID to reload.</small>")
            session_input = gr.Textbox(
                placeholder="e.g. session_2",
                show_label=False, lines=1, elem_id="session-input",
            )
            load_btn    = gr.Button("Load →", elem_id="load-btn", size="sm")
            load_status = gr.Markdown("")
            gr.Markdown("---")
            gr.Markdown("**Recent Conversations**")
            sidebar_history = gr.Markdown("*No conversations yet.*")

        #  Main 
        with gr.Column(scale=4):
            gr.HTML("""
            <div style='text-align:center; padding:28px 0 12px;'>
                <h1 style='font-size:1.9rem; font-weight:700; margin:0;'> NaijaCodex</h1>
                <p style='color:#777; font-size:13px; margin:6px 0 0;'>Nigerian Regulatory Intelligence Platform</p>
                <p style='color:#444; font-size:11px; margin:4px 0 0;'>CBN · SEC · NDPC · NRS · NITDA</p>
            </div>
            """)

            with gr.Row():
                ex_btns = []
                for ex in EXAMPLES:
                    with gr.Column(min_width=1, elem_classes=["pill"]):
                        b = gr.Button(ex, size="sm")
                        ex_btns.append(b)

            chatbot = gr.Chatbot(
                value=[], elem_id="chatbot", height=440,
                show_label=False, bubble_full_width=False, render_markdown=True,
            )

            with gr.Row():
                question_box = gr.Textbox(
                    placeholder="Ask anything about Nigerian regulations...",
                    show_label=False, lines=1, scale=6, elem_id="question-box",
                )
                search_btn = gr.Button("Search", elem_id="search-btn", scale=1)
                clear_btn  = gr.Button("Clear",  elem_id="clear-btn",  scale=1)

            gr.HTML("""
            <div id='footer'>
                Regulatory information only — not legal advice.
                Consult a qualified Nigerian lawyer for specific situations.<br><br>
                Built by <strong style='color:#888;'>James Danas</strong>
            </div>
            """)

    # Events 

    def respond(question, history):
        h, q = query_naijacodex(question, history)
        return h, q, _build_sidebar_html()

    toggle_btn.click(
        fn=toggle_sidebar,
        inputs=[sidebar_open],
        outputs=[sidebar_open, sidebar_col, toggle_btn],
        api_name=False,
    )
    search_btn.click(fn=respond, inputs=[question_box, chatbot], outputs=[chatbot, question_box, sidebar_history], api_name=False)
    question_box.submit(fn=respond, inputs=[question_box, chatbot], outputs=[chatbot, question_box, sidebar_history], api_name=False)
    clear_btn.click(fn=lambda h: (h, ""), inputs=[chatbot], outputs=[chatbot, question_box], api_name=False)
    new_chat_btn.click(fn=new_chat, outputs=[chatbot, question_box, sidebar_history], api_name=False)
    load_btn.click(fn=load_session, inputs=[session_input], outputs=[chatbot, load_status, sidebar_history], api_name=False)
    session_input.submit(fn=load_session, inputs=[session_input], outputs=[chatbot, load_status, sidebar_history], api_name=False)
    for btn, ex in zip(ex_btns, EXAMPLES):
        btn.click(fn=lambda e=ex: e, outputs=[question_box], api_name=False)

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, show_error=True, share=True)