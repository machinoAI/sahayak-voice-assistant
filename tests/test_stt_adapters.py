"""
Unit tests for STT multi-provider adapters (Deepgram, Sarvam, Local Whisper).
"""

import pytest
from app.interfaces.adapters import STTTranscriptEvent
from app.adapters.stt.deepgram import TranscriptAccumulator, DeepgramSTTAdapter, MockDeepgramStreamSession
from app.adapters.stt.sarvam import SarvamSTTAdapter
from app.adapters.stt.local_whisper import LocalWhisperSTTAdapter

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
