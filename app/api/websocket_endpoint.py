"""
FastAPI WebSocket endpoint for bi-directional streaming voice communication.
Integrates live multi-provider STT, LLM, TTS, automatic barge-in detection,
and connection-scoped VoiceSessionContext isolation.
"""

import asyncio
import json
import uuid
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.voice_orchestrator import VoiceRAGOrchestrator, VoiceSessionContext
from app.services.session_memory import SessionMemory
from app.adapters.registry import (
    get_stt_adapter,
    get_llm_adapter,
    get_tts_adapter,
    validate_provider,
)
from app.core.logger import logger
from app.core.config import settings

router = APIRouter()

def get_voice_router(orchestrator: VoiceRAGOrchestrator) -> APIRouter:
    @router.websocket("/ws/voice")
    async def voice_websocket(websocket: WebSocket):
        await websocket.accept()

        # Connection-scoped conversational memory buffer (default last 3 turns)
        session_memory = SessionMemory(max_turns=3)

        # 1. Parse connection-scoped negotiation query parameters
        stt_param = websocket.query_params.get("stt")
        llm_param = websocket.query_params.get("llm")
        tts_param = websocket.query_params.get("tts")
        lang_param = websocket.query_params.get("lang") or getattr(orchestrator, "session_language", settings.DEFAULT_LANGUAGE)

        # 2. Instantiate connection-scoped adapters
        try:
            stt_adapter = get_stt_adapter(stt_param, language=lang_param) if stt_param else orchestrator.stt
        except Exception as e:
            logger.warning(f"[WS Voice] Failed to load STT '{stt_param}': {e}. Using orchestrator default.")
            stt_adapter = orchestrator.stt

        try:
            llm_adapter = get_llm_adapter(llm_param) if llm_param else orchestrator.llm
        except Exception as e:
            logger.warning(f"[WS Voice] Failed to load LLM '{llm_param}': {e}. Using orchestrator default.")
            llm_adapter = orchestrator.llm

        try:
            tts_adapter = get_tts_adapter(tts_param) if tts_param else orchestrator.tts
        except Exception as e:
            logger.warning(f"[WS Voice] Failed to load TTS '{tts_param}': {e}. Using orchestrator default.")
            tts_adapter = orchestrator.tts

        indic_tts_adapter = getattr(orchestrator, "indic_tts", None) or get_tts_adapter("edge")

        session_id = str(uuid.uuid4())
        context = VoiceSessionContext(
            session_id=session_id,
            stt_adapter=stt_adapter,
            llm_adapter=llm_adapter,
            tts_adapter=tts_adapter,
            indic_tts_adapter=indic_tts_adapter,
            language=lang_param,
        )

        stt_reconnect_lock = asyncio.Lock()
        stt_listener_task: Optional[asyncio.Task] = None
        stt_stream = None

        def _resolve_stream(adapter, language):
            factory = getattr(adapter, "create_stream_session", None)
            if factory:
                return factory(language=language)
            return adapter

        stt_stream = _resolve_stream(context.stt_adapter, context.language)

        async def stt_event_listener(active_session):
            """Monitors transcripts from STT and dispatches voice turns & barge-in."""
            if not active_session:
                return

            try:
                async for event in active_session.receive_transcripts():
                    event_type = event.get("type") if hasattr(event, "get") else getattr(event, "type", "interim")
                    text = (event.get("text") if hasattr(event, "get") else getattr(event, "text", "")).strip()
                    if not text:
                        continue

                    # Server-side automatic barge-in detection
                    if orchestrator.is_speaking(context=context):
                        logger.info(f"[BARGE_IN] User interruption detected during speech: '{text[:30]}'")
                        await orchestrator.handle_user_interruption(websocket, session_memory=session_memory, context=context)

                    if event_type == "interim":
                        await orchestrator._send_safe_json(websocket, {
                            "event": "INTERIM_TRANSCRIPT",
                            "text": text,
                        }, lock=context.ws_lock)
                    elif event_type == "final":
                        logger.info(f"[STT] Dispatched final transcript: '{text}'")
                        await orchestrator._send_safe_json(websocket, {
                            "event": "FINAL_TRANSCRIPT",
                            "text": text,
                        }, lock=context.ws_lock)
                        # Launch connection-scoped voice turn
                        async def _run_turn():
                            try:
                                await orchestrator.process_voice_turn(
                                    text, websocket, session_memory=session_memory, context=context
                                )
                            except Exception as ex:
                                logger.exception(f"[WS Voice] Turn processing error: {ex}")

                        asyncio.create_task(_run_turn())

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"[STT Listener] Upstream session ended: {e}")

        async def rebind_stt(language: str):
            nonlocal stt_stream, stt_listener_task
            async with stt_reconnect_lock:
                if stt_listener_task and not stt_listener_task.done():
                    stt_listener_task.cancel()
                    try:
                        await stt_listener_task
                    except asyncio.CancelledError:
                        pass
                if stt_stream:
                    try:
                        await stt_stream.close()
                    except Exception:
                        pass
                stt_stream = _resolve_stream(context.stt_adapter, language)
                if stt_stream:
                    try:
                        await stt_stream.start()
                        stt_listener_task = asyncio.create_task(stt_event_listener(stt_stream))
                    except Exception as err:
                        logger.error(f"[WS Voice] Failed to restart STT stream: {err}")

        async def ensure_stt_connected() -> None:
            """Guarantees an active STT session, reconnecting lazily if dropped."""
            nonlocal stt_stream, stt_listener_task
            if stt_stream and getattr(stt_stream, "is_connected", False):
                return

            async with stt_reconnect_lock:
                if stt_stream and getattr(stt_stream, "is_connected", False):
                    return

                logger.info("[WS Voice] Reconnecting STT streaming session...")
                if stt_listener_task and not stt_listener_task.done():
                    stt_listener_task.cancel()
                    try:
                        await stt_listener_task
                    except asyncio.CancelledError:
                        pass

                if stt_stream:
                    try:
                        await stt_stream.close()
                    except Exception:
                        pass
                    stt_stream = None

                stt_stream = _resolve_stream(context.stt_adapter, context.language)
                if stt_stream:
                    try:
                        await stt_stream.start()
                        stt_listener_task = asyncio.create_task(stt_event_listener(stt_stream))
                        logger.info(f"[WS Voice] STT session restored (language={context.language}).")
                    except Exception as e:
                        logger.error(f"[WS Voice] Failed to reconnect STT session: {e}")
                        stt_stream = None

        if stt_stream:
            try:
                await stt_stream.start()
                stt_listener_task = asyncio.create_task(stt_event_listener(stt_stream))
            except Exception as e:
                logger.error(f"[WS Voice] Failed to start STT session: {e}")
                stt_stream = None

        # Record active provider keys on session context
        active_stt_id = stt_param or ("local" if settings.VOICE_PROFILE == "local" else settings.ACTIVE_STT_PROVIDER)
        active_llm_id = llm_param or ("ollama" if settings.VOICE_PROFILE == "local" else settings.ACTIVE_LLM_PROVIDER)
        active_tts_id = tts_param or ("edge" if settings.VOICE_PROFILE == "local" else (settings.ACTIVE_TTS_PROVIDER or settings.TTS_PROVIDER))
        setattr(context, "_active_stt_name", active_stt_id)
        setattr(context, "_active_llm_name", active_llm_id)
        setattr(context, "_active_tts_name", active_tts_id)

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if "bytes" in message and message["bytes"]:
                    # Binary PCM audio frame (e.g. 20ms chunk = 640 bytes)
                    audio_bytes = message["bytes"]
                    await ensure_stt_connected()
                    if stt_stream:
                        await stt_stream.send_audio(audio_bytes)

                elif "text" in message and message["text"]:
                    # JSON control event
                    try:
                        event = json.loads(message["text"])
                        event_type = event.get("event")

                        if event_type == "USER_BARGE_IN":
                            await orchestrator.handle_user_interruption(websocket, session_memory=session_memory, context=context)
                        elif event_type == "RESET_SESSION":
                            session_memory.clear()
                            await orchestrator._send_safe_json(websocket, {"event": "SESSION_RESET"}, lock=context.ws_lock)
                        elif event_type == "SET_LANGUAGE":
                            new_lang = str(event.get("language", "auto")).strip().lower()
                            logger.info(f"[WS Voice] Language switch requested: '{new_lang}'")
                            context.language = new_lang
                            if hasattr(orchestrator, "session_language"):
                                orchestrator.session_language = new_lang
                            await rebind_stt(context.language)
                            await orchestrator._send_safe_json(websocket, {
                                "event": "LANGUAGE_CHANGED",
                                "language": context.language,
                            }, lock=context.ws_lock)
                        elif event_type == "SET_PROVIDER":
                            new_stt = event.get("stt")
                            new_llm = event.get("llm")
                            new_tts = event.get("tts")
                            if new_stt and validate_provider("stt", new_stt):
                                context.stt_adapter = get_stt_adapter(new_stt, language=context.language)
                                setattr(context, "_active_stt_name", new_stt)
                                await rebind_stt(context.language)
                            if new_llm and validate_provider("llm", new_llm):
                                context.llm_adapter = get_llm_adapter(new_llm)
                                setattr(context, "_active_llm_name", new_llm)
                            if new_tts and validate_provider("tts", new_tts):
                                context.tts_adapter = get_tts_adapter(new_tts)
                                setattr(context, "_active_tts_name", new_tts)

                            await orchestrator._send_safe_json(websocket, {
                                "event": "PROVIDER_CHANGED",
                                "stt": getattr(context, "_active_stt_name", "deepgram"),
                                "llm": getattr(context, "_active_llm_name", "groq"),
                                "tts": getattr(context, "_active_tts_name", "cartesia"),
                                "language": context.language,
                            }, lock=context.ws_lock)
                        elif event_type == "FINAL_TRANSCRIPT":
                            transcript = event.get("text", "").strip()
                            if transcript:
                                asyncio.create_task(
                                    orchestrator.process_voice_turn(
                                        transcript, websocket, session_memory=session_memory, context=context
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
            if stt_stream:
                try:
                    await stt_stream.close()
                except Exception:
                    pass
            await context.cancel_active_tasks()
            session_memory.clear()

    return router
