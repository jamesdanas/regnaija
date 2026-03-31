"""
src/ingestion/metadata_extractor.py

WHY THIS EXISTS:
Zero-hallucination citations require structured metadata on every chunk:
  - Which agency published this? (CBN, SEC, NRS, NDPC, NITDA)
  - What is the document name?
  - When was it published?
  - What section number does this chunk come from?
  - What is the source URL for the audit trail?

This extractor pulls all of that from the filename, folder name,
and document text itself - so every answer NaijaCodex gives
can be traced back to a specific section of a specific document.
"""

import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DocumentMetadata:
    """Complete metadata for a regulatory document."""
    agency: str
    document_name: str
    short_name: str
    publication_date: str
    publication_year: str
    doc_type: str           # circular, guideline, act, regulation, framework
    source_url: str
    filename: str
    doc_id: str


# Known document registry - maps filenames to clean metadata
KNOWN_DOCUMENTS = {
    # CBN
    "cbn_cybersecurity_framework": {
        "name": "CBN Cybersecurity Framework for Nigerian Banking Sector",
        "short": "CBN Cybersecurity Framework",
        "date": "2021-01-01",
        "type": "framework",
        "url": "https://www.cbn.gov.ng/out/2021/fprd/cyber%20security%20framework.pdf"
    },
    "cbn_open_banking_policy": {
        "name": "CBN Open Banking Policy for Nigeria",
        "short": "CBN Open Banking Policy",
        "date": "2023-01-01",
        "type": "policy",
        "url": "https://www.cbn.gov.ng/out/2023/fprd/open%20banking%20policy.pdf"
    },
    "cbn_consumer_protection": {
        "name": "CBN Consumer Protection Framework",
        "short": "CBN Consumer Protection",
        "date": "2016-01-01",
        "type": "framework",
        "url": "https://www.cbn.gov.ng/out/2016/ccd/consumer%20protection%20framework.pdf"
    },
    # NDPC
    "ndpa_2023": {
        "name": "Nigeria Data Protection Act 2023",
        "short": "NDPA 2023",
        "date": "2023-06-14",
        "type": "act",
        "url": "https://ndpc.gov.ng/media/NDPA_2023.pdf"
    },
    "ndpc_implementation_framework": {
        "name": "NDPC Implementation Framework",
        "short": "NDPC Implementation Framework",
        "date": "2023-01-01",
        "type": "framework",
        "url": "https://ndpc.gov.ng/media/NDPC_ImplementationFramework.pdf"
    },
    # NRS
    "nigeria_tax_act_2025": {
        "name": "Nigeria Tax Act 2025",
        "short": "NTA 2025",
        "date": "2025-06-26",
        "type": "act",
        "url": "https://nrs.gov.ng/nigeria-tax-act-2025.pdf"
    },
    # SEC Nigeria
    "investments_securities_act": {
        "name": "Investments and Securities Act 2007",
        "short": "ISA 2007",
        "date": "2007-01-01",
        "type": "act",
        "url": "https://sec.gov.ng/wp-content/uploads/2023/01/Investments-and-Securities-Act-2007.pdf"
    },
    # NITDA
    "ndpr_2019": {
        "name": "Nigeria Data Protection Regulation 2019",
        "short": "NDPR 2019",
        "date": "2019-01-25",
        "type": "regulation",
        "url": "https://nitda.gov.ng/wp-content/uploads/2020/01/NigeriaDataProtectionRegulation.pdf"
    },
}

# Map folder names to agency names
AGENCY_MAP = {
    "CBN": "CBN",
    "SEC_Nigeria": "SEC",
    "NRS": "NRS",
    "NDPC": "NDPC",
    "NITDA": "NITDA",
}


