"""
Automated unit & integration tests for the CLI streaming client and playback engine.
"""

import asyncio
import os
import tempfile
import wave
import pytest
from unittest.mock import AsyncMock, MagicMock

from client_stream import (
    AudioPlaybackEngine,
    VoiceClientBenchmark,
    pcm_chunks_from_bytes,
    pcm_chunks_from_wav_file,
    CHUNK_BYTES,
    SAMPLE_RATE,
)

def test_playback_engine_barge_in_clear():
    """Verify that AudioPlaybackEngine flushes its queue on barge-in clear."""
    async def _run():
        engine = AudioPlaybackEngine()
        # Enqueue multiple audio packets
        for _ in range(5):
            await engine.enqueue(b"\x00" * 640)

        # Clear buffer (simulates barge-in)
        engine.clear()
        assert engine.queue.empty()

    asyncio.run(_run())

def test_playback_engine_export_wav():
    """Verify that received audio bytes can be exported to a valid 16kHz mono WAV file."""
    async def _run():
        engine = AudioPlaybackEngine()
        sample_audio = b"\x01\x02" * 1600  # 3200 bytes = 1600 samples = 100ms
        await engine.enqueue(sample_audio)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            temp_path = tf.name

        try:
            engine.export_wav(temp_path)
            assert os.path.exists(temp_path)
            with wave.open(temp_path, "rb") as wf:
                assert wf.getframerate() == 16000
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getnframes() == 1600
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    asyncio.run(_run())

def test_pcm_chunks_from_bytes():
    """Verify that byte chunks are sliced exactly at 640-byte boundaries."""
    async def _run():
        raw_data = b"\xaa" * 1600  # 1600 bytes = 2 chunks of 640 + 1 chunk of 320
        chunks = []
        async for chunk in pcm_chunks_from_bytes(raw_data):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert len(chunks[0]) == CHUNK_BYTES
        assert len(chunks[1]) == CHUNK_BYTES
        assert len(chunks[2]) == 320

    asyncio.run(_run())

def test_pcm_chunks_from_wav_file():
    """Verify streaming from an on-disk WAV file."""
    async def _run():
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            temp_path = tf.name

        try:
            # Create 16kHz mono WAV file
            with wave.open(temp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00" * 1280)  # 2 chunks of 640 bytes

            chunks = []
            async for chunk in pcm_chunks_from_wav_file(temp_path):
                chunks.append(chunk)

            assert len(chunks) == 2
            assert all(len(c) == 640 for c in chunks)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    asyncio.run(_run())

def test_live_cli_client_turn():
    """Verify live end-to-end voice turn using the CLI client against the FastAPI server."""
    from app.core.config import settings
    if not settings.DEEPGRAM_API_KEY or not settings.GROQ_API_KEY:
        pytest.skip("Live API keys not configured")

    import websockets
    import uvicorn
    from app.main import app
    from client_stream import generate_synthetic_audio

    async def _run():
        port = 8779
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve())

        while not server.started:
            await asyncio.sleep(0.05)

        ws_url = f"ws://127.0.0.1:{port}/ws/voice"
        client = VoiceClientBenchmark(ws_url=ws_url, enable_audio_out=False)

        phrase = "What is Sahayak?"
        pcm_data = await generate_synthetic_audio(phrase)

        async with websockets.connect(ws_url) as ws:
            metrics = await client.run_turn(ws, pcm_chunks_from_bytes(pcm_data))

            print("\n[CLI CLIENT TEST RESULT]")
            print(f"  Final Transcript : '{metrics['transcript']}'")
            print(f"  TTFAB            : {metrics['first_audio_byte_time']:.1f}ms")
            print(f"  Total Audio      : {metrics['total_audio_bytes']} bytes")
            print(f"  Total Turn Time  : {metrics['turn_completed_time']:.1f}ms")

            assert metrics["total_audio_bytes"] > 5000
            assert metrics["first_audio_byte_time"] is not None

        server.should_exit = True
        await server_task

    asyncio.run(_run())
