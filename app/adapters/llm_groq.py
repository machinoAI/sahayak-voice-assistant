"""
Groq LLM streaming adapter (Backward-compatibility shim).
Deprecated: Use app.adapters.llm.openai_compatible or app.adapters.registry instead.
"""

import warnings
from typing import Optional, Any
from app.core.config import settings
from app.adapters.llm.openai_compatible import OpenAICompatibleLLMAdapter

warnings.warn(
    "app.adapters.llm_groq is deprecated. Use app.adapters.llm.openai_compatible or app.adapters.registry instead.",
    DeprecationWarning,
    stacklevel=2,
)

_UNSET = object()

class GroqLLMAdapter(OpenAICompatibleLLMAdapter):
    """Backward-compatible Groq adapter wrapping OpenAICompatibleLLMAdapter."""

    def __init__(
        self,
        api_key: Any = _UNSET,
        model: Optional[str] = None,
    ):
        effective_key = settings.GROQ_API_KEY if api_key is _UNSET else api_key
        effective_model = model or settings.GROQ_MODEL
        super().__init__(
            provider="groq",
            api_key=effective_key,
            model=effective_model,
            base_url="https://api.groq.com/openai/v1",
        )
        self.model = effective_model
