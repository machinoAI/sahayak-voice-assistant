# Stage 7: Critic Review Report

**Target Document:** `docs/designs/multi_provider_architecture.md` (Lines 1–495)  
**Auditors:** egm-structural, egm-style, egm-design  
**Date:** 2026-11-20

---

## Structural & Layout Audit (egm-structural)

### Major Findings

1. **Dataflow Break & Orphan Nodes in Mermaid Diagram**
   * **Affected Scope:** Lines 173–184
   * **Critique:** STT providers (`STT_DG`, `STT_GROQ`, etc.) receive from `STT_FACT` but have no outgoing edges into the orchestrator `VO` or endpoint `EP`. In addition, `TTS_DG` (Deepgram Aura) is an orphan node not connected to the audio normalizer `NORM` or `EP`.
   * **Recommendation:** Connect STT provider outputs into `EP` / `VO` and link `TTS_DG` to `NORM` or `EP`.

2. **Interface Contract Contradiction: Goals vs. Technical Plan**
   * **Affected Scope:** Line 44 vs. Lines 203–224
   * **Critique:** Line 44 specifies `stream_audio_frames(audio_generator)` while Section 2.A defines `send_audio(chunk)` and `receive_transcripts()`.
   * **Recommendation:** Standardize on the decoupled `send_audio` / `receive_transcripts` contract in both Goals and Section 2.

### Minor / Nit Findings

3. **LaTeX Math in Heading Slugs & Body Text**
   * **Affected Scope:** Line 97, Line 360
   * **Critique:** `#### Client $\to$ Server Frame: SET_PROVIDER` breaks Markdown anchor link generation.
   * **Recommendation:** Replace with plain text arrow `#### Client -> Server Frame: SET_PROVIDER` and use `< 1000ms` in prose.

4. **Inconsistent Delimiters & Colons**
   * **Affected Scope:** Line 9, Lines 335, 373
   * **Critique:** Line 9 uses an 80-hyphen rule instead of `---`. Subheadings `#### Failover Rules:` contain trailing colons inconsistent with other headings.
   * **Recommendation:** Standardize horizontal rule to `---` and remove terminal colons from subheadings.

---

## Technical Style & Prose Audit (egm-style)

### Major Findings: Uncalibrated Claims

1. **Uncalibrated 99.99% Availability Claim**
   * **Affected Scope:** Line 302
   * **Critique:** Stating in-process adapters "guarantee 99.99% availability" outruns operational modeling (no multi-region topology or DR).
   * **Recommendation:** Replace with `"To prevent runtime session termination from upstream rate limits or transient errors..."`

2. **Uncalibrated "Zero-Overhead" Execution Claim**
   * **Affected Scope:** Line 454
   * **Critique:** Python async generators and protocol dispatch have non-zero runtime overhead.
   * **Recommendation:** Replace with `"Custom pure-Python typing.Protocol implementations minimize runtime execution overhead..."`

3. **Uncalibrated Audio Playback Guarantee**
   * **Affected Scope:** Line 492
   * **Critique:** Claiming 16kHz linear PCM "guarantees clean, gapless audio playback" ignores network jitter or buffer underruns.
   * **Recommendation:** Replace with `"Delivering standardized 16kHz linear PCM eliminates browser-side audio decoding inconsistencies..."`

4. **Self-Contradictory Protocol Docstring**
   * **Affected Scope:** Lines 260–261
   * **Critique:** Asserts output is "guaranteed to be 16kHz linear PCM (or raw MP3 handled via normalization)".
   * **Recommendation:** Clarify docstring: `"Yields synthesized audio chunks for a single sentence or clause in 16kHz mono linear PCM (or provider-native audio prior to downstream normalization)."`

### Superlatives & Terminology Neutralization

5. **Strip Promotional Adjectives & Marketing Jargon**
   * **Affected Scope:** Lines 15, 19, 22, 55, 61, 62, 70, 109, 112, 152
   * **Critique:** Remove vendor marketing acronyms ("LPU"), promotional adjectives ("ultra-low latency", "production-grade", "high-performance"), and commercial framing ("zero-cost", "zero external billing").
   * **Recommendation:** Use neutral engineering terms ("Groq API", "low-latency", "commercial cloud", "offline / local profile").

6. **Strip Pejorative Judgments & Decorative Adverbs**
   * **Affected Scope:** Lines 15, 31, 120, 336, 339, 376, 450, 454
   * **Critique:** Remove pejorative characterizations ("ad-hoc", "rigid", "monolithic", "dependency bloat") and decorative adverbs ("cleanly").

---

## Hostile Design & Architecture Audit (egm-design)

### Blockers

