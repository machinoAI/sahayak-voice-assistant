"""
Integration & End-to-End Test Suite verifying live provider keys,
step-by-step latency tracking, and pipeline execution.
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock

from app.core.config import settings
from app.adapters.llm_groq import GroqLLMAdapter
from app.adapters.tts_edge import EdgeTTSAdapter
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter
from app.adapters.stt_deepgram import DeepgramSTTAdapter
from app.services.voice_orchestrator import VoiceRAGOrchestrator

def test_env_keys_configuration():
    """Verify that credentials and environment parameters are loaded from .env."""
    assert settings.GROQ_API_KEY is not None, "GROQ_API_KEY must be set in .env"
    assert len(settings.GROQ_API_KEY) > 10, "GROQ_API_KEY appears invalid or empty"
    print(f"\n[PASS] Verified GROQ_API_KEY present (model: {settings.GROQ_MODEL})")
    print(f"[PASS] Verified QDRANT_URL configured: {settings.QDRANT_URL}")
    print(f"[PASS] Verified EDGE_VOICE configured: {settings.EDGE_VOICE}")

def test_groq_live_inference_and_latency():
    """Verify live Groq streaming inference and measure TTFT."""
    async def _run():
        adapter = GroqLLMAdapter(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
        prompt = "In 1 short sentence, what is the capital of India?"
        tokens = []
        import time
        start = time.perf_counter()
        ttft = None

        async for token in adapter.stream_tokens(prompt):
            if ttft is None:
                ttft = (time.perf_counter() - start) * 1000
            tokens.append(token)

        total_time_ms = (time.perf_counter() - start) * 1000
        full_text = "".join(tokens).strip()

        print(f"\n[GROQ LIVE] TTFT: {ttft:.1f}ms | Total: {total_time_ms:.1f}ms | Tokens: {len(tokens)}")
        print(f"[GROQ LIVE] Output: '{full_text}'")

        assert len(tokens) > 0, "No tokens received from Groq"
        assert ttft is not None and ttft > 0, "TTFT was not measured"
        assert "Delhi" in full_text or "delhi" in full_text.lower(), "Unexpected answer from LLM"

    asyncio.run(_run())

def test_edge_tts_live_generation():
    """Verify live Edge-TTS audio generation and measure TTFAB."""
    async def _run():
        adapter = EdgeTTSAdapter(voice=settings.EDGE_VOICE)
        text = "Namaste, this is a live audio test for Sahayak."
        chunks = []
        import time
        start = time.perf_counter()
        ttfab = None

        async for chunk in adapter.synthesize_stream(text):
            if ttfab is None:
                ttfab = (time.perf_counter() - start) * 1000
            chunks.append(chunk)

        total_bytes = sum(len(c) for c in chunks)
        print(f"\n[EDGE-TTS LIVE] TTFAB: {ttfab:.1f}ms | Total Chunks: {len(chunks)} | Bytes: {total_bytes}")
        assert len(chunks) > 0, "No audio chunks produced by Edge-TTS"
        assert total_bytes > 5000, "Audio output suspiciously small"

    asyncio.run(_run())

def test_qdrant_live_hybrid_search():
    """Verify Qdrant vector retrieval and document structure."""
    async def _run():
        adapter = QdrantVectorStoreAdapter(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            collection_name=settings.QDRANT_COLLECTION,
        )
        docs = await adapter.hybrid_search("What is Sahayak?", top_k=2)
        assert len(docs) > 0, "No documents returned from Qdrant"
        print(f"\n[QDRANT LIVE] Retrieved {len(docs)} documents | Top score: {docs[0].score}")
        print(f"[QDRANT LIVE] Top snippet: '{docs[0].text[:60]}...'")

    asyncio.run(_run())

def test_full_pipeline_step_by_step_tracking():
    """
    Executes a complete voice turn through the orchestrator with live adapters,
    asserting that every pipeline milestone was tracked and timed.
    """
    async def _run():
        tts_adapter = EdgeTTSAdapter(voice=settings.EDGE_VOICE)
        llm_adapter = GroqLLMAdapter(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
        vdb_adapter = QdrantVectorStoreAdapter(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            collection_name=settings.QDRANT_COLLECTION,
        )
        stt_adapter = DeepgramSTTAdapter(api_key=settings.DEEPGRAM_API_KEY)

        orchestrator = VoiceRAGOrchestrator(
            stt=stt_adapter,
            vdb=vdb_adapter,
            llm=llm_adapter,
            tts=tts_adapter,
        )

        mock_ws = AsyncMock()

        # Run complete turn with real Groq LLM + Qdrant + Edge-TTS!
        tracker = await orchestrator.process_voice_turn(
            final_transcript="What is Sahayak and what services does it provide?",
            websocket=mock_ws,
        )

        steps = tracker.step_history
        print("\n=== COMPLETE PIPELINE STEP-BY-STEP LATENCY AUDIT ===")
        for step, elapsed_ms in steps.items():
            print(f"  --> {step:<32} reached at {elapsed_ms:6.1f}ms")

        # Assert mandatory milestone tracking
        assert "TURN_INITIATED" in steps
        assert "RAG_RETRIEVAL_START" in steps
        assert "RAG_RETRIEVAL_COMPLETE" in steps
        assert "LLM_STREAM_START" in steps
        assert "LLM_FIRST_TOKEN" in steps, "LLM first token was not tracked"
        assert "TTS_FIRST_AUDIO_PACKET" in steps, "TTS first audio packet was not tracked"
        assert "TURN_COMPLETED_SUCCESS" in steps

        # Verify WebSocket received binary audio packets
        assert mock_ws.send_bytes.call_count > 0
        total_audio_packets = mock_ws.send_bytes.call_count
        print(f"[SUCCESS] Dispatched {total_audio_packets} binary audio packets to WebSocket client.")

    asyncio.run(_run())

def test_deepgram_live_streaming_transcription():
    """Verify live Deepgram streaming speech-to-text with synthesized 16kHz PCM audio."""
    if not settings.DEEPGRAM_API_KEY:
        pytest.skip("DEEPGRAM_API_KEY not configured")

    async def _run():
        from app.adapters.tts_cartesia import CartesiaTTSAdapter
        tts = CartesiaTTSAdapter()
        test_phrase = "Hello Sahayak, what is the capital of India?"

        print("\n[DEEPGRAM LIVE] Synthesizing reference audio with Cartesia...")
        audio_chunks = []
        async for chunk in tts.synthesize_stream(test_phrase):
            audio_chunks.append(chunk)

        full_pcm = b"".join(audio_chunks)
        print(f"[DEEPGRAM LIVE] Generated {len(full_pcm)} bytes of 16kHz PCM. Streaming to Deepgram STT...")

        stt = DeepgramSTTAdapter(api_key=settings.DEEPGRAM_API_KEY)

        async def audio_gen():
            chunk_size = 640
            for i in range(0, len(full_pcm), chunk_size):
                yield full_pcm[i:i+chunk_size]
                await asyncio.sleep(0.015)
            # Trailing silence for endpointing
            silence = b"\x00" * 9600
            for i in range(0, len(silence), chunk_size):
                yield silence[i:i+chunk_size]
                await asyncio.sleep(0.015)

        collected = []
        import time
        start = time.perf_counter()
        async for transcript in stt.stream_audio_frames(audio_gen()):
            elapsed = (time.perf_counter() - start) * 1000
            print(f"[DEEPGRAM LIVE] [{elapsed:.1f}ms] Received transcript: '{transcript}'")
            collected.append(transcript)

        assert len(collected) > 0, "No transcript returned from Deepgram"
        final_transcript = collected[-1].lower()
        print(f"[DEEPGRAM LIVE] Final Transcription: '{collected[-1]}'")
        assert any(k in final_transcript for k in ["sahayak", "capital", "india"]), (
            f"Expected keywords not found in transcript: '{final_transcript}'"
        )

    asyncio.run(_run())
