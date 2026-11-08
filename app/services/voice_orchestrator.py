"""
Async Streaming Voice RAG Orchestrator
Coordinates barge-in cancellation, vector retrieval, LLM token streaming,
queue-decoupled TTS audio generation, and thread-safe WebSocket transmission.
"""

import asyncio
import re
from typing import AsyncGenerator, List, Optional, Tuple
from fastapi import WebSocket, WebSocketDisconnect

from app.interfaces.adapters import (
    STTClientProtocol,
    VectorStoreProtocol,
    LLMClientProtocol,
    TTSClientProtocol,
    RetrievedDocument,
)

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
        
        # If the candidate ends in a known abbreviation or a digit followed by a period (e.g. 'Rs.', '3.')
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

    async def handle_user_interruption(self, websocket: WebSocket) -> None:
        """Triggered immediately by VAD when user speaks while assistant is generating/speaking."""
        tasks_to_cancel = []
        if self.active_generation_task and not self.active_generation_task.done():
            self.active_generation_task.cancel()
            tasks_to_cancel.append(self.active_generation_task)

        if self.active_tts_task and not self.active_tts_task.done():
            self.active_tts_task.cancel()
            tasks_to_cancel.append(self.active_tts_task)

        if tasks_to_cancel:
            # Await task teardown to prevent trailing audio emission
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        await self._send_safe_json(websocket, {"event": "CLEAR_AUDIO_BUFFER"})

    async def _tts_worker(self, queue: asyncio.Queue[Optional[str]], websocket: WebSocket) -> None:
        """Decoupled consumer worker synthesizing sentences concurrently without freezing LLM intake."""
        try:
            while True:
                sentence = await queue.get()
                if sentence is None:  # Sentinel value signaling end of response
                    queue.task_done()
                    break

                try:
                    async for audio_chunk in self.tts.synthesize_stream(sentence):
                        await self._send_safe_bytes(websocket, audio_chunk)
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass

    async def process_voice_turn(self, final_transcript: str, websocket: WebSocket) -> None:
        """Executes vector retrieval, prompt compilation, and decoupled token-to-speech streaming."""
        self.sentence_queue = asyncio.Queue()
        self.active_tts_task = asyncio.create_task(self._tts_worker(self.sentence_queue, websocket))
        self.active_generation_task = asyncio.current_task()

        try:
            # 1. Hybrid retrieval (target budget: <60ms execution)
            docs: List[RetrievedDocument] = await self.vdb.hybrid_search(
                query=final_transcript, 
                top_k=2
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
            sentence_buffer = ""
            async for token in self.llm.stream_tokens(prompt):
                sentence_buffer += token

                # Drain all matched sentences from the buffer without slicing corruption
                while True:
                    sentence, sentence_buffer = extract_next_sentence(sentence_buffer)
                    if sentence is None:
                        break
                    if sentence:
                        await self.sentence_queue.put(sentence)

            # Flush any remaining text in buffer upon token completion
            remaining = sentence_buffer.strip()
            if remaining:
                await self.sentence_queue.put(remaining)

            # Enqueue sentinel and await audio synthesis worker completion
            await self.sentence_queue.put(None)
            await self.active_tts_task

        except asyncio.CancelledError:
            # Clean exit on user barge-in
            if self.active_tts_task and not self.active_tts_task.done():
                self.active_tts_task.cancel()
        except WebSocketDisconnect:
            if self.active_tts_task and not self.active_tts_task.done():
                self.active_tts_task.cancel()
        finally:
            self.active_generation_task = None
            self.active_tts_task = None
