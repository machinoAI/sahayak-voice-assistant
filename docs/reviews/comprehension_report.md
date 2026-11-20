# Stage 6: Comprehension Test Report

**Target Document:** `docs/designs/multi_provider_architecture.md`  
**Auditor:** egm-comprehension (Naive Reader Persona)  
**Date:** 2026-11-20

---

# Paraphrase of Proposed Architecture & Intent

The document proposes refactoring the Sahayak streaming Voice RAG pipeline from its current hardcoded, single-vendor implementation (Deepgram Nova-2 for STT, Groq LPU for LLM, and Cartesia Sonic/Edge-TTS for TTS) into a modular, pluggable multi-provider framework. Currently, vendor lock-in creates single points of failure (such as Groq rate limits or Deepgram outages terminating user sessions), limits Indian regional language coverage, prevents runtime model switching, causes audio format mismatches, and impedes local testing without paid credentials.

To resolve this, the architecture establishes standardized asynchronous streaming protocols (`STTClientProtocol`, `LLMClientProtocol`, `TTSClientProtocol`) using Python's `typing.Protocol` and `AsyncGenerator`. A centralized Provider Registry and Factory system manages 4 to 5 production-grade and local providers per tier. Automated multi-tier failover chains with 60-second circuit-breaker cooldowns catch upstream rate limits and transient connection errors without dropping sessions. In addition, an in-memory streaming audio normalization layer resamples varied TTS audio outputs into uniform 16kHz mono linear PCM (`pcm_s16le`), dynamic WebSocket control frames (`SET_PROVIDER`) permit on-the-fly provider switching without socket reconnection, and a zero-cost local development profile (`VOICE_PROFILE=local`) enables testing with Ollama, local Whisper, and Edge-TTS.

---

# Paraphrase of Detailed Implementation Plan

The plan executes the migration across five sequential phases designed to preserve backwards compatibility:
1. **Phase 1 (Core Protocols, Registry & Normalization)**: Formalizes the streaming protocols in `adapters.py`, expands Pydantic environment configurations in `config.py` for 15 provider engines, creates generic provider registries and domain factories in `registry.py`, builds the in-memory audio normalizer in `audio_normalizer.py`, and updates `requirements.txt` with official provider SDKs and `miniaudio`.
2. **Phase 2 (LLM Multi-Provider Suite & Failover)**: Implements concrete LLM adapters for Groq, OpenAI, Anthropic, Gemini, and Ollama/vLLM under `app/adapters/llm/`, and develops `FailoverLLMAdapter` in `failover.py` with 60-second circuit breaker cooldown logic.
3. **Phase 3 (TTS Multi-Provider Suite & Failover)**: Implements concrete TTS streaming adapters for Cartesia, Microsoft Edge-TTS, ElevenLabs, Deepgram Aura, and Sarvam Bulbul under `app/adapters/tts/`, and builds `FailoverTTSAdapter`.
4. **Phase 4 (STT Multi-Provider Suite)**: Implements concrete streaming STT adapters for Deepgram Nova-2, Groq Whisper, ElevenLabs Realtime, OpenAI Whisper, and Sarvam Indic ASR under `app/adapters/stt/`.
5. **Phase 5 (Orchestrator Integration, Gateway Control & Testing)**: Refactors `voice_orchestrator.py` to accept pluggable failover adapters and dynamic provider switching, updates `websocket_endpoint.py` to handle session-scoped STT and `SET_PROVIDER` control frames, adds provider selection dropdowns to the diagnostic UI (`index.html`), implements protocol and failover test suites, and updates documentation.

---

# Comprehension Findings

### 🔴 Blocker

