import json
import warnings
warnings.filterwarnings('ignore')
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from langchain_core.documents import Document
from src.retrieval.embedder import NaijaCodexEmbedder
from src.retrieval.vector_store import NaijaCodexVectorStore

print("Loading pre-processed chunks...")
with open('data/processed/chunks_ready.json', 'r') as f:
    chunks = json.load(f)

print(f"Found {len(chunks)} chunks to upload")

embedder = NaijaCodexEmbedder()
store = NaijaCodexVectorStore(embedder=embedder)

docs = [
    Document(page_content=c['text'], metadata=c['metadata'])
    for c in chunks
]

upserted = store.upsert_chunks(docs)
stats = store.get_index_stats()

print(f"Uploaded {upserted} chunks to Pinecone")
print(f"Pinecone total vectors: {stats['total_vectors']}")
