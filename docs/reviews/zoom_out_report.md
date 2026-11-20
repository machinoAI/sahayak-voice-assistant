# Stage 5: Initial Zoom Out Review Report

**Target Document:** `docs/designs/multi_provider_architecture.md` (Full File, Lines 1–591)  
**Auditors:** egm-zoom-out (Skeptical Architect), egm-inventive-catalyst (Inventive Catalyst)  
**Date:** 2026-11-20

---

## Skeptical Architect Review (egm-zoom-out)

### Blocker Findings

1. **Speculative Proliferation of 15 Provider Adapters (YAGNI)**
   * **Affected Scope:** Lines 47–65, 143–165, 518–565
   * **Critique:** Implementing 15 distinct provider adapters (5 STT, 5 LLM, 5 TTS) in a single leap creates enormous operational drag, credential configuration overhead, and an unmaintainable combinatorial testing matrix. The project requirements only need high-speed cloud execution, zero-cost local development, and Indic regional dialect support.
   * **Recommendation:** Constrain initial execution to a lean 2-to-3 engine model per tier:
     - **STT:** Deepgram Nova-2 (primary streaming cloud) + Sarvam AI / local Whisper (Indic & local fallback).
     - **LLM:** Groq LPU (primary fast cloud) + OpenAI-compatible endpoint (covers Ollama, vLLM, OpenAI, and Gemini).
     - **TTS:** Cartesia Sonic (primary low-latency PCM) + Microsoft Edge-TTS (already implemented, zero-cost, Indian English & Devanagari Hindi).

### Major Findings

2. **Reinventing LLM Abstractions Instead of Leveraging OpenAI API Compatibility**
   * **Affected Scope:** Lines 54–59, 151–157, 518–531
   * **Critique:** Groq, OpenAI, Ollama, vLLM, and Google Gemini all support the standard OpenAI Chat Completions REST/SSE protocol (`/v1/chat/completions`). Creating 5 separate adapter modules is redundant boilerplate.
   * **Recommendation:** Consolidate Groq, OpenAI, Ollama, and vLLM into a single `OpenAICompatibleLLMAdapter` (~40 lines of code) parameterized by `base_url`, `api_key`, and `model_name`.

3. **Cascading Failover Chains Violate Sub-1.2s TTFAB Latency Budget**
   * **Affected Scope:** Lines 67, 301–340, 408–410, 532–535
   * **Critique:** Cascading 3 sequential providers (`Groq -> Gemini -> OpenAI`) on the synchronous critical path causes 2.5s–4.0s delays when the primary times out. Mid-stream non-restart rules cause truncated speech.
   * **Recommendation:** Eliminate multi-hop tertiary failovers. Fail fast within a 500ms timeout to a single pre-warmed secondary, and emit a synthesized fallback message on mid-stream failure.

4. **In-Flight Dynamic Provider Hot-Swapping (`SET_PROVIDER`) is Unnecessary Complexity**
   * **Affected Scope:** Lines 21, 68, 85–86, 99–103, 356–393, 566–576
   * **Critique:** Hot-swapping STT, LLM, and TTS mid-session via WebSocket frames introduces race conditions and state machine complexity during active speech. Real users configure providers at session start.
   * **Recommendation:** Negotiate provider selection during the initial WebSocket handshake (e.g. `/ws/voice?llm=ollama&tts=edge`). If the user toggles a dropdown in the UI, cleanly close and re-open the WebSocket connection (~30ms overhead).

5. **Redundant Audio Normalization Engine and Native C-Extension (`miniaudio`)**
   * **Affected Scope:** Lines 37, 69, 88–89, 140, 342–353, 511–516
   * **Critique:** The client UI (`app/static/index.html`) already supports dual-format playback (detecting and decoding both raw linear PCM and MP3 frames). Server-side transcoding adds CPU contention and requires native C-extensions.
   * **Recommendation:** Drop `miniaudio` and delete `audio_normalizer.py`. Let TTS providers emit native PCM or MP3, and allow the client's dual-format audio decoder to handle playback.

---

## Inventive Catalyst Review (egm-inventive-catalyst)

### TRIZ Contradictions & Inventive Solutions

1. **Serial Cascading Failover vs. Sub-1.2s TTFAB SLA (Severity: Blocker)**
   * **Contradiction:** High availability via fallback chains vs. strict voice turnaround budget.
   * **TRIZ Principle:** *Preliminary Action (Pattern 3)* + *Dynamics (Pattern 6)*.
   * **Resolution:** Use hedged speculative requests. If primary doesn't emit a valid first token within `p95 + 100ms`, dispatch a speculative request to the secondary. First token to arrive wins; the slower request is cancelled.

2. **Server-Side MP3 Chunk Transcoding vs. Audio Purity (Severity: Blocker)**
   * **Contradiction:** Format standardization vs. CPU transcoding jitter and boundary click artifacts.
   * **TRIZ Principle:** *Inversion (Pattern 5)* + *Self-Service (Pattern 9)*.
   * **Resolution:** Invert format enforcement from server transcoding to upstream protocol negotiation (requesting `pcm_16000` from Deepgram, ElevenLabs, OpenAI). For Edge-TTS MP3, use syncword-aligned boundary demuxing or client-side playback.

3. **Immediate Hot-Swapping vs. Turn State Integrity (Severity: Major)**
   * **Contradiction:** Operational reconfigurability vs. in-flight audio/transcript continuity.
   * **TRIZ Principle:** *Segmentation (Pattern 1)* + *Intermediary (Pattern 8)*.
   * **Resolution:** Monotonic Epoch-based turn fencing. If pipeline is active, pre-initialize the new provider for Epoch $N+1$ while Epoch $N$ completes through the existing provider.

4. **English Abstractions vs. Indic Sovereign Linguistic Realities (Severity: Major)**
   * **Contradiction:** Uniform interfaces vs. multi-byte UTF-8 token splitting and Indic punctuation.
   * **TRIZ Principle:** *Dynamics (Pattern 6)* + *Beforehand Cushioning (Pattern 4)*.
   * **Resolution:** Extend provider metadata with a linguistic capability matrix (filtering non-Indic voices). Add multi-byte UTF-8 stream reassembly and support Indic sentence delimiters (`।`, `॥`).
