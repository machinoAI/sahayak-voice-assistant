# Stage 9: Implementation Readiness & Codebase Details Report

**Target Document:** `docs/designs/multi_provider_architecture.md` (DetailedRange, Lines 496–591)  
**Auditors:** egm-implementation-readiness (Pragmatic Tech Lead), egm-codebase-details (Pedantic Quality Auditor)  
**Date:** 2026-11-20

---

## Executive Summary

The Detailed Implementation Plan outlines an ambitious migration from hardcoded single providers to a pluggable multi-provider architecture across STT, LLM, and TTS. However, an engineer attempting to write code immediately from lines 496–591 faces critical blockers, codebase wiring omissions, and dependency hazards:
1. **Missing Wiring Entrypoint (`app/main.py`)**: `app/main.py` is omitted, and moving legacy adapters without backwards-compatibility shims will immediately break `app/main.py` and `tests/test_adapters.py`.
2. **False Attribution of Instantiation**: `VoiceRAGOrchestrator.__init__` in `app/services/voice_orchestrator.py` is already decoupled and accepts protocol instances; the concrete instantiations actually reside in `app/main.py`.
3. **Python 3.13 & Dependency Hazards**: Standard library `audioop` was removed in Python 3.13; `requirements.txt` leaves ambiguous choices (`google-genai` vs `google-generativeai`) and misses required dependencies (`elevenlabs`, resamplers like `soxr` or `audioop-lts`).
4. **Topological Inversion**: Protocol breaking changes in Phase 1 leave the system broken through Phase 5, and tests are deferred until after everything is built.
5. **Vague REST vs. Streaming Specifications**: Groq Whisper and OpenAI Whisper do not offer streaming WebSocket endpoints; the plan does not define how they satisfy streaming `STTClientProtocol`.
6. **Incomplete Error Boundaries**: Unhandled edge cases when all providers in a failover chain fail, mid-turn `SET_PROVIDER` races, and lack of STT error degradation.

---

## Prioritized Findings

### 🔴 Blockers

1. **Missing Application Entrypoint (`app/main.py`) & Unspecified Deprecation/Shim Strategy**
   * **Affected Scope:** Lines 500–576 (Phases 1–5), missing `app/main.py`, and legacy adapter paths (`app/adapters/llm_groq.py`, `app/adapters/tts_cartesia.py`, `app/adapters/tts_edge.py`, `app/adapters/stt_deepgram.py`).
   * **Discrepancy Description & Rationale:**
     - In the existing codebase, `app/main.py` (lines 12–48) directly imports and instantiates concrete classes (`GroqLLMAdapter`, `CartesiaTTSAdapter`, `EdgeTTSAdapter`, `DeepgramSTTAdapter`). `app/main.py` is **completely absent** from the 33 implementation tasks.
     - Tasks 7, 14, 15, and 20 state `Create / Migrate from <legacy_file>.py`. If these files are moved or deleted, `app/main.py` and `tests/test_adapters.py` (which directly imports `from app.adapters.llm_groq import ...`) will immediately crash on `ModuleNotFoundError`.
     - The plan claims in line 498: *"The implementation proceeds in five sequential phases to ensure backwards compatibility and zero regressions across existing tests."* This claim is violated without explicit shim preservation.
   * **Proposed Correction:**
     - Add an explicit task in Phase 5: **`app/main.py` (Modify)** to bootstrap `VoiceRAGOrchestrator` using `LLMProviderFactory`, `TTSProviderFactory`, and `FailoverLLMAdapter` / `FailoverTTSAdapter`.
     - In Tasks 7, 14, 15, and 20, specify that the legacy root files (`app/adapters/llm_groq.py`, etc.) are retained as **deprecated re-export shims** (e.g., `from app.adapters.llm.groq import GroqLLMAdapter`) to keep `tests/test_adapters.py` functional throughout all migration phases.

2. **False Attribution of Concrete Instantiation to `voice_orchestrator.py`**
   * **Affected Scope:** Lines 568–570 (Phase 5, Item 25)
   * **Discrepancy Description & Rationale:**
     - Item 25 states: *"Rationale: Decouple concrete adapter instantiations in favor of `FailoverLLMAdapter` and `FailoverTTSAdapter` created via factories. Action: Update `__init__` to accept pluggable adapters."*
     - `VoiceRAGOrchestrator.__init__` in `app/services/voice_orchestrator.py` is **already fully decoupled**. It takes abstract protocol instances (`stt: STTClientProtocol`, `vdb: VectorStoreProtocol`, `llm: LLMClientProtocol`, `tts: TTSClientProtocol`, `indic_tts: Optional[TTSClientProtocol] = None`). It does *not* instantiate concrete adapters.
   * **Proposed Correction:**
     - Correct Item 25 to clarify that `VoiceRAGOrchestrator.__init__` already accepts protocol instances, but needs support for dynamic runtime provider updates via session-scoped overrides.

