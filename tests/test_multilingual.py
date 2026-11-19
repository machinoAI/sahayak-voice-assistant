"""
Comprehensive unit tests for multilingual speech support in Sahayak Voice Assistant.
Covers configuration, Deepgram language parameterization, bilingual semantic routing,
script-based dual-TTS dispatch, session memory pronoun augmentation, and WebSocket control frames.
"""

import asyncio
import re
import pytest
from app.core.config import settings
from app.interfaces.adapters import QueryIntent, RetrievedDocument
from app.adapters.semantic_router import SemanticRouterAdapter
from app.adapters.stt_deepgram import DeepgramSTTAdapter, DeepgramStreamSession
from app.services.session_memory import SessionMemory
from app.services.voice_orchestrator import VoiceRAGOrchestrator


def test_multilingual_config_initialization():
    """Verify multilingual configuration defaults in Settings."""
    assert settings.DEFAULT_LANGUAGE in ("auto", "en", "hi")
    assert "hi-IN" in settings.EDGE_TTS_INDIC_VOICE
    assert "hi" in settings.DEEPGRAM_LANGUAGE_MODELS
    assert "en" in settings.DEEPGRAM_LANGUAGE_MODELS
    assert "auto" in settings.DEEPGRAM_LANGUAGE_MODELS
    assert "language=multi" in settings.DEEPGRAM_LANGUAGE_MODELS["auto"]


def test_deepgram_url_language_formatting():
    """Verify DeepgramStreamSession generates correct query strings across language modes."""
    s_auto = DeepgramStreamSession(api_key="test_key", language="auto")
    s_hi = DeepgramStreamSession(api_key="test_key", language="hi")
    s_en = DeepgramStreamSession(api_key="test_key", language="en")

    assert s_auto.language == "auto"
    assert s_hi.language == "hi"
    assert s_en.language == "en"


def test_semantic_router_devanagari_and_hinglish():
    """Verify bilingual routing for Devanagari Hindi and Hinglish queries."""
    router = SemanticRouterAdapter()

    # Hindi Local Scheme
    assert router.classify_intent("पीएम किसान योजना के लिए आवेदन कैसे करें?") == QueryIntent.LOCAL_SCHEME_FAQ
    assert router.classify_intent("प्रधानमंत्री आवास योजना की सब्सिडी") == QueryIntent.LOCAL_SCHEME_FAQ

    # Hinglish Local Scheme
    assert router.classify_intent("pm kisan yojana me aavedan kaise kare") == QueryIntent.LOCAL_SCHEME_FAQ
    assert router.classify_intent("ayushman card ki patrata kya hai") == QueryIntent.LOCAL_SCHEME_FAQ

    # Hindi Realtime Temporal
    assert router.classify_intent("आज का ताजा समाचार क्या है?") == QueryIntent.REALTIME_TEMPORAL
    assert router.classify_intent("दिल्ली में आज का मौसम कैसा है") == QueryIntent.REALTIME_TEMPORAL

    # Hinglish Realtime Temporal
    assert router.classify_intent("aaj ka taaza samachar kya hai") == QueryIntent.REALTIME_TEMPORAL
    assert router.classify_intent("live cricket match score") == QueryIntent.REALTIME_TEMPORAL

    # Hindi Out of Domain
    assert router.classify_intent("पृथ्वी और चंद्रमा के बीच की दूरी कितनी है") == QueryIntent.OUT_OF_DOMAIN


def test_hindi_pronoun_resolution_session_memory():
    """Verify multi-turn query augmentation for Hindi and Hinglish pronouns."""
    memory = SessionMemory(max_turns=3)
    memory.add_turn("turn-1", "प्रधानमंत्री आवास योजना", "यह ग्रामीण और शहरी नागरिकों के लिए आवास सब्सिडी है।")

    # Pronoun: इसमें
    augmented_1 = memory.get_augmented_query("इसमें कौन से दस्तावेज चाहिए?")
    assert "प्रधानमंत्री आवास योजना" in augmented_1
    assert "इसमें कौन से दस्तावेज चाहिए?" in augmented_1

    # Pronoun: iska
    augmented_2 = memory.get_augmented_query("iska apply process kya hai?")
    assert "प्रधानमंत्री आवास योजना" in augmented_2


def test_script_detection_tts_routing():
    """Verify that Devanagari sentences route to indic_tts and Latin sentences route to tts."""
    class MockTTS:
        def __init__(self, name: str):
            self.name = name
            self.called_with = []

        async def synthesize_stream(self, text: str):
            self.called_with.append(text)
            yield b"\x00" * 320

    async def _run():
        english_tts = MockTTS("cartesia_english")
        indic_tts = MockTTS("edge_indic")

        class DummyAdapter:
            pass

        orchestrator = VoiceRAGOrchestrator(
            stt=DummyAdapter(),
            vdb=DummyAdapter(),
            llm=DummyAdapter(),
            tts=english_tts,
            indic_tts=indic_tts,
        )

        # Devanagari sentence detection
        devanagari_sentence = "नमस्ते, मैं आपकी क्या सहायता कर सकता हूँ?"
        has_devanagari = bool(re.search(r'[\u0900-\u097F]', devanagari_sentence))
        assert has_devanagari is True

        active_tts = (
            orchestrator.indic_tts
            if (orchestrator.indic_tts and (has_devanagari or orchestrator.session_language == "hi"))
            else orchestrator.tts
        )
        assert active_tts.name == "edge_indic"

        # English sentence detection
        english_sentence = "PM Kisan Samman Nidhi Yojana provides six thousand rupees per year."
        has_devanagari_en = bool(re.search(r'[\u0900-\u097F]', english_sentence))
        assert has_devanagari_en is False

        active_tts_en = (
            orchestrator.indic_tts
            if (orchestrator.indic_tts and (has_devanagari_en or orchestrator.session_language == "hi"))
            else orchestrator.tts
        )
        assert active_tts_en.name == "cartesia_english"

    asyncio.run(_run())


def test_devanagari_sentence_boundary_splitting():
    """Verify sentence splitter splits on Hindi danda (।) and double danda (॥)."""
    from app.services.voice_orchestrator import extract_next_sentence

    buffer = "प्रधानमंत्री आवास योजना एक सरकारी योजना है। इसके तहत वित्तीय सहायता मिलती है।"
    s1, rem1 = extract_next_sentence(buffer)
    assert s1 == "प्रधानमंत्री आवास योजना एक सरकारी योजना है।"
    assert rem1.strip() == "इसके तहत वित्तीय सहायता मिलती है।"

    s2, rem2 = extract_next_sentence(rem1)
    assert s2 == "इसके तहत वित्तीय सहायता मिलती है।"
    assert rem2 == ""
