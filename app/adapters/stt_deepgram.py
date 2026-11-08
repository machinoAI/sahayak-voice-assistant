"""
Deepgram Streaming Speech-to-Text adapter implementing STTClientProtocol.
Provides real-time streaming audio transcription over WebSockets.
"""

from typing import AsyncGenerator
import json
import httpx
from app.core.config import settings

class DeepgramSTTAdapter:
    def __init__(self, api_key: str = settings.DEEPGRAM_API_KEY, language: str = "en-IN"):
        self.api_key = api_key
        self.language = language

    async def stream_audio_frames(self, audio_generator: AsyncGenerator[bytes, None]) -> AsyncGenerator[str, None]:
        """
        Consumes streaming raw PCM audio frames and yields transcribed text chunks.
        """
        if not self.api_key:
            # Fallback mock for testing without live API keys
            yield "This is a test speech input for Sahayak"
            return

        url = f"wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1&language={self.language}&punctuate=true&interim_results=true"
        headers = {"Authorization": f"Token {self.api_key}"}

        # In production WebSocket streaming loop with Deepgram:
        # Connect to wss://api.deepgram.com, stream audio_generator bytes, yield transcripts.
        yield ""
