"""
Microsoft Edge-TTS streaming adapter (Backward-compatibility shim).
Deprecated: Use app.adapters.tts.edge or app.adapters.registry instead.
"""

import warnings
from app.adapters.tts.edge import EdgeTTSAdapter

warnings.warn(
    "app.adapters.tts_edge is deprecated. Use app.adapters.tts.edge or app.adapters.registry instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["EdgeTTSAdapter"]
