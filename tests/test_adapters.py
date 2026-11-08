"""
Unit tests for concrete adapters (QdrantVectorStore, EdgeTTS, GroqLLM, CartesiaTTS).
"""

import asyncio
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter
from app.adapters.llm_groq import GroqLLMAdapter
from app.adapters.tts_edge import EdgeTTSAdapter
from app.adapters.tts_cartesia import CartesiaTTSAdapter
from app.core.config import settings
from app.rag.ingest import chunk_text

def test_chunk_text():
    """Verify text chunking logic for voice RAG."""
    sample_text = "word " * 350
    chunks = chunk_text(sample_text, chunk_size=150)
    assert len(chunks) == 3
    assert len(chunks[0].split()) == 150
    assert len(chunks[1].split()) == 150
    assert len(chunks[2].split()) == 50

def test_qdrant_adapter_fallback():
    """Verify Qdrant adapter returns structured documents even in local in-memory fallback."""
    async def _run():
        adapter = QdrantVectorStoreAdapter(url=":memory:")
        docs = await adapter.hybrid_search("Tell me about Sahayak", top_k=2)
        assert len(docs) >= 1
        assert "Sahayak" in docs[0].text

    asyncio.run(_run())

def test_groq_mock_fallback():
    """Verify Groq adapter yields fallback tokens gracefully when API key is missing."""
    async def _run():
        adapter = GroqLLMAdapter(api_key=None)
        tokens = []
        async for token in adapter.stream_tokens("test prompt"):
            tokens.append(token)
        assert len(tokens) > 0
        assert "Sahayak" in "".join(tokens)

    asyncio.run(_run())

def test_cartesia_adapter_fallback_without_key():
    """Verify Cartesia adapter safely delegates to Edge-TTS when key is None."""
    async def _run():
        adapter = CartesiaTTSAdapter(api_key=None)
        chunks = []
        async for chunk in adapter.synthesize_stream("Fallback voice test"):
            chunks.append(chunk)
        assert len(chunks) > 0

    asyncio.run(_run())

def test_cartesia_live_stream_synthesis():
    """Verify live Cartesia Sonic WebSocket synthesis when key is configured."""
    if not settings.CARTESIA_API_KEY:
        return

    async def _run():
        adapter = CartesiaTTSAdapter(
            api_key=settings.CARTESIA_API_KEY,
            voice_id=settings.CARTESIA_VOICE_ID,
        )
        chunks = []
        import time
        start = time.perf_counter()
        ttfab = None

        async for chunk in adapter.synthesize_stream("Namaste from Cartesia Sonic."):
            if ttfab is None:
                ttfab = (time.perf_counter() - start) * 1000
            chunks.append(chunk)

        total_bytes = sum(len(c) for c in chunks)
        print(f"\n[CARTESIA LIVE] TTFAB: {ttfab:.1f}ms | Chunks: {len(chunks)} | Total bytes: {total_bytes}")
        assert len(chunks) > 0
        assert total_bytes > 5000

    asyncio.run(_run())
