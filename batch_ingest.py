"""
batch_ingest.py - RegNaija Production Ingestion Script
=======================================================
Uses the full src/ingestion pipeline directly:
    OCRProcessor -> NigerianLegalChunker → RegNaijaVectorStore

Bypasses DocumentIngester.ingest() which skips scanned PDFs instead
of falling back to OCR. This script handles every edge case:

  - Scanned PDFs       -> OCRProcessor auto-detects and runs Tesseract
  - Corrupt PDF struct -> Paragraph fallback chunker kicks in
  - Low quality OCR    -> Flagged in manifest, still ingested
  - Pinecone errors    -> Retry up to 3 times per batch
  - Duplicate check    -> Warns if index already has vectors

Run: python batch_ingest.py [--dry-run] [--clear]
"""

import os
import re
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from langchain_core.documents import Document

load_dotenv()
sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BATCH] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("batch_ingest")


# ------------------------------------------------------------------------------
# DOCUMENT REGISTRY — 32 documents across 8 agencies
# (pdf_path, agency, doc_id, document_name, publication_date, source_url)
# ------------------------------------------------------------------------------

DOCUMENTS = [

    # CBN - Core 
    (
        "data/documents/CBN/CBN Risk-Based Cybersecurity Framework for DMBs and PSBs_2024.pdf",
        "CBN", "CBN-CYBERSECURITY-FRAMEWORK-2024",
        "CBN Risk-Based Cybersecurity Framework for DMBs and PSBs 2024",
        "2024", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/cbn_consumer_protection.pdf",
        "CBN", "CBN-CONSUMER-PROTECTION-FRAMEWORK-2016",
        "CBN Consumer Protection Framework 2016",
        "2016", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/cbn_open_banking_policy.pdf",
        "CBN", "CBN-OPEN-BANKING-POLICY-2023",
        "CBN Open Banking Policy 2023",
        "2023", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/REGULATORY_FRAMEWORK_FOR_MOBILE_PAYMENTS_SERVICES_IN_NIGERIA.pdf",
        "CBN", "CBN-MOBILE-PAYMENTS-FRAMEWORK",
        "CBN Regulatory Framework for Mobile Payments Services in Nigeria",
        "2021", "https://www.cbn.gov.ng",
    ),

    # CBN - AML (both scanned - OCR will be applied automatically)
    (
        "data/documents/CBN/AML/AML CIRCULAR AND REGULATIONS MERGED.pdf",
        "CBN", "CBN-AML-REGULATIONS-MERGED",
        "CBN AML Circular and Regulations",
        "2022", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/AML/Circular_and_AML_Licensing_Guideline.pdf",
        "CBN", "CBN-AML-LICENSING-GUIDELINE",
        "CBN AML Licensing Guideline",
        "2022", "https://www.cbn.gov.ng",
    ),

    # CBN - Basel III 
    (
        "data/documents/CBN/Basel/Circular on Basel III Implementation by DMBS in Nigeria.pdf",
        "CBN", "CBN-BASEL-III-CIRCULAR",
        "CBN Basel III Implementation Circular for DMBs in Nigeria",
        "2024", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/Basel/1. GUIDELINES ON REGULATORY CAPITAL.pdf",
        "CBN", "CBN-BASEL-REGULATORY-CAPITAL",
        "CBN Guidelines on Regulatory Capital",
        "2024", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/Basel/2. GUIDELINES ON LEVERAGE RATIO (LeR).pdf",
        "CBN", "CBN-BASEL-LEVERAGE-RATIO",
        "CBN Guidelines on Leverage Ratio",
        "2024", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/Basel/3. GUIDELINES ON LIQUIDITY COVERAGE RATIO (LCR).pdf",
        "CBN", "CBN-BASEL-LIQUIDITY-COVERAGE-RATIO",
        "CBN Guidelines on Liquidity Coverage Ratio",
        "2024", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/Basel/4. GUIDELINES ON LIQUIDITY MONITORING TOOLS (LMT).pdf",
        "CBN", "CBN-BASEL-LIQUIDITY-MONITORING-TOOLS",
        "CBN Guidelines on Liquidity Monitoring Tools",
        "2024", "https://www.cbn.gov.ng",
    ),
    (
        "data/documents/CBN/Basel/5. GUIDELINES ON LARGE EXPOSURES (LEX).pdf",
        "CBN", "CBN-BASEL-LARGE-EXPOSURES",
        "CBN Guidelines on Large Exposures",
        "2024", "https://www.cbn.gov.ng",
    ),

    # CBN - Forex 
    (
        "data/documents/CBN/Forex/The new Forex Manual - 4th Edition.pdf",
        "CBN", "CBN-FOREX-MANUAL-4TH-EDITION",
        "CBN Foreign Exchange Manual 4th Edition",
        "2024", "https://www.cbn.gov.ng",
    ),

    # CBN - PSP 
    (
        "data/documents/CBN/PSP/CIRCULAR AND GUIDELINES FOR LICENSING AND REGULATION OF PAYMENTS SERVICE HOLDING COMPANIES IN NIGERIA.pdf",
        "CBN", "CBN-PSP-HOLDING-COMPANIES-CIRCULAR",
        "CBN Circular and Guidelines for Licensing and Regulation of Payment Service Holding Companies",
        "2021", "https://www.cbn.gov.ng",
    ),

    # CAC 
    (
        "data/documents/CAC/CAMA-NOTE-BOOK-FULL-VERSION.pdf",
        "CAC", "CAC-CAMA-2020",
        "Companies and Allied Matters Act 2020",
        "2020", "https://www.cac.gov.ng",
    ),
    (
        "data/documents/CAC/COMPANIES-REGULATIONS-2021-published.pdf",
        "CAC", "CAC-COMPANIES-REGULATIONS-2021",
        "Companies Regulations 2021",
        "2021", "https://www.cac.gov.ng",
    ),

    # SEC               
    (
        "data/documents/SEC/investments_securities_act.pdf",
        "SEC", "SEC-ISA-2007",
        "Investments and Securities Act 2007",
        "2007", "https://sec.gov.ng",
    ),
    (
        "data/documents/SEC/New-Rules-and-sundry-amendments-April-2025.pdf",
        "SEC", "SEC-RULES-APRIL-2025",
        "SEC New Rules and Sundry Amendments April 2025",
        "2025", "https://sec.gov.ng",
    ),
    (
        "data/documents/SEC/Rules-on-Issuance-Offering-and-Custody-of-Digital-Assets.pdf",
        "SEC", "SEC-DIGITAL-ASSETS-RULES",
        "SEC Rules on Issuance Offering and Custody of Digital Assets",
        "2022", "https://sec.gov.ng",
    ),
    (
        "data/documents/SEC/Amendment_to_Rules_on_Fund_Portfolio_Management_Operations.pdf",
        "SEC", "SEC-FUND-PORTFOLIO-MANAGEMENT-RULES",
        "SEC Amendment to Rules on Fund Portfolio Management Operations",
        "2023", "https://sec.gov.ng",
    ),
    (
        "data/documents/SEC/Rules-on-Private-Company-Securities.pdf",
        "SEC", "SEC-PRIVATE-COMPANY-SECURITIES-RULES",
        "SEC Rules on Private Company Securities",
        "2021", "https://sec.gov.ng",
    ),
    (
        "data/documents/SEC/Rules-on-Robo-Advisory-and-Trade-Repositories.pdf",
        "SEC", "SEC-ROBO-ADVISORY-TRADE-REPOSITORIES",
        "SEC Rules on Robo-Advisory Services and Trade Repositories",
        "2021", "https://sec.gov.ng",
    ),
    (
        "data/documents/SEC/Rules_on_Sharia_Advisory_Services.pdf",
        "SEC", "SEC-SHARIA-ADVISORY-SERVICES-RULES",
        "SEC Rules on Sharia Advisory Services",
        "2022", "https://sec.gov.ng",
    ),
    (
        "data/documents/SEC/SEC-AMLCFTCPF-REGULATIONS-12-MAY-2022.pdf",
        "SEC", "SEC-AML-CFT-CPF-REGULATIONS-2022",
        "SEC Capital Market Operators Anti-Money Laundering Regulations 2022",
        "2022", "https://sec.gov.ng",
    ),

    # NDPC                
    (
        "data/documents/NDPC/ndpa_2023.pdf",
        "NDPC", "NDPC-NDPA-2023",
        "Nigeria Data Protection Act 2023",
        "2023", "https://ndpc.gov.ng",
    ),
    (
        "data/documents/NDPC/GuidelinesForImplementationOfNDPRInPublicInstitutionsFinal11.pdf",
        "NDPC", "NDPC-NDPR-IMPLEMENTATION-GUIDELINES",
        "NDPC Guidelines for Implementation of NDPR in Public Institutions",
        "2020", "https://ndpc.gov.ng",
    ),
    (
        "data/documents/NDPC/NDP-ACT-GAID-2025-MARCH-20TH.pdf",
        "NDPC", "NDPC-NDP-ACT-GAID-2025",
        "Nigeria Data Protection Act General Application and Implementation Directive 2025",
        "2025", "https://ndpc.gov.ng",
    ),

    # NITDA 
    (
        "data/documents/NITDA/ndpr_2019.pdf",
        "NITDA", "NITDA-NDPR-2019",
        "Nigeria Data Protection Regulation 2019",
        "2019", "https://nitda.gov.ng",
    ),

    # NRS                
    (
        "data/documents/NRS/nigeria_tax_act_2025.pdf",
        "NRS", "NRS-NIGERIA-TAX-ACT-2025",
        "Nigeria Tax Act 2025",
        "2025", "https://nrs.gov.ng",
    ),
    (
        "data/documents/NRS/NIGERIA_REVENUE_SERVICE_ESTABLISHMENT_ACT_2025_84bc74e1bf.pdf",
        "NRS", "NRS-ESTABLISHMENT-ACT-2025",
        "Nigeria Revenue Service Establishment Act 2025",
        "2025", "https://nrs.gov.ng",
    ),

    # FIRS                
    (
        "data/documents/FIRS/Companies Income Tax Act.pdf",
        "FIRS", "FIRS-COMPANIES-INCOME-TAX-ACT",
        "Companies Income Tax Act",
        "2004", "https://www.firs.gov.ng",
    ),

    # NCC                
    (
        "data/documents/NCC/Legislation-Nigerian_Communications_Act_2003.pdf",
        "NCC", "NCC-COMMUNICATIONS-ACT-2003",
        "Nigerian Communications Act 2003",
        "2003", "https://www.ncc.gov.ng",
    ),
]