1. **Singleton Concurrency Stomp & Cross-Session Race Conditions in Dynamic Provider Switching**
   * **Affected Scope:** Lines 130–135, Lines 356–393 (`voice_orchestrator.py` lines 60–84, 125–149; `websocket_endpoint.py` lines 18–32)
   * **Critique:** `VoiceRAGOrchestrator` is an application-level singleton injected into the API router. It maintains mutable per-turn state (`self.active_generation_task`, `self.active_tts_task`, `self.sentence_queue`, `self.llm`, `self.tts`). If Client A and Client B are concurrently connected, Client B's `SET_PROVIDER` mutates the shared singleton and user barge-in cancels Client A's running generation!
   * **Fix:** Refactor `VoiceRAGOrchestrator` to be connection-scoped or stateless; bind active generation tasks and adapter references strictly to the WebSocket session context.

2. **Contract Invariant Violation: Batch REST Endpoints Masquerading as Streaming STT**
   * **Affected Scope:** Lines 47–53, 145–148, 203–224
   * **Critique:** Groq Whisper and OpenAI Whisper are non-streaming HTTP multipart REST endpoints (`/v1/audio/transcriptions`), not bidirectional streaming WebSockets. They cannot produce real-time interim transcripts without complex local VAD buffering and 400ms–1500ms latency spikes.
   * **Fix:** Separate STT into `StreamingSTTProtocol` (WebSocket engines with interim hypothesis: Deepgram, ElevenLabs Scribe) and `BufferedBatchSTTAdapter` (REST engines with Silero VAD gating), with clear latency trade-offs documented.

3. **Critical-Path Latency Breach: Python-Space MP3 Decoding and Resampling**
   * **Affected Scope:** Line 69, Lines 88–89, Lines 342–354
   * **Critique:** The proposal mentions `pydub` (which spawns `ffmpeg` subprocesses adding 150ms–300ms overhead) and in-memory MP3 chunk decoding on the asyncio event loop. This transcoding latency will breach the sub-1.2s TTFAB budget.
   * **Fix:** Mandate upstream raw PCM negotiation (`pcm_s16le` supported natively by Deepgram Aura, ElevenLabs, OpenAI Audio). For Edge-TTS MP3, use client-negotiated codec streaming (`/ws/voice?codec=mp3`) or a C-extension streaming demuxer with <15ms overhead.

4. **Truncation & Dead Silence on Mid-Stream Failover**
   * **Affected Scope:** Line 87, Lines 338–340
   * **Critique:** Rule 3 states that if failure occurs after >0 tokens have been emitted, failover will not restart to avoid duplicate speech. If the primary LLM disconnects before reaching a sentence boundary, zero audio was dispatched, yet the system drops the turn, producing complete silence.
   * **Fix:** Redefine mid-stream based on dispatched audio: if 0 audio packets were sent, restart on fallback LLM; if partial audio was sent, execute prefix continuation passing completed clauses as assistant history.

### Major Findings

5. **Socket Descriptor & Connection Pool Leaks Across 15 Adapters**
   * **Affected Scope:** Lines 267–299, 401–438
   * **Critique:** Repeated adapter instantiations without shared connection pools cause OS file descriptor exhaustion (`EMFILE`). Eagerly connecting 15 WebSocket adapters causes idle timeout drops and billing quota exhaustion.
   * **Fix:** Implement a centralized `HTTPClientManager` singleton for connection pooling and enforce lazy, on-demand connection for WebSockets.

6. **Acoustic Clashing & Turn Incoherence in Sentence-Level TTS Failover**
   * **Affected Scope:** Lines 301–340
   * **Critique:** If Sentence 1 is spoken by Cartesia (American English) and Sentence 2 fails over to Edge-TTS (Indian English Neerja), the voice abruptly clashes mid-thought.
   * **Fix:** Enforce turn-level provider stickiness and maintain a voice-timbre cross-mapping table with matched pitch/volume normalizations.

7. **Deadlock and Audio Loss Race Condition During `SET_PROVIDER` STT Swap**
   * **Affected Scope:** Line 86, Lines 373–375
   * **Critique:** Awaiting `session.close()` during speech drops in-flight PCM frames in the TCP buffer and severs the active turn.
   * **Fix:** Implement graceful speech boundary handoff: defer swap until `speech_final` or add a 500ms circular pre-roll audio buffer.

8. **Billing DoS Vulnerability via Unvalidated Control Frames**
   * **Affected Scope:** Lines 361–372
   * **Critique:** Arbitrary strings in `SET_PROVIDER` allow malicious clients to force high-cost models (GPT-4o, Claude 3.5 Sonnet) or crash on uncredentialed providers.
   * **Fix:** Enforce strict server-side whitelist validation and session rate limits on control frames.

