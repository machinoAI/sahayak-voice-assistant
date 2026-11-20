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
