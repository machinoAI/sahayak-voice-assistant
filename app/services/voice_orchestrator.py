"""
Async Streaming Voice RAG Orchestrator
Coordinates barge-in cancellation, vector retrieval, LLM token streaming,
queue-decoupled TTS audio generation, thread-safe WebSocket transmission,
and millisecond-precision step-by-step lifecycle tracking.
"""

import asyncio
import re
import uuid
import time
from typing import AsyncGenerator, List, Optional, Tuple
from fastapi import WebSocket, WebSocketDisconnect

from app.interfaces.adapters import (
    STTClientProtocol,
    VectorStoreProtocol,
    LLMClientProtocol,
    TTSClientProtocol,
    RetrievedDocument,
)
from app.core.logger import TurnTracker, logger

ABBREVIATIONS = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "e.g.", "i.e.", "rs.", "vs.", "approx."
}
RAW_DELIMITER_REGEX = re.compile(r'([^.!?\n]+[.!?\n]+)')

def extract_next_sentence(buffer: str) -> Tuple[Optional[str], str]:
    """
    Extracts the next complete sentence from an incremental token buffer.
    Guards against splitting prematurely on common honorifics, abbreviations, and numbers.
    Returns:
        (extracted_sentence, remaining_buffer)
    """
    pos = 0
    while True:
        match = RAW_DELIMITER_REGEX.search(buffer, pos)
        if not match:
            return None, buffer
            
        candidate = match.group(1)
        words = candidate.strip().split()
        last_word = words[-1].lower() if words else ""
        
        # If candidate ends in known abbreviation or digit followed by period (e.g. 'Rs.', '3.')
        if last_word in ABBREVIATIONS or re.search(r'\d\.$', last_word):
            pos = match.end()
            continue
            
        sentence = buffer[:match.end()].strip()
        remaining = buffer[match.end():]
        return sentence, remaining