1. **Missing Local Whisper Implementation & Dependency in Implementation Plan**
   * **Affected Scope**: Lines 22, 70, 110–112, Lines 401–438, Lines 514–517, Lines 552–565
   * **Discrepancy Description & Rationale**:
     The document repeatedly promotes a "Zero-Cost Local Development Profile" that allows developers to run without commercial API keys using Ollama, Edge-TTS, and local Whisper (CUJ 4, lines 110–113: *"Server is launched with `VOICE_PROFILE=local` and zero commercial API keys... Pipeline uses local Whisper / mock STT"*).
     However:
     - In Phase 4 (STT Multi-Provider Suite, lines 552–565), all five planned adapters are external commercial cloud services requiring API keys: Deepgram (`deepgram.py`), Groq Whisper (`groq_whisper.py`), ElevenLabs (`elevenlabs.py`), OpenAI/Azure Whisper (`openai_whisper.py`), and Sarvam Indic (`sarvam_indic.py`). There is NO local Whisper or mock STT adapter planned or created.
     - In Phase 1 (`requirements.txt`, lines 514–517), no local Whisper library (such as `faster-whisper` or `whisper.cpp`) is added.
     - In `Settings` (lines 401–438), `VOICE_PROFILE` is not declared as a field in `Settings`, and no configuration exists for a local Whisper model or endpoint.
     A developer attempting to run the system with zero API keys under CUJ 4 cannot run the pipeline because the local STT component does not exist in the design or implementation plan.

---

### 🟡 Major

2. **Protocol Interface Contradiction for `STTClientProtocol`**
   * **Affected Scope**: Line 44 vs. Lines 213–219
   * **Discrepancy Description & Rationale**:
     In Goals (line 44), `STTClientProtocol` is declared as:
     `stream_audio_frames(audio_generator) -> AsyncGenerator[STTTranscriptEvent, None]`
     However, in Section 2 (Component Protocols, lines 213–219), `STTClientProtocol` is defined with two decoupled methods:
     `async def send_audio(self, chunk: bytes) -> None:`
     `async def receive_transcripts(self) -> AsyncGenerator[STTTranscriptEvent, None]:`
     These are incompatible streaming contracts: one passes an input generator into a single method, whereas the other requires the caller to imperatively push audio chunks via `send_audio` and concurrently consume an async generator from `receive_transcripts`. A developer implementing new STT adapters cannot determine which protocol method the orchestrator/endpoint will call.

3. **STT Excluded from Automated Multi-Tier Failover**
   * **Affected Scope**: Line 29, Line 67, Lines 301–340, Lines 408–410, Lines 532–535
   * **Discrepancy Description & Rationale**:
     In "The Problem" (line 29), the document explicitly flags Deepgram outages as a critical risk: *"If Groq encounters API rate limits (HTTP 429) or Deepgram suffers a regional outage, the voice assistant fails completely with unhandled exceptions or hangs."*
     Yet, Section 4 (Automatic Multi-Tier Failover Engine), Section 7 (`Settings`), and Phase 2/3 of the implementation plan only implement failover chains for LLM (`FailoverLLMAdapter`, `LLM_FAILOVER_CHAIN`) and TTS (`FailoverTTSAdapter`, `TTS_FAILOVER_CHAIN`). There is no `FailoverSTTAdapter` and no `STT_FAILOVER_CHAIN`. If Deepgram encounters network failure or an outage, there is no automated fallback. The document does not explain why STT is excluded or how STT outages are handled.

4. **Contradiction and Ambiguity in Mid-Stream Failover ("Sentinel Completion")**
   * **Affected Scope**: Lines 87–88 vs. Lines 338–339
   * **Discrepancy Description & Rationale**:
     In Open Questions (lines 87–88), Question 2 asks: *"For automated LLM failover, if the primary LLM provider drops after emitting partial tokens (e.g., after 5 tokens), should the failover LLM restart token generation from the beginning or append to the existing stream?"*
     However, Section 4, Rule 3 (lines 338–339) asserts: *"If a failure occurs mid-stream (after >0 tokens or audio bytes have been delivered to the client), failover does not restart from token 0 (to avoid duplicating speech); instead, the error boundary logs the incident and sentinel completion drains cleanly."*
     This is conflicting and vague:
     - Question 2 is listed as an unresolved open question, but Rule 3 states a concrete non-restarting policy.
     - Rule 3 introduces the vague term *"sentinel completion drains cleanly"*. It does not specify what the sentinel is, whether a truncation message is played to the user, or how half-generated sentences are handled by the downstream TTS engine and sentence splitter.

