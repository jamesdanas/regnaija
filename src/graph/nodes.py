"""
src/graph/nodes.py
Each function here is a node in the LangGraph pipeline.
Nodes are pure functions: they receive state and return updated state.
"""

import os
import re
import json
import uuid
from typing import List
from datetime import datetime

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from src.graph.state import NaijaCodexState
from src.generation.system_prompt import (
    NAIJACODEX_SYSTEM_PROMPT,
    QUERY_DECOMPOSE_PROMPT,
)
from src.generation.citation_builder import (
    build_citations,
    format_citations,
    format_context_for_llm,
)
from dotenv import load_dotenv

load_dotenv()


def get_llm():
    return ChatGroq(
        model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        temperature = 0,
        max_tokens = 2048,
    )


# ------------------------------------------------------
# NODE 1: Query Analyser
# Detects agencies and breaks query into sub-questions
# ------------------------------------------------------

AGENCY_KEYWORDS = {
    "CBN": [
        "cbn", "bank", "fintech", "payment", "lending", "microfinance",
        "monetary", "cybersecurity", "open banking", "consumer protection",
        "deposit", "credit", "loan", "interest rate", "liquidity",
    ],
    "SEC": [
        "sec", "securities", "capital market", "investment", "stockbroker",
        "shares", "ipo", "bonds", "listed company", "public offer",
        "asset management", "fund manager",
    ],
    "NDPC": [
        "data protection", "privacy", "ndpc", "personal data", "data subject",
        "gdpr", "ndpa", "data controller", "consent", "erasure", "dpo",
    ],
    "NRS": [
        "tax", "nrs", "firs", "income tax", "vat", "levy", "withholding",
        "cit", "revenue", "filing", "assessment", "penalty", "cita",
        "companies income", "nigeria tax act",
    ],
    "NITDA": [
        "nitda", "it policy", "technology development", "ndpr",
        "information technology", "digital economy",
    ],
}


def query_analyser(state: NaijaCodexState) -> NaijaCodexState:
    """
    NODE 1: Analyses the query.
    - Detects which agencies are relevant
    - Generates sub-queries for multi-agency questions
    """
    query = state["query"]
    query_lower = query.lower()

    # Detect relevant agencies
    detected = []
    for agency, keywords in AGENCY_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            detected.append(agency)

    # Default to all agencies if none detected
    if not detected:
        detected = ["CBN", "SEC", "NDPC", "NRS", "NITDA"]

    # Generate sub-queries only for multi-agency questions
    sub_queries = [query]  # Default: use original query
    if len(detected) > 1:
        try:
            llm = get_llm()
            prompt = QUERY_DECOMPOSE_PROMPT.format(query=query)
            resp = llm.invoke([HumanMessage(content=prompt)])

            # Parse JSON array from response
            text  = resp.content.strip()
            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                if isinstance(parsed, list) and len(parsed) > 0:
                    sub_queries = parsed
        except Exception:
            sub_queries = [query]  # Fallback to original

    print(f"Agencies detected: {detected}")
    print(f"Sub-queries: {len(sub_queries)}")

    return {
        **state,
        "detected_agencies": detected,
        "sub_queries": sub_queries,
        "query_id": f"NCX-{uuid.uuid4().hex[:8].upper()}",
    }


# ---------------------------------------------------
# NODE 2: Retrieval Agent
# Searches Pinecone for relevant regulatory chunks
# ---------------------------------------------------

def retrieval_agent(state: NaijaCodexState, store) -> NaijaCodexState:
    """
    NODE 2: Retrieves relevant regulatory chunks from Pinecone.
    Searches each sub-query across detected agencies.
    """
    agencies = state["detected_agencies"]
    sub_queries = state["sub_queries"]
    all_results = []
    seen_ids = set()

    for sub_query in sub_queries:
        if len(agencies) == 1:
            results = store.search(
                sub_query,
                top_k = 8,
                agency_filter = agencies[0],
            )
        else:
            results = store.search_multi_agency(
                sub_query,
                agencies = agencies,
                top_k_per_agency = 4,
            )

        # Deduplicate by doc_id + section_number
        for doc, score in results:
            doc_id    = doc.metadata.get("doc_id", "")
            section   = doc.metadata.get("section_number", "")
            text_key  = doc.page_content[:50]
            dedup_key = f"{doc_id}_{section}_{text_key}"
            if dedup_key not in seen_ids:
                seen_ids.add(dedup_key)
                all_results.append((doc, score))

    # Sort by score
    all_results.sort(key=lambda x: x[1], reverse=True)
    top_results = all_results[:8]

    scores = [score for _, score in top_results]
    print(f"Retrieved {len(top_results)} unique chunks")
    print(f"Top score: {scores[0]:.3f}" if scores else "  No results")

    return {
        **state,
        "retrieved_docs": top_results,
        "retrieval_scores": scores,
        "agencies_searched": agencies,
    }


# ----------------------------------------------------------
# NODE 3: Conflict Detector
# Checks if retrieved docs contain regulatory conflicts
# ----------------------------------------------------------

