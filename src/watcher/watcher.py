"""
src/watcher/watcher.py
Background service that monitors Nigerian regulatory agency websites
for new documents and auto-ingests them into Pinecone.
"""

import os
import json
import hashlib
import logging
import time
import requests
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [WATCHER] %(levelname)s — %(message)s",
)
log = logging.getLogger("regnaija.watcher")

# Registry of pages to watch 
WATCH_TARGETS = [
    {
        "agency": "CBN",
        "name": "CBN Policy Circulars",
        "url": "https://www.cbn.gov.ng/documents/policycirculars.html",
        "base_url": "https://www.cbn.gov.ng",
        "selectors": ["a[href$='.pdf']", "a[href*='/out/']"],
    },
    {
        "agency": "CBN",
        "name": "CBN Banking Supervision Circulars",
        "url": "https://www.cbn.gov.ng/Documents/BSDCircularsNEW.html",
        "base_url": "https://www.cbn.gov.ng",
        "selectors": ["a[href$='.pdf']", "a[href*='/out/']"],
    },
    {
        "agency": "CBN",
        "name": "CBN All Documents",
        "url": "https://www.cbn.gov.ng/Documents/",
        "base_url": "https://www.cbn.gov.ng",
        "selectors": ["a[href$='.pdf']", "a[href*='/out/']"],
    },
    {
        "agency": "SEC",
        "name": "SEC Nigeria Rules and Regulations",
        "url": "https://home.sec.gov.ng/our-mandate/regulation/rules-and-regulations/",
        "base_url": "https://home.sec.gov.ng",
        "selectors": ["a[href$='.pdf']", "a[href*='documents']"],
    },
    {
        "agency": "SEC",
        "name": "SEC Nigeria Circulars",
        "url": "https://sec.gov.ng/for-investors/keep-track-of-circulars/",
        "base_url": "https://sec.gov.ng",
        "selectors": ["a[href$='.pdf']", "a[href*='wp-content']"],
    },
    {
        "agency": "NDPC",
        "name": "NDPC Publications",
        "url": "https://ndpc.gov.ng/publications",
        "base_url": "https://ndpc.gov.ng",
        "selectors": ["a[href$='.pdf']", "a[href*='wp-content']"],
    },
]

_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = _ROOT / "data/watcher_registry.json"
DOWNLOAD_DIR  = _ROOT / "data/watcher_downloads"
CHECK_INTERVAL_HOURS = 24  # Check every 24 hours


