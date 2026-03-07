import json
import os
import sys
from pathlib import Path

# Setup pathing
sys.path.insert(0, '.')
from src.ingestion.ocr_processor import OCRProcessor
from src.ingestion.legal_chunker import NigerianLegalChunker

def generate_processed_manifest():
    print("=" * 40)
    print("NAIJACODEX — LOCAL CACHE GENERATOR")
    print("=" * 40)
    
    ocr = OCRProcessor()
    chunker = NigerianLegalChunker()
    
    # Target your most important file to seed the cache
    source_pdf = "data/documents/NDPC/ndpa_2023.pdf"
    output_path = "data/processed/chunks_ready.json"
    
    if not os.path.exists(source_pdf):
        # Fallback to the .txt version if the PDF isn't there
        source_pdf = "data/documents/NDPC/ndpa_2023.txt"

    if os.path.exists(source_pdf):
        print(f"Reading: {source_pdf}")
        
        # 1. Get Text
        if source_pdf.endswith('.pdf'):
            processed = ocr.process(source_pdf)
            text = processed.text
        else:
            with open(source_pdf, 'r') as f:
                text = f.read()
        
        # 2. Chunk it
        chunks = chunker.chunk_document(text, "NDPC", "Nigeria Data Protection Act 2023")
        
        # 3. Format for JSON
        manifest = []
        for i, c in enumerate(chunks):
            manifest.append({
                "id": f"ndpa_2023_{i}",
                "text": c.text,
                "metadata": {
                    "agency": "NDPC",
                    "section": c.section_number,
                    "title": c.section_title
                }
            })
            
        # 4. SAVE TO DATA/PROCESSED/
        os.makedirs("data/processed", exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(manifest, f, indent=4)
            
        print(f"\nSUCCESS: Created {output_path}")
        print(f"Total Chunks Cached: {len(manifest)}")
    else:
        print(f"Error: Could not find source file at {source_pdf}")

if __name__ == "__main__":
    generate_processed_manifest()
