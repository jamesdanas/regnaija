"""
src/graph/state.py
Defines the state object that flows through the LangGraph pipeline.
Every node reads from and writes to this state.
"""

from typing import List, Optional, TypedDict
from langchain_core.documents import Document


class NaijaCodexState(TypedDict):
    # Input
    query: str
    session_id: str

    # Query analysis
    detected_agencies: List[str]
    sub_queries: List[str]

    # Retrieval
    retrieved_docs: List[tuple]   # List of (Document, score)
    retrieval_scores: List[float]

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
    agencies_searched: List[str]
    latency_ms: int
    error: Optional[str]