class DocumentRegistry:
    """Tracks which documents have already been ingested."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path) as f:
                return json.load(f)
        return {"documents": {}, "last_check": {}}

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def is_known(self, url: str) -> bool:
        return url in self.data["documents"]

    def mark_ingested(self, url: str, metadata: dict):
        self.data["documents"][url] = {
            "ingested_at": datetime.now().isoformat(),
            **metadata,
        }
        self._save()

    def update_last_check(self, agency: str):
        self.data["last_check"][agency] = datetime.now().isoformat()
        self._save()

    def get_last_check(self, agency: str) -> str:
        return self.data["last_check"].get(agency, "Never")


class AgencyWatcher:
    """Watches a single agency page for new documents."""

    def __init__(self, target: dict, registry: DocumentRegistry):
        self.target = target
        self.registry = registry
        self.session  = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 RegNaija Research Bot"
        })

    def fetch_page(self) -> BeautifulSoup | None:
        try:
            resp = self.session.get(self.target["url"], timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            log.warning(f"Failed to fetch {self.target['url']}: {e}")
            return None

    def extract_pdf_links(self, soup: BeautifulSoup) -> list[dict]:
        links = []
        for selector in self.target["selectors"]:
            for tag in soup.select(selector):
                href = tag.get("href", "")
                if not href:
                    continue
                # Make absolute URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    full_url = self.target["base_url"] + href
                else:
                    full_url = self.target["base_url"] + "/" + href

                title = tag.get_text(strip=True) or Path(href).stem
                links.append({
                    "url": full_url,
                    "title": title,
                    "agency": self.target["agency"],
                })
        return links

    def check(self) -> list[dict]:
        """Returns list of new documents found."""
        log.info(f"Checking {self.target['agency']} — {self.target['name']}")
        soup = self.fetch_page()
        if not soup:
            return []

        links = self.extract_pdf_links(soup)
        new_docs  = [l for l in links if not self.registry.is_known(l["url"])]
        log.info(f"  Found {len(links)} links, {len(new_docs)} new")
        self.registry.update_last_check(self.target["agency"])
        return new_docs


class DocumentIngester:
    """Downloads and ingests a new document into Pinecone."""

    def __init__(self):
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def download(self, url: str) -> Path | None:
        try:
            resp = requests.get(url, timeout=30, stream=True)
            resp.raise_for_status()
            filename = hashlib.md5(url.encode()).hexdigest() + ".pdf"
            path = DOWNLOAD_DIR / filename
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            log.info(f"  Downloaded: {path.name} ({path.stat().st_size // 1024}KB)")
            return path
        except Exception as e:
            log.warning(f"  Download failed for {url}: {e}")
            return None

    def ingest(self, pdf_path: Path, metadata: dict) -> bool:
        try:
            import sys
            root = str(Path(__file__).resolve().parents[2])
            if root not in sys.path:
                sys.path.insert(0, root)
            from src.retrieval.embedder import RegNaijaEmbedder
            from src.retrieval.vector_store import RegNaijaVectorStore
            from src.ingestion.legal_chunker import NigerianLegalChunker
            from langchain.schema import Document

            if not hasattr(self, "_embedder"):
                self._embedder = RegNaijaEmbedder()
                self._store = RegNaijaVectorStore(embedder=self._embedder)
                self._chunker = NigerianLegalChunker()
            embedder = self._embedder
            store = self._store
            chunker  = self._chunker

            # Read PDF text
            import pypdf
            reader = pypdf.PdfReader(str(pdf_path))
            text = "\n".join(
                page.extract_text() or "" for page in reader.pages
            )

            if len(text.strip()) < 100:
                log.warning("Too little text extracted - skipping")
                return False

            # Chunk it
            legal_chunks = chunker.chunk_document(
                text = text,
                agency = metadata.get("agency", ""),
                document_name = metadata.get("document_name", ""),
                source_url = metadata.get("source_url", ""),
                publication_date= metadata.get("publication_date", ""),
            )
            chunks = chunker.chunks_to_documents(legal_chunks)
            store.upsert_chunks(chunks)
            log.info(f"  Ingested {len(chunks)} chunks into Pinecone")
            return True

        except Exception as e:
            log.error(f"  Ingestion failed: {e}")
            return False


class RegNaijaWatcher:
    """Main watcher service — orchestrates all agency watchers."""

    def __init__(self):
        self.registry = DocumentRegistry(REGISTRY_PATH)
        self.ingester = DocumentIngester()
        self.watchers = [
            AgencyWatcher(target, self.registry)
            for target in WATCH_TARGETS
        ]

    def run_once(self) -> dict:
        """Run one check cycle across all agencies."""
        summary = {"checked": 0, "new_found": 0, "ingested": 0, "failed": 0}

        for watcher in self.watchers:
            new_docs = watcher.check()
            summary["checked"] += 1
            summary["new_found"] += len(new_docs)

            for doc in new_docs[:10]:  # Max 10 new docs per cycle
                log.info(f"  New doc: {doc['title'][:60]} — {doc['url'][:60]}")
                time.sleep(2)  # Polite delay between downloads
                pdf_path = self.ingester.download(doc["url"])

                if pdf_path:
                    success = self.ingester.ingest(pdf_path, {
                        "agency": doc["agency"],
                        "document_name": doc["title"],
                        "source_url": doc["url"],
                        "publication_date": datetime.now().strftime("%Y-%m-%d"),
                    })
                    if success:
                        self.registry.mark_ingested(doc["url"], doc)
                        summary["ingested"] += 1
                    else:
                        summary["failed"] += 1
                else:
                    summary["failed"] += 1

        log.info(f"Cycle complete: {summary}")
        return summary

    def run_forever(self, interval_hours: int = CHECK_INTERVAL_HOURS):
        """Run continuously, checking every interval_hours."""
        log.info(f"Watcher started — checking every {interval_hours}h")
        while True:
            try:
                self.run_once()
            except Exception as e:
                log.error(f"Watcher cycle error: {e}")
            log.info(f"Sleeping {interval_hours}h until next check...")
            time.sleep(interval_hours * 3600)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once",  action="store_true", help="Run once and exit")
    parser.add_argument("--hours", type=int, default=24, help="Check interval in hours")
    args = parser.parse_args()

    watcher = RegNaijaWatcher()
    if args.once:
        summary = watcher.run_once()
        print(f"\nSummary: {summary}")
    else:
        watcher.run_forever(interval_hours=args.hours)