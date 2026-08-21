"""
src/retrieval/vector_store.py

Manages all Pinecone operations for RegNaija.
Stores regulatory chunks with full legal metadata.
Retrieves using semantic search with agency filtering.
"""

import os
import time
from typing import List, Tuple, Optional
from langchain_core.documents import Document
from pinecone import Pinecone, ServerlessSpec
from src.retrieval.embedder import RegNaijaEmbedder
from dotenv import load_dotenv

load_dotenv()


class RegNaijaVectorStore:
    """
    Pinecone vector store for Nigerian regulatory documents.

    Each vector stores:
    - The embedded text (384 dims)
    - Full legal metadata: agency, section, date, doc_id, source_url
    """

    def __init__(self, embedder: Optional[RegNaijaEmbedder] = None):
        self.index_name = os.getenv("PINECONE_INDEX", "naijacodex")
        self.embedder = embedder or RegNaijaEmbedder()

        # Connect to Pinecone
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self._ensure_index()
        self.index = self.pc.Index(self.index_name)
        print(f"Connected to Pinecone index: {self.index_name}")

    def _ensure_index(self):
        """Creates the Pinecone index if it doesn't exist."""
        existing = self.pc.list_indexes().names()

        if self.index_name not in existing:
            print(f"  Creating Pinecone index: {self.index_name}")
            self.pc.create_index(
                name = self.index_name,
                dimension = self.embedder.dimension,
                metric = "cosine",
                spec = ServerlessSpec(
                    cloud = "aws",
                    region = "us-east-1"
                )
            )
            print("Waiting for index to be ready...")
            time.sleep(15)
            print("Index ready")
        else:
            print(f"Index '{self.index_name}' already exists")

    def upsert_chunks(
        self,
        documents: List[Document],
        batch_size: int = 100,
    ) -> int:
        """
        Embeds and stores document chunks in Pinecone.
        Returns number of chunks upserted.
        """
        if not documents:
            print("No documents to upsert")
            return 0

        total_upserted = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i: i + batch_size]
            texts = [doc.page_content for doc in batch]

            # Embed the batch
            print(f"Embedding batch {i//batch_size + 1} ({len(batch)} chunks)...")
            embeddings = self.embedder.embed_texts(texts)

            # Build Pinecone vectors
            vectors = []
            for doc, embedding in zip(batch, embeddings):
                meta = doc.metadata
                vectors.append({
                    "id": meta.get("chunk_id", f"chunk_{i}"),
                    "values": embedding,
                    "metadata": {
                        # Text for retrieval
                        "text":             doc.page_content[:1000],
                        # Legal citation metadata
                        "agency": meta.get("agency", "UNKNOWN"),
                        "document_name": meta.get("document_name", ""),
                        "section_number": meta.get("section_number", ""),
                        "section_title": meta.get("section_title", ""),
                        "publication_date": meta.get("publication_date", ""),
                        "source_url": meta.get("source_url", ""),
                        "doc_id": meta.get("doc_id", ""),
                        "page_number": meta.get("page_number", 0),
                        "chunk_index": meta.get("chunk_index", 0),
                    }
                })

            # Upsert to Pinecone
            self.index.upsert(vectors=vectors)
            total_upserted += len(vectors)
            print(f"Upserted {total_upserted}/{len(documents)} chunks")

        return total_upserted

    def search(
        self,
        query: str,
        top_k: int = 10,
        agency_filter: Optional[str] = None,
    ) -> List[Tuple[Document, float]]:
        """
        Searches for relevant regulatory chunks.

        Args:
            query: User's question
            top_k: Number of results to return
            agency_filter: Optional — restrict to one agency
                          e.g. "CBN", "NDPC", "FIRS"

        Returns:
            List of (Document, score) tuples sorted by relevance
        """
        # Embed the query
        query_vector = self.embedder.embed_query(query)

        # Build filter if agency specified
        filter_dict = None
        if agency_filter:
            filter_dict = {"agency": {"$eq": agency_filter}}

        # Search Pinecone
        results = self.index.query(
            vector = query_vector,
            top_k = top_k,
            include_metadata = True,
            filter = filter_dict,
        )

        # Convert to Document objects
        documents = []
        for match in results.matches:
            doc = Document(
                page_content=match.metadata.get("text", ""),
                metadata={
                    "agency": match.metadata.get("agency", ""),
                    "document_name": match.metadata.get("document_name", ""),
                    "section_number": match.metadata.get("section_number", ""),
                    "section_title": match.metadata.get("section_title", ""),
                    "publication_date": match.metadata.get("publication_date", ""),
                    "source_url": match.metadata.get("source_url", ""),
                    "doc_id": match.metadata.get("doc_id", ""),
                    "score": match.score,
                }
            )
            documents.append((doc, match.score))

        return documents

    def search_multi_agency(
        self,
        query: str,
        agencies: List[str],
        top_k_per_agency: int = 5,
    ) -> List[Tuple[Document, float]]:
        """
        Searches across multiple agencies simultaneously.
        Used by the cross-regulation intelligence layer.
        """
        all_results = []

        for agency in agencies:
            results = self.search(
                query=query,
                top_k=top_k_per_agency,
                agency_filter=agency,
            )
            all_results.extend(results)

        # Sort all results by score
        all_results.sort(key=lambda x: x[1], reverse=True)
        return all_results

    def get_index_stats(self) -> dict:
        """Returns current index statistics."""
        stats = self.index.describe_index_stats()
        return {
            "total_vectors": stats.total_vector_count,
            "dimension": stats.dimension,
            "index_name": self.index_name,
        }
