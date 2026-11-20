"""
Cartesia Sonic WebSocket Streaming TTS Adapter (Backward-compatibility shim).
Deprecated: Use app.adapters.tts.cartesia or app.adapters.registry instead.
"""

import warnings
from app.adapters.tts.cartesia import CartesiaTTSAdapter

warnings.warn(
    "app.adapters.tts_cartesia is deprecated. Use app.adapters.tts.cartesia or app.adapters.registry instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["CartesiaTTSAdapter"]
