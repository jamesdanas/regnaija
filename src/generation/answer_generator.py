"""
src/generation/answer_generator.py
Zero-hallucination answer engine for NaijaCodex.
"""

import os
import uuid
from typing import List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.documents import Document

from src.generation.system_prompt import NAIJACODEX_SYSTEM_PROMPT
from src.generation.citation_builder import (
    build_citations, format_citations, format_context_for_llm
)
from src.retrieval.vector_store import NaijaCodexVectorStore
from dotenv import load_dotenv

load_dotenv()


@dataclass
class NaijaCodexAnswer:
    query_id: str
    query: str
    answer: str
    citations: str
    confidence: str
    agencies_searched: List[str]
    retrieval_count: int
    timestamp: str
    latency_ms: int
 

class AnswerGenerator:
    """
    Generates zero-hallucination answers with full citations.

    Flow:
    1. Search Pinecone for relevant chunks
    2. Format chunks as labelled context
    3. Call Groq LLM with system prompt + context + query
    4. Build structured citations
    5. Return complete NaijaCodexAnswer
    """

    ALL_AGENCIES = ["CBN", "SEC", "NDPC", "NRS", "NITDA"]

    def __init__(self, vector_store: NaijaCodexVectorStore):
        self.store = vector_store
        self.llm = ChatGroq(
            model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
            temperature = 0,        # Zero temp = deterministic, less hallucination
            max_tokens = 2048,
        )

    def _detect_relevant_agencies(self, query: str) -> List[str]:
        """
        Detects which agencies are relevant to a query.
        Returns all agencies if unclear — better to search too many
        than miss a relevant regulation.
        """
        query_lower = query.lower()
        relevant = []

        agency_keywords = {
            "CBN": ["cbn", "bank", "fintech", "payment", "lending",
                      "microfinance", "monetary", "cybersecurity",
                      "open banking", "consumer protection"],
            "SEC": ["sec", "securities", "capital market", "investment",
                      "stockbroker", "shares", "ipo", "bonds"],
            "NDPC": ["data protection", "privacy", "ndpc", "personal data",
                      "data subject", "gdpr", "ndpa"],
            "NRS": ["tax", "nrs", "firs", "income tax", "vat", "levy",
                      "withholding", "cit", "revenue"],
            "NITDA": ["nitda", "it policy", "technology development",
                      "digital", "ndpr"],
        }

        for agency, keywords in agency_keywords.items():
            if any(kw in query_lower for kw in keywords):
                relevant.append(agency)

        # If nothing detected search all agencies
        return relevant if relevant else self.ALL_AGENCIES

    def _calculate_confidence(
        self,
        retrieved_docs: List[Tuple[Document, float]]
    ) -> str:
        """Calculates confidence based on retrieval scores."""
        if not retrieved_docs:
            return "LOW — No relevant documents found"

        top_score = retrieved_docs[0][1]

        if top_score >= 0.75:
            return "HIGH — Direct match found in regulatory documents"
        elif top_score >= 0.55:
            return "MEDIUM — Related provisions found, review sources"
        else:
            return "LOW — Weak match, verify with official sources"

    def answer(
        self,
        query: str,
        agencies: Optional[List[str]] = None,
        top_k: int = 6,
    ) -> NaijaCodexAnswer:
        """
        Main method. Answers a regulatory compliance question.
        """
        start_time = datetime.now()
        query_id = f"NCX-{uuid.uuid4().hex[:8].upper()}"

        # Detect relevant agencies
        search_agencies = agencies or self._detect_relevant_agencies(query)

        # Search Pinecone across relevant agencies
        if len(search_agencies) == 1:
            retrieved = self.store.search(
                query,
                top_k=top_k,
                agency_filter=search_agencies[0]
            )
        else:
            retrieved = self.store.search_multi_agency(
                query,
                agencies=search_agencies,
                top_k_per_agency=3,
            )

        # Build context for LLM
        context = format_context_for_llm(retrieved)

        # Build citations
        citations = build_citations(retrieved)
        citations_str = format_citations(citations)

        # Calculate confidence
        confidence = self._calculate_confidence(retrieved)

        # Generate answer
        if retrieved:
            prompt = (
                f"Using ONLY the regulatory sources provided below, "
                f"answer this compliance question:\\n\\n"
                f"QUESTION: {query}\\n\\n"
                f"REGULATORY SOURCES:\\n{context}\\n\\n"
                f"Remember to cite specific sections in your answer."
            )
        else:
            prompt = (
                f"The following compliance question was asked but no "
                f"relevant regulatory provisions were found in the "
                f"NaijaCodex document library:\\n\\n"
                f"QUESTION: {query}\\n\\n"
                f"Inform the user clearly and suggest next steps."
            )

        messages = [
            SystemMessage(content=NAIJACODEX_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)
        answer = response.content

        # Calculate latency
        latency = int(
            (datetime.now() - start_time).total_seconds() * 1000
        )

        return NaijaCodexAnswer(
            query_id = query_id,
            query = query,
            answer = answer,
            citations = citations_str,
            confidence = confidence,
            agencies_searched = search_agencies,
            retrieval_count = len(retrieved),
            timestamp = datetime.now().isoformat(),
            latency_ms = latency,
        )


def print_answer(result: NaijaCodexAnswer):
    """Pretty prints a NaijaCodexAnswer to terminal."""
    print("\\n" + "=" * 60)
    print(f"NAIJACODEX ANSWER  [{result.query_id}]")
    print("=" * 60)
    print(f"Query: {result.query}")
    print(f"Agencies searched: {', '.join(result.agencies_searched)}")
    print(f"Documents retrieved: {result.retrieval_count}")
    print(f"Confidence: {result.confidence}")
    print(f"Latency: {result.latency_ms}ms")
    print()
    print("ANSWER:")
    print(result.answer)
    print()
    print("CITATIONS:")
    print(result.citations)
    print("=" * 60)
