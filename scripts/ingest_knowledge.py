#!/usr/bin/env python3
"""
Sahayak Voice Assistant: Knowledge Base Ingestion Script.
Reads structured citizen welfare schemes and domain documentation from data/knowledge_base/
and indexes them into the Qdrant vector database using local FastEmbed dense vectors.
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in pythonpath
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.interfaces.adapters import RetrievedDocument
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter


def load_knowledge_documents(data_dir: Path) -> List[RetrievedDocument]:
    """Loads and transforms JSON, Markdown, and TXT files into RetrievedDocument objects."""
    docs: List[RetrievedDocument] = []
    if not data_dir.exists():
        print(f"[INGEST] Warning: Data directory does not exist: {data_dir}", file=sys.stderr)
        return docs

    for file_path in sorted(data_dir.glob("*.*")):
        if file_path.suffix == ".json":
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    items = data
                else:
                    items = [data]

                for idx, item in enumerate(items):
                    doc_id = item.get("id", f"{file_path.stem}-{idx}")
                    name = item.get("name", file_path.stem)
                    category = item.get("category", "General Scheme")
                    summary = item.get("summary", "")
                    eligibility = item.get("eligibility", "")
                    benefits = item.get("benefits", "")
                    app_proc = item.get("application_process", "")
                    facts = " ".join(item.get("key_facts", []))

                    # Build dense text representation for semantic similarity matching
                    combined_text = (
                        f"Scheme: {name} ({category}). "
                        f"Summary: {summary} "
                        f"Eligibility: {eligibility} "
                        f"Benefits: {benefits} "
                        f"Application Process: {app_proc} "
                        f"Key Details: {facts}"
                    ).strip()

                    docs.append(RetrievedDocument(id=doc_id, text=combined_text, score=1.0))
            except Exception as e:
                print(f"[INGEST] Error parsing {file_path.name}: {e}", file=sys.stderr)

        elif file_path.suffix in [".txt", ".md"]:
            try:
                content = file_path.read_text(encoding="utf-8").strip()
                if content:
                    docs.append(RetrievedDocument(id=file_path.stem, text=content, score=1.0))
            except Exception as e:
                print(f"[INGEST] Error reading {file_path.name}: {e}", file=sys.stderr)

    return docs


async def run_ingestion(
    data_dir: Path,
    url: str = None,
    path: str = None,
    collection: str = None,
) -> int:
    """Executes the ingestion pipeline."""
    target_collection = collection or settings.QDRANT_COLLECTION
    target_path = path or settings.QDRANT_PATH
    target_url = url or settings.QDRANT_URL

    print("=" * 70)
    print(" Sahayak AI Voice Assistant: Knowledge Base Ingestion")
    print("=" * 70)
    print(f" Source Directory : {data_dir}")
    print(f" Collection Name  : {target_collection}")
    if target_url:
        print(f" Target Qdrant    : Cluster at {target_url}")
    else:
        print(f" Target Qdrant    : Local disk at '{target_path}'")

    docs = load_knowledge_documents(data_dir)
    if not docs:
        print("[INGEST] No documents found to ingest. Exiting.", file=sys.stderr)
        return 1

    print(f"[INGEST] Parsed {len(docs)} scheme documents from {data_dir.name}/.")

    try:
        adapter = QdrantVectorStoreAdapter(
            url=target_url,
            path=target_path,
            collection_name=target_collection,
        )
        print(f"[INGEST] Generating FastEmbed dense vectors (dim={settings.EMBEDDING_DIM})...")
        await adapter.add_documents(docs)
        print(f"[INGEST] SUCCESS: Indexed {len(docs)} documents into collection '{target_collection}'.")
        print("=" * 70)
        return 0
    except Exception as e:
        err_msg = str(e)
        if "already accessed by another instance" in err_msg or "Resource temporarily unavailable" in err_msg:
            print(
                "\n[LOCK ERROR] The local Qdrant directory is locked by a running Sahayak server process.",
                file=sys.stderr,
            )
            print(
                "Options to resolve:\n"
                "  1. Temporarily stop the running uvicorn server before ingesting:\n"
                "     pkill -f uvicorn && python scripts/ingest_knowledge.py && make dev\n"
                "  2. Or run a standalone Qdrant container and point via QDRANT_URL:\n"
                "     docker run -d -p 6333:6333 qdrant/qdrant\n"
                "     python scripts/ingest_knowledge.py --url http://localhost:6333",
                file=sys.stderr,
            )
        else:
            print(f"[INGEST] Failed to index documents: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Ingest citizen schemes into Qdrant vector database.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "knowledge_base",
        help="Path to folder containing JSON/MD knowledge files.",
    )
    parser.add_argument("--url", type=str, default=None, help="Remote Qdrant URL (e.g. http://localhost:6333)")
    parser.add_argument("--path", type=str, default=None, help="Local disk storage path")
    parser.add_argument("--collection", type=str, default=None, help="Collection name")

    args = parser.parse_args()
    exit_code = asyncio.run(
        run_ingestion(
            data_dir=args.data_dir,
            url=args.url,
            path=args.path,
            collection=args.collection,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