3. **Python 3.13 Incompatibilities and Incomplete / Ambiguous Dependencies**
   * **Affected Scope:** Lines 514–516 (Phase 1, Item 5: `requirements.txt`)
   * **Discrepancy Description & Rationale:**
     - **Python 3.13 `audioop` Removal**: PEP 594 completely removed `audioop` from Python 3.13. Standard Python audio resampling/conversion libraries (e.g. `pydub`, standard wave operations) crash with `ModuleNotFoundError: No module named 'audioop'`.
     - **Ambiguity in GenAI SDK**: Line 516 specifies `google-genai>=0.1.0 (or google-generativeai)`. `google-genai>=0.1.0` is already in `requirements.txt` (line 11). `google-genai` and `google-generativeai` have completely incompatible SDK interfaces (`genai.Client()` vs `genai.GenerativeModel()`).
     - **Missing Vendor Dependencies**: Tasks 16 & 22 introduce ElevenLabs TTS and STT, but `elevenlabs` is not added to `requirements.txt`. Tasks 18 & 24 introduce Sarvam Bulbul and Indic STT without specifying client dependencies.
   * **Proposed Correction:**
     - Update Item 5 (`requirements.txt`) to specify exact packages:
       ```text
       openai>=1.50.0
       anthropic>=0.36.0
       google-genai>=0.1.0        # Enforce official SDK; eliminate '(or google-generativeai)'
       elevenlabs>=1.0.0          # Required for ElevenLabs TTS and Realtime STT
       soxr>=0.3.7                # C-level high-performance resampler compatible with Python 3.11 and 3.13
       audioop-lts>=0.2.1; python_version>='3.13'  # Backport for 3.13 compatibility
       miniaudio>=1.59
       ```

---

### 🟡 Major Findings

4. **Topological Execution Ordering Breaks Pipeline During Intermediate Phases**
   * **Affected Scope:** Lines 500–589 (Phases 1 through 5)
   * **Discrepancy Description & Rationale:**
     - In Phase 1 (Item 1), modifying `app/interfaces/adapters.py` redefines protocols. However, `app/services/voice_orchestrator.py` and `app/api/websocket_endpoint.py` are not updated until Phase 5 (Items 25–26). During Phases 1–4, the orchestrator and gateway are in direct protocol violation.
     - In Phase 1, `requirements.txt` is updated at Item 5, *after* `registry.py` (Item 3) and `audio_normalizer.py` (Item 4).
     - Unit test creation is postponed entirely to Phase 5 (Items 28–29). Phases 1–4 create over 20 files without intermediate verification.
   * **Proposed Correction:**
     - Move `requirements.txt` modification to Step 1 of Phase 1.
     - Implement backward-compatible protocol definitions (using `@runtime_checkable` or default method stubs) in Phase 1 so unmigrated adapters continue to type-check.
     - Colocate tests within their respective phases (Phase 1: registry/normalizer tests; Phase 2: LLM tests; Phase 3: TTS tests; Phase 4: STT tests; Phase 5: integration tests).

5. **Unspecified Streaming Architectures for REST-Only Providers (Groq & OpenAI Whisper, Sarvam)**
   * **Affected Scope:** Lines 557–565 (Phase 4, Items 21, 23, 24) and lines 548–550 (Phase 3, Item 18)
   * **Discrepancy Description & Rationale:**
     - Neither Groq Whisper nor standard OpenAI Whisper provides a bidirectional streaming WebSocket API. Both are HTTP POST endpoints accepting complete audio files.
     - An engineer implementing `STTClientProtocol` (`send_audio`, `receive_transcripts`) cannot stream chunks to these endpoints directly. The plan leaves it completely undefined whether the adapter must implement an internal VAD silence chunker, accumulate 1-second audio frames in memory, or use Azure Speech SDK / OpenAI Realtime API (`wss://api.openai.com/v1/realtime`).
   * **Proposed Correction:**
     - Explicitly specify the buffering model for REST transcription in `GroqWhisperSTTAdapter` and `OpenAIWhisperSTTAdapter` (e.g. `AudioBufferAccumulator` collecting 16kHz PCM chunks until energy-based VAD or a fixed window triggers an HTTP POST request in a background thread).
     - Clarify that OpenAI STT uses REST Whisper with VAD chunking or the Realtime WebSocket API.

6. **Audio Normalizer Architecture & Integration Contradiction**
   * **Affected Scope:** Lines 511–513 (Phase 1, Item 4) & lines 342–354 (Section 5)
   * **Discrepancy Description & Rationale:**
     - The Mermaid diagram (lines 182–185) shows `TTS_EDGE & TTS_11 & TTS_SARVAM --> NORM --> EP` (an external normalization filter sitting between TTS and WebSocket endpoint). Conversely, Section 2.C (line 260) states `TTSClientProtocol.synthesize_stream` guarantees 16kHz linear PCM, requiring internal normalization inside each adapter.
   * **Proposed Correction:**
     - Resolve the contradiction: mandate that all TTS adapters normalize internally before yielding chunks, so that `TTSClientProtocol` maintains a single strict contract (16kHz mono `pcm_s16le`).