5. **Incomplete / Ambiguous `SET_PROVIDER` Schema for Multi-Tier Model Switching**
   * **Affected Scope**: Lines 361–370, Lines 387–391
   * **Discrepancy Description & Rationale**:
     The `SET_PROVIDER` frame defines top-level flat fields:
     `{"event": "SET_PROVIDER", "stt": "groq_whisper", "llm": "gemini", "tts": "elevenlabs", "model": "gemini-2.0-flash", "voice": "rachel", "language": "en"}`.
     Both STT and LLM providers require specific model identifiers (e.g., STT has `whisper-large-v3` vs `whisper-large-v3-turbo`; LLM has `gemini-2.0-flash` vs `gemini-1.5-flash`). Having a single generic `"model"` parameter creates ambiguity as to which tier it applies to. Furthermore, the confirmation frame emits a structured dictionary (`"models": {"llm": "gemini-2.0-flash", "tts_voice": "rachel"}`), which does not mirror the flat structure of the request. Finally, the document states the server validates credentials upon receiving this frame (line 374), but never specifies the error message frame schema returned if a requested provider is invalid or uncredentialed.

6. **Unspecified Client MP3 Capability Advertisement Mechanism**
   * **Affected Scope**: Lines 353–354
   * **Discrepancy Description & Rationale**:
     Section 5 states: *"If the connected client explicitly advertises MP3 decoding capability, normalized frames or passthrough MP3 chunks are delivered without transcoding overhead."*
     The document never explains *how* the client advertises this capability (e.g., via WebSocket query parameters during handshake, a dedicated client greeting frame, or inside `SET_PROVIDER`). A reader implementing the client or endpoint has no contract to follow.

7. **Missing Credentials and Discarded Indic Providers (Bhashini and Azure Neural TTS)**
   * **Affected Scope**: Line 31, Lines 52–53, 65, Lines 412–438, Lines 548–550, 563–565
   * **Discrepancy Description & Rationale**:
     In "The Problem" (line 31) and "Goals" (lines 52–53, 65), the document emphasizes integrating Indic models, specifically naming Bhashini and Azure Neural TTS / Azure Speech.
     However:
     - Section 7 (`Settings`) contains zero configuration settings or API keys for Bhashini or Azure (`AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `BHASHINI_API_KEY` are absent).
     - In the Detailed Implementation Plan (Phases 3 and 4), Bhashini and Azure Neural TTS have completely disappeared; only Sarvam AI is scheduled. A reader cannot tell if Bhashini and Azure were dropped or simply forgotten.

8. **Undefined Project-Specific Term: "OATS semantic router"**
   * **Affected Scope**: Line 80
   * **Discrepancy Description & Rationale**:
     Line 80 states: *"The in-process OATS semantic router and the Qdrant hybrid vector store remain unchanged."*
     While Qdrant is an industry-standard vector database, "OATS semantic router" is specific to this project. The document neither expands the acronym, defines its role in the pipeline, nor links to internal or external documentation.

---

### 🔵 Nit

9. **Frontend Provider Discovery Contract Missing**
   * **Affected Scope**: Lines 574–576
   * **Discrepancy Description & Rationale**:
     Phase 5, Item 27 calls for adding dropdown selectors to `app/static/index.html` to dispatch `SET_PROVIDER`. The document does not describe how the frontend retrieves the available provider list (e.g., via a REST endpoint `GET /api/providers`, an initial WebSocket handshake event, or static hardcoding in the HTML).

10. **Undefined Acronyms and Technical Terms**
    * **Affected Scope**: Line 15, Line 148, Line 199, Line 317, Line 525
    * **Discrepancy Description & Rationale**:
      - **TTFT** (lines 317, 525): Used in the sequence diagram without definition (presumably Time-to-First-Token).
      - **LPU** (lines 15, 55, 152, 310, 523): Used in Groq references without definition (presumably Language Processing Unit).
      - **ASR** (line 148): Used in the Mermaid diagram without definition (presumably Automated Speech Recognition).
      - **`speech_final`** (line 199): Included as a boolean attribute on `STTTranscriptEvent` alongside `is_final` and `type`, but its specific behavior, how non-Deepgram providers compute it, and whether it triggers the turn are never explained.

11. **Registry vs. Factory Terminology Inconsistency**
    * **Affected Scope**: Line 66, Lines 272–298, Lines 508–510
    * **Discrepancy Description & Rationale**:
      Line 66 refers to creating `STTProviderRegistry`, `LLMProviderRegistry`, and `TTSProviderRegistry` supporting "health checks". Section 3 and Phase 1 only define a generic `ProviderRegistry[T]` and factories named `STTProviderFactory`, `LLMProviderFactory`, and `TTSProviderFactory`. Neither the code snippet nor the text provides any health check interface or logic.
