"""
ingest.py

Master ingestion script for NaijaCodex.
Run this to process all Nigerian regulatory documents
and load them into Pinecone.

Usage:
    python ingest.py
    python ingest.py --agency CBN
    python ingest.py --dry-run
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.ingestion.ocr_processor import OCRProcessor
from src.ingestion.legal_chunker import NigerianLegalChunker
from src.ingestion.metadata_extractor import MetadataExtractor
from src.retrieval.embedder import NaijaCodexEmbedder
from src.retrieval.vector_store import NaijaCodexVectorStore


# Documents folder structure
DOCS_ROOT = Path("data/documents")

AGENCY_FOLDERS = {
    "CBN": DOCS_ROOT / "CBN",
    "SEC": DOCS_ROOT / "SEC_Nigeria",
    "FIRS": DOCS_ROOT / "FIRS",
    "NDPC": DOCS_ROOT / "NDPC",
    "NITDA": DOCS_ROOT / "NITDA",
}


def ingest_agency(
    agency: str,
    folder: Path,
    ocr: OCRProcessor,
    chunker: NigerianLegalChunker,
    extractor: MetadataExtractor,
    vector_store: NaijaCodexVectorStore,
    dry_run: bool = False,
) -> dict:
    """
    Ingests all PDFs from one agency folder.
    Returns summary stats.
    """
    pdfs = list(folder.glob("*.pdf"))

    if not pdfs:
        print(f"No PDFs found in {folder}")
        return {"agency": agency, "documents": 0, "chunks": 0}

    print(f"\n{'='*50}")
    print(f"INGESTING: {agency} ({len(pdfs)} documents)")
    print(f"{'='*50}")

    total_chunks = 0
    total_docs = 0
    ingestion_log = []

    for pdf_path in pdfs:
        print(f"\n{pdf_path.name}")

        try:
            # Step 1: Extract text (with OCR if needed)
            processed = ocr.process(str(pdf_path))

            if processed.quality_score < 0.1:
                print(f"Quality too low ({processed.quality_score}) — skipping")
                continue

            # Step 2: Extract metadata
            metadata = extractor.extract(
                file_path=str(pdf_path),
                document_text=processed.text,
            )
            print(f"{metadata.document_name}")
            print(f"{metadata.publication_date}")

            # Step 3: Legal chunking
            chunks = chunker.chunk_document(
                text = processed.text,
                agency = metadata.agency,
                document_name = metadata.document_name,
                source_url = metadata.source_url,
                publication_date = metadata.publication_date,
            )

            if not chunks:
                print(f"No chunks created — skipping")
                continue

            # Step 4: Convert to Documents with full metadata
            documents = chunker.chunks_to_documents(chunks)

            # Add doc_id to all chunk metadata
            for doc in documents:
                doc.metadata["doc_id"] = metadata.doc_id
                doc.metadata["doc_type"] = metadata.doc_type

            # Step 5: Upsert to Pinecone
            if not dry_run:
                upserted = vector_store.upsert_chunks(documents)
                print(f"{upserted} chunks → Pinecone")
            else:
                print(f"DRY RUN: would upsert {len(documents)} chunks")

            total_chunks += len(documents)
            total_docs += 1

            ingestion_log.append({
                "filename": pdf_path.name,
                "document_name": metadata.document_name,
                "agency": metadata.agency,
                "doc_id": metadata.doc_id,
                "publication_date": metadata.publication_date,
                "chunks": len(documents),
                "was_ocr": processed.was_ocr,
                "quality_score": processed.quality_score,
                "ingested_at": datetime.now().isoformat(),
            })

        except Exception as e:
            print(f"Failed: {e}")
            continue

    return {
        "agency": agency,
        "documents": total_docs,
        "chunks": total_chunks,
        "log": ingestion_log,
    }


def save_ingestion_report(results: list):
    """Saves ingestion summary to results folder."""
    os.makedirs("results", exist_ok=True)

    report = {
        "ingestion_timestamp": datetime.now().isoformat(),
        "total_documents": sum(r["documents"] for r in results),
        "total_chunks": sum(r["chunks"] for r in results),
        "agencies": results,
    }

    report_path = f"results/ingestion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved: {report_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description="NaijaCodex Document Ingestion")
    parser.add_argument("--agency", help="Ingest only this agency (CBN, SEC, FIRS, NDPC, NITDA)")
    parser.add_argument("--dry-run", action="store_true", help="Test without writing to Pinecone")
    args = parser.parse_args()

    print("=" * 50)
    print("NAIJACODEX — DOCUMENT INGESTION PIPELINE")
    print("=" * 50)

    if args.dry_run:
        print("DRY RUN MODE — nothing will be written to Pinecone")

    # Initialise components
    print("\nInitialising components...")
    ocr = OCRProcessor()
    chunker = NigerianLegalChunker()
    extractor = MetadataExtractor()
    embedder = NaijaCodexEmbedder()
    store = NaijaCodexVectorStore(embedder=embedder)

    # Determine which agencies to process
    if args.agency:
        agencies = {args.agency: AGENCY_FOLDERS[args.agency]}
    else:
        agencies = AGENCY_FOLDERS

    # Run ingestion
    all_results = []
    for agency, folder in agencies.items():
        result = ingest_agency(
            agency=agency,
            folder=folder,
            ocr=ocr,
            chunker=chunker,
            extractor=extractor,
            vector_store=store,
            dry_run=args.dry_run,
        )
        all_results.append(result)

    # Save report
    report = save_ingestion_report(all_results)

    # Final summary
    print("\n" + "=" * 50)
    print("INGESTION COMPLETE")
    print("=" * 50)
    print(f"Total documents: {report['total_documents']}")
    print(f"Total chunks: {report['total_chunks']}")
    print()

    # Show Pinecone stats
    if not args.dry_run:
        stats = store.get_index_stats()
        print(f"Pinecone index: {stats['index_name']}")
        print(f"Total vectors: {stats['total_vectors']}")

    print("\nNaijaCodex knowledge base ready")


if __name__ == "__main__":
    main()
