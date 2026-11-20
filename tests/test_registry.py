"""
Unit tests for the multi-provider registry and factory dispatchers.
"""

import pytest
from app.adapters.registry import (
    list_supported_providers,
    validate_provider,
    get_stt_adapter,
    get_llm_adapter,
    get_tts_adapter,
)
from app.interfaces.adapters import StreamingSTTProtocol, LLMClientProtocol, TTSClientProtocol
from app.adapters.failover import FailoverLLMAdapter
from app.adapters.failover_tts import FailoverTTSAdapter
from app.adapters.stt.deepgram import DeepgramSTTAdapter
from app.adapters.stt.sarvam import SarvamSTTAdapter
from app.adapters.stt.local_whisper import LocalWhisperSTTAdapter

def test_supported_providers():
    providers = list_supported_providers()
    assert "stt" in providers
    assert "llm" in providers
    assert "tts" in providers
    assert "deepgram" in providers["stt"]
    assert "groq" in providers["llm"]
    assert "cartesia" in providers["tts"]

    assert validate_provider("stt", "deepgram") is True
    assert validate_provider("stt", "sarvam") is True
    assert validate_provider("stt", "unknown_stt") is False
    assert validate_provider("llm", "groq") is True
    assert validate_provider("llm", "gemini") is True
    assert validate_provider("tts", "edge") is True

def test_get_stt_adapter():
    stt_dg = get_stt_adapter("deepgram")
    assert isinstance(stt_dg, DeepgramSTTAdapter)

    stt_sarvam = get_stt_adapter("sarvam")
    assert isinstance(stt_sarvam, SarvamSTTAdapter)

    stt_local = get_stt_adapter("local")
    assert isinstance(stt_local, LocalWhisperSTTAdapter)

    with pytest.raises(ValueError):
        get_stt_adapter("nonexistent_stt")

def test_get_llm_adapter_with_and_without_failover():
    # Without failover
    llm_single = get_llm_adapter("groq", enable_failover=False)
    assert not isinstance(llm_single, FailoverLLMAdapter)
    assert "groq" in llm_single.model or "gpt-oss" in llm_single.model

    # With failover
    llm_failover = get_llm_adapter("groq", enable_failover=True)
    assert isinstance(llm_failover, FailoverLLMAdapter)
    assert len(llm_failover.adapters) >= 1

    with pytest.raises(ValueError):
        get_llm_adapter("invalid_llm", enable_failover=False)

def test_get_tts_adapter_with_and_without_failover():
    # Without failover
    tts_single = get_tts_adapter("edge", enable_failover=False)
    assert not isinstance(tts_single, FailoverTTSAdapter)

    # With failover
    tts_failover = get_tts_adapter("cartesia", enable_failover=True)
    assert isinstance(tts_failover, FailoverTTSAdapter)
    assert len(tts_failover.adapters) >= 1

    with pytest.raises(ValueError):
        get_tts_adapter("invalid_tts", enable_failover=False)