7. **Singleton Orchestrator Concurrency Race on `set_providers`**
   * **Affected Scope:** Lines 568–574 (Items 25 & 26), `app/main.py` lines 61–72, `app/api/websocket_endpoint.py` lines 18–20
   * **Discrepancy Description & Rationale:**
     - Item 25 adds `set_providers(llm, tts)` to `VoiceRAGOrchestrator`, and Item 26 has `websocket_endpoint.py` parse `SET_PROVIDER` frames to reconfigure providers.
     - If Client A sends a `SET_PROVIDER` WebSocket control frame switching LLM to Gemini, invoking `orchestrator.set_providers(...)` directly mutates the shared singleton instance, silently hijacking the LLM provider for concurrent Client B.
   * **Proposed Correction:**
     - Update Item 25 and Item 26: `voice_orchestrator.process_voice_turn` should accept optional session-scoped provider overrides (`llm: Optional[LLMClientProtocol] = None`, `tts: Optional[TTSClientProtocol] = None`), or `voice_websocket` should maintain session-scoped adapter instances passed to each turn.

8. **Neglect of `indic_tts` Dual-Tier Voice Routing in Orchestrator Refactor**
   * **Affected Scope:** Lines 568–570 (Item 25), `app/services/voice_orchestrator.py` lines 69–75, 173–178
   * **Discrepancy Description & Rationale:**
     - In `VoiceRAGOrchestrator` lines 173–178, speech synthesis routes through a dual-tier TTS mechanism: Devanagari sentences route to `self.indic_tts`.
     - Item 25 only specifies `set_providers(llm, tts)`. It does not specify whether `indic_tts` is updated, whether `indic_tts` is replaced by an Indic-aware provider (e.g. Sarvam Bulbul), or how `FailoverTTSAdapter` interacts with `indic_tts`.
   * **Proposed Correction:**
     - Expand Item 25's action to: `set_providers(llm, tts, indic_tts=None)`. Clarify how `TTSProviderFactory` instantiates both default and Indic-specialized synthesis adapters.

9. **Configuration Naming Drift and Duplicate Settings Declarations**
   * **Affected Scope:** Lines 506–507 (Item 2), Lines 401–438 (Section 7), `app/core/config.py` lines 26–47, `tests/test_multilingual.py` line 21
   * **Discrepancy Description & Rationale:**
     - Item 2 lists `GEMINI_API_KEY`, `GEMINI_MODEL`, and `SARVAM_API_KEY` as new keys to add; they are already defined in `app/core/config.py`.
     - Section 7 defines `EDGE_VOICE_HI: str = "hi-IN-SwaraNeural"`, whereas `app/core/config.py` line 47 defines `EDGE_TTS_INDIC_VOICE: str = "hi-IN-SwaraNeural"` (actively referenced in `main.py` and asserted in `tests/test_multilingual.py`).
     - Line 43 of `config.py` already defines `TTS_PROVIDER: str = "edge"`. The plan introduces `ACTIVE_TTS_PROVIDER`, creating redundant and conflicting settings.
   * **Proposed Correction:**
     - Distinguish between existing keys (`GEMINI_API_KEY`, `SARVAM_API_KEY`, `TTS_PROVIDER`) and genuinely new keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`).
     - Preserve `EDGE_TTS_INDIC_VOICE` (or define `EDGE_VOICE_HI = EDGE_TTS_INDIC_VOICE` as an alias).

10. **Method Name (`start` vs `connect`) & Event Object Contract Mismatch in STT Gateway**
    * **Affected Scope:** Lines 209–218, Lines 502–504, Lines 571–574, `app/adapters/stt_deepgram.py`, `app/api/websocket_endpoint.py`
    * **Discrepancy Description & Rationale:**
      - In `STTClientProtocol`, the initialization method is defined as `async def connect(self) -> None:`. In `DeepgramStreamSession`, the method is named `start()`. `app/api/websocket_endpoint.py` and tests invoke `await session.start()`.
      - `STTClientProtocol.receive_transcripts()` yields `STTTranscriptEvent` (Pydantic model), while `websocket_endpoint.py` currently parses events as dictionary lookups (`event.get("type")`), which will raise `AttributeError`.
    * **Proposed Correction:**
      - In `STTClientProtocol`, retain `start()` as an alias for `connect()`.
      - In Item 26, update `stt_event_listener` to support both attribute access and dictionary lookups (`getattr(event, "type", None) or event.get("type")`).

---

### 🟢 Nits

11. **Code Reuse Opportunity for Local Ollama LLM Adapter**
    * `local_ollama.py` can directly subclass or alias `OpenAILLMAdapter` initialized with `base_url=settings.LOCAL_LLM_URL`.

12. **Telemetry Attribute Name Mismatch in LLM Protocol**
    * `VoiceRAGOrchestrator` logs `getattr(self.llm, "model", "default")`, while `LLMClientProtocol` defines `model_name`. Expose `model` as an alias property of `model_name`.
