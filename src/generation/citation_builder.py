"""
src/generation/citation_builder.py
Builds structured citations for every answer NaijaCodex produces.
"""

from dataclasses import dataclass
from typing import List, Optional
from langchain_core.documents import Document


@dataclass
class Citation:
    document_name: str
    agency: str
    section_number: str
    publication_date: str
    source_url: str
    relevance_score: float
    excerpt: str


def build_citations(
    retrieved_docs: List[tuple]
) -> List[Citation]:
    """
    Builds Citation objects from retrieved (Document, score) tuples.
    Deduplicates by section — same section cited once only.
    """
    seen = set()
    citations = []

    for doc, score in retrieved_docs:
        meta = doc.metadata
        key  = f"{meta.get('doc_id','')}_{meta.get('section_number','')}"

        if key in seen:
            continue
        seen.add(key)

        citations.append(Citation(
            document_name = meta.get("document_name", "Unknown"),
            agency = meta.get("agency", "Unknown"),
            section_number = meta.get("section_number", ""),
            publication_date = meta.get("publication_date", ""),
            source_url = meta.get("source_url", ""),
            relevance_score = round(score, 3),
            excerpt = doc.page_content[:200],
        ))

    return sorted(citations, key=lambda x: x.relevance_score, reverse=True)


def format_citations(citations: List[Citation]) -> str:
    """Formats citations into the standard NaijaCodex display format."""
    if not citations:
        return "No sources found."

    lines = []
    for i, c in enumerate(citations, 1):
        line = (
            f"[{i}] {c.document_name} | "
            f"{c.agency} | "
            f"Section {c.section_number} | "
            f"{c.publication_date}"
        )
        if c.source_url:
            line += f"\\n 🔗 {c.source_url}"
        lines.append(line)

    return "\\n".join(lines)


def format_context_for_llm(
    retrieved_docs: List[tuple],
    max_docs: int = 6
) -> str:
    """
    Formats retrieved documents into context for the LLM.
    Each chunk is labelled with its source metadata so the
    LLM can cite it accurately.
    """
    context_parts = []

    for i, (doc, score) in enumerate(retrieved_docs[:max_docs]):
        meta = doc.metadata
        context_parts.append(
            f"--- SOURCE {i+1} ---\\n"
            f"Document: {meta.get('document_name', 'Unknown')}\\n"
            f"Agency: {meta.get('agency', 'Unknown')}\\n"
            f"Section: {meta.get('section_number', 'N/A')}\\n"
            f"Date: {meta.get('publication_date', 'Unknown')}\\n"
            f"Relevance Score: {score:.3f}\\n"
            f"Content:\\n{doc.page_content}\\n"
        )

    return "\\n".join(context_parts)
