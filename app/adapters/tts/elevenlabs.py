"""
ElevenLabs Streaming TTS Adapter.
Provides low-latency streaming text-to-speech yielding 16kHz linear PCM or MP3 chunks.
"""

import logging
from typing import AsyncGenerator, Optional
from elevenlabs.client import AsyncElevenLabs

from app.core.config import settings
from app.adapters.tts.edge import EdgeTTSAdapter

logger = logging.getLogger(__name__)

class ElevenLabsTTSAdapter:
    """ElevenLabs streaming TTS adapter implementing TTSClientProtocol."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.ELEVENLABS_API_KEY
        self.voice_id = voice_id or settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"
        self.model_id = model_id or settings.ELEVENLABS_MODEL_ID or "eleven_turbo_v2_5"
        self._fallback_adapter = EdgeTTSAdapter()
        self.client = AsyncElevenLabs(api_key=self.api_key) if self.api_key else None

    async def synthesize_stream(
        self,
        text: str,
        voice_override: Optional[str] = None,
        language: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Streams raw 16kHz PCM audio bytes for the given text."""
        if not self.client:
            logger.warning("[ELEVENLABS] No ELEVENLABS_API_KEY configured; falling back to Edge-TTS")
            async for chunk in self._fallback_adapter.synthesize_stream(text, voice_override=voice_override, language=language):
                yield chunk
            return

        effective_voice = voice_override or self.voice_id
        try:
            audio_stream = await self.client.text_to_speech.convert(
                voice_id=effective_voice,
                text=text,
                model_id=self.model_id,
                output_format="pcm_16000",
                optimize_streaming_latency=3,
            )

            async for chunk in audio_stream:
                if chunk:
                    yield chunk

        except Exception as e:
            logger.warning(f"[ELEVENLABS] Streaming error ({e}); falling back to Edge-TTS")
            async for chunk in self._fallback_adapter.synthesize_stream(text, voice_override=voice_override, language=language):
                yield chunk
