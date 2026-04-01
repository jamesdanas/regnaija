import json
import os
import sys
from pathlib import Path

# Ensure we can import from src
sys.path.insert(0, '.')

from src.ingestion.ocr_processor import OCRProcessor
from src.ingestion.legal_chunker import NigerianLegalChunker
from src.ingestion.metadata_extractor import MetadataExtractor

def generate_full_library_cache():
    print("=" * 50)
    print("NAIJACODEX - FULL LIBRARY CACHE GENERATOR")
    print("=" * 50)
    
    ocr = OCRProcessor()
    chunker = NigerianLegalChunker()
    extractor = MetadataExtractor()
    
    docs_root = Path("data/documents")
    # Our 5 core agencies
    agencies = ["CBN", "NDPC", "NITDA", "NRS", "SEC_Nigeria"]
    
    all_processed_chunks = []
    total_docs = 0

    for agency in agencies:
        agency_folder = docs_root / agency
        if not agency_folder.exists():
            print(f"Skipping: {agency} (Folder not found)")
            continue
            
        print(f"\nProcessing Agency: {agency}")
        
        # Grab both PDFs and Text files
        files = list(agency_folder.glob("*.pdf")) + list(agency_folder.glob("*.txt"))
        
        for file_path in files:
            print(f"{file_path.name}")
            try:
                # 1. Extract raw text
                if file_path.suffix.lower() == '.pdf':
                    proc = ocr.process(str(file_path))
                    text = proc.text
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()

                # 2. Extract Metadata
                meta = extractor.extract(str(file_path), text)

                # 3. Use the Smart Chunker
                chunks = chunker.chunk_document(
                    text=text, 
                    agency=meta.agency, 
                    document_name=meta.document_name,
                    source_url=meta.source_url,
                    publication_date=meta.publication_date
                )

                # 4. Map to the JSON Schema
                for i, c in enumerate(chunks):
                    all_processed_chunks.append({
                        "id": f"{meta.doc_id}_{i}",
                        "text": c.text,
                        "metadata": {
                            "agency": meta.agency,
                            "document_name": meta.document_name,
                            "section": c.section_number,
                            "title": c.section_title,
                            "doc_id": meta.doc_id,
                            "date": meta.publication_date,
                            "url": meta.source_url,
                            "doc_type": meta.doc_type
                        }
                    })
                total_docs += 1
                print(f"Added {len(chunks)} chunks")

            except Exception as e:
                print(f"Error processing {file_path.name}: {e}")

    # 5. Final Save to data/processed
    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / "chunks_ready.json"
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(all_processed_chunks, f, indent=4)
        
    print("\n" + "=" * 50)
    print("SUCCESS: Full Library Cached!")
    print(f"Destination: {output_path}")
    print(f"Total Documents: {total_docs}")
    print(f"Total Chunks: {len(all_processed_chunks)}")
    print("=" * 50)

if __name__ == "__main__":
    generate_full_library_cache()
