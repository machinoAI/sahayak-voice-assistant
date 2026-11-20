# Consolidated Review Report: Pluggable Multi-Provider Architecture

**Target Document:** [`docs/designs/multi_provider_architecture.md`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/docs/designs/multi_provider_architecture.md)  
**Date:** 2026-11-20  
**Status:** Review Complete (Actionable Synthesis & Traceability Matrix)

---

## 1. Executive Summary

A comprehensive multi-persona Goldfish review was executed across all five stages of the review protocol:
1. **Stage 5 (Initial Zoom Out)**: Skeptical Architect (`egm-zoom-out`) & Inventive Catalyst (`egm-inventive-catalyst`).
2. **Stage 6 (Comprehension Test)**: Naive Reader (`egm-comprehension`).
3. **Stage 7 (Critic Review)**: Hostile Design Critic (`egm-design`), Document Architect (`egm-structural`), and Copy Editor (`egm-style`).
4. **Stage 8 (Intermediate Zoom Out)**: Skeptical Architect (`egm-zoom-out`).
5. **Stage 9 (Implementation Readiness Test)**: Pragmatic Tech Lead (`egm-implementation-readiness`) and Codebase Details Auditor (`egm-codebase-details`).

### Verdict
**CHANGES REQUIRED BEFORE IMPLEMENTATION**. While the core objective of decoupling the pipeline from single vendors is sound, the current design contains **7 Blocker findings** (concurrency race conditions, protocol mismatches for batch REST models, latency budget breaches via server-side transcoding, unshimmed migrations that break existing tests, and missing wiring entrypoints) along with **10 Major architectural risks**.

---

## 2. Prioritized Consolidated Action Items

### 🔴 Blockers

#### Action 1: Decouple Shared Orchestrator Singleton to Connection-Scoped Session State
* **Origin:** `egm-design` (Finding 1), `egm-codebase-details` (Finding 4)
* **Problem:** `VoiceRAGOrchestrator` is an application-level singleton instantiated in `app/main.py`. It holds mutable per-turn state (`self.active_generation_task`, `self.active_tts_task`, `self.sentence_queue`, `self.llm`, `self.tts`). Allowing clients to call `SET_PROVIDER` or trigger user barge-in cancels running tasks and mutates providers for all concurrent users.
* **Resolution:** 
  1. Keep shared stateless resources (VectorDB, Semantic Router, HTTP Client Pools) as singletons.
  2. Instantiate a lightweight, connection-scoped `VoiceSessionState` or pass per-turn provider overrides (`llm`, `tts`, `indic_tts`) directly into `process_voice_turn()` from `websocket_endpoint.py`.
  3. Ensure barge-in and cancellation tokens are strictly bound to the individual WebSocket connection.

#### Action 2: Bifurcate Streaming STT from Batch REST Transcription
* **Origin:** `egm-design` (Finding 2), `egm-implementation-readiness` (Finding 5)
* **Problem:** Groq Whisper (`whisper-large-v3-turbo`) and OpenAI Whisper are non-streaming HTTP multipart REST endpoints (`/v1/audio/transcriptions`). They cannot satisfy a real-time duplex WebSocket contract (`send_audio` / `receive_transcripts`) without an internal VAD chunker and 400ms–1500ms turnaround delays.
* **Resolution:**
  1. Define `StreamingSTTProtocol` exclusively for genuine bidirectional streaming WebSockets (Deepgram Nova-2, ElevenLabs Realtime Scribe, Azure Speech).
  2. Define `BufferedBatchSTTAdapter` for REST endpoints with an internal `AudioBufferAccumulator` and Silero VAD gating, explicitly documenting the latency trade-off.

#### Action 3: Eliminate Server-Side Audio Transcoding on the Critical Path
* **Origin:** `egm-design` (Finding 3), `egm-zoom-out` (Finding 5), `egm-inventive-catalyst` (Finding 2)
* **Problem:** Transcoding MP3 frames and resampling 24kHz streams to 16kHz PCM using Python/miniaudio on the server adds 80ms–250ms of CPU overhead and bit-reservoir frame jitter, breaching the <1.2s TTFAB budget. Furthermore, `app/static/index.html` already supports dual-format decoding natively.
* **Resolution:**
  1. Negotiate upstream raw 16kHz PCM (`pcm_s16le`) where supported (Deepgram Aura, ElevenLabs, OpenAI Audio).
  2. For Edge-TTS MP3, deliver native MP3 chunks directly to the client's existing dual-format Web Audio player.
  3. Delete `app/adapters/audio_normalizer.py` and drop `miniaudio`/`pydub` from the server critical path.

