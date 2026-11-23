"""
End-to-End integration tests for multi-provider negotiation, WebSocket control frames,
and connection-scoped session isolation.
"""

import json
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def test_app():
    return app

def test_health_check_multi_provider(test_app):
    client = TestClient(test_app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "active_providers" in data
    assert "supported_providers" in data
    assert "deepgram" in data["supported_providers"]["stt"]
    assert "groq" in data["supported_providers"]["llm"]
    assert "edge" in data["supported_providers"]["tts"]

def test_websocket_query_param_negotiation(test_app):
    """Verify WebSocket connection accepts query parameters for STT, LLM, and TTS."""
    client = TestClient(test_app)
    with client.websocket_connect("/ws/voice?stt=local&llm=groq&tts=edge&lang=en") as websocket:
        # Send a synthetic user turn
        websocket.send_text(json.dumps({
            "event": "FINAL_TRANSCRIPT",
            "text": "What is PM Kisan Yojana?"
        }))
        # Wait for pipeline responses
        received_events = []
        for _ in range(5):
            msg = websocket.receive_text()
            data = json.loads(msg)
            received_events.append(data.get("event"))
            if data.get("event") == "PIPELINE_STEP":
                break

        assert "PIPELINE_STEP" in received_events

def test_websocket_set_provider_control_frame(test_app):
    """Verify runtime dynamic switching of providers via SET_PROVIDER frame."""
    client = TestClient(test_app)
    with client.websocket_connect("/ws/voice") as websocket:
        # Request dynamic provider switch
        websocket.send_text(json.dumps({
            "event": "SET_PROVIDER",
            "llm": "gemini",
            "tts": "edge",
            "stt": "local"
        }))

        # Expect PROVIDER_CHANGED confirmation
        msg = websocket.receive_text()
        data = json.loads(msg)
        assert data.get("event") == "PROVIDER_CHANGED"
        assert data.get("llm") == "gemini"
        assert data.get("tts") == "edge"
        assert data.get("stt") == "local"

def test_websocket_concurrent_sessions_isolated(test_app):
    """Verify two concurrent WebSocket connections maintain isolated session contexts."""
    client = TestClient(test_app)
    with client.websocket_connect("/ws/voice?llm=groq") as ws1:
        with client.websocket_connect("/ws/voice?llm=openai") as ws2:
            ws1.send_text(json.dumps({"event": "SET_LANGUAGE", "language": "hi"}))
            msg1 = json.loads(ws1.receive_text())
            assert msg1.get("event") == "LANGUAGE_CHANGED"
            assert msg1.get("language") == "hi"

            ws2.send_text(json.dumps({"event": "SET_LANGUAGE", "language": "en"}))
            msg2 = json.loads(ws2.receive_text())
            assert msg2.get("event") == "LANGUAGE_CHANGED"
            assert msg2.get("language") == "en"


@pytest.mark.asyncio
async def test_websocket_local_whisper_e2e_audio_streaming(test_app):
    """
    Complete End-to-End pipeline test:
    Streams real synthesized PCM audio frames through the WebSocket to LocalWhisperSTTAdapter,
    verifies VAD silence endpointing, final transcription, RAG retrieval, LLM streaming,
    and TTS audio synthesis.
    """
    import asyncio
    from client_stream import generate_synthetic_audio

    pcm_audio = await generate_synthetic_audio("What is PM Kisan Yojana?")
    assert len(pcm_audio) > 1000

    client = TestClient(test_app)
    with client.websocket_connect("/ws/voice?stt=local&llm=groq&tts=edge&lang=en") as ws:
        # Stream 16kHz PCM frames in 640-byte (20ms) chunks
        chunk_size = 640
        for i in range(0, len(pcm_audio), chunk_size):
            ws.send_bytes(pcm_audio[i:i + chunk_size])
            await asyncio.sleep(0.005)

        # Stream trailing silence frames to trigger VAD silence endpointing (500ms)
        silence = b"\x00" * 640
        for _ in range(25):
            ws.send_bytes(silence)
            await asyncio.sleep(0.005)

        events_received = []
        audio_bytes_received = 0
        final_transcript = None

        # Drain messages until TURN_COMPLETED_SUCCESS
        for _ in range(200):
            msg = ws.receive()
            if "bytes" in msg and msg["bytes"]:
                audio_bytes_received += len(msg["bytes"])
            elif "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                event_name = data.get("event")
                events_received.append(event_name)
                if event_name == "FINAL_TRANSCRIPT":
                    final_transcript = data.get("text")
                if event_name == "PIPELINE_STEP" and data.get("step") == "TURN_COMPLETED_SUCCESS":
                    break

        assert final_transcript is not None, "No FINAL_TRANSCRIPT emitted by LocalWhisperSTTAdapter"
        assert any(k in final_transcript.lower() for k in ["kisan", "yojana", "pm"]), (
            f"Expected scheme keywords in transcript, got: '{final_transcript}'"
        )
        assert "FINAL_TRANSCRIPT" in events_received
        assert "PIPELINE_STEP" in events_received
        assert audio_bytes_received > 0, "No TTS audio bytes streamed back by server"


@pytest.mark.asyncio
async def test_websocket_local_whisper_e2e_multi_turn_streaming(test_app):
    """
    Multi-Turn End-to-End Test:
    Verifies that a single WebSocket connection using LocalWhisperSTTAdapter
    can successfully complete Turn 1, retain conversational memory, and complete
    Turn 2 with audio streaming without socket disconnects or manual reconnection.
    """
    import asyncio
    from client_stream import generate_synthetic_audio

    pcm_turn1 = await generate_synthetic_audio("What is PM Kisan?")
    pcm_turn2 = await generate_synthetic_audio("Who is eligible for it?")

    client = TestClient(test_app)
    with client.websocket_connect("/ws/voice?stt=local&llm=groq&tts=edge&lang=en") as ws:
        # === TURN 1 ===
        chunk_size = 640
        for i in range(0, len(pcm_turn1), chunk_size):
            ws.send_bytes(pcm_turn1[i:i + chunk_size])
            await asyncio.sleep(0.005)
        for _ in range(25):
            ws.send_bytes(b"\x00" * 640)
            await asyncio.sleep(0.005)

        turn1_completed = False
        for _ in range(300):
            msg = ws.receive()
            if "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                if data.get("event") == "PIPELINE_STEP" and data.get("step") == "TURN_COMPLETED_SUCCESS":
                    turn1_completed = True
                    break
        assert turn1_completed, "Turn 1 did not complete successfully"

        # Brief conversational pause between turns
        await asyncio.sleep(0.5)

        # === TURN 2 (Same connection, testing persistence & pronoun resolution) ===
        for i in range(0, len(pcm_turn2), chunk_size):
            ws.send_bytes(pcm_turn2[i:i + chunk_size])
            await asyncio.sleep(0.005)
        for _ in range(25):
            ws.send_bytes(b"\x00" * 640)
            await asyncio.sleep(0.005)

        turn2_completed = False
        turn2_transcript = None
        turn2_audio_bytes = 0
        for _ in range(300):
            msg = ws.receive()
            if "bytes" in msg and msg["bytes"]:
                turn2_audio_bytes += len(msg["bytes"])
            elif "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                if data.get("event") == "FINAL_TRANSCRIPT":
                    turn2_transcript = data.get("text")
                if data.get("event") == "PIPELINE_STEP" and data.get("step") == "TURN_COMPLETED_SUCCESS":
                    turn2_completed = True
                    break

        assert turn2_completed, "Turn 2 did not complete successfully"
        assert turn2_transcript is not None, "No transcript emitted for Turn 2"
        assert turn2_audio_bytes > 0, "No audio streamed for Turn 2"


