"""
Microsoft Edge-TTS streaming adapter implementing TTSClientProtocol.
Free, zero API key required, with high-quality Indian English & Hindi neural voices.
"""

from typing import AsyncGenerator, Optional
import edge_tts
from app.core.config import settings

class EdgeTTSAdapter:
    """Microsoft Edge-TTS streaming adapter emitting MP3 audio chunks."""

    def __init__(
        self,
        voice: Optional[str] = None,
        indic_voice: Optional[str] = None,
    ):
        self.voice = voice or settings.EDGE_VOICE
        self.indic_voice = indic_voice or settings.EDGE_TTS_INDIC_VOICE

    async def synthesize_stream(
        self,
        text: str,
        voice_override: Optional[str] = None,
        language: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Streams audio packets from Edge-TTS for the provided sentence/clause."""
        selected_voice = voice_override
        if not selected_voice:
            if language == "hi":
                selected_voice = self.indic_voice
            else:
                selected_voice = self.voice

        communicate = edge_tts.Communicate(text=text, voice=selected_voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and chunk["data"]:
                yield chunk["data"]
