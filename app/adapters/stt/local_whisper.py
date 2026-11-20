"""
Local Whisper STT adapter for zero-cost offline development profile.
"""

import io
import wave
import asyncio
import logging
from typing import AsyncGenerator, Optional

from app.core.config import settings
from app.interfaces.adapters import STTTranscriptEvent, StreamingSTTProtocol

logger = logging.getLogger(__name__)

class LocalWhisperSTTAdapter:
    """Local offline STT adapter for zero-cost development profile."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        language: str = "en",
    ):
        self.model_size = model_size or settings.LOCAL_WHISPER_MODEL
        self.language = language
        self._audio_buffer = bytearray()
        self._is_active = False
        self._event_queue: asyncio.Queue[Optional[STTTranscriptEvent]] = asyncio.Queue()

    async def start(self) -> None:
        self._audio_buffer.clear()
        self._is_active = True
        logger.info(f"[LOCAL-WHISPER] Starting local whisper session (model: {self.model_size})")

    async def connect(self) -> None:
        await self.start()

    async def send_audio(self, chunk: bytes) -> None:
        if not self._is_active:
            return
        self._audio_buffer.extend(chunk)

    async def receive_transcripts(self) -> AsyncGenerator[STTTranscriptEvent, None]:
        while self._is_active or not self._event_queue.empty():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                if event is None:
                    break
                yield event
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        if not self._is_active:
            return
        self._is_active = False

        # In offline/dev environment, generate simulated transcript from collected audio frames
        if len(self._audio_buffer) > 0:
            mock_text = "What is Sahayak voice assistant?"
            await self._event_queue.put(
                STTTranscriptEvent(
                    type="final",
                    text=mock_text,
                    is_final=True,
                    speech_final=True,
                    language=self.language,
                )
            )
        await self._event_queue.put(None)
