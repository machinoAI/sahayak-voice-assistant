"""
Unit tests for STT multi-provider adapters (Deepgram, Sarvam, Local Whisper).
"""

import pytest
from app.interfaces.adapters import STTTranscriptEvent
from app.adapters.stt.deepgram import TranscriptAccumulator, DeepgramSTTAdapter, MockDeepgramStreamSession
from app.adapters.stt.sarvam import SarvamSTTAdapter
from app.adapters.stt.local_whisper import LocalWhisperSTTAdapter, LocalWhisperStreamSession
import asyncio
import numpy as np

def test_stt_transcript_event_dict_compat():
    event = STTTranscriptEvent(
        type="final",
        text="Hello Sahayak",
        is_final=True,
        speech_final=True,
        confidence=0.98,
        language="en",
    )
    # Direct attribute
    assert event.type == "final"
    assert event.text == "Hello Sahayak"

    # Dict-like .get()
    assert event.get("type") == "final"
    assert event.get("missing_key", "default") == "default"

    # Dict-like __getitem__
    assert event["text"] == "Hello Sahayak"
    with pytest.raises(KeyError):
        _ = event["nonexistent"]

def test_transcript_accumulator():
    acc = TranscriptAccumulator()
    # Interim result
    e1 = acc.process_result(is_final=False, speech_final=False, text="Hello")
    assert e1["type"] == "interim"
    assert e1["text"] == "Hello"

    # Final segment but not speech final
    e2 = acc.process_result(is_final=True, speech_final=False, text="world")
    assert e2["type"] == "interim"
    assert e2["text"] == "world"

    # Speech final
    e3 = acc.process_result(is_final=True, speech_final=True, text="how are you")
    assert e3["type"] == "final"
    assert "world how are you" in e3["text"]

@pytest.mark.asyncio
async def test_sarvam_adapter_buffering_and_wav_conversion():
    adapter = SarvamSTTAdapter(api_key="", language_code="hi-IN")
    await adapter.start()

    # Stream 3 chunks of 640 bytes (linear 16kHz PCM)
    for _ in range(3):
        await adapter.send_audio(b"\x00" * 640)

    # Verify PCM to WAV helper generates a valid WAV header
    wav_bytes = adapter._pcm_to_wav(bytes(adapter._audio_buffer))
    assert wav_bytes.startswith(b"RIFF")
    assert b"WAVE" in wav_bytes[:12]

    # Close adapter to trigger flush
    await adapter.close()

    events = []
    async for ev in adapter.receive_transcripts():
        events.append(ev)

    assert len(events) == 1
    assert events[0].is_final is True
    assert events[0].language == "hi"

@pytest.mark.asyncio
async def test_local_whisper_adapter_lifecycle():
    adapter = LocalWhisperSTTAdapter(model_size="base", language="en")
    await adapter.start()

    await adapter.send_audio(b"\x00" * 1280)
    await adapter.close()

    events = []
    async for ev in adapter.receive_transcripts():
        events.append(ev)

    assert len(events) == 1
    assert events[0].text != ""
    assert events[0].is_final is True


def test_local_whisper_stream_session_creation():
    adapter = LocalWhisperSTTAdapter(model_size="tiny", language="en")
    session = adapter.create_stream_session(language="hi")
    assert isinstance(session, LocalWhisperStreamSession)
    assert session.model_size == "tiny"
    assert session.language == "hi"


@pytest.mark.asyncio
async def test_local_whisper_vad_silence_endpointing():
    # Generate 500ms tone at 440Hz with amplitude 5000 (RMS ~3500)
    t = np.linspace(0, 0.5, 8000, endpoint=False)
    sine_bytes = (np.sin(2 * np.pi * 440 * t) * 5000).astype(np.int16).tobytes()

    adapter = LocalWhisperSTTAdapter(model_size="tiny", language="en", silence_threshold_ms=300)
    session = adapter.create_stream_session()
    await session.start()

    # Stream active tone chunks
    for i in range(0, len(sine_bytes), 640):
        await session.send_audio(sine_bytes[i:i + 640])

    # Stream silence chunks exceeding 300ms (20 chunks * 20ms = 400ms)
    for _ in range(20):
        await session.send_audio(b"\x00" * 640)
        await asyncio.sleep(0.005)

    # Allow background dispatch to complete
    await asyncio.sleep(0.8)

    assert not session._event_queue.empty()
    ev = await session._event_queue.get()
    assert ev.type == "final"
    assert ev.is_final is True
    assert ev.text != ""

    await session.close()


@pytest.mark.asyncio
async def test_local_whisper_multi_turn_continuity():
    # 300ms tone chunks
    t = np.linspace(0, 0.3, 4800, endpoint=False)
    sine_bytes = (np.sin(2 * np.pi * 440 * t) * 5000).astype(np.int16).tobytes()

    adapter = LocalWhisperSTTAdapter(model_size="tiny", language="en", silence_threshold_ms=200)
    session = adapter.create_stream_session()
    await session.start()

    # --- Turn 1 ---
    for i in range(0, len(sine_bytes), 640):
        await session.send_audio(sine_bytes[i:i + 640])
    for _ in range(15):  # 300ms silence
        await session.send_audio(b"\x00" * 640)
        await asyncio.sleep(0.005)

    await asyncio.sleep(0.5)
    assert not session._event_queue.empty()
    ev1 = await session._event_queue.get()
    assert ev1.type == "final"

    # --- Turn 2 (Session remains active without reconnect) ---
    for i in range(0, len(sine_bytes), 640):
        await session.send_audio(sine_bytes[i:i + 640])
    for _ in range(15):  # 300ms silence
        await session.send_audio(b"\x00" * 640)
        await asyncio.sleep(0.005)

    await asyncio.sleep(0.5)
    assert not session._event_queue.empty()
    ev2 = await session._event_queue.get()
    assert ev2.type == "final"

    await session.close()


@pytest.mark.asyncio
async def test_local_whisper_mock_fallback_on_uninitialized_model():
    session = LocalWhisperStreamSession(
        model_size="tiny",
        language="en",
        allow_mock_fallback=True,
        mock_text="Mock Sahayak fallback",
    )
    # Manually leave model uninitialized / None to simulate environment failure
    session._model = None
    session._is_active = True

    await session.send_audio(b"\x00" * 640)
    await session.close()

    events = []
    async for ev in session.receive_transcripts():
        events.append(ev)

    assert len(events) == 1
    assert events[0].text == "Mock Sahayak fallback"
    assert events[0].is_final is True


@pytest.mark.asyncio
async def test_local_whisper_stream_audio_frames_helper():
    adapter = LocalWhisperSTTAdapter(model_size="tiny", language="en")

    async def _audio_gen():
        for _ in range(3):
            yield b"\x00" * 640

    chunks = []
    async for text in adapter.stream_audio_frames(_audio_gen()):
        chunks.append(text)

    assert len(chunks) >= 1
    assert "Sahayak" in chunks[0]

