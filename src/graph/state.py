"""
src/graph/state.py
Defines the state object that flows through the LangGraph pipeline.
Every node reads from and writes to this state.
"""

from typing import TypedDict
from langchain_core.documents import Document


class RegNaijaState(TypedDict):
    # Input
    query: str
    session_id: str

    # Query analysis
    detected_agencies: list[str]
    sub_queries: list[str]

    # Retrieval
    retrieved_docs: list[tuple]   # List of (Document, score)
    retrieval_scores: list[float]

    # Conflict detection
    conflicts_found: bool
    conflict_details: str

    # Generation
    context: str
    answer: str
    citations: str
    confidence: str

    # Metadata
    query_id: str
    agencies_searched: list[str]
    latency_ms: int
    
error: str | None