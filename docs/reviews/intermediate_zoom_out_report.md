# Stage 8: Intermediate Zoom Out Review Report

**Target Document:** `docs/designs/multi_provider_architecture.md` (Full File, Lines 1–591)  
**Auditor:** egm-zoom-out (Skeptical Architect)  
**Date:** 2026-11-20

---

## Executive Summary

Following the Critic and Comprehension reviews, the intermediate zoom-out review assesses the holistic architecture, checking whether mitigating the findings will balloon complexity or whether simplifying the core model yields a superior, more maintainable system.

---

## Strategic Architecture Findings & Simplification Directives

### 1. Radically Prune the Provider Surface Area (2–3 Providers per Tier)
The proposal to implement 15 providers simultaneously across STT, LLM, and TTS introduces combinatorial testing nightmares and massive dependency bloat without tangible product necessity.
* **Streamline to Core Capabilities:**
  - **STT (2 Providers):** Deepgram Nova-2 (Production cloud WebSocket) + Sarvam AI / Local Whisper (Indic regional & offline profile).
  - **LLM (1 Consolidated Adapter):** Standard OpenAI-compatible streaming client (`base_url`, `api_key`, `model`) supporting Groq, OpenAI, Gemini (via OpenAI endpoint), and Ollama/vLLM locally.
  - **TTS (2 Providers):** Cartesia Sonic (ultra-low latency linear PCM) + Microsoft Edge-TTS (zero-cost Indian English and Hindi neural voices).

### 2. Leverage Existing Frontend Audio Capabilities Instead of Server Transcoding
The proposal to insert an in-memory MP3 decoding and resampling engine (`miniaudio`, `pydub`) on the server CPU directly endangers the sub-1.2s TTFAB budget.
* **Observation:** The browser frontend ([`app/static/index.html`](file:///Users/amankumar/Aman/project/sahayak-voice-assistant/app/static/index.html#L1589-L1601)) **already includes native dual-format handling** for both raw PCM and MP3 frames.
* **Simplification:** Drop server-side transcoding entirely. Configure cloud TTS to stream raw 16kHz PCM where available, and let Edge-TTS emit MP3 directly to the dual-format browser player.

### 3. Eliminate Connection-Scoped WebSocket Hot-Swapping (`SET_PROVIDER`)
Handling mid-turn provider swaps during continuous audio streaming creates complex race conditions, TCP buffer drops, and task cancellation deadlocks.
* **Simplification:** Negotiate providers at session establishment (via query parameters `?stt=...&llm=...&tts=...` or initial hello frame). If the user changes providers in the UI, re-open the WebSocket connection (~30ms) rather than attempting in-flight hot-swapping.
