"""
Sarvam AI Indic Speech-to-Text adapter implementing StreamingSTTProtocol.
Supports high-accuracy ASR across 10+ Indian languages (Hindi, Bengali, Tamil, etc.).
"""

import io
import wave
import asyncio
import logging
from typing import AsyncGenerator, Optional, List
import httpx

from app.core.config import settings
from app.interfaces.adapters import STTTranscriptEvent, StreamingSTTProtocol
from app.adapters.base import HTTPClientManager

logger = logging.getLogger(__name__)

class SarvamSTTAdapter:
    """Buffered batch adapter for Sarvam AI Saaras ASR endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        language_code: str = "hi-IN",
        model: str = "saaras:v3",
    ):
        self.api_key = api_key if api_key is not None else settings.SARVAM_API_KEY
        self.language_code = language_code
        self.model = model
        self.endpoint = "https://api.sarvam.ai/speech-to-text"
        self._audio_buffer = bytearray()
        self._is_active = False
        self._event_queue: asyncio.Queue[Optional[STTTranscriptEvent]] = asyncio.Queue()

    async def start(self) -> None:
        self._audio_buffer.clear()
        self._is_active = True
        logger.info(f"[SARVAM-STT] Initialized session for language {self.language_code}")

    async def connect(self) -> None:
        await self.start()

    async def send_audio(self, chunk: bytes) -> None:
        if not self._is_active:
            return
        self._audio_buffer.extend(chunk)

    def _pcm_to_wav(self, pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit linear PCM
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return wav_io.getvalue()

    async def _transcribe_buffer(self) -> None:
        if not self._audio_buffer:
            return

        pcm_data = bytes(self._audio_buffer)
        self._audio_buffer.clear()

        if not self.api_key:
            # Fallback mock transcript for development
            logger.warning("[SARVAM-STT] No SARVAM_API_KEY configured; yielding mock Hindi transcript.")
            await self._event_queue.put(
                STTTranscriptEvent(
                    type="final",
                    text="नमस्ते, यह सर्वम एआई का परीक्षण भाषण है।",
                    is_final=True,
                    speech_final=True,
                    language="hi",
                )
            )
            return

        wav_data = self._pcm_to_wav(pcm_data)
        client = HTTPClientManager.get_client("sarvam", timeout=12.0)

        files = {"file": ("audio.wav", wav_data, "audio/wav")}
        data = {
            "model": self.model,
            "language_code": self.language_code,
        }
        headers = {"api-subscription-key": self.api_key}

        try:
            response = await client.post(self.endpoint, files=files, data=data, headers=headers)
            if response.status_code == 200:
                result = response.json()
                transcript = result.get("transcript", "").strip()
                if transcript:
                    await self._event_queue.put(
                        STTTranscriptEvent(
                            type="final",
                            text=transcript,
                            is_final=True,
                            speech_final=True,
                            language=self.language_code[:2],
                        )
                    )
            else:
                logger.error(f"[SARVAM-STT] API error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"[SARVAM-STT] Transcription error: {e}")

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
        await self._transcribe_buffer()
        await self._event_queue.put(None)
