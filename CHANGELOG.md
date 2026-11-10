# Changelog

All notable changes to the Sahayak Voice Assistant codebase are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.0] - 2026-11-10

### Added
- **Real-Time Neural Decision Canvas UI**:
  - Implemented an interactive single-page application served directly by FastAPI at `GET /` and `/static/index.html`.
  - Visualizes query routing using dynamic cubic Bézier splines on a dark-slate dot-grid canvas, inspired by tree-of-thought agent workflows.
  - Features real-time particle animation along active branches and explicit terminal markers: pruned `(x)` cross marker on cancelled web search and glowing `(o)` circle on active paths.
  - Integrated 3-column live inspector: Tool Calls & Retrieval, CRAG Decision Arbiter & Reasoning, and LLM Stream Terminal with Latency Scoreboard.
- **Web Audio API Browser Engine**:
  - Direct 16kHz mono linear PCM microphone recording and WebSocket streaming via `ScriptProcessorNode`.
  - Auto-detecting streaming audio player supporting both 16kHz raw PCM (`pcm_s16le`) and MP3 streams with real-time oscilloscope waveform visualizer.
  - Interactive test presets covering all 4 reasoning branches (PM Kisan, Today's News, Fertilizer Subsidy, US President).
- **Persistent File Logging**:
  - Added dedicated `FileHandler` in `app/core/logger.py` continuously streaming to `logs/sahayak.log`.
- **Welfare Knowledge Base & Relevance Scoring**:
  - Enriched `QdrantVectorStoreAdapter` with core Indian citizen welfare scheme documentation (PM Kisan, Ayushman Bharat, Fertilizer Subsidies).
  - Added dynamic keyword overlap relevance scoring to accurately trigger CRAG confidence zones.

### Changed
- `app/services/voice_orchestrator.py`: Emits fine-grained WebSocket telemetry frames (`PIPELINE_STEP`, `LLM_TOKEN`) with millisecond-precision timing.
- `app/main.py`: Mounted `/static` directory and added `serve_index` route handling `GET` and `HEAD` methods.

---

## [0.3.0] - 2026-11-09

### Added
- **Outcome-Aware Semantic Router (OATS)** (`app/adapters/semantic_router.py`):
  - In-process, pure Python centroid classifier based on arXiv:2603.13426.
  - Extracts dual n-gram features (word unigrams + character 3-grams) with $L_2$ unit normalization.
  - Classifies queries into `LOCAL_SCHEME_FAQ`, `REALTIME_TEMPORAL`, or `OUT_OF_DOMAIN` in $< 0.5\text{ms}$ on CPU.
- **Corrective RAG (CRAG) Tri-State Arbitration**:
  - Implemented confidence zones: `CORRECT` ($\ge 0.82$), `AMBIGUOUS` ($0.55 \dots 0.82$), and `INCORRECT` ($< 0.55$).
  - Suppresses irrelevant local documents in `INCORRECT` state to eliminate hallucinations.
  - Merges local background with live web search in `AMBIGUOUS` state.
- **Speculative Concurrent Fetching (RaLMSpec)**:
  - Dispatches Tavily Web Search in parallel with Qdrant vector retrieval at $t \approx 1\text{ms}$ for temporal queries.
  - Cancels in-flight web search tasks instantly when local confidence is $\ge 0.82$.

### Fixed
- **Groq Reasoning Token Starvation**:
  - Configured `reasoning_format="hidden"` on `openai/gpt-oss-120b` in `app/adapters/llm_groq.py`, dropping TTFT to ~590ms and preventing reasoning tokens from consuming the output budget.

---

## [0.2.0] - 2026-11-09

### Added
- **Tavily Web Search Adapter** (`app/adapters/search_tavily.py`):
  - Implemented `WebSearchProtocol` with `AsyncTavilyClient`.
  - Added AI direct answer extraction and snippet parsing.
  - Configured configurable timeouts and graceful degradation.
- **Automated Tests**:
  - Added `tests/test_search_tavily.py` covering successful search, direct answer fallback, timeout resilience, and disabled configuration.

---

## [0.1.0] - 2026-11-08

### Added
- **Core Async Streaming Voice Orchestrator** (`app/services/voice_orchestrator.py`):
  - Sub-1.2s TTFAB pipeline coordinating STT, RAG, LLM token streaming, and TTS synthesis.
  - Incremental sentence boundary splitter with abbreviation and honorific protection.
  - Decoupled producer/consumer queue architecture.
  - Server-side automatic barge-in detection with sub-40ms buffer clearing.
- **Multi-Turn Session Memory** (`app/services/session_memory.py`):
  - Connection-scoped rolling buffer retaining the last 3 dialogue turns.
  - Contextual query augmentation for pronoun resolution.
- **Concrete Provider Adapters**:
  - Deepgram Nova-2 streaming STT adapter (`app/adapters/stt_deepgram.py`).
  - Cartesia Sonic 16kHz PCM streaming TTS adapter (`app/adapters/tts_cartesia.py`).
  - Microsoft Edge-TTS neural voice adapter (`app/adapters/tts_edge.py`).
  - Groq LPU streaming LLM adapter (`app/adapters/llm_groq.py`).
  - Qdrant vector store adapter (`app/adapters/vector_store_qdrant.py`).
- **CLI Streaming Client** (`client_stream.py`):
  - Non-blocking audio playback engine using `sounddevice` and `numpy`.
- **Test Suite**:
  - 43 automated unit and integration tests across adapters, pipeline, session memory, and streaming clients.
