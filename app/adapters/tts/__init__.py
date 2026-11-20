"""
TTS Adapters package.
"""
from app.adapters.tts.cartesia import CartesiaTTSAdapter
from app.adapters.tts.edge import EdgeTTSAdapter
from app.adapters.tts.elevenlabs import ElevenLabsTTSAdapter
from app.adapters.failover_tts import FailoverTTSAdapter

__all__ = [
    "CartesiaTTSAdapter",
    "EdgeTTSAdapter",
    "ElevenLabsTTSAdapter",
    "FailoverTTSAdapter",
]
