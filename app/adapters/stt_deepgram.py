"""
Deepgram Streaming Speech-to-Text adapter implementing STTClientProtocol.
Provides real-time streaming audio transcription over WebSockets using Deepgram Nova-2.
Supports interim and speech_final endpointing for ultra-low latency voice RAG.
"""

import asyncio
import json
import ssl
from typing import AsyncGenerator, Optional
import certifi
import websockets

from app.core.config import settings
from app.core.logger import logger
from app.interfaces.adapters import STTClientProtocol


class TranscriptAccumulator:
    """Accumulates partial and finalized transcript segments from Deepgram events."""

    def __init__(self) -> None:
        self.accumulated_finals: list[str] = []

    def process_result(
        self, is_final: bool, speech_final: bool, text: str
    ) -> Optional[dict]:
        text = text.strip()
        if not text:
            return None

        if is_final:
            self.accumulated_finals.append(text)
            if speech_final:
                full_transcript = " ".join(self.accumulated_finals)
                self.accumulated_finals = []
                return {"type": "final", "text": full_transcript}
            else:
                return {
                    "type": "interim",
                    "text": " ".join(self.accumulated_finals),
                }
        else:
            interim = " ".join(self.accumulated_finals + [text]).strip()
            return {"type": "interim", "text": interim}

    def handle_utterance_end(self) -> Optional[dict]:
        if self.accumulated_finals:
            full_transcript = " ".join(self.accumulated_finals)
            self.accumulated_finals = []
            return {"type": "final", "text": full_transcript}
        return None


class DeepgramStreamSession:
    """Manages an active bi-directional WebSocket streaming session with Deepgram."""

    def __init__(
        self,
        api_key: str,
        language: str = "en-IN",
        model: str = "nova-2",
        endpointing_ms: int = 300,
    ) -> None:
        self.api_key = api_key
        self.language = language
        self.model = model
        self.endpointing_ms = endpointing_ms
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        self._accumulator = TranscriptAccumulator()
        self._is_connected = False
        self._send_lock = asyncio.Lock()

    async def start(self) -> None:
        """Connects to the Deepgram streaming WebSocket endpoint."""
        url = (
            f"wss://api.deepgram.com/v1/listen?"
            f"encoding=linear16&sample_rate=16000&channels=1&"
            f"model={self.model}&language={self.language}&"
            f"punctuate=true&interim_results=true&smart_format=true&"
            f"endpointing={self.endpointing_ms}"
        )
        headers = {"Authorization": f"Token {self.api_key}"}
        try:
            self._ws = await websockets.connect(
                url,
                additional_headers=headers,
                ssl=self._ssl_context,
            )
            self._is_connected = True
            logger.info("[DEEPGRAM] Connected to streaming STT WebSocket.")
        except Exception as e:
            logger.error(f"[DEEPGRAM] Connection failed: {e}")
            self._is_connected = False
            raise

    async def send_audio(self, chunk: bytes) -> None:
        """Streams a raw linear16 PCM audio frame to Deepgram."""
        if not self._is_connected or not self._ws:
            return
        async with self._send_lock:
            try:
                await self._ws.send(chunk)
            except websockets.exceptions.ConnectionClosed:
                self._is_connected = False
            except Exception as e:
                logger.warning(f"[DEEPGRAM] Send audio error: {e}")

    async def receive_transcripts(self) -> AsyncGenerator[dict, None]:
        """Yields interim and final transcript events from Deepgram."""
        if not self._is_connected or not self._ws:
            return

        try:
            while self._is_connected and self._ws:
                msg = await self._ws.recv()
                data = json.loads(msg)
                msg_type = data.get("type")

                if msg_type == "Results":
                    is_final = data.get("is_final", False)
                    speech_final = data.get("speech_final", False)
                    alts = data.get("channel", {}).get("alternatives", [])
                    raw_text = alts[0].get("transcript", "") if alts else ""

                    event = self._accumulator.process_result(
                        is_final=is_final,
                        speech_final=speech_final,
                        text=raw_text,
                    )
                    if event:
                        yield event

                elif msg_type == "UtteranceEnd":
                    event = self._accumulator.handle_utterance_end()
                    if event:
                        yield event

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"[DEEPGRAM] Receive error: {e}")
        finally:
            self._is_connected = False

    async def close(self) -> None:
        """Flushes the stream with CloseStream and shuts down WebSocket."""
        if not self._is_connected or not self._ws:
            return
        self._is_connected = False
        try:
            await self._ws.send(json.dumps({"type": "CloseStream"}))
            await self._ws.close()
        except Exception:
            pass
        finally:
            self._ws = None


class MockDeepgramStreamSession:
    """Safe fallback session used when no DEEPGRAM_API_KEY is configured."""

    def __init__(self) -> None:
        self._is_connected = False

    async def start(self) -> None:
        self._is_connected = True
        logger.warning("[DEEPGRAM] Operating with MockDeepgramStreamSession (no API key).")

    async def send_audio(self, chunk: bytes) -> None:
        pass

    async def receive_transcripts(self) -> AsyncGenerator[dict, None]:
        if False:
            yield {}

    async def close(self) -> None:
        self._is_connected = False


class DeepgramSTTAdapter:
    """Deepgram Speech-to-Text adapter complying with STTClientProtocol."""

    def __init__(
        self,
        api_key: Optional[str] = settings.DEEPGRAM_API_KEY,
        language: str = settings.DEEPGRAM_LANGUAGE,
        model: str = settings.DEEPGRAM_MODEL,
        endpointing_ms: int = 300,
    ) -> None:
        self.api_key = api_key
        self.language = language
        self.model = model
        self.endpointing_ms = endpointing_ms

    def create_stream_session(
        self,
    ) -> DeepgramStreamSession | MockDeepgramStreamSession:
        """Creates a streaming WebSocket session instance."""
        if not self.api_key:
            return MockDeepgramStreamSession()
        return DeepgramStreamSession(
            api_key=self.api_key,
            language=self.language,
            model=self.model,
            endpointing_ms=self.endpointing_ms,
        )

    async def stream_audio_frames(
        self, audio_generator: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """
        Consumes streaming raw PCM audio frames and yields transcribed text chunks.
        Complies with STTClientProtocol.
        """
        if not self.api_key:
            yield "This is a test speech input for Sahayak"
            return

        session = self.create_stream_session()
        await session.start()

        async def _sender():
            try:
                async for chunk in audio_generator:
                    await session.send_audio(chunk)
            finally:
                await session.close()

        sender_task = asyncio.create_task(_sender())

        try:
            async for event in session.receive_transcripts():
                text = event.get("text", "").strip()
                if text:
                    yield text
        finally:
            await sender_task
