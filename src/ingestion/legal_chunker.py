"""
src/ingestion/legal_chunker.py
"""

import re
from typing import List, Tuple
from dataclasses import dataclass
from langchain_core.documents import Document


@dataclass
class LegalChunk:
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

    SECTION_PATTERNS = [
        r'^(PART\s+[IVXLCDM]+[\.\s])',
        r'^(PART\s+\d+[\.\s])',
        r'^(Chapter\s+\d+[\.\s])',
        r'^(Section\s+\d+[\.\d]*[\.\s])',
        r'^(\d+\.\d+[\.\d]*\s)',
        r'^(\d+\.\s+[A-Z])',
        r'^(Article\s+\d+[\.\s])',
        r'^(Schedule\s+[IVXLCDM\d]+[\.\s])',
        r'^(Regulation\s+\d+[\.\s])',
    ]

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
                remaining = text[match.end():].strip()
                title_line = remaining.split('\n')[0].strip()[:80]
                return section_num, title_line
        return "General", text[:50].strip()

    def _split_into_sections(self, text: str) -> List[dict]:
        lines = text.split('\n')
        sections = []
        current_section_lines = []
        current_section_header = "Preamble"

        for line in lines:
            stripped = line.strip()
            if not stripped:
                current_section_lines.append(line)
                continue

            is_new_section = bool(self.section_regex.match(stripped))

            if is_new_section and current_section_lines:
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

        if current_section_lines:
            section_text = '\n'.join(current_section_lines).strip()
            if len(section_text) >= self.min_chunk_size:
                sections.append({
                    'header': current_section_header,
                    'text': section_text,
                })

        return sections

    def _split_large_section(self, section_text: str) -> List[str]:
        if len(section_text) <= self.max_chunk_size:
            return [section_text]

        chunks = []
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
                    ends_with_bridge = self.bridge_regex.search(
                        current_chunk[-200:]
                    )
                    if ends_with_bridge and part:
                        current_chunk += part
                    else:
                        chunks.append(current_chunk.strip())
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
        print(f"\n  Chunking: {document_name}")
        sections = self._split_into_sections(text)
        print(f"  Detected {len(sections)} legal sections")

        chunks = []
        chunk_index = 0

        for section in sections:
            section_num, section_title = self._detect_section_number(
                section['header']
            )
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
                    text=sub_chunk.strip(),
                    section_number=section_num,
                    section_title=section_title,
                    chunk_index=chunk_index,
                    parent_section=section['header'][:100],
                    agency=agency,
                    document_name=document_name,
                    source_url=source_url,
                    publication_date=publication_date,
                    page_number=page_number,
                    chunk_id=chunk_id,
                ))
                chunk_index += 1

        print(f"  Created {len(chunks)} legal chunks")
        return chunks

    def chunks_to_documents(
        self,
        chunks: List[LegalChunk]
    ) -> List[Document]:
        documents = []
        for chunk in chunks:
            documents.append(Document(
                page_content=chunk.text,
                metadata={
                    "chunk_id":         chunk.chunk_id,
                    "chunk_index":      chunk.chunk_index,
                    "section_number":   chunk.section_number,
                    "section_title":    chunk.section_title,
                    "parent_section":   chunk.parent_section,
                    "agency":           chunk.agency,
                    "document_name":    chunk.document_name,
                    "source_url":       chunk.source_url,
                    "publication_date": chunk.publication_date,
                    "page_number":      chunk.page_number,
                }
            ))
        return documents
