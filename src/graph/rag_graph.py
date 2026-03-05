"""
src/graph/rag_graph.py
LangGraph pipeline for NaijaCodex.
Connects all nodes into a stateful agentic workflow.
"""

from functools import partial
from langgraph.graph import StateGraph, END

from src.graph.state import NaijaCodexState
from src.graph.nodes import (
    query_analyser,
    retrieval_agent,
    conflict_detector,
    answer_synthesiser,
    confidence_guard,
)
from src.retrieval.embedder import NaijaCodexEmbedder
from src.retrieval.vector_store import NaijaCodexVectorStore


def blocked_response(state: NaijaCodexState) -> NaijaCodexState:
    """Returns a safe response when confidence is too low."""
    return {
        **state,
        "answer": (
            "I could not find sufficient regulatory information to "
            "answer this question confidently from the NaijaCodex "
            "document library.\\n\\n"
            "Recommended actions:\\n"
            "1. Rephrase your question with specific regulatory terms\\n"
            "2. Specify which agency you are asking about "
            "(CBN, SEC, NDPC, NRS, NITDA)\\n"
            "3. Check directly with the relevant regulatory agency\\n"
            "4. Consult a qualified Nigerian legal practitioner"
        ),
        "citations": "No sources found.",
        "confidence": "BLOCKED — Insufficient regulatory context found",
    }


def build_graph(store: NaijaCodexVectorStore) -> StateGraph:
    """
    Builds and compiles the NaijaCodex LangGraph pipeline.

    Flow:
    query_analyser -> retrieval_agent -> conflict_detector
        -> confidence_guard (conditional)
            -> pass  -> answer_synthesiser -> END
            -> block -> blocked_response   -> END
    """
    graph = StateGraph(NaijaCodexState)

    # Add nodes
    graph.add_node("query_analyser", query_analyser)
    graph.add_node("retrieval_agent", partial(retrieval_agent, store=store))
    graph.add_node("conflict_detector", conflict_detector)
    graph.add_node("answer_synthesiser", answer_synthesiser)
    graph.add_node("blocked_response", blocked_response)

    # Add edges
    graph.set_entry_point("query_analyser")
    graph.add_edge("query_analyser", "retrieval_agent")
    graph.add_edge("retrieval_agent", "conflict_detector")

    # Conditional edge after conflict detector
    graph.add_conditional_edges(
        "conflict_detector",
        confidence_guard,
        {
            "pass": "answer_synthesiser",
            "block": "blocked_response",
        }
    )

    graph.add_edge("answer_synthesiser", END)
    graph.add_edge("blocked_response", END)

    return graph.compile()


class NaijaCodexPipeline:
    """
    Main interface for the NaijaCodex agentic RAG pipeline.
    Initialize once, call .query() for each question.
    """

    def __init__(self):
        print("Initialising NaijaCodex Pipeline...")
        embedder = NaijaCodexEmbedder()
        store = NaijaCodexVectorStore(embedder=embedder)
        self.graph = build_graph(store)
        print("Pipeline ready")

    def query(self, question: str, session_id: str = "default") -> dict:
        """
        Runs a question through the full agentic pipeline.
        Returns the final state with answer and citations.
        """
        from datetime import datetime
        start = datetime.now()

        initial_state: NaijaCodexState = {
            "query": question,
            "session_id": session_id,
            "detected_agencies": [],
            "sub_queries": [],
            "retrieved_docs": [],
            "retrieval_scores": [],
            "conflicts_found": False,
            "conflict_details": "",
            "context": "",
            "answer": "",
            "citations": "",
            "confidence":"",
            "query_id": "",
            "agencies_searched": [],
            "latency_ms": 0,
            "error": None,
        }

        result = self.graph.invoke(initial_state)

        latency = int(
            (datetime.now() - start).total_seconds() * 1000
        )
        result["latency_ms"] = latency

        return result

    def print_result(self, result: dict):
        """Pretty prints pipeline result."""
        print("\\n" + "=" * 60)
        print(f"NAIJACODEX  [{result.get('query_id', 'N/A')}]")
        print("=" * 60)
        print(f"Query: {result['query']}")
        print(f"Agencies: {', '.join(result.get('agencies_searched', []))}")
        print(f"Chunks: {len(result.get('retrieved_docs', []))}")
        print(f"Conflicts: {result.get('conflicts_found', False)}")
        print(f"Confidence:{result.get('confidence', 'N/A')}")
        print(f"Latency: {result.get('latency_ms', 0)}ms")
        print()
        print("ANSWER:")
        print(result.get("answer", "No answer generated"))
        print()
        print("CITATIONS:")
        print(result.get("citations", "No citations"))
        print("=" * 60)
