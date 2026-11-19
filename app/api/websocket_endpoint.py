"""
FastAPI WebSocket endpoint for bi-directional streaming voice communication.
Integrates live Deepgram streaming STT, automatic barge-in detection,
and decoupled Voice RAG orchestration.
"""

import asyncio
import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.voice_orchestrator import VoiceRAGOrchestrator
from app.services.session_memory import SessionMemory
from app.core.logger import logger
from app.core.config import settings

router = APIRouter()

def get_voice_router(orchestrator: VoiceRAGOrchestrator) -> APIRouter:
    @router.websocket("/ws/voice")
    async def voice_websocket(websocket: WebSocket):
        await websocket.accept()

        # Connection-scoped conversational memory buffer (default last 3 turns)
        session_memory = SessionMemory(max_turns=3)

        # Initialize live STT stream session if supported by the adapter
        stt_session_factory = getattr(orchestrator.stt, "create_stream_session", None)
        current_language = getattr(orchestrator, "session_language", settings.DEFAULT_LANGUAGE)
        stt_reconnect_lock = asyncio.Lock()
        stt_listener_task: Optional[asyncio.Task] = None
        session = stt_session_factory(language=current_language) if stt_session_factory else None

        async def stt_event_listener(active_session):
            """Monitors transcripts from Deepgram and dispatches voice turns & barge-in."""
            if not active_session:
                return

            try:
                async for event in active_session.receive_transcripts():
                    event_type = event.get("type")
                    text = event.get("text", "").strip()
                    if not text:
                        continue

                    # Server-side automatic barge-in detection
                    if orchestrator.is_speaking():
                        logger.info(f"[BARGE_IN] User interruption detected during speech: '{text[:30]}'")
                        await orchestrator.handle_user_interruption(websocket, session_memory=session_memory)

                    if event_type == "interim":
                        await orchestrator._send_safe_json(websocket, {
                            "event": "INTERIM_TRANSCRIPT",
                            "text": text,
                        })
                    elif event_type == "final":
                        logger.info(f"[STT] Dispatched final transcript: '{text}'")
                        await orchestrator._send_safe_json(websocket, {
                            "event": "FINAL_TRANSCRIPT",
                            "text": text,
                        })
                        # Launch voice turn with session memory
                        asyncio.create_task(
                            orchestrator.process_voice_turn(
                                text, websocket, session_memory=session_memory
                            )
                        )

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"[STT Listener] Upstream session ended: {e}")

        async def ensure_stt_connected() -> None:
            """Guarantees an active STT session and listener task, reconnecting lazily if dropped."""
            nonlocal session, stt_listener_task
            if session and getattr(session, "is_connected", False):
                return

            async with stt_reconnect_lock:
                if session and getattr(session, "is_connected", False):
                    return

                logger.info("[WS Voice] Reconnecting STT streaming session...")
                if stt_listener_task and not stt_listener_task.done():
                    stt_listener_task.cancel()
                    try:
                        await stt_listener_task
                    except asyncio.CancelledError:
                        pass

                if session:
                    try:
                        await session.close()
                    except Exception as e:
                        logger.warning(f"[WS Voice] Error closing prior session: {e}")
                    session = None

                if stt_session_factory:
                    try:
                        session = stt_session_factory(language=current_language)
                        if session:
                            await session.start()
                            stt_listener_task = asyncio.create_task(stt_event_listener(session))
                            logger.info(f"[WS Voice] STT session restored (language={current_language}).")
                    except Exception as e:
                        logger.error(f"[WS Voice] Failed to reconnect STT session: {e}")
                        session = None

        if session:
            try:
                await session.start()
                stt_listener_task = asyncio.create_task(stt_event_listener(session))
            except Exception as e:
                logger.error(f"[WS Voice] Failed to start STT session: {e}")
                session = None

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if "bytes" in message and message["bytes"]:
                    # Binary PCM audio frame (e.g. 20ms chunk = 640 bytes)
                    audio_bytes = message["bytes"]
                    await ensure_stt_connected()
                    if session:
                        await session.send_audio(audio_bytes)

                elif "text" in message and message["text"]:
                    # JSON control event
                    try:
                        event = json.loads(message["text"])
                        event_type = event.get("event")

                        if event_type == "USER_BARGE_IN":
                            await orchestrator.handle_user_interruption(websocket, session_memory=session_memory)
                        elif event_type == "RESET_SESSION":
                            session_memory.clear()
                            await orchestrator._send_safe_json(websocket, {"event": "SESSION_RESET"})
                        elif event_type == "SET_LANGUAGE":
                            new_lang = str(event.get("language", "auto")).strip().lower()
                            logger.info(f"[WS Voice] Language switch requested: '{new_lang}'")
                            current_language = new_lang
                            if hasattr(orchestrator, "session_language"):
                                orchestrator.session_language = new_lang

                            # Re-bind connection-scoped STT session with new language
                            if stt_listener_task and not stt_listener_task.done():
                                stt_listener_task.cancel()
                                try:
                                    await stt_listener_task
                                except asyncio.CancelledError:
                                    pass

                            if session:
                                await session.close()
                                session = None

                            if stt_session_factory:
                                try:
                                    session = stt_session_factory(language=current_language)
                                    if session:
                                        await session.start()
                                        stt_listener_task = asyncio.create_task(stt_event_listener(session))
                                except Exception as e:
                                    logger.error(f"[WS Voice] Failed to rebind STT session with language '{current_language}': {e}")

                            await orchestrator._send_safe_json(websocket, {
                                "event": "LANGUAGE_CHANGED",
                                "language": current_language,
                            })
                        elif event_type == "FINAL_TRANSCRIPT":
                            transcript = event.get("text", "").strip()
                            if transcript:
                                asyncio.create_task(
                                    orchestrator.process_voice_turn(
                                        transcript, websocket, session_memory=session_memory
                                    )
                                )
                    except json.JSONDecodeError:
                        pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if stt_listener_task and not stt_listener_task.done():
                stt_listener_task.cancel()
                try:
                    await stt_listener_task
                except asyncio.CancelledError:
                    pass
            if session:
                await session.close()
            session_memory.clear()

    return router
