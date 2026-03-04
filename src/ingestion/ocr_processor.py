"""
src/ingestion/ocr_processor.py

WHY THIS EXISTS:
Nigerian government PDFs come in two forms:
1. Clean PDFs — text layer is present, pypdf reads them directly
2. Scanned PDFs — image-based, no text layer, common with CBN/FIRS docs

This processor detects which type you have and applies the right treatment.
If it's scanned, it converts each page to an image and runs Tesseract OCR.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass

from pypdf import PdfReader
from PIL import Image
import pytesseract
from pdf2image import convert_from_path


@dataclass
class ProcessedDocument:
    """Output of the OCR processor."""
    text: str
    page_count: int
    was_ocr: bool           # True if Tesseract was used
    quality_score: float    # 0.0 - 1.0, how clean the text is
    source_path: str
    filename: str


class OCRProcessor:
    """
    Detects PDF type and extracts clean text.

    Strategy:
    - Try pypdf first (fast, accurate for clean PDFs)
    - If text yield is too low → it's a scanned PDF → use Tesseract
    - Clean the extracted text either way
    """

    # If fewer than this many chars per page, assume scanned
    MIN_CHARS_PER_PAGE = 100

    def __init__(self, tesseract_lang: str = "eng"):
        self.tesseract_lang = tesseract_lang
        self._verify_tesseract()

    def _verify_tesseract(self):
        """Confirms Tesseract is installed on the system."""
        try:
            version = pytesseract.get_tesseract_version()
            print(f"  Tesseract available: {version}")
        except Exception:
            print("  ⚠️  Tesseract not found — OCR will fail on scanned PDFs")
            print("  Fix: sudo apt install tesseract-ocr")

    def _extract_with_pypdf(self, pdf_path: str) -> Tuple[str, int]:
        """
        Attempts direct text extraction using pypdf.
        Returns (text, page_count).
        """
        reader = PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return '\n\n'.join(pages), len(pages)

    def _extract_with_ocr(self, pdf_path: str) -> Tuple[str, int]:
        """
        Converts PDF pages to images and runs Tesseract OCR.
        Used for scanned/image-based PDFs.
        Returns (text, page_count).
        """
        print(f"  Running OCR on: {Path(pdf_path).name}")

        # Convert PDF to images
        images = convert_from_path(
            pdf_path,
            dpi=300,            # Higher DPI = better OCR accuracy
            fmt='PNG',
        )

        pages = []
        for i, image in enumerate(images):
            print(f"    OCR page {i+1}/{len(images)}...")

            # Preprocess image for better OCR
            image = self._preprocess_image(image)

            # Run Tesseract
            text = pytesseract.image_to_string(
                image,
                lang=self.tesseract_lang,
                config='--psm 6',   # Assume uniform block of text
            )
            pages.append(text)

        return '\n\n'.join(pages), len(images)

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Basic image preprocessing to improve OCR accuracy.
        Converts to grayscale — sufficient for most government docs.
        """
        # Convert to grayscale
        if image.mode != 'L':
            image = image.convert('L')
        return image

    def _calculate_quality_score(self, text: str, page_count: int) -> float:
        """
        Estimates text quality on a 0.0-1.0 scale.
        Based on: chars per page, ratio of real words to garbage chars.
        """
        if not text or page_count == 0:
            return 0.0

        chars_per_page = len(text) / page_count

        # Count real words vs garbage
        words = text.split()
        if not words:
            return 0.0

        real_words = sum(
            1 for w in words
            if re.match(r'^[a-zA-Z]{2,}$', w)
        )
        word_quality = real_words / len(words)

        # Score based on both metrics
        volume_score = min(chars_per_page / 500, 1.0)
        quality = (volume_score * 0.4) + (word_quality * 0.6)

        return round(quality, 2)

    def _clean_text(self, text: str) -> str:
        """
        Cleans extracted text:
        - Removes non-printable characters
        - Normalises whitespace
        - Removes page number artifacts
        - Removes common PDF extraction garbage
        """
        # Remove non-printable chars (keep newlines and tabs)
        text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\x80-\xFF]', ' ', text)

        # Remove page number patterns: "Page 1 of 20", "- 1 -"
        text = re.sub(r'-\s*\d+\s*-', '', text)
        text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)

        # Normalize multiple spaces and blank lines
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove lone single characters on a line (OCR artifacts)
        text = re.sub(r'^\s*[^a-zA-Z0-9\(\)]\s*$', '', text, flags=re.MULTILINE)

        return text.strip()

    def _is_scanned(self, text: str, page_count: int) -> bool:
        """
        Determines if a PDF is scanned based on text yield.
        If average chars per page is below threshold → scanned.
        """
        if page_count == 0:
            return True
        avg_chars = len(text.strip()) / page_count
        return avg_chars < self.MIN_CHARS_PER_PAGE

    def process(self, pdf_path: str) -> ProcessedDocument:
        """
        Main method. Processes any PDF and returns clean text.

        Flow:
        1. Try pypdf (fast path)
        2. Check if result looks like scanned PDF
        3. If scanned → retry with Tesseract OCR
        4. Clean and score the result
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        print(f"\n  Processing: {path.name}")

        # Step 1: Try direct extraction
        raw_text, page_count = self._extract_with_pypdf(pdf_path)
        was_ocr = False

        # Step 2: Check if scanned
        if self._is_scanned(raw_text, page_count):
            print(f"  Scanned PDF detected — switching to OCR")
            raw_text, page_count = self._extract_with_ocr(pdf_path)
            was_ocr = True
        else:
            print(f"  Clean PDF — direct extraction successful")

        # Step 3: Clean the text
        clean_text = self._clean_text(raw_text)

        # Step 4: Score quality
        quality = self._calculate_quality_score(clean_text, page_count)

        print(f"  Pages: {page_count} | OCR used: {was_ocr} | Quality: {quality:.0%}")
        print(f"  Extracted {len(clean_text):,} characters")

        return ProcessedDocument(
            text=clean_text,
            page_count=page_count,
            was_ocr=was_ocr,
            quality_score=quality,
            source_path=str(path.absolute()),
            filename=path.name,
        )

    def process_folder(
        self,
        folder_path: str,
        agency: str
    ) -> List[ProcessedDocument]:
        """
        Processes all PDFs in a folder.
        Returns list of ProcessedDocument objects.
        """
        folder = Path(folder_path)
        pdfs = list(folder.glob("*.pdf"))

        if not pdfs:
            print(f"  No PDFs found in {folder_path}")
            return []

        print(f"\nProcessing {len(pdfs)} PDFs from {agency}...")
        results = []

        for pdf_path in pdfs:
            try:
                doc = self.process(str(pdf_path))
                results.append(doc)
            except Exception as e:
                print(f"  ❌ Failed: {pdf_path.name} — {e}")
                continue

        print(f"\n✅ Processed {len(results)}/{len(pdfs)} documents from {agency}")
        return results
