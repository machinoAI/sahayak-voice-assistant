"""
Unit and integration tests for knowledge base loading, schema normalization, and Qdrant ingestion.
"""

import pytest
from pathlib import Path

from scripts.ingest_knowledge import load_knowledge_documents
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter
from app.interfaces.adapters import RetrievedDocument


def test_load_knowledge_documents_from_disk():
    data_dir = Path(__file__).resolve().parent.parent / "data" / "knowledge_base"
    assert data_dir.exists(), "data/knowledge_base directory must exist"

    docs = load_knowledge_documents(data_dir)
    assert len(docs) >= 6, f"Expected at least 6 scheme documents, found {len(docs)}"

    doc_ids = {d.id for d in docs}
    assert "scheme-pm-kisan-01" in doc_ids
    assert "scheme-ayushman-bharat-01" in doc_ids
    assert "scheme-pm-awas-01" in doc_ids
    assert "scheme-atal-pension-01" in doc_ids
    assert "scheme-pm-ujjwala-01" in doc_ids
    assert "scheme-sukanya-samriddhi-01" in doc_ids

    # Validate document content completeness
    for d in docs:
        assert len(d.text) > 100
        assert "Scheme:" in d.text
        assert "Eligibility:" in d.text


@pytest.mark.asyncio
async def test_in_memory_qdrant_indexing_and_search():
    adapter = QdrantVectorStoreAdapter(
        url=":memory:",
        collection_name="test_sahayak_schemes",
    )

    test_docs = [
        RetrievedDocument(
            id="doc-pm-kisan",
            text="PM Kisan scheme provides ₹6,000 per year income support to all landholding farmer families.",
            score=1.0,
        ),
        RetrievedDocument(
            id="doc-ayushman",
            text="Ayushman Bharat provides secondary and tertiary healthcare coverage of ₹5 lakh per family.",
            score=1.0,
        ),
    ]

    await adapter.add_documents(test_docs)

    results = await adapter.hybrid_search("How much financial assistance does PM Kisan give?", top_k=1)
    assert len(results) > 0
    assert "PM Kisan" in results[0].text
    assert results[0].score > 0.6
