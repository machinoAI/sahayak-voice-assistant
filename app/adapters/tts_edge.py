"""
Microsoft Edge-TTS streaming adapter implementing TTSClientProtocol.
Free, zero API key required, with high-quality Indian English & Hindi neural voices.
"""

from typing import AsyncGenerator
import edge_tts
from app.core.config import settings

class EdgeTTSAdapter:
    def __init__(self, voice: str = settings.EDGE_VOICE):
        self.voice = voice

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Streams audio packets from Edge-TTS for the provided sentence/clause.
        """
        communicate = edge_tts.Communicate(text=text, voice=self.voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and chunk["data"]:
                yield chunk["data"]