#### Action 4: Fix Truncation & Silence on Mid-Stream Failover (Prefix Continuation)
* **Origin:** `egm-design` (Finding 4), `egm-inventive-catalyst` (Finding 1), `egm-comprehension` (Finding 4), `egm-zoom-out` (Finding 3)
* **Problem:** Rule 3 specifies that if an LLM crashes after emitting >0 tokens, failover does not restart to avoid duplicate speech. If the failure occurs before sentence boundary dispatch, zero audio was played and the turn terminates in complete silence.
* **Resolution:**
  1. If zero audio chunks have been dispatched to the client, failover **must** restart generation on the secondary provider.
  2. If prior sentences were already synthesized and spoken, pass completed sentences as assistant history (`messages=[..., {"role": "assistant", "content": completed_sentences}]`) so the fallback LLM completes the response seamlessly without repetition.

#### Action 5: Add `app/main.py` Wiring & Backward-Compatible Adapter Re-Export Shims
* **Origin:** `egm-codebase-details` (Findings 1 & 2), `egm-implementation-readiness` (Finding 1)
* **Problem:** `app/main.py` directly instantiates concrete adapters and is omitted from the plan. Moving files to subpackages (`stt/`, `llm/`, `tts/`) without shims immediately breaks `main.py` and `tests/test_adapters.py` with `ModuleNotFoundError`.
* **Resolution:**
  1. Add an explicit task in Phase 5: **`app/main.py` (Modify)** to bootstrap adapters and failover chains via factories.
  2. Retain legacy adapter paths (`app/adapters/llm_groq.py`, `app/adapters/tts_cartesia.py`, `app/adapters/tts_edge.py`, `app/adapters/stt_deepgram.py`) as deprecated re-export shims during all migration phases.

#### Action 6: Complete the Zero-Cost Local Profile (Local Whisper & Settings)
* **Origin:** `egm-comprehension` (Finding 1), `egm-implementation-readiness` (Finding 2)
* **Problem:** CUJ 4 promises an offline local development run with Ollama, Edge-TTS, and local Whisper, but Phase 4 implements 5 external cloud STT services with zero local Whisper adapter, and `VOICE_PROFILE` is missing from `Settings`.
* **Resolution:**
  1. Add `LocalWhisperSTTAdapter` (or mock streaming STT) in Phase 4.
  2. Add `VOICE_PROFILE: str = "cloud"` and local model settings to `app/core/config.py`.

#### Action 7: Resolve Python 3.13 Dependencies & Specify Exact SDK Versions
* **Origin:** `egm-implementation-readiness` (Finding 2), `egm-codebase-details` (Finding 7)
* **Problem:** Python 3.13 removed `audioop`. Ambiguous `(or google-generativeai)` conflicts with installed `google-genai`. `elevenlabs` is missing from requirements.
* **Resolution:**
  1. Enforce `google-genai>=0.1.0` (already installed).
  2. Add `elevenlabs>=1.0.0` and `soxr>=0.3.7` (with `audioop-lts` backport for Python 3.13).

---

### 🟡 Major Findings

#### Action 8: Prune Speculative Scope to Lean 2–3 Provider Architecture (YAGNI)
* **Origin:** `egm-zoom-out` (Findings 1 & 2)
* **Problem:** Building 15 adapters simultaneously adds combinatorial maintenance and testing drag.
* **Resolution:** Consolidate LLMs around an `OpenAICompatibleLLMAdapter` that unifies Groq, OpenAI, Gemini, and Ollama/vLLM. Constrain initial STT to Deepgram + Sarvam/Local Whisper, and TTS to Cartesia + Edge-TTS + ElevenLabs.

#### Action 9: Simplify Connection-Time Provider Selection vs. In-Flight Hot-Swapping
* **Origin:** `egm-zoom-out` (Finding 4), `egm-design` (Finding 7), `egm-inventive-catalyst` (Finding 3)
* **Problem:** Mid-turn WebSocket `SET_PROVIDER` drops TCP socket audio buffers and triggers race conditions during speech.
* **Resolution:** Allow provider selection via WebSocket query parameters (`/ws/voice?llm=ollama&tts=edge`). When changed in the UI, cleanly re-open the WebSocket connection (~30ms) or defer swap to the turn epoch boundary.

