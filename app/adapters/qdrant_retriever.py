"""
Backward-compatibility alias for app.adapters.vector_store_qdrant.
Deprecated: Use app.adapters.vector_store_qdrant or scripts/ingest_knowledge.py instead.
"""

import sys
import asyncio
import warnings
from pathlib import Path

from app.adapters.vector_store_qdrant import (
    QdrantVectorStoreAdapter,
    get_text_embedder,
)

warnings.warn(
    "app.adapters.qdrant_retriever is deprecated. Use app.adapters.vector_store_qdrant instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["QdrantVectorStoreAdapter", "get_text_embedder"]

if __name__ == "__main__":
    from scripts.ingest_knowledge import run_ingestion

    data_path = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_base"
    exit_code = asyncio.run(run_ingestion(data_dir=data_path))
    sys.exit(exit_code)
