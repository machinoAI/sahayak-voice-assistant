"""
Centralized Factory & Registry for STT, LLM, and TTS providers.
Supports dynamic switching, profile presets (production, local), and tiered failover.
"""

import logging
from typing import Optional, Dict, List, Tuple

from app.core.config import settings
from app.interfaces.adapters import (
    StreamingSTTProtocol,
    LLMClientProtocol,
    TTSClientProtocol,
)
from app.adapters.stt.deepgram import DeepgramSTTAdapter
from app.adapters.stt.sarvam import SarvamSTTAdapter
from app.adapters.stt.local_whisper import LocalWhisperSTTAdapter

from app.adapters.llm.openai_compatible import OpenAICompatibleLLMAdapter
from app.adapters.llm.anthropic import AnthropicClaudeAdapter
from app.adapters.failover import FailoverLLMAdapter

from app.adapters.tts.cartesia import CartesiaTTSAdapter
from app.adapters.tts.edge import EdgeTTSAdapter
from app.adapters.tts.elevenlabs import ElevenLabsTTSAdapter
from app.adapters.failover_tts import FailoverTTSAdapter

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = {
    "stt": ["deepgram", "sarvam", "local", "whisper"],
    "llm": ["groq", "openai", "gemini", "anthropic", "claude", "ollama"],
    "tts": ["cartesia", "edge", "elevenlabs"],
}

def list_supported_providers() -> Dict[str, List[str]]:
    """Returns dictionary of supported providers per tier."""
    return SUPPORTED_PROVIDERS

def validate_provider(tier: str, provider: str) -> bool:
    """Validates if a given provider name is supported in the specified tier."""
    tier_lower = tier.lower()
    return provider.lower() in SUPPORTED_PROVIDERS.get(tier_lower, [])


def _create_single_llm_adapter(name: str) -> LLMClientProtocol:
    name_clean = name.strip().lower()
    if name_clean == "groq":
        return OpenAICompatibleLLMAdapter(
            provider="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
        )
    elif name_clean == "openai":
        return OpenAICompatibleLLMAdapter(
            provider="openai",
            base_url=settings.OPENAI_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_MODEL,
        )
    elif name_clean == "gemini":
        return OpenAICompatibleLLMAdapter(
            provider="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )
    elif name_clean == "ollama":
        return OpenAICompatibleLLMAdapter(
            provider="ollama",
            base_url=settings.OLLAMA_BASE_URL,
            api_key="ollama",
            model=settings.OLLAMA_MODEL,
        )
    elif name_clean in ("anthropic", "claude"):
        return AnthropicClaudeAdapter(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: '{name}'. Supported: {SUPPORTED_PROVIDERS['llm']}")


def _create_single_tts_adapter(name: str) -> TTSClientProtocol:
    name_clean = name.strip().lower()
    if name_clean == "cartesia":
        return CartesiaTTSAdapter(
            api_key=settings.CARTESIA_API_KEY,
            voice_id=settings.CARTESIA_VOICE_ID,
        )
    elif name_clean == "edge":
        return EdgeTTSAdapter(
            voice=settings.EDGE_VOICE,
            indic_voice=settings.EDGE_TTS_INDIC_VOICE,
        )
    elif name_clean == "elevenlabs":
        return ElevenLabsTTSAdapter(
            api_key=settings.ELEVENLABS_API_KEY,
            voice_id=settings.ELEVENLABS_VOICE_ID,
            model_id=settings.ELEVENLABS_MODEL_ID,
        )
    else:
        raise ValueError(f"Unsupported TTS provider: '{name}'. Supported: {SUPPORTED_PROVIDERS['tts']}")


def get_stt_adapter(
    provider_name: Optional[str] = None,
    language: str = "auto",
) -> StreamingSTTProtocol:
    """Factory to instantiate STT adapters based on profile and provider choice."""
    if not provider_name:
        if settings.VOICE_PROFILE == "local":
            provider_name = "local"
        else:
            provider_name = settings.ACTIVE_STT_PROVIDER

    name_clean = provider_name.strip().lower()

    if name_clean == "deepgram":
        return DeepgramSTTAdapter(
            api_key=settings.DEEPGRAM_API_KEY,
            language=language or settings.DEEPGRAM_LANGUAGE,
            model=settings.DEEPGRAM_MODEL,
        )
    elif name_clean == "sarvam":
        lang_code = "hi-IN" if language in ("hi", "auto") else "en-IN"
        return SarvamSTTAdapter(
            api_key=settings.SARVAM_API_KEY,
            language_code=lang_code,
        )
    elif name_clean in ("local", "whisper"):
        return LocalWhisperSTTAdapter(
            model_size=settings.LOCAL_WHISPER_MODEL,
            language=language,
        )
    else:
        raise ValueError(f"Unsupported STT provider: '{provider_name}'. Supported: {SUPPORTED_PROVIDERS['stt']}")


def get_llm_adapter(
    provider_name: Optional[str] = None,
    enable_failover: bool = True,
) -> LLMClientProtocol:
    """Factory to instantiate LLM adapters with automated failover chain."""
    if not provider_name:
        if settings.VOICE_PROFILE == "local":
            primary_name = "ollama"
        else:
            primary_name = settings.ACTIVE_LLM_PROVIDER
    else:
        primary_name = provider_name.strip().lower()

    if not enable_failover:
        return _create_single_llm_adapter(primary_name)

    # Build chain starting with primary
    chain_names: List[str] = [primary_name]
    for candidate in settings.LLM_FAILOVER_CHAIN:
        cand_clean = candidate.strip().lower()
        if cand_clean not in chain_names:
            chain_names.append(cand_clean)

    adapters: List[Tuple[str, LLMClientProtocol]] = []
    for c_name in chain_names:
        try:
            adapters.append((c_name, _create_single_llm_adapter(c_name)))
        except Exception as e:
            logger.warning(f"[REGISTRY] Skipping LLM failover candidate '{c_name}': {e}")

    if not adapters:
        adapters.append((primary_name, _create_single_llm_adapter(primary_name)))

    return FailoverLLMAdapter(adapters, cooldown_seconds=settings.FAILOVER_COOLDOWN_SECONDS)


def get_tts_adapter(
    provider_name: Optional[str] = None,
    enable_failover: bool = True,
) -> TTSClientProtocol:
    """Factory to instantiate TTS adapters with turn-sticky failover chain."""
    if not provider_name:
        if settings.VOICE_PROFILE == "local":
            primary_name = "edge"
        else:
            primary_name = settings.ACTIVE_TTS_PROVIDER or settings.TTS_PROVIDER
    else:
        primary_name = provider_name.strip().lower()

    if not enable_failover:
        return _create_single_tts_adapter(primary_name)

    # Build chain starting with primary
    chain_names: List[str] = [primary_name]
    for candidate in settings.TTS_FAILOVER_CHAIN:
        cand_clean = candidate.strip().lower()
        if cand_clean not in chain_names:
            chain_names.append(cand_clean)

    adapters: List[Tuple[str, TTSClientProtocol]] = []
    for c_name in chain_names:
        try:
            adapters.append((c_name, _create_single_tts_adapter(c_name)))
        except Exception as e:
            logger.warning(f"[REGISTRY] Skipping TTS failover candidate '{c_name}': {e}")

    if not adapters:
        adapters.append((primary_name, _create_single_tts_adapter(primary_name)))

    return FailoverTTSAdapter(adapters, cooldown_seconds=settings.FAILOVER_COOLDOWN_SECONDS)