#### Action 10: Include STT in Failover Topology
* **Origin:** `egm-comprehension` (Finding 3), `egm-design` (Finding 7)
* **Problem:** Deepgram outages are flagged as a primary risk, yet failover chains are only implemented for LLM and TTS.
* **Resolution:** Introduce `FailoverSTTAdapter` or gateway-level STT fallback with pre-roll buffering.

#### Action 11: Enforce Turn-Level TTS Stickiness & Timbre Mapping
* **Origin:** `egm-design` (Finding 6), `egm-inventive-catalyst` (Finding 4)
* **Problem:** Falling back from Cartesia to Edge-TTS between Sentence 1 and Sentence 2 mid-turn clashes American and Indian English accents.
* **Resolution:** Enforce turn-level provider stickiness (once fallback occurs, subsequent sentences stay on the fallback) and maintain voice-timbre cross-mapping in `config.py`.

#### Action 12: Manage HTTP Client Pools & File Descriptors
* **Origin:** `egm-design` (Finding 5)
* **Problem:** Unpooled adapter instantiations risk OS file descriptor exhaustion (`EMFILE`).
* **Resolution:** Implement a shared `HTTPClientManager` singleton for connection pooling and enforce lazy WebSocket initialization.

#### Action 13: Whitelist Validation for Control Frames (Prevent Billing DoS)
* **Origin:** `egm-design` (Finding 8), `egm-comprehension` (Finding 5)
* **Problem:** Unauthenticated clients can force expensive models (GPT-4o) via `SET_PROVIDER`.
* **Resolution:** Validate requested models against a strict server-side whitelist and return a structured `PROVIDER_ERROR` frame if unauthorized.

#### Action 14: Update `indic_tts` Dual-Tier Voice Routing in Orchestrator
* **Origin:** `egm-codebase-details` (Finding 5)
* **Problem:** The existing dual-tier routing for Devanagari script is ignored during runtime provider updates.
* **Resolution:** Ensure `set_providers(llm, tts, indic_tts=None)` updates both default and Indic-specialized synthesis adapters.

#### Action 15: Reconcile Configuration Naming & Existing Settings
* **Origin:** `egm-codebase-details` (Finding 6), `egm-comprehension` (Finding 7)
* **Problem:** `EDGE_VOICE_HI` conflicts with existing `EDGE_TTS_INDIC_VOICE` (asserted in tests); `ACTIVE_TTS_PROVIDER` conflicts with `TTS_PROVIDER`.
* **Resolution:** Retain `EDGE_TTS_INDIC_VOICE` and preserve `TTS_PROVIDER` aliases in `config.py`.

#### Action 16: Standardize Protocol Signatures & Gateway Event Access
* **Origin:** `egm-comprehension` (Finding 2), `egm-codebase-details` (Finding 3), `egm-structural` (Finding 1.2)
* **Problem:** `stream_audio_frames` vs `send_audio`/`receive_transcripts`; `start()` vs `connect()`; Pydantic `STTTranscriptEvent` breaking `event.get("type")` in `websocket_endpoint.py`.
* **Resolution:** Standardize on `send_audio` / `receive_transcripts`, alias `connect()` to `start()`, and update gateway event parsing to support both attribute access and `.get()`.

#### Action 17: Colocate Unit Tests & Topological Reordering
* **Origin:** `egm-implementation-readiness` (Findings 1 & 5)
* **Problem:** Tests are deferred to Phase 5, and Phase 1 breaks contracts before Phase 5 updates callers.
* **Resolution:** Move dependencies to Step 1, maintain backward-compatible shims, and embed test tasks directly within Phases 1–4.

---

### 🟢 Nits

#### Action 18: Neutralize Promotional Jargon, Superlatives & Uncalibrated Claims
* **Origin:** `egm-style` (Findings 1–12)
* **Resolution:** Replace uncalibrated four-nines SLA claims, remove "LPU", "ultra-low latency", and "zero-cost" sales framing, and strip redundant meta-commentary prefixes.

#### Action 19: Fix Mermaid Architecture Diagram & Delimiters
* **Origin:** `egm-structural` (Findings 1.1, 2.1–2.4)
* **Resolution:** Connect STT provider outputs to `EP`/`VO`, connect `TTS_DG` to `NORM`/`EP`, replace LaTeX math in headings, and standardize delimiters to `---`.