# ------------------------------------------------------------------------------
# FALLBACK PARAGRAPH CHUNKER
# Used when NigerianLegalChunker finds too few sections relative to page count.
# Triggered when: sections_found < (page_count / 5)
# This handles SEC documents with corrupt internal PDF structure.
# ------------------------------------------------------------------------------

def paragraph_chunk(
    text: str,
    agency: str,
    doc_id: str,
    document_name: str,
    publication_date: str,
    source_url: str,
    max_chunk_size: int = 1000,
    min_chunk_size: int = 100,
    overlap_size: int = 80,
) -> list[Document]:
    """
    Paragraph-based fallback chunker for documents where legal section
    detection fails. Splits on double newlines and groups into
    overlapping windows of max_chunk_size characters.
    """
    # Split on paragraph boundaries
    paragraphs = re.split(r'\n{2,}', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: list[Document] = []
    current = ""
    chunk_index = 0

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if len(current) >= min_chunk_size:
                chunk_id = (
                    f"{agency.lower()}"
                    f"_{re.sub(r'[^a-z0-9]', '_', doc_id.lower()[:20])}"
                    f"_chunk{chunk_index:04d}"
                )
                chunks.append(Document(
                    page_content=current,
                    metadata={
                        "chunk_id": chunk_id,
                        "chunk_index": chunk_index,
                        "section_number": "General",
                        "section_title":  "",
                        "parent_section": "Paragraph-chunked",
                        "agency": agency,
                        "document_name": document_name,
                        "source_url": source_url,
                        "publication_date": publication_date,
                        "doc_id": doc_id,
                        "page_number": 0
                    }
                ))
                chunk_index += 1
                # Overlap: keep tail of previous chunk
                tail = current[-overlap_size:] if len(current) > overlap_size else current
                current = (tail + "\n\n" + para).strip()
            else:
                current = (current + "\n\n" + para).strip() if current else para

    # Flush last chunk
    if len(current) >= min_chunk_size:
        chunk_id = (
            f"{agency.lower()}"
            f"_{re.sub(r'[^a-z0-9]', '_', doc_id.lower()[:20])}"
            f"_chunk{chunk_index:04d}"
        )
        chunks.append(Document(
            page_content=current,
            metadata={
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "section_number": "General",
                "section_title": "",
                "parent_section": "Paragraph-chunked",
                "agency": agency,
                "document_name": document_name,
                "source_url": source_url,
                "publication_date": publication_date,
                "doc_id": doc_id,
                "page_number": 0
            }
        ))

    return chunks


# ------------------------------------------------------------------------------
# PREFLIGHT CHECKS
# ------------------------------------------------------------------------------

def preflight_checks() -> bool:
    """Verifies all required services and files are ready before ingestion."""
    log.info("Running preflight checks...")
    passed = True

    # 1. Environment variables
    required_env = ["PINECONE_API_KEY", "PINECONE_INDEX"]
    for var in required_env:
        if not os.getenv(var):
            log.error(f"Missing env var: {var}")
            passed = False
        else:
            log.info(f"{var} set")

    # 2. Pinecone connectivity
    try:
        from pinecone import Pinecone
        pc  = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        idx = pc.Index(os.getenv("PINECONE_INDEX", "naijacodex"))
        stats = idx.describe_index_stats()
        count = stats["total_vector_count"]
        log.info(f"Pinecone connected -- {count} vectors in index")
        if count > 0:
            log.warning(f"Index is NOT empty ({count} vectors). Use --clear to wipe.")
    except Exception as e:
        log.error(f"Pinecone connection failed: {e}")
        passed = False

    # 3. Tesseract availability
    try:
        import pytesseract
        ver = pytesseract.get_tesseract_version()
        log.info(f"Tesseract {ver}")
    except Exception:
        log.warning("Tesseract not found -- scanned PDFs will fail OCR")

    # 4. All document files exist
    missing = []
    for entry in DOCUMENTS:
        path = Path(entry[0])
        if not path.exists():
            missing.append(str(path))
    if missing:
        log.error(f"{len(missing)} files not found:")
        for m in missing:
            log.error(f"{m}")
        passed = False
    else:
        log.info(f"All {len(DOCUMENTS)} document files found")

    return passed


def clear_index() -> None:
    """Wipes all vectors from the Pinecone index."""
    from pinecone import Pinecone
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    idx = pc.Index(os.getenv("PINECONE_INDEX", "naijacodex"))
    log.info("Clearing Pinecone index...")
    idx.delete(delete_all=True)
    time.sleep(8)
    stats = idx.describe_index_stats()
    log.info(f"Index cleared. Vectors remaining: {stats['total_vector_count']}")


# ------------------------------------------------------------------------------
# UPSERT WITH RETRY
# ------------------------------------------------------------------------------

def upsert_with_retry(
    store,
    documents: list[Document],
    max_retries: int = 3,
    delay: float = 5.0,
) -> int:
    """Upserts documents to Pinecone with exponential backoff retry."""
    for attempt in range(1, max_retries + 1):
        try:
            return store.upsert_chunks(documents)
        except Exception as e:
            if attempt == max_retries:
                log.error(f"Upsert failed after {max_retries} attempts: {e}")
                raise
            wait = delay * attempt
            log.warning(f"Upsert attempt {attempt} failed -- retrying in {wait}s: {e}")
            time.sleep(wait)
    return 0


# ------------------------------------------------------------------------------
# MAIN INGESTION
# ------------------------------------------------------------------------------

def ingest_all(dry_run: bool = False) -> dict:
    """
    Main ingestion loop. Returns a manifest dict for audit trail.
    """
    from src.ingestion.ocr_processor   import OCRProcessor
    from src.ingestion.legal_chunker   import NigerianLegalChunker
    from src.retrieval.embedder        import RegNaijaEmbedder
    from src.retrieval.vector_store    import RegNaijaVectorStore

    # Initialise shared components once
    log.info("Initialising pipeline components...")
    ocr = OCRProcessor()
    chunker = NigerianLegalChunker(
        max_chunk_size = 1000,
        min_chunk_size = 100,
        overlap_size = 80
    )

    if not dry_run:
        embedder = RegNaijaEmbedder()
        store = RegNaijaVectorStore(embedder=embedder)

    total_docs = len(DOCUMENTS)
    total_chunks  = 0
    failed = []
    manifest = {
        "run_date": datetime.now().isoformat(),
        "dry_run": dry_run,
        "documents": []
    }

    print(f"\n{'='*65}")
    print(f"RegNaija Batch Ingestion -- {total_docs} documents")
    print(f"Mode: {'DRY RUN (no Pinecone writes)' if dry_run else 'LIVE'}")
    print(f"{'='*65}\n")

    for i, entry in enumerate(DOCUMENTS, 1):
        pdf_path, agency, doc_id, doc_name, pub_date, source_url = entry
        path = Path(pdf_path)

        print(f"[{i:02d}/{total_docs}] {agency:5s} | {path.name[:60]}")

        doc_record = {
            "index": i,
            "path": pdf_path,
            "agency": agency,
            "doc_id": doc_id,
            "doc_name": doc_name,
            "status": None,
            "chunks": 0,
            "was_ocr": False,
            "quality": 0.0,
            "chunker_used": None,
            "error": None
        }

        # STEP 1: Extract text
        try:
            processed = ocr.process(str(path))
            doc_record["was_ocr"]  = processed.was_ocr
            doc_record["quality"]  = processed.quality_score
            text = processed.text

            if not text or len(text.strip()) < 50:
                raise ValueError(f"Extracted text too short ({len(text.strip())} chars)")

            log.info(
                f"         Text: {len(text):,} chars | "
                f"Pages: {processed.page_count} | "
                f"OCR: {processed.was_ocr} | "
                f"Quality: {processed.quality_score:.0%}"
            )
        except Exception as e:
            log.error(f"Text extraction failed: {e}")
            doc_record["status"] = "FAILED_EXTRACTION"
            doc_record["error"]  = str(e)
            failed.append(doc_record)
            manifest["documents"].append(doc_record)
            print()
            continue

        # STEP 2: Chunk
        try:
            legal_chunks = chunker.chunk_document(
                text = text,
                agency = agency,
                document_name = doc_name,
                source_url = source_url,
                publication_date= pub_date
            )
            legal_docs = chunker.chunks_to_documents(legal_chunks)

            # Detect low-quality legal chunking relative to document size
            # Threshold: fewer than 1 section per 5 pages -> fallback
            section_ratio = len(legal_chunks) / max(processed.page_count, 1)
            if section_ratio < 0.2 and processed.page_count > 5:
                log.warning(
                    f"Low section density ({len(legal_chunks)} chunks "
                    f"for {processed.page_count} pages) -- switching to paragraph chunker"
                )
                documents = paragraph_chunk(
                    text = text,
                    agency = agency,
                    doc_id = doc_id,
                    document_name = doc_name,
                    publication_date = pub_date,
                    source_url = source_url
                )
                doc_record["chunker_used"] = "paragraph_fallback"
            else:
                # Override chunk_id using doc_id (not document_name[:20])
                # This prevents Pinecone ID collisions when document names share
                # the same first 20 characters (e.g. LCR vs LMT, NDPA vs NDP-GAID)
                for i, doc in enumerate(legal_docs):
                    doc.metadata["chunk_id"] = f"{doc_id.lower()}_chunk{i:04d}"
                    doc.metadata["doc_id"] = doc_id
                documents = legal_docs
                doc_record["chunker_used"] = "legal_chunker"

            log.info(
                f"Chunks: {len(documents)} "
                f"({doc_record['chunker_used']})"
            )

        except Exception as e:
            log.error(f"Chunking failed: {e}")
            doc_record["status"] = "FAILED_CHUNKING"
            doc_record["error"] = str(e)
            failed.append(doc_record)
            manifest["documents"].append(doc_record)
            print()
            continue

        # STEP 3: Upsert to Pinecone 
        if dry_run:
            log.info(f"[DRY RUN] Would upsert {len(documents)} chunks")
            doc_record["status"] = "DRY_RUN"
            doc_record["chunks"] = len(documents)
        else:
            try:
                upserted = upsert_with_retry(store, documents)
                total_chunks += len(documents)
                doc_record["status"] = "OK"
                doc_record["chunks"] = len(documents)
                log.info(f"Upserted {len(documents)} chunks")
            except Exception as e:
                log.error(f"Upsert failed: {e}")
                doc_record["status"] = "FAILED_UPSERT"
                doc_record["error"] = str(e)
                failed.append(doc_record)

        manifest["documents"].append(doc_record)
        print()

    # Summary 
    ok_docs = [d for d in manifest["documents"] if d["status"] == "OK"]
    print(f"\n{'='*65}")
    print("INGESTION COMPLETE")
    print(f"{'='*65}")
    print(f"Documents ingested: {len(ok_docs)}/{total_docs}")
    print(f"Total chunks: {total_chunks:,}")
    print(f"OCR used: {sum(1 for d in ok_docs if d['was_ocr'])} docs")
    print(f"Fallback chunker: {sum(1 for d in ok_docs if d['chunker_used'] == 'paragraph_fallback')} docs")
    print(f"Failed: {len(failed)}")

    if failed:
        print("Failed documents:")
        for d in failed:
            print(f"[{d['agency']}] {Path(d['path']).name}")
            print(f"Reason: {d['status']} -- {d['error']}")

    # Verify final index count
    if not dry_run:
        print()
        time.sleep(5)
        from pinecone import Pinecone
        pc  = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        idx = pc.Index(os.getenv("PINECONE_INDEX", "naijacodex"))
        stats = idx.describe_index_stats()
        final_count = stats["total_vector_count"]
        print(f"Final vector count: {final_count:,}")
        manifest["final_vector_count"] = final_count

    print(f"{'='*65}\n")

    # Save manifest
    manifest_path = Path("data/ingestion_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    log.info(f"Manifest saved -> {manifest_path}")

    return manifest


# ------------------------------------------------------------------------------
# ENTRY POINT
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="RegNaija production batch ingestion script"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run extraction and chunking but do NOT write to Pinecone",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the Pinecone index before ingestion",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip preflight checks (not recommended)",
    )
    args = parser.parse_args()

    # Preflight
    if not args.skip_preflight and not preflight_checks():
        log.error("Preflight failed -- fix errors above before ingesting.")
        sys.exit(1)

    # Optional clear
    if args.clear and not args.dry_run:
        confirm = input("\nThis will DELETE all vectors in Pinecone. Type YES to confirm: ")
        if confirm.strip().upper() == "YES":
            clear_index()
        else:
            log.info("Clear cancelled.")
            sys.exit(0)

    # Run
    ingest_all(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
