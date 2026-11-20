"""
Cartesia Sonic WebSocket Streaming TTS Adapter.
Provides low-latency (150-350ms TTFAB) raw 16kHz linear PCM audio streaming.
Falls back automatically to EdgeTTSAdapter if Cartesia credentials are absent or fail.
"""

import ssl
import certifi
import logging
from typing import AsyncGenerator, Optional
from cartesia import AsyncCartesia

from app.core.config import settings
from app.adapters.tts.edge import EdgeTTSAdapter

logger = logging.getLogger(__name__)

class CartesiaTTSAdapter:
    """Cartesia Sonic WebSocket streaming adapter emitting 16kHz linear PCM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: str = "sonic-latest",
    ):
        self.api_key = api_key if api_key is not None else settings.CARTESIA_API_KEY
        self.voice_id = voice_id or settings.CARTESIA_VOICE_ID or "30894953-bcce-41fe-892c-15ce19c843ff"
        self.model_id = model_id
        self._fallback_adapter = EdgeTTSAdapter()
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        self.client = AsyncCartesia(api_key=self.api_key) if self.api_key else None

    async def synthesize_stream(
        self,
        text: str,
        voice_override: Optional[str] = None,
        language: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Streams 16kHz linear PCM audio chunks over Cartesia WebSocket."""
        if not self.client:
            logger.warning("[CARTESIA] No CARTESIA_API_KEY configured; falling back to Edge-TTS")
            async for chunk in self._fallback_adapter.synthesize_stream(text, voice_override=voice_override, language=language):
                yield chunk
            return

        ws = None
        try:
            ws = await self.client.tts.websocket(
                websocket_connection_options={"ssl": self._ssl_context}
            )
            output_format = {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 16000,
            }
            voice = {"mode": "id", "id": voice_override or self.voice_id}

            output_iter = await ws.send(
                model_id=self.model_id,
                transcript=text,
                output_format=output_format,
                voice=voice,
                stream=True,
            )

            chunk_count = 0
            async for output in output_iter:
                if output.audio:
                    chunk_count += 1
                    yield output.audio

            if chunk_count == 0:
                raise RuntimeError("Cartesia returned 0 audio chunks")

        except Exception as e:
            logger.warning(f"[CARTESIA] Streaming error ({e}); falling back to Edge-TTS")
            async for chunk in self._fallback_adapter.synthesize_stream(text, voice_override=voice_override, language=language):
                yield chunk
        finally:
            if ws:
                try:
                    await ws.close()
                except Exception:
                    pass