class MetadataExtractor:
    """
    Extracts and structures metadata from Nigerian regulatory documents.
    Combines filename matching, folder detection, and text scanning.
    """

    def _detect_agency_from_path(self, file_path: str) -> str:
        """Detects agency from the folder structure."""
        path = Path(file_path)
        for part in path.parts:
            if part in AGENCY_MAP:
                return AGENCY_MAP[part]
        return "UNKNOWN"

    def _detect_agency_from_text(self, text: str) -> str:
        """Fallback: detects agency from document text content."""
        text_upper = text[:2000].upper()
        if "CENTRAL BANK OF NIGERIA" in text_upper or "CBN" in text_upper[:500]:
            return "CBN"
        if "SECURITIES AND EXCHANGE COMMISSION" in text_upper:
            return "SEC"
        if "FEDERAL INLAND REVENUE" in text_upper or "FIRS" in text_upper[:500] or "NIGERIA REVENUE SERVICE" in text_upper or "NRS" in text_upper[:500]:
            return "NRS"
        if "DATA PROTECTION COMMISSION" in text_upper or "NDPC" in text_upper:
            return "NDPC"
        if "NITDA" in text_upper or "INFORMATION TECHNOLOGY" in text_upper[:500]:
            return "NITDA"
        return "UNKNOWN"

    def _extract_date_from_text(self, text: str) -> str:
        """
        Scans document text for publication date.
        Handles common Nigerian regulatory date formats.
        """
        date_patterns = [
            # "January 2023", "January, 2023"
            r'(January|February|March|April|May|June|July|August|'
            r'September|October|November|December)[,\s]+(\d{4})',
            # "2023", standalone year near top of doc
            r'(?:Published|Issued|Dated?)[:\s]+.*?(\d{4})',
            # "15th January 2023", "15 January 2023"
            r'(\d{1,2})(?:st|nd|rd|th)?\s+'
            r'(January|February|March|April|May|June|July|August|'
            r'September|October|November|December)\s+(\d{4})',
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text[:3000], re.IGNORECASE)
            if match:
                groups = match.groups()
                # Format as best we can
                if len(groups) == 2:
                    return f"{groups[0]} {groups[1]}"
                elif len(groups) == 3:
                    return f"{groups[0]} {groups[1]} {groups[2]}"

        return "Date not found"

    def _extract_year(self, date_str: str) -> str:
        """Extracts 4-digit year from a date string."""
        match = re.search(r'\d{4}', date_str)
        return match.group(0) if match else str(datetime.now().year)

    def _generate_doc_id(
        self,
        agency: str,
        short_name: str,
        year: str
    ) -> str:
        """
        Generates a unique document ID for the audit trail.
        Format: CBN-CYBERSECURITY-2021
        """
        clean_name = re.sub(r'[^A-Z0-9]', '-', short_name.upper())
        clean_name = re.sub(r'-+', '-', clean_name).strip('-')[:30]
        return f"{agency}-{clean_name}-{year}"

    def extract(
        self,
        file_path: str,
        document_text: str = "",
        override_url: str = ""
    ) -> DocumentMetadata:
        """
        Main method. Extracts full metadata for a document.

        Priority order:
        1. Known document registry (most accurate)
        2. Filename pattern matching
        3. Text scanning (fallback)
        """
        path = Path(file_path)
        filename_stem = path.stem.lower()

        # Try known document registry first
        for key, info in KNOWN_DOCUMENTS.items():
            if key in filename_stem or filename_stem in key:
                agency = self._detect_agency_from_path(file_path)
                if agency == "UNKNOWN" and document_text:
                    agency = self._detect_agency_from_text(document_text)

                year = self._extract_year(info["date"])
                doc_id = self._generate_doc_id(agency, info["short"], year)

                return DocumentMetadata(
                    agency=agency,
                    document_name=info["name"],
                    short_name=info["short"],
                    publication_date=info["date"],
                    publication_year=year,
                    doc_type=info["type"],
                    source_url=override_url or info["url"],
                    filename=path.name,
                    doc_id=doc_id,
                )

        # Fallback: extract from file path and text
        agency = self._detect_agency_from_path(file_path)
        if agency == "UNKNOWN" and document_text:
            agency = self._detect_agency_from_text(document_text)

        # Clean up filename as document name
        clean_name = filename_stem.replace('_', ' ').replace('-', ' ').title()
        date_str = self._extract_date_from_text(document_text) if document_text else "Unknown"
        year = self._extract_year(date_str)
        doc_id = self._generate_doc_id(agency, clean_name[:20], year)

        return DocumentMetadata(
            agency = agency,
            document_name = clean_name,
            short_name = clean_name[:40],
            publication_date = date_str,
            publication_year = year,
            doc_type = "document",
            source_url = override_url or "",
            filename = path.name,
            doc_id = doc_id,
        )
