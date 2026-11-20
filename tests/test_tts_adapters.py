"""
Unit tests for TTS multi-provider adapters (Edge, Cartesia, ElevenLabs, and FailoverTTSAdapter).
"""

import pytest
from app.adapters.tts.edge import EdgeTTSAdapter
from app.adapters.tts.cartesia import CartesiaTTSAdapter
from app.adapters.tts.elevenlabs import ElevenLabsTTSAdapter
from app.adapters.failover_tts import FailoverTTSAdapter

class MockFailingTTS:
    def __init__(self, name: str):
        self.name = name

    async def synthesize_stream(self, text: str, voice_override=None, language=None):
        if False:
            yield b""
        raise RuntimeError(f"{self.name} TTS network error")

class MockHealthyTTS:
    def __init__(self, name: str, chunk_byte: bytes = b"\x01\x02"):
        self.name = name
        self.chunk_byte = chunk_byte
        self.call_count = 0

    async def synthesize_stream(self, text: str, voice_override=None, language=None):
        self.call_count += 1
        yield self.chunk_byte * 160

@pytest.mark.asyncio
async def test_cartesia_fallback_without_key():
    adapter = CartesiaTTSAdapter(api_key=None)
    chunks = []
    async for chunk in adapter.synthesize_stream("Testing fallback without key"):
        chunks.append(chunk)
    assert len(chunks) > 0

@pytest.mark.asyncio
async def test_elevenlabs_fallback_without_key():
    adapter = ElevenLabsTTSAdapter(api_key=None)
    chunks = []
    async for chunk in adapter.synthesize_stream("Testing elevenlabs fallback"):
        chunks.append(chunk)
    assert len(chunks) > 0

@pytest.mark.asyncio
async def test_failover_tts_immediate_switch():
    primary = MockFailingTTS("cartesia")
    fallback = MockHealthyTTS("edge", b"\xaa\xbb")

    failover = FailoverTTSAdapter(
        adapters=[("cartesia", primary), ("edge", fallback)],
        cooldown_seconds=10.0,
    )

    chunks = []
    async for chunk in failover.synthesize_stream("Sentence 1"):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert chunk.startswith(b"\xaa\xbb")
    assert failover.active_turn_provider == "edge"
    assert failover._is_cooling_down("cartesia") is True

@pytest.mark.asyncio
async def test_failover_tts_turn_stickiness():
    """Verify that once failover switches to fallback, subsequent sentences in the turn stick to fallback."""
    primary = MockFailingTTS("cartesia")
    fallback = MockHealthyTTS("edge")

    failover = FailoverTTSAdapter(
        adapters=[("cartesia", primary), ("edge", fallback)],
        cooldown_seconds=10.0,
    )

    # First sentence triggers failover
    async for _ in failover.synthesize_stream("Sentence 1"):
        pass
    assert failover.active_turn_provider == "edge"
    assert fallback.call_count == 1

    # Second sentence in the same turn should stick directly to edge without re-trying failing cartesia
    async for _ in failover.synthesize_stream("Sentence 2"):
        pass
    assert fallback.call_count == 2
    assert failover.active_turn_provider == "edge"

    # Reset turn boundary (simulates new user turn)
    failover.reset_turn()
    assert failover.active_turn_provider is None
