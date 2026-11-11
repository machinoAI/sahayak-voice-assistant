"""
Document Ingestion & Chunking Pipeline for Sahayak Voice RAG.
Splits source documents into voice-optimized chunks (150-250 tokens),
computes 384-dimensional dense vectors via FastEmbed, and indexes them into Qdrant.
"""

import os
import sys
import time
import asyncio
from pathlib import Path
from typing import List, Tuple, Optional
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter
from app.interfaces.adapters import RetrievedDocument
from app.core.logger import logger


def chunk_text(text: str, chunk_size: int = 150, overlap: int = 0) -> List[str]:
    """
    Splits text into compact, voice-optimized chunks with word-level overlap.
    Preserves paragraph breaks where possible.
    """
    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    current_words: List[str] = []

    for para in paragraphs:
        para_words = para.split()
        if not para_words:
            continue

        if len(current_words) + len(para_words) <= chunk_size:
            current_words.extend(para_words)
        else:
            if current_words:
                chunks.append(" ".join(current_words))
                # Carry over overlap words for context continuity
                current_words = current_words[-overlap:] if overlap > 0 else []
            
            # If the single paragraph exceeds chunk_size, split by words
            for i in range(0, len(para_words), chunk_size - overlap):
                sub_chunk = para_words[i:i + chunk_size]
                if sub_chunk:
                    chunks.append(" ".join(sub_chunk))
            current_words = []

    if current_words:
        chunks.append(" ".join(current_words))

    # Clean empty chunks
    return [c.strip() for c in chunks if len(c.strip()) > 20]


def collect_files(targets: List[str]) -> List[Path]:
    """Recursively collects supported document files (.md, .txt) from file/folder paths."""
    resolved_files: List[Path] = []
    supported_exts = {".md", ".txt", ".rst"}

    for target in targets:
        p = Path(target).resolve()
        if p.is_file():
            if p.suffix.lower() in supported_exts:
                resolved_files.append(p)
        elif p.is_dir():
            for root, _, files in os.walk(p):
                for f in files:
                    file_path = Path(root) / f
                    if file_path.suffix.lower() in supported_exts:
                        resolved_files.append(file_path)

    return sorted(list(set(resolved_files)))


async def ingest_documents(
    file_paths: List[str],
    adapter: Optional[QdrantVectorStoreAdapter] = None,
    chunk_size: int = 150,
) -> int:
    """Reads local text/markdown files, embeds them with FastEmbed, and indexes into Qdrant."""
    if adapter is None:
        adapter = QdrantVectorStoreAdapter()

    files = collect_files(file_paths)
    if not files:
        logger.warning(f"No valid documents found in {file_paths}")
        return 0

    logger.info(f"Ingesting {len(files)} document file(s)...")
    documents: List[RetrievedDocument] = []

    start_read = time.perf_counter()
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            rel_path = file_path.name
            chunks = chunk_text(content, chunk_size=chunk_size)
            
            for idx, chunk in enumerate(chunks):
                doc_id = f"{file_path.stem}-{idx}"
                # Prepend source header to give the chunk immediate voice grounding
                grounded_chunk = f"[{rel_path}] {chunk}"
                documents.append(
                    RetrievedDocument(id=doc_id, text=grounded_chunk, score=1.0)
                )
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")

    read_time = (time.perf_counter() - start_read) * 1000

    if not documents:
        logger.warning("No document chunks were extracted.")
        return 0

    logger.info(
        f"Extracted {len(documents)} voice chunks across {len(files)} file(s) in {read_time:.1f}ms. "
        f"Generating dense embeddings via FastEmbed ({adapter.embedding_model_name})..."
    )

    start_embed = time.perf_counter()
    await adapter.add_documents(documents)
    total_time = (time.perf_counter() - start_embed) * 1000

    logger.info(
        f"Successfully indexed {len(documents)} chunks into collection '{adapter.collection_name}' "
        f"in {total_time:.1f}ms ({total_time / len(documents):.2f}ms/chunk)."
    )
    return len(documents)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest local documents into Sahayak Qdrant RAG.")
    parser.add_argument(
        "paths",
        nargs="*",
        default=["docs", "README.md"],
        help="Files or directories to ingest (default: docs/ and README.md)",
    )
    parser.add_argument("--chunk-size", type=int, default=150, help="Target words per chunk")
    args = parser.parse_args()

    vdb = QdrantVectorStoreAdapter()
    count = asyncio.run(ingest_documents(args.paths, adapter=vdb, chunk_size=args.chunk_size))
    print(f"\n[DONE] Ingested {count} chunks into {vdb.collection_name}.")
