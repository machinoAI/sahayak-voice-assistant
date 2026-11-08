"""
Document Ingestion & Chunking Pipeline for Sahayak Voice RAG.
Splits source documents into voice-optimized chunks (150-250 tokens) and indexes them into Qdrant.
"""

import asyncio
from typing import List
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter
from app.interfaces.adapters import RetrievedDocument

def chunk_text(text: str, chunk_size: int = 150) -> List[str]:
    """Splits plain text into compact chunks suitable for low-latency voice context."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

async def ingest_documents(file_paths: List[str], adapter: QdrantVectorStoreAdapter):
    """Reads local text/markdown files and indexes them into Qdrant."""
    documents: List[RetrievedDocument] = []
    dummy_vectors: List[List[float]] = []

    doc_counter = 1
    for path in file_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            chunks = chunk_text(content)
            for idx, chunk in enumerate(chunks):
                doc_id = f"doc-{doc_counter}-{idx}"
                documents.append(
                    RetrievedDocument(id=doc_id, text=chunk, score=1.0)
                )
                # 384-dimensional vector placeholder (replaced by embedding model in production)
                dummy_vectors.append([0.01] * 384)
            doc_counter += 1
        except Exception as e:
            print(f"Failed to read {path}: {e}")

    if documents:
        await adapter.add_documents(documents, dummy_vectors)
        print(f"Successfully indexed {len(documents)} voice chunks into Qdrant collection: {adapter.collection_name}")

if __name__ == "__main__":
    vdb = QdrantVectorStoreAdapter()
    # Ingest example
    asyncio.run(ingest_documents(["requirements.txt"], vdb))