class VoiceRAGOrchestrator:
    def __init__(
        self,
        stt: STTClientProtocol,
        vdb: VectorStoreProtocol,
        llm: LLMClientProtocol,
        tts: TTSClientProtocol,
    ) -> None:
        self.stt = stt
        self.vdb = vdb
        self.llm = llm
        self.tts = tts
        self._ws_lock = asyncio.Lock()
        self.active_generation_task: Optional[asyncio.Task] = None
        self.active_tts_task: Optional[asyncio.Task] = None
        self.sentence_queue: Optional[asyncio.Queue[Optional[str]]] = None
        self.current_tracker: Optional[TurnTracker] = None

    async def _send_safe_json(self, websocket: WebSocket, payload: dict) -> None:
        """Thread-safe WebSocket JSON frame transmission."""
        async with self._ws_lock:
            try:
                await websocket.send_json(payload)
            except (WebSocketDisconnect, RuntimeError):
                pass

    async def _send_safe_bytes(self, websocket: WebSocket, data: bytes) -> None:
        """Thread-safe WebSocket binary audio packet transmission."""
        async with self._ws_lock:
            try:
                await websocket.send_bytes(data)
            except (WebSocketDisconnect, RuntimeError):
                pass

    def is_speaking(self) -> bool:
        """Returns True if the assistant is currently generating tokens or streaming audio."""
        gen_active = self.active_generation_task is not None and not self.active_generation_task.done()
        tts_active = self.active_tts_task is not None and not self.active_tts_task.done()
        return gen_active or tts_active

    async def handle_user_interruption(self, websocket: WebSocket) -> None:
        """Triggered immediately by VAD when user speaks while assistant is generating/speaking."""
        if self.current_tracker:
            self.current_tracker.log_step("USER_BARGE_IN_TRIGGERED")

        tasks_to_cancel = []
        if self.active_generation_task and not self.active_generation_task.done():
            self.active_generation_task.cancel()
            tasks_to_cancel.append(self.active_generation_task)

        if self.active_tts_task and not self.active_tts_task.done():
            self.active_tts_task.cancel()
            tasks_to_cancel.append(self.active_tts_task)

        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        await self._send_safe_json(websocket, {"event": "CLEAR_AUDIO_BUFFER"})
        if self.current_tracker:
            self.current_tracker.log_step("BUFFER_CLEARED_ON_BARGE_IN")

    async def _tts_worker(
        self, queue: asyncio.Queue[Optional[str]], websocket: WebSocket, tracker: TurnTracker
    ) -> None:
        """Decoupled consumer worker synthesizing sentences concurrently without freezing LLM intake."""
        sentence_count = 0
        total_audio_bytes = 0
        first_audio_packet_sent = False

        try:
            while True:
                sentence = await queue.get()
                if sentence is None:  # Sentinel value signaling end of response
                    queue.task_done()
                    break

                sentence_count += 1
                tracker.log_step(
                    f"TTS_SYNTHESIS_START_S{sentence_count}",
                    {"chars": len(sentence), "text_preview": sentence[:40]},
                )

                try:
                    async for audio_chunk in self.tts.synthesize_stream(sentence):
                        if not first_audio_packet_sent:
                            first_audio_packet_sent = True
                            tracker.log_step(
                                "TTS_FIRST_AUDIO_PACKET",
                                {"ttfab_ms": round((time.perf_counter() - tracker.start_time) * 1000, 1)},
                            )
                        total_audio_bytes += len(audio_chunk)
                        await self._send_safe_bytes(websocket, audio_chunk)
                    
                    tracker.log_step(
                        f"TTS_SENTENCE_STREAMED_S{sentence_count}",
                        {"bytes_sent": total_audio_bytes},
                    )
                finally:
                    queue.task_done()

            tracker.log_step(
                "TTS_ALL_SENTENCES_STREAMED",
                {"sentences": sentence_count, "total_bytes": total_audio_bytes},
            )
        except asyncio.CancelledError:
            tracker.log_step("TTS_WORKER_CANCELLED")

    async def process_voice_turn(self, final_transcript: str, websocket: WebSocket) -> TurnTracker:
        """Executes vector retrieval, prompt compilation, and decoupled token-to-speech streaming."""
        turn_id = str(uuid.uuid4())
        tracker = TurnTracker(turn_id)
        self.current_tracker = tracker

        tracker.log_step("TURN_INITIATED", {"transcript": final_transcript, "length": len(final_transcript)})

        self.sentence_queue = asyncio.Queue()
        self.active_tts_task = asyncio.create_task(
            self._tts_worker(self.sentence_queue, websocket, tracker)
        )
        self.active_generation_task = asyncio.current_task()

        try:
            # 1. Hybrid retrieval
            tracker.log_step("RAG_RETRIEVAL_START", {"query": final_transcript})
            docs: List[RetrievedDocument] = await self.vdb.hybrid_search(
                query=final_transcript, 
                top_k=2
            )
            tracker.log_step(
                "RAG_RETRIEVAL_COMPLETE",
                {"docs_retrieved": len(docs), "top_doc_preview": docs[0].text[:40] if docs else "None"},
            )
            context_text = "\n".join([doc.text for doc in docs])

            # 2. Voice-first system prompt
            system_prompt = (
                "You are Sahayak, a voice assistant. "
                "Answer using ONLY the provided context in 1-2 spoken sentences. "
                "Never use lists, markdown, asterisks, or URLs. Speak naturally."
            )
            prompt = f"{system_prompt}\nContext:\n{context_text}\nUser Question: {final_transcript}"

            # 3. LLM Token Stream -> Sentence Boundary Splitter -> Queue Producer
            tracker.log_step("LLM_STREAM_START", {"model": getattr(self.llm, "model", "default")})
            sentence_buffer = ""
            token_count = 0
            first_token_received = False
            sentence_dispatched = 0

            async for token in self.llm.stream_tokens(prompt):
                if not first_token_received:
                    first_token_received = True
                    tracker.log_step(
                        "LLM_FIRST_TOKEN",
                        {"ttft_ms": round((time.perf_counter() - tracker.start_time) * 1000, 1)},
                    )

                token_count += 1
                sentence_buffer += token

                # Drain all matched sentences from the buffer without slicing corruption
                while True:
                    sentence, sentence_buffer = extract_next_sentence(sentence_buffer)
                    if sentence is None:
                        break
                    if sentence:
                        sentence_dispatched += 1
                        tracker.log_step(
                            f"SENTENCE_QUEUED_S{sentence_dispatched}",
                            {"text": sentence[:40]},
                        )
                        await self.sentence_queue.put(sentence)

            # Flush any remaining text in buffer upon token completion
            remaining = sentence_buffer.strip()
            if remaining:
                sentence_dispatched += 1
                tracker.log_step(
                    f"SENTENCE_QUEUED_S{sentence_dispatched}_REMAINING",
                    {"text": remaining[:40]},
                )
                await self.sentence_queue.put(remaining)

            tracker.log_step(
                "LLM_STREAM_COMPLETE",
                {"total_tokens": token_count, "sentences_dispatched": sentence_dispatched},
            )

            # Enqueue sentinel and await audio synthesis worker completion
            await self.sentence_queue.put(None)
            await self.active_tts_task

            tracker.log_step(
                "TURN_COMPLETED_SUCCESS",
                {"total_turn_ms": round((time.perf_counter() - tracker.start_time) * 1000, 1)},
            )

        except asyncio.CancelledError:
            tracker.log_step("TURN_CANCELLED_ON_BARGE_IN")
            if self.active_tts_task and not self.active_tts_task.done():
                self.active_tts_task.cancel()
        except WebSocketDisconnect:
            tracker.log_step("CLIENT_DISCONNECTED")
            if self.active_tts_task and not self.active_tts_task.done():
                self.active_tts_task.cancel()
        except Exception as e:
            tracker.log_error("TURN_EXECUTION_ERROR", e)
            raise
        finally:
            self.active_generation_task = None
            self.active_tts_task = None

        return tracker
