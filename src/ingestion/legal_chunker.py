"""
src/ingestion/legal_chunker.py

WHY THIS EXISTS:
Normal chunkers split at character count — they will cut a sentence like:
"The penalty for late filing shall be..." mid-clause, destroying its meaning.

Nigerian legal documents have a very specific structure:
  PART I
  Section 1.
  Section 1.1
  (a), (b), (c) sub-clauses
  "Provided that..."
  "Notwithstanding..."

This chunker detects those boundaries and NEVER splits mid-clause.
Every chunk keeps its section number intact — which is what makes
zero-hallucination citations possible.
"""

import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
from langchain_core.documents import Document


@dataclass
class LegalChunk:
    """A single legal chunk with full metadata."""
    text: str
    section_number: str
    section_title: str
    chunk_index: int
    parent_section: str
    agency: str
    document_name: str
    source_url: str
    publication_date: str
    page_number: int
    chunk_id: str


class NigerianLegalChunker:
    """
    Chunks Nigerian regulatory documents by legal structure.

    Keeps section numbers, clause letters, and legal phrases intact.
    Never splits mid-clause. Every chunk is fully self-contained.
    """

    # Regex patterns for Nigerian legal document structure
    SECTION_PATTERNS = [
        r'^(PART\s+[IVXLCDM]+[\.\s])',           # PART I, PART II
        r'^(PART\s+\d+[\.\s])',                    # PART 1, PART 2
        r'^(Chapter\s+\d+[\.\s])',                 # Chapter 1
        r'^(Section\s+\d+[\.\d]*[\.\s])',          # Section 1, Section 1.1
        r'^(\d+\.\d+[\.\d]*\s)',                   # 1.1, 1.1.1
        r'^(\d+\.\s+[A-Z])',                       # 1. TITLE
        r'^(Article\s+\d+[\.\s])',                 # Article 1
        r'^(Schedule\s+[IVXLCDM\d]+[\.\s])',       # Schedule I
        r'^(Regulation\s+\d+[\.\s])',              # Regulation 1
    ]

    # Legal transition phrases — never split after these
    LEGAL_BRIDGES = [
        r'provided that',
        r'notwithstanding',
        r'subject to',
        r'in addition to',
        r'without prejudice',
        r'for the purposes of',
        r'in accordance with',
        r'pursuant to',
    ]

    def __init__(
        self,
        max_chunk_size: int = 1000,
        min_chunk_size: int = 100,
        overlap_size: int = 100,
    ):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap_size = overlap_size
        self._compile_patterns()

    def _compile_patterns(self):
        self.section_regex = re.compile(
            '|'.join(self.SECTION_PATTERNS),
            re.MULTILINE | re.IGNORECASE
        )
        self.bridge_regex = re.compile(
            '|'.join(self.LEGAL_BRIDGES),
            re.IGNORECASE
        )

    def _detect_section_number(self, text: str) -> Tuple[str, str]:
        """
        Extracts section number and title from the start of a text block.
        Returns (section_number, remaining_title)
        """
        # Try each pattern
        patterns = [
            r'^(PART\s+[IVXLCDM\d]+)',
            r'^(Section\s+[\d\.]+)',
            r'^([\d]+\.[\d\.]*)',
            r'^(Article\s+\d+)',
            r'^(Regulation\s+\d+)',
            r'^(Schedule\s+[IVXLCDM\d]+)',
            r'^(Chapter\s+\d+)',
        ]
        for pattern in patterns:
            match = re.match(pattern, text.strip(), re.IGNORECASE)
            if match:
                section_num = match.group(1).strip()
                # Get title — first line after section number
                remaining = text[match.end():].strip()
                title_line = remaining.split('\n')[0].strip()[:80]
                return section_num, title_line

        return "General", text[:50].strip()

    def _split_into_sections(self, text: str) -> List[Dict]:
        """
        Splits document text into logical sections based on
        detected legal structure markers.
        """
        lines = text.split('\n')
        sections = []
        current_section_lines = []
        current_section_header = "Preamble"

        for line in lines:
            stripped = line.strip()
            if not stripped:
                current_section_lines.append(line)
                continue

            # Check if this line starts a new section
            is_new_section = bool(self.section_regex.match(stripped))

            if is_new_section and current_section_lines:
                # Save the current section
                section_text = '\n'.join(current_section_lines).strip()
                if len(section_text) >= self.min_chunk_size:
                    sections.append({
                        'header': current_section_header,
                        'text': section_text,
                    })
                current_section_lines = [line]
                current_section_header = stripped[:100]
            else:
                current_section_lines.append(line)

        # Don't forget the last section
        if current_section_lines:
            section_text = '\n'.join(current_section_lines).strip()
            if len(section_text) >= self.min_chunk_size:
                sections.append({
                    'header': current_section_header,
                    'text': section_text,
                })

        return sections

    def _split_large_section(self, section_text: str) -> List[str]:
        """
        Splits a section that's too large into smaller pieces.
        Respects sub-clause boundaries — never splits mid-sentence
        if that sentence contains a legal bridge phrase.
        """
        if len(section_text) <= self.max_chunk_size:
            return [section_text]

        chunks = []
        # Split on sub-clause markers: (a), (b), (i), (ii)
        sub_clause_pattern = re.compile(
            r'(?=\n\s*\([a-z]{1,3}\)\s)',
            re.IGNORECASE
        )
        parts = sub_clause_pattern.split(section_text)

        current_chunk = ""
        for part in parts:
            if len(current_chunk) + len(part) <= self.max_chunk_size:
                current_chunk += part
            else:
                if current_chunk.strip():
                    # Don't break if ends with a legal bridge phrase
                    ends_with_bridge = self.bridge_regex.search(
                        current_chunk[-200:]
                    )
                    if ends_with_bridge and part:
                        current_chunk += part
                    else:
                        chunks.append(current_chunk.strip())
                        # Add overlap from end of previous chunk
                        overlap = current_chunk[-self.overlap_size:]
                        current_chunk = overlap + part
                else:
                    current_chunk = part

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks if chunks else [section_text]

    def chunk_document(
        self,
        text: str,
        agency: str,
        document_name: str,
        source_url: str = "",
        publication_date: str = "",
        page_number: int = 0,
    ) -> List[LegalChunk]:
        """
        Main method. Takes raw document text and returns
        a list of LegalChunk objects with full metadata.
        """
        print(f"\nChunking: {document_name}")

        # Split into logical sections first
        sections = self._split_into_sections(text)
        print(f"Detected {len(sections)} legal sections")

        chunks = []
        chunk_index = 0

        for section in sections:
            # Detect section number from header
            section_num, section_title = self._detect_section_number(
                section['header']
            )

            # Split large sections further
            sub_chunks = self._split_large_section(section['text'])

            for sub_chunk in sub_chunks:
                if len(sub_chunk.strip()) < self.min_chunk_size:
                    continue

                chunk_id = (
                    f"{agency.lower()}"
                    f"_{re.sub(r'[^a-z0-9]', '_', document_name.lower()[:20])}"
                    f"_chunk{chunk_index:04d}"
                )

                chunks.append(LegalChunk(
                    text = sub_chunk.strip(),
                    section_number = section_num,
                    section_title = section_title,
                    chunk_index = chunk_index,
                    parent_section = section['header'][:100],
                    agency = agency,
                    document_name = document_name,
                    source_url = source_url,
                    publication_date = publication_date,
                    page_number = page_number,
                    chunk_id = chunk_id,
                ))
                chunk_index += 1

        print(f"Created {len(chunks)} legal chunks")
        return chunks

    def chunks_to_documents(
        self,
        chunks: List[LegalChunk]
    ) -> List[Document]:
        """
        Converts LegalChunk objects to LangChain Document objects
        for use with the vector store.
        """
        documents = []
        for chunk in chunks:
            documents.append(Document(
                page_content=chunk.text,
                metadata={
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "section_number": chunk.section_number,
                    "section_title": chunk.section_title,
                    "parent_section": chunk.parent_section,
                    "agency": chunk.agency,
                    "document_name": chunk.document_name,
                    "source_url": chunk.source_url,
                    "publication_date": chunk.publication_date,
                    "page_number": chunk.page_number,
                }
            ))
        return documents
