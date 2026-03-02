# src/ingestion/contextual_chunker.py
#
# WHAT IS CONTEXTUAL CHUNKING?
# Anthropic published research showing that prepending a short
# context summary to each chunk before embedding it reduces
# retrieval failure rates by ~49%.
#
# PROBLEM with normal chunking:
#   Chunk: "The policy applies to all full-time staff."
#   ← No context. Full-time staff for WHAT policy?
#
# WITH contextual chunking:
#   Chunk: "Context: This is from the Leave Policy section of the
#            Employee Handbook, discussing who qualifies for annual leave.
#            The policy applies to all full-time staff."
#   ← Now the embedding knows exactly what this is about.

import os
from typing import List, Tuple
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

# Prompt that asks the LLM to generate context for each chunk
CONTEXT_PROMPT = """You are given a document and one chunk from that document.
Write a short 1-2 sentence context that explains what this chunk is about
and where it fits in the document. Be specific and concise.

FULL DOCUMENT:
{document}

CHUNK TO CONTEXTUALIZE:
{chunk}

Context (1-2 sentences only):"""


class ContextualChunker:
    """
    Implements Anthropic's Contextual Retrieval chunking strategy.
    
    Each chunk gets an LLM-generated context prepended before embedding.
    This dramatically improves retrieval accuracy.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        # Use fast small model for context generation — saves cost
        self.llm = ChatGroq(
            model="llama-3.1-8b-instant",   # Fast + cheap for this task
            temperature=0.0,
            max_tokens=150,
        )

    def _generate_context(self, full_document: str, chunk: str) -> str:
        """Ask LLM to write a context sentence for this chunk."""
        prompt = CONTEXT_PROMPT.format(
            document=full_document[:3000],  # Limit to avoid token overflow
            chunk=chunk
        )
        try:
            response = self.llm.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            # If LLM fails, continue without context rather than crashing
            print(f"  Warning: context generation failed: {e}")
            return ""

    def chunk_documents(
        self,
        documents: List[Document]
    ) -> List[Document]:
        """
        Chunks documents and prepends LLM-generated context to each chunk.
        
        Returns chunks where page_content = context + original chunk text
        """
        all_chunks = []

        for doc_index, doc in enumerate(documents):
            source = doc.metadata.get("source", f"doc_{doc_index}")
            print(f"\nProcessing: {source}")

            # Split into raw chunks first
            raw_chunks = self.splitter.split_documents([doc])
            print(f"  Split into {len(raw_chunks)} chunks")
            print(f"  Generating context for each chunk (LLM call)...")

            for chunk_index, chunk in enumerate(raw_chunks):
                # Generate context using the full document + this chunk
                context = self._generate_context(
                    full_document=doc.page_content,
                    chunk=chunk.page_content
                )

                # Prepend context to chunk text
                if context:
                    contextualized_text = f"{context}\n\n{chunk.page_content}"
                else:
                    contextualized_text = chunk.page_content

                # Build enriched metadata
                enriched_metadata = {
                    **chunk.metadata,
                    "chunk_id": f"doc{doc_index}_chunk{chunk_index}",
                    "chunk_index": chunk_index,
                    "original_text": chunk.page_content,   # Keep original for display
                    "context": context,
                    "source": source,
                }

                all_chunks.append(Document(
                    page_content=contextualized_text,
                    metadata=enriched_metadata
                ))

                print(f"  ✅ Chunk {chunk_index + 1}/{len(raw_chunks)} contextualized")

        print(f"\nTotal contextualized chunks: {len(all_chunks)}")
        return all_chunks