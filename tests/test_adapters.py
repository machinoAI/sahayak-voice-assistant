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

def test_qdrant_dense_embedding_search():
    """Verify FastEmbed generates dense embeddings and Qdrant retrieves semantic matches."""
    from app.interfaces.adapters import RetrievedDocument

    async def _run():
        adapter = QdrantVectorStoreAdapter(url=":memory:", collection_name="test_dense_coll")
        docs = [
            RetrievedDocument(id="doc-1", text="Voice assistants require ultra-low latency audio streaming.", score=1.0),
            RetrievedDocument(id="doc-2", text="Quantum computing uses qubits and superposition.", score=1.0),
        ]
        await adapter.add_documents(docs)

        matches = await adapter.hybrid_search("How fast is the voice audio stream?", top_k=1)
        assert len(matches) == 1
        assert "audio streaming" in matches[0].text
        assert matches[0].score > 0.60

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

def test_transcript_accumulator():
    """Verify phrase accumulation and speech_final endpointing."""
    from app.adapters.stt_deepgram import TranscriptAccumulator

    acc = TranscriptAccumulator()
    r1 = acc.process_result(is_final=False, speech_final=False, text="Hello")
    assert r1 == {"type": "interim", "text": "Hello"}

    r2 = acc.process_result(is_final=True, speech_final=False, text="Hello world")
    assert r2 == {"type": "interim", "text": "Hello world"}

    r3 = acc.process_result(is_final=True, speech_final=True, text="from Deepgram.")
    assert r3 == {"type": "final", "text": "Hello world from Deepgram."}

def test_deepgram_adapter_mock_fallback():
    """Verify Deepgram STT adapter fallback when API key is None."""
    from app.adapters.stt_deepgram import DeepgramSTTAdapter

    async def _run():
        adapter = DeepgramSTTAdapter(api_key=None)
        
        async def mock_audio():
            yield b"\x00" * 640

        transcripts = []
        async for text in adapter.stream_audio_frames(mock_audio()):
            transcripts.append(text)

        assert len(transcripts) == 1
        assert "Sahayak" in transcripts[0]

    asyncio.run(_run())
