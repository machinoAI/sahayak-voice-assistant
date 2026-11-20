"""
Deepgram STT adapter (Backward-compatibility shim).
Deprecated: Use app.adapters.stt.deepgram or app.adapters.registry instead.
"""

import warnings
from app.adapters.stt.deepgram import (
    DeepgramStreamSession,
    MockDeepgramStreamSession,
    DeepgramSTTAdapter,
    TranscriptAccumulator,
)

warnings.warn(
    "app.adapters.stt_deepgram is deprecated. Use app.adapters.stt.deepgram or app.adapters.registry instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "DeepgramStreamSession",
    "MockDeepgramStreamSession",
    "DeepgramSTTAdapter",
    "TranscriptAccumulator",
]