#### Action 20: Subclass `OpenAILLMAdapter` for Local Ollama & Telemetry Field Alignment
* **Origin:** `egm-codebase-details` (Findings 8 & 9)
* **Resolution:** Subclass `OpenAILLMAdapter` for `LocalOllamaLLMAdapter` and alias `model_name` as `model`.

---

## 3. Comprehensive Traceability Matrix

| Consolidated Action Item | Priority | Originating Reviewers & Findings | Target Affected Files |
| :--- | :---: | :--- | :--- |
| **Action 1: Session-Scoped Orchestrator State** | 🔴 Blocker | `egm-design` (F1), `egm-codebase-details` (F4) | `voice_orchestrator.py`, `websocket_endpoint.py` |
| **Action 2: Bifurcate Streaming STT from Batch REST** | 🔴 Blocker | `egm-design` (F2), `egm-implementation-readiness` (F5) | `adapters.py`, `app/adapters/stt/` |
| **Action 3: Eliminate Server-Side MP3 Transcoding** | 🔴 Blocker | `egm-design` (F3), `egm-zoom-out` (F5), `egm-inventive-catalyst` (F2) | `adapters.py`, `audio_normalizer.py`, `index.html` |
| **Action 4: Fix Truncation & Silence on Mid-Stream Failover** | 🔴 Blocker | `egm-design` (F4), `egm-inventive-catalyst` (F1), `egm-comprehension` (F4) | `failover.py`, `voice_orchestrator.py` |
| **Action 5: Add `app/main.py` Wiring & Adapter Shims** | 🔴 Blocker | `egm-codebase-details` (F1, F2), `egm-implementation-readiness` (F1) | `app/main.py`, `app/adapters/*.py`, `tests/` |
| **Action 6: Complete Zero-Cost Local Profile** | 🔴 Blocker | `egm-comprehension` (F1), `egm-implementation-readiness` (F2) | `app/adapters/stt/`, `config.py` |
| **Action 7: Python 3.13 & Dependency Specifications** | 🔴 Blocker | `egm-implementation-readiness` (F2), `egm-codebase-details` (F7) | `requirements.txt` |
| **Action 8: Prune 15-Provider Scope (YAGNI)** | 🟡 Major | `egm-zoom-out` (F1, F2) | `app/adapters/llm/`, `app/adapters/` |
| **Action 9: Simplify Connection-Time Provider Selection** | 🟡 Major | `egm-zoom-out` (F4), `egm-design` (F7), `egm-inventive-catalyst` (F3) | `websocket_endpoint.py`, `index.html` |
| **Action 10: Include STT in Failover Topology** | 🟡 Major | `egm-comprehension` (F3), `egm-design` (F7) | `failover.py`, `websocket_endpoint.py` |
| **Action 11: Turn-Level TTS Stickiness & Timbre Mapping** | 🟡 Major | `egm-design` (F6), `egm-inventive-catalyst` (F4) | `failover.py`, `config.py` |
| **Action 12: Manage HTTP Client Pools & FDs** | 🟡 Major | `egm-design` (F5) | `app/adapters/base.py` |
| **Action 13: Whitelist Validation for Control Frames** | 🟡 Major | `egm-design` (F8), `egm-comprehension` (F5) | `websocket_endpoint.py` |
| **Action 14: Update `indic_tts` Dual-Tier Routing** | 🟡 Major | `egm-codebase-details` (F5) | `voice_orchestrator.py` |
| **Action 15: Reconcile Configuration Naming** | 🟡 Major | `egm-codebase-details` (F6), `egm-comprehension` (F7) | `config.py` |
| **Action 16: Standardize Protocol Signatures & Gateway** | 🟡 Major | `egm-comprehension` (F2), `egm-codebase-details` (F3), `egm-structural` (F1.2) | `adapters.py`, `websocket_endpoint.py` |
| **Action 17: Colocate Unit Tests & Topological Order** | 🟡 Major | `egm-implementation-readiness` (F1, F5) | `tests/`, `design_draft.md` |
| **Action 18: Neutralize Promotional Jargon & Claims** | 🟢 Nit | `egm-style` (F1–F12) | `docs/designs/multi_provider_architecture.md` |
| **Action 19: Fix Mermaid Diagram & Delimiters** | 🟢 Nit | `egm-structural` (F1.1, F2.1–F2.4) | `docs/designs/multi_provider_architecture.md` |
| **Action 20: Subclass `OpenAILLMAdapter` for Ollama** | 🟢 Nit | `egm-codebase-details` (F8, F9) | `app/adapters/llm/` |
