"""
src/ingestion/metadata_extractor.py

WHY THIS EXISTS:
Zero-hallucination citations require structured metadata on every chunk:
  - Which agency published this? (CBN, SEC, NRS, NDPC, NITDA, CAC, NCC, FIRS)
  - What is the document name?
  - When was it published?
  - What section number does this chunk come from?
  - What is the source URL for the audit trail?

This extractor pulls all of that from the filename, folder name,
and document text itself — so every answer RegNaija gives
can be traced back to a specific section of a specific document.

AGENCY NOTE — FIRS vs NRS:
  The Nigeria Revenue Service Establishment Act 2025 replaced FIRS with NRS.
  Documents issued before 2025 carry the FIRS tag; 2025+ documents carry NRS.
  Both tags are routed to the same query path in nodes.py so users asking
  about "FIRS" still retrieve NRS content and vice versa.
"""

import re
from pathlib import Path
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


# ----- Known document registry ----------------------------------------
# Maps filename stems (lowercase) to clean metadata.
# Priority: this registry beats filename heuristics and text scanning.
# Keep in sync with batch_ingest.py DOCUMENTS list.

KNOWN_DOCUMENTS = {

    # CBN — Core 
    "cbn risk-based cybersecurity framework for dmbs and psbs_2024": {
        "name":  "CBN Risk-Based Cybersecurity Framework for DMBs and PSBs 2024",
        "short": "CBN Cybersecurity Framework 2024",
        "date":  "2024-01-01",
        "type":  "framework",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },
    "cbn_consumer_protection": {
        "name":  "CBN Consumer Protection Framework 2016",
        "short": "CBN Consumer Protection Framework",
        "date":  "2016-01-01",
        "type":  "framework",
        "url":   "https://www.cbn.gov.ng/out/2016/ccd/consumer%20protection%20framework.pdf",
        "agency": "CBN",
    },
    "cbn_open_banking_policy": {
        "name":  "CBN Open Banking Policy 2023",
        "short": "CBN Open Banking Policy",
        "date":  "2023-01-01",
        "type":  "policy",
        "url":   "https://www.cbn.gov.ng/out/2023/fprd/open%20banking%20policy.pdf",
        "agency": "CBN",
    },
    "regulatory_framework_for_mobile_payments_services_in_nigeria": {
        "name":  "CBN Regulatory Framework for Mobile Payments Services in Nigeria",
        "short": "CBN Mobile Payments Framework",
        "date":  "2021-01-01",
        "type":  "framework",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },

    # CBN — AML 
    "aml circular and regulations merged": {
        "name":  "CBN AML Circular and Regulations",
        "short": "CBN AML Regulations",
        "date":  "2022-01-01",
        "type":  "regulation",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },
    "circular_and_aml_licensing_guideline": {
        "name":  "CBN AML Licensing Guideline",
        "short": "CBN AML Licensing Guideline",
        "date":  "2022-01-01",
        "type":  "circular",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },

    # CBN — Basel III 
    "circular on basel iii implementation by dmbs in nigeria": {
        "name":  "CBN Basel III Implementation Circular for DMBs in Nigeria",
        "short": "CBN Basel III Circular",
        "date":  "2024-01-01",
        "type":  "circular",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },
    "1. guidelines on regulatory capital": {
        "name":  "CBN Guidelines on Regulatory Capital",
        "short": "CBN Regulatory Capital Guidelines",
        "date":  "2024-01-01",
        "type":  "guideline",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },
    "2. guidelines on leverage ratio (ler)": {
        "name":  "CBN Guidelines on Leverage Ratio",
        "short": "CBN Leverage Ratio Guidelines",
        "date":  "2024-01-01",
        "type":  "guideline",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },
    "3. guidelines on liquidity coverage ratio (lcr)": {
        "name":  "CBN Guidelines on Liquidity Coverage Ratio",
        "short": "CBN Liquidity Coverage Ratio Guidelines",
        "date":  "2024-01-01",
        "type":  "guideline",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },
    "4. guidelines on liquidity monitoring tools (lmt)": {
        "name":  "CBN Guidelines on Liquidity Monitoring Tools",
        "short": "CBN Liquidity Monitoring Tools Guidelines",
        "date":  "2024-01-01",
        "type":  "guideline",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },
    "5. guidelines on large exposures (lex)": {
        "name":  "CBN Guidelines on Large Exposures",
        "short": "CBN Large Exposures Guidelines",
        "date":  "2024-01-01",
        "type":  "guideline",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },

    #  CBN — Forex 
    "the new forex manual - 4th edition": {
        "name":  "CBN Foreign Exchange Manual 4th Edition",
        "short": "CBN Forex Manual 4th Edition",
        "date":  "2024-01-01",
        "type":  "manual",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },

    #  CBN — PSP 
    "circular and guidelines for licensing and regulation of payments service holding companies in nigeria": {
        "name":  "CBN Circular and Guidelines for Licensing and Regulation of Payment Service Holding Companies",
        "short": "CBN PSP Holding Companies Circular",
        "date":  "2021-01-01",
        "type":  "circular",
        "url":   "https://www.cbn.gov.ng",
        "agency": "CBN",
    },

    #  CAC 
    "cama-note-book-full-version": {
        "name":  "Companies and Allied Matters Act 2020",
        "short": "CAMA 2020",
        "date":  "2020-08-07",
        "type":  "act",
        "url":   "https://www.cac.gov.ng",
        "agency": "CAC",
    },
    "companies-regulations-2021-published": {
        "name":  "Companies Regulations 2021",
        "short": "CAC Companies Regulations 2021",
        "date":  "2021-01-01",
        "type":  "regulation",
        "url":   "https://www.cac.gov.ng",
        "agency": "CAC",
    },

    #  SEC 
    "investments_securities_act": {
        "name":  "Investments and Securities Act 2007",
        "short": "ISA 2007",
        "date":  "2007-01-01",
        "type":  "act",
        "url":   "https://sec.gov.ng/wp-content/uploads/2023/01/Investments-and-Securities-Act-2007.pdf",
        "agency": "SEC",
    },
    "new-rules-and-sundry-amendments-april-2025": {
        "name":  "SEC New Rules and Sundry Amendments April 2025",
        "short": "SEC Rules April 2025",
        "date":  "2025-04-01",
        "type":  "regulation",
        "url":   "https://sec.gov.ng",
        "agency": "SEC",
    },
    "rules-on-issuance-offering-and-custody-of-digital-assets": {
        "name":  "SEC Rules on Issuance Offering and Custody of Digital Assets",
        "short": "SEC Digital Assets Rules",
        "date":  "2022-01-01",
        "type":  "regulation",
        "url":   "https://sec.gov.ng",
        "agency": "SEC",
    },
    "amendment_to_rules_on_fund_portfolio_management_operations": {
        "name":  "SEC Amendment to Rules on Fund Portfolio Management Operations",
        "short": "SEC Fund Portfolio Management Rules",
        "date":  "2023-01-01",
        "type":  "regulation",
        "url":   "https://sec.gov.ng",
        "agency": "SEC",
    },
    "rules-on-private-company-securities": {
        "name":  "SEC Rules on Private Company Securities",
        "short": "SEC Private Company Securities Rules",
        "date":  "2021-01-01",
        "type":  "regulation",
        "url":   "https://sec.gov.ng",
        "agency": "SEC",
    },
    "rules-on-robo-advisory-and-trade-repositories": {
        "name":  "SEC Rules on Robo-Advisory Services and Trade Repositories",
        "short": "SEC Robo-Advisory and Trade Repository Rules",
        "date":  "2021-01-01",
        "type":  "regulation",
        "url":   "https://sec.gov.ng",
        "agency": "SEC",
    },
    "rules_on_sharia_advisory_services": {
        "name":  "SEC Rules on Sharia Advisory Services",
        "short": "SEC Sharia Advisory Services Rules",
        "date":  "2022-01-01",
        "type":  "regulation",
        "url":   "https://sec.gov.ng",
        "agency": "SEC",
    },
    "sec-amlcftcpf-regulations-12-may-2022": {
        "name":  "SEC Capital Market Operators Anti-Money Laundering Regulations 2022",
        "short": "SEC AML/CFT/CPF Regulations 2022",
        "date":  "2022-05-12",
        "type":  "regulation",
        "url":   "https://sec.gov.ng",
        "agency": "SEC",
    },

    #  NDPC 
    "ndpa_2023": {
        "name":  "Nigeria Data Protection Act 2023",
        "short": "NDPA 2023",
        "date":  "2023-06-14",
        "type":  "act",
        "url":   "https://ndpc.gov.ng/media/NDPA_2023.pdf",
        "agency": "NDPC",
    },
    "guidelinesforimplementationofndprinpublicinstitutionsfinal11": {
        "name":  "NDPC Guidelines for Implementation of NDPR in Public Institutions",
        "short": "NDPC NDPR Implementation Guidelines",
        "date":  "2020-01-01",
        "type":  "guideline",
        "url":   "https://ndpc.gov.ng",
        "agency": "NDPC",
    },
    "ndp-act-gaid-2025-march-20th": {
        "name":  "Nigeria Data Protection Act General Application and Implementation Directive 2025",
        "short": "NDP-ACT GAID 2025",
        "date":  "2025-03-20",
        "type":  "directive",
        "url":   "https://ndpc.gov.ng",
        "agency": "NDPC",
    },

    #  NITDA 
    "ndpr_2019": {
        "name":  "Nigeria Data Protection Regulation 2019",
        "short": "NDPR 2019",
        "date":  "2019-01-25",
        "type":  "regulation",
        "url":   "https://nitda.gov.ng/wp-content/uploads/2020/01/NigeriaDataProtectionRegulation.pdf",
        "agency": "NITDA",
    },

    #  NRS (Nigeria Revenue Service — replaced FIRS 2025) 
    "nigeria_tax_act_2025": {
        "name":  "Nigeria Tax Act 2025",
        "short": "NTA 2025",
        "date":  "2025-06-26",
        "type":  "act",
        "url":   "https://nrs.gov.ng/nigeria-tax-act-2025.pdf",
        "agency": "NRS",
    },
    "nigeria_revenue_service_establishment_act_2025_84bc74e1bf": {
        "name":  "Nigeria Revenue Service Establishment Act 2025",
        "short": "NRS Establishment Act 2025",
        "date":  "2025-01-01",
        "type":  "act",
        "url":   "https://nrs.gov.ng",
        "agency": "NRS",
    },

    #  FIRS (Federal Inland Revenue Service — pre-2025 tax authority) 
    # NOTE: FIRS was replaced by NRS via NRS Establishment Act 2025.
    # FIRS documents keep the FIRS tag for citation accuracy.
    # nodes.py routes both FIRS and NRS keywords to both agencies.
    "companies income tax act": {
        "name":  "Companies Income Tax Act",
        "short": "CITA",
        "date":  "2004-01-01",
        "type":  "act",
        "url":   "https://www.firs.gov.ng",
        "agency": "FIRS",
    },

    #  NCC 
    "legislation-nigerian_communications_act_2003": {
        "name":  "Nigerian Communications Act 2003",
        "short": "NCA 2003",
        "date":  "2003-01-01",
        "type":  "act",
        "url":   "https://www.ncc.gov.ng",
        "agency": "NCC",
    },
}