def conflict_detector(state: NaijaCodexState) -> NaijaCodexState:
    """
    NODE 3: Detects regulatory conflicts between agencies.
    Example: CBN requires 5yr data retention but NDPC
    grants right to erasure — this is a real conflict.
    """
    docs = state["retrieved_docs"]
    agencies = set()

    for doc, _ in docs:
        agencies.add(doc.metadata.get("agency", ""))

    conflicts_found = False
    conflict_details = ""

    # Only check for conflicts if multiple agencies retrieved
    if len(agencies) > 1:
        known_conflicts = [
            {
                "agencies": ("CBN", "NDPC"),
                "topic": "data retention",
                "description": (
                    "REGULATORY TENSION DETECTED: CBN regulations may require "
                    "financial institutions to retain customer data for up to 5 years "
                    "for AML/KYC compliance purposes. However, the NDPC Nigeria Data "
                    "Protection Act 2023 Section 4.1(d) grants data subjects the right "
                    "to request erasure of personal data. RESOLUTION: CBN-specific "
                    "retention requirements take precedence for licensed financial "
                    "institutions per NDPA 2023 Section 5.2, which permits longer "
                    "retention where required by applicable law."
                ),
            },
            {
                "agencies": ("CBN", "NRS"),
                "topic": "customer information sharing",
                "description": (
                    "REGULATORY NOTE: CBN consumer protection rules protect customer "
                    "financial information confidentiality. However, NRS (Nigeria Tax "
                    "Act 2025 Section 6.1) requires banks to report transactions "
                    "exceeding N25M (individuals) and N100M (companies) to the NRS. "
                    "RESOLUTION: Tax reporting obligations to NRS are a legal exception "
                    "to CBN confidentiality requirements."
                ),
            },
            {
                "agencies": ("SEC", "CBN"),
                "topic": "fintech dual regulation",
                "description": (
                    "REGULATORY NOTE: Fintechs operating in both payment services "
                    "(CBN jurisdiction) and investment/securities activities (SEC "
                    "jurisdiction) are subject to dual regulation. Both sets of "
                    "requirements must be satisfied independently."
                ),
            },
        ]

        query_lower = state["query"].lower()
        for conflict in known_conflicts:
            a1, a2 = conflict["agencies"]
            if (a1 in agencies and a2 in agencies and
                    conflict["topic"] in query_lower):
                conflicts_found  = True
                conflict_details = conflict["description"]
                break

    print(f"Conflicts detected: {conflicts_found}")

    return {
        **state,
        "conflicts_found": conflicts_found,
        "conflict_details": conflict_details,
    }


# ------------------------------------------------
# NODE 4: Answer Synthesiser
# Generates the final answer with citations
# ------------------------------------------------

def answer_synthesiser(state: NaijaCodexState) -> NaijaCodexState:
    """
    NODE 4: Generates final answer using retrieved context.
    Incorporates conflict details if any were found.
    """
    query = state["query"]
    docs = state["retrieved_docs"]
    scores = state["retrieval_scores"]
    conflict = state.get("conflict_details", "")

    # Build context
    context = format_context_for_llm(docs)

    # Calculate confidence
    if not scores:
        confidence = "LOW — No relevant documents found"
    elif scores[0] >= 0.75:
        confidence = "HIGH — Direct match found in regulatory documents"
    elif scores[0] >= 0.55:
        confidence = "MEDIUM — Related provisions found, verify with sources"
    else:
        confidence = "LOW — Weak match, consult official sources directly"

    # Build prompt
    conflict_note = (
        f"\n\nIMPORTANT — REGULATORY CONFLICT TO ADDRESS:\n{conflict}"
        if conflict else ""
    )

    if docs:
        prompt = (
            f"Using ONLY the regulatory sources provided below, "
            f"answer this compliance question:\n\n"
            f"QUESTION: {query}"
            f"{conflict_note}\n\n"
            f"REGULATORY SOURCES:\n{context}\n\n"
            f"Cite specific sections in your answer."
        )
    else:
        prompt = (
            f"No relevant regulatory provisions were found for:\n\n"
            f"QUESTION: {query}\n\n"
            f"Inform the user and suggest checking directly with "
            f"the relevant regulatory agency."
        )

    llm      = get_llm()
    messages = [
        SystemMessage(content=NAIJACODEX_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
    response = llm.invoke(messages)
    answer = response.content

    # Build citations
    citations = build_citations(docs)
    citations_str = format_citations(citations)

    return {
        **state,
        "context": context,
        "answer": answer,
        "citations": citations_str,
        "confidence": confidence,
    }


# ---------------------------------------------------
# NODE 5: Confidence Guard
# Blocks low confidence answers
# ---------------------------------------------------

def confidence_guard(state: NaijaCodexState) -> str:
    """
    CONDITIONAL EDGE: Routes based on confidence.
    Returns "pass" or "block".
    """
    scores = state.get("retrieval_scores", [])

    if not scores or scores[0] < 0.40:
        return "block"
    return "pass"
