"""
src/retrieval/embedder.py

Wraps BGE-small-en-v1.5 for use across the entire RegNaija pipeline.
Single place to swap embedding models if needed.
"""

import os
import numpy as np
from typing import List
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()


class RegNaijaEmbedder:
    """
    Embedding wrapper for RegNaija.
    Uses BAAI/bge-small-en-v1.5 — 384 dimensions, fast, free.
    """

    def __init__(self):
        model_name = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
        print(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        print(f"Embedding dimension: {self.dimension}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embeds a list of texts.
        BGE models work best with a query instruction prefix
        for document embedding.
        """
        # BGE instruction prefix for document chunks
        prefixed = [f"Represent this Nigerian regulatory text: {t}" for t in texts]
        embeddings = self.model.encode(
            prefixed,
            batch_size = 32,
            show_progress_bar = len(texts) > 10,
            normalize_embeddings = True,  # Cosine similarity ready
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        """
        Embeds a single user query.
        Uses a different prefix optimised for retrieval.
        """
        prefixed = f"Represent this regulatory compliance query: {query}"
        embedding = self.model.encode(
            prefixed,
            normalize_embeddings=True,
        )
        return embedding.tolist()

    def embed_single(self, text: str) -> List[float]:
        """Embeds a single document text."""
        return self.embed_texts([text])[0]