# ----- Folder → agency mapping ----------------------------------------
# Maps folder names in data/documents/ to the correct agency code.
# FIRS folder maps to "FIRS" (not NRS) for citation accuracy.

AGENCY_MAP = {
    "CBN": "CBN",
    "CAC": "CAC",
    "SEC": "SEC",
    "SEC_Nigeria": "SEC",   # legacy folder name alias
    "NDPC": "NDPC",
    "NITDA": "NITDA",
    "NRS": "NRS",
    "FIRS": "FIRS",
    "NCC": "NCC",
}


class MetadataExtractor:
    """
    Extracts and structures metadata from Nigerian regulatory documents.
    Combines filename matching, folder detection, and text scanning.

    Priority order:
      1. KNOWN_DOCUMENTS registry  — most accurate, manually curated
      2. Folder-based agency detection
      3. Text scanning              — fallback for unknown documents
    """

    def _detect_agency_from_path(self, file_path: str) -> str:
        """Detects agency from the folder structure."""
        path = Path(file_path)
        for part in path.parts:
            if part in AGENCY_MAP:
                return AGENCY_MAP[part]
        return "UNKNOWN"

    def _detect_agency_from_text(self, text: str) -> str:
        """Fallback: detects issuing agency from document text content."""
        t = text[:2000].upper()

        if "CENTRAL BANK OF NIGERIA" in t or ("CBN" in t[:500] and "SECURITIES" not in t[:500]):
            return "CBN"
        if "SECURITIES AND EXCHANGE COMMISSION" in t or "SEC NIGERIA" in t:
            return "SEC"
        if "NIGERIA REVENUE SERVICE" in t or "NRS" in t[:500]:
            return "NRS"
        if "FEDERAL INLAND REVENUE" in t or ("FIRS" in t[:500] and "NRS" not in t[:500]):
            return "FIRS"
        if "DATA PROTECTION COMMISSION" in t or "NDPC" in t[:500]:
            return "NDPC"
        if "NITDA" in t or ("INFORMATION TECHNOLOGY DEVELOPMENT" in t and "CBN" not in t[:500]):
            return "NITDA"
        if "CORPORATE AFFAIRS COMMISSION" in t or "CAC" in t[:500]:
            return "CAC"
        if "NIGERIAN COMMUNICATIONS COMMISSION" in t or "NCC" in t[:500]:
            return "NCC"
        return "UNKNOWN"

    def _extract_date_from_text(self, text: str) -> str:
        """
        Scans document text for publication date.
        Handles common Nigerian regulatory date formats.
        """
        patterns = [
            (
                r'(January|February|March|April|May|June|July|August|'
                r'September|October|November|December)[,\s]+(\d{4})'
            ),
            r'(?:Published|Issued|Dated?)[:\s]+.*?(\d{4})',
            (
                r'(\d{1,2})(?:st|nd|rd|th)?\s+'
                r'(January|February|March|April|May|June|July|August|'
                r'September|October|November|December)\s+(\d{4})'
            ),
        ]
        for pattern in patterns:
            match = re.search(pattern, text[:3000], re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    return f"{groups[0]} {groups[1]}"
                elif len(groups) == 3:
                    return f"{groups[0]} {groups[1]} {groups[2]}"
        return "Date not found"

    def _extract_year(self, date_str: str) -> str:
        """Extracts 4-digit year from a date string."""
        match = re.search(r'\d{4}', date_str)
        return match.group(0) if match else str(datetime.now().year)

    def _generate_doc_id(self, agency: str, short_name: str, year: str) -> str:
        """
        Generates a unique document ID for the audit trail.
        Format: CBN-CYBERSECURITY-FRAMEWORK-2024
        """
        clean = re.sub(r'[^A-Z0-9]', '-', short_name.upper())
        clean = re.sub(r'-+', '-', clean).strip('-')[:40]
        return f"{agency}-{clean}-{year}"

    def extract(
        self,
        file_path: str,
        document_text: str = "",
        override_url: str = "",
    ) -> DocumentMetadata:
        """
        Main method. Extracts full metadata for a document.
        """
        path = Path(file_path)
        # Normalise: lowercase, remove extension
        stem = path.stem.lower()

        #  Step 1: Exact key match in registry 
        if stem in KNOWN_DOCUMENTS:
            info = KNOWN_DOCUMENTS[stem]
            agency = info.get("agency") or self._detect_agency_from_path(file_path)
            year = self._extract_year(info["date"])
            return DocumentMetadata(
                agency = agency,
                document_name = info["name"],
                short_name  = info["short"],
                publication_date = info["date"],
                publication_year = year,
                doc_type = info["type"],
                source_url = override_url or info["url"],
                filename = path.name,
                doc_id = self._generate_doc_id(agency, info["short"], year),
            )

        #  Step 2: Partial match in registry 
        for key, info in KNOWN_DOCUMENTS.items():
            if key in stem or stem in key:
                agency = info.get("agency") or self._detect_agency_from_path(file_path)
                if agency == "UNKNOWN" and document_text:
                    agency = self._detect_agency_from_text(document_text)
                year = self._extract_year(info["date"])
                return DocumentMetadata(
                    agency = agency,
                    document_name = info["name"],
                    short_name  = info["short"],
                    publication_date = info["date"],
                    publication_year = year,
                    doc_type = info["type"],
                    source_url = override_url or info["url"],
                    filename = path.name,
                    doc_id = self._generate_doc_id(agency, info["short"], year),
                )

        #  Step 3: Fallback — derive from path and text 
        agency = self._detect_agency_from_path(file_path)
        if agency == "UNKNOWN" and document_text:
            agency = self._detect_agency_from_text(document_text)

        clean_name = stem.replace('_', ' ').replace('-', ' ').title()
        date_str = self._extract_date_from_text(document_text) if document_text else "Unknown"
        year = self._extract_year(date_str)

        return DocumentMetadata(
            agency = agency,
            document_name = clean_name,
            short_name = clean_name[:40],
            publication_date = date_str,
            publication_year = year,
            doc_type = "document",
            source_url = override_url or "",
            filename = path.name,
            doc_id = self._generate_doc_id(agency, clean_name[:20], year),
        )
