"""
FastAPI WebSocket endpoint for bi-directional streaming voice communication.
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.voice_orchestrator import VoiceRAGOrchestrator
from app.core.audio_config import AUDIO_CONFIG

router = APIRouter()

def get_voice_router(orchestrator: VoiceRAGOrchestrator) -> APIRouter:
    @router.websocket("/ws/voice")
    async def voice_websocket(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"]:
                    # Binary PCM audio frame (e.g. 20ms chunk = 640 bytes)
                    audio_bytes = message["bytes"]
                    # Audio chunk processing hook (VAD / STT streaming pipeline)
                elif "text" in message and message["text"]:
                    # JSON control event
                    try:
                        event = json.loads(message["text"])
                        event_type = event.get("event")

                        if event_type == "USER_BARGE_IN":
                            await orchestrator.handle_user_interruption(websocket)
                        elif event_type == "FINAL_TRANSCRIPT":
                            transcript = event.get("text", "")
                            if transcript:
                                await orchestrator.process_voice_turn(transcript, websocket)
                    except json.JSONDecodeError:
                        pass
        except WebSocketDisconnect:
            pass

    return router
