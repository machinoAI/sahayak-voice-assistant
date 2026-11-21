# Changelog

All notable changes to the Sahayak Voice Assistant codebase are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.9.0] - 2026-11-21 (Release: `v0.4.0-hygiene-and-tooling`)

### Added
- **Knowledge Base Seed Data & Ingestion Script** (`data/knowledge_base/`, `scripts/ingest_knowledge.py`):
  - Added structured datasets for 6 core Indian citizen welfare schemes: PM-KISAN, Ayushman Bharat (PM-JAY), Pradhan Mantri Awas Yojana (PMAY), Atal Pension Yojana (APY), PM Ujjwala Yojana (PMUY), and Sukanya Samriddhi Yojana (SSY).
  - Built `scripts/ingest_knowledge.py` CLI supporting remote Qdrant clusters, local embedded storage, and graceful concurrency lock detection.
  - Added CLI entrypoint directly into `app/adapters/vector_store_qdrant.py` and a backwards-compatible shim in `app/adapters/qdrant_retriever.py`.
- **Developer Automation Task Runner** (`Makefile`):
  - Shortcuts for `make dev`, `make test`, `make test-fast`, `make ingest`, `make benchmark`, `make lint`, `make clean`, and Docker targets.
- **Containerization & Deployment** (`Dockerfile`, `docker-compose.yml`):
  - Production-ready `Dockerfile` based on `python:3.12-slim-bookworm` with system audio libraries (`portaudio`, `ffmpeg`, `libsndfile1`) and container health checks.
  - `docker-compose.yml` orchestrating FastAPI with a standalone Qdrant vector database container, resolving local file lock contention.
- **Continuous Integration Pipeline** (`.github/workflows/ci.yml`):
  - GitHub Actions matrix testing on Python 3.11, 3.12, and 3.13 with Ruff linting and in-memory test suite execution.
- **FastAPI Favicon & Static Polish** (`app/main.py`):
  - Added `/favicon.ico` route returning an inline SVG microphone icon to eliminate 404 spam in server logs.
- **Dependency & Configuration Hardening** (`requirements.txt`, `requirements-dev.txt`, `pyproject.toml`):
  - Added missing dependencies: `tabulate`, `certifi`, `numpy`, `portalocker`.
  - Configured `pyproject.toml` with `asyncio_default_fixture_loop_scope = "function"` and filtered legacy deprecation warnings.

---

## [0.8.0] - 2026-11-20 (Release: `v0.3.0-multi-provider-framework`)

### Added
- **Pluggable Multi-Provider Architecture** (`app/interfaces/adapters.py`, `app/adapters/registry.py`, `app/adapters/base.py`):
  - Defined asynchronous streaming protocol interfaces: `StreamingSTTProtocol` (`start()`, `send_audio()`, `receive_transcripts()`, `close()`), `STTTranscriptEvent` (with dual object-attribute and dict-key access), `LLMClientProtocol` (with dynamic model property), and `TTSClientProtocol`.
  - Implemented centralized factory dispatchers (`get_stt_adapter()`, `get_llm_adapter()`, `get_tts_adapter()`) supporting `VOICE_PROFILE="production"` (cloud) and `VOICE_PROFILE="local"` (Ollama + Edge-TTS + Local Whisper).
  - Implemented `HTTPClientManager` providing shared, pooled `httpx.AsyncClient` instances to minimize connection establishment overhead across providers.
- **Multi-Provider LLM Suite & Prefix Continuation Failover** (`app/adapters/llm/`, `app/adapters/failover.py`):
  - Consolidated `OpenAICompatibleLLMAdapter` supporting Groq LPU (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`), OpenAI (`gpt-4o`, `gpt-4o-mini`), Google Gemini (`gemini-2.0-flash` via OpenAI endpoint), and local Ollama (`llama3.2`).
  - Added native `AnthropicClaudeAdapter` for Claude 3.5 Sonnet and Haiku streaming.
  - Implemented `FailoverLLMAdapter` with `Retry-After` circuit breaker cooldowns and **prefix continuation** (if an LLM fails mid-stream after sentences were spoken, completed sentences are passed as assistant history context to the fallback LLM to continue without speech duplication).
- **Multi-Provider TTS Suite & Turn-Sticky Failover** (`app/adapters/tts/`, `app/adapters/failover_tts.py`):
  - `CartesiaTTSAdapter` for ultra-low latency 16kHz linear PCM streaming.
  - `EdgeTTSAdapter` for zero-cost neural Indian English and Hindi speech synthesis.
  - `ElevenLabsTTSAdapter` for high-fidelity 16kHz linear PCM streaming via `AsyncElevenLabs`.
  - Implemented `FailoverTTSAdapter` with **turn stickiness** ensuring that once a sentence triggers fallback, subsequent sentences in that dialogue turn remain on the fallback provider for voice consistency.
- **Multi-Provider STT Suite** (`app/adapters/stt/`):
  - `DeepgramSTTAdapter` with duplex WebSocket streaming and proactive KeepAlive heartbeats.
  - `SarvamSTTAdapter` with buffered batch ASR and in-memory PCM-to-WAV conversion for high-accuracy Indic languages.
  - `LocalWhisperSTTAdapter` for zero-cost offline local development.
- **Connection-Scoped Concurrency Isolation & Dynamic Control Frames** (`app/services/voice_orchestrator.py`, `app/api/websocket_endpoint.py`):
  - Introduced `VoiceSessionContext` isolating mutable task handles (`active_generation_task`, `active_tts_task`), sentence queues, and locks per WebSocket connection, eliminating singleton race conditions.
  - Implemented handshake query parameter negotiation (`/ws/voice?stt=...&llm=...&tts=...&lang=...`).
  - Added runtime mid-session switching via `SET_PROVIDER` control frame with `PROVIDER_CHANGED` acknowledgment.
  - Updated web interface (`app/static/index.html`) with header dropdown selectors for STT, LLM, and TTS providers.
- **Deprecation Shims for Zero-Regression Compatibility**:
  - Maintained `app/adapters/llm_groq.py`, `app/adapters/tts_cartesia.py`, `app/adapters/tts_edge.py`, and `app/adapters/stt_deepgram.py` as transparent re-export shims.
- **Test Suite**:
  - Added `tests/test_registry.py`, `tests/test_llm_adapters.py`, `tests/test_llm_failover.py`, `tests/test_tts_adapters.py`, `tests/test_stt_adapters.py`, and `tests/test_multi_provider_e2e.py` (total 49 passing tests).

---

## [0.7.0] - 2026-11-19 (Release: `v0.2.1-multi-turn-persistence`)

### Fixed
- **Consecutive Question Microphone Freeze & STT Session Persistence** (`app/adapters/stt_deepgram.py`, `app/api/websocket_endpoint.py`):
  - Solved the upstream Deepgram 10–12 second inactivity timeout that silently dropped streaming WebSocket connections during conversational pauses.
  - Implemented an autonomous `_keepalive_loop()` inside `DeepgramStreamSession` that transmits native `{"type": "KeepAlive"}` JSON control frames every 5.0 seconds during idle audio intervals, synchronized via `_send_lock`.
  - Added robust connection liveness detection (`is_connected` property) supporting modern websockets `ClientConnection.state` (`State.OPEN` vs `State.CLOSED`) with legacy and mock fallback compatibility.
  - Introduced lazy auto-reconnection (`ensure_stt_connected()`) in `app/api/websocket_endpoint.py` guarded by `stt_reconnect_lock = asyncio.Lock()` to prevent connection stampedes when incoming audio bursts arrive.
  - Isolated `stt_event_listener` to cleanly exit on provider disconnects without crashing the client-facing WebSocket gateway.

### Added
- **Clean Turn Boundary Transitions** (`app/services/voice_orchestrator.py`):
  - Implemented explicit cancellation and awaiting of both `active_generation_task` (LLM generation) and `active_tts_task` (TTS synthesis) when a new user turn initiates before previous turns fully wind down.
  - Re-initialized `self.sentence_queue = asyncio.Queue()` per turn to eliminate cross-turn sentence leakage.
- **Microphone Audio Graph Isolation** (`app/static/index.html`):
  - Routed live microphone audio through a muted gain node (`GainNode.gain.value = 0`) before connecting to `AudioContext.destination`, completely eliminating acoustic loopback through device speakers while preserving continuous Web Audio frame pumping.
  - Implemented `stopAudioPlayback()` to immediately stop active `AudioBufferSourceNode` playback and flush queues on turn initiation and barge-in.
- **Regression Test Coverage**:
  - Added `test_deepgram_keepalive_lifecycle` in `tests/test_adapters.py` testing keepalive dispatch, task cancellation, and connection liveness.
  - Added `test_live_multi_turn_pause` in `tests/test_cli_client.py` validating consecutive turns over an 11-second conversational pause on a single WebSocket connection.

---

## [0.6.0] - 2026-11-19 (Release: `v0.2.0-indic-multilingual`)

### Added
- **Indic & Multilingual Speech Support** (`app/adapters/stt_deepgram.py`, `app/adapters/tts_cartesia.py`, `app/adapters/tts_edge.py`, `app/services/voice_orchestrator.py`):
  - Dynamic language parameterization in Deepgram streaming STT supporting `en-IN` (Indian English), `hi` (Hindi), and `multi` (multilingual auto-detection).
  - Dynamic per-session language re-binding via `SET_LANGUAGE` client WebSocket control frame with `LANGUAGE_CHANGED` acknowledgment.
  - Groq LPU system prompt steering enforcing language mirroring: generating clear Devanagari Hindi for Hindi/Hinglish inputs and standard English for English inputs.
  - Dual-tier neural TTS routing: ultra-low latency Cartesia Sonic English (`c45bc5ec-5968-4f0b-a898-92743eed0000`, ~180ms TTFAB) for English queries, and high-naturalness Microsoft Edge-TTS neural Indic voices (`hi-IN-SwaraNeural`, `hi-IN-MadhurNeural`, ~450ms TTFAB) for Devanagari Hindi queries.
- **Multilingual Conversational Memory** (`app/services/session_memory.py`):
  - Expanded pronoun query augmentation to recognize Indic demonstratives and honorifics (`यह`, `वह`, `इनका`, `उनका`, `इन्हें`, `उन्हें`, `इस`, `उस`).
- **Client Language Controls** (`app/static/index.html`):
  - Added a session language dropdown selector (`English`, `Hindi`, `Auto`) in the web UI header with real-time WebSocket state propagation.
- **Multilingual Test Suite & Benchmarks**:
  - Added `tests/test_multilingual.py` covering language parameterization, prompt steering, and Indic pronoun resolution.
  - Added multi-language streaming test suite in `client_stream.py`.

---

## [0.5.0] - 2026-11-12

### Added
- **Local Dense Neural Embeddings with FastEmbed** (`app/adapters/vector_store_qdrant.py`):
  - Integrated `fastembed` with `BAAI/bge-small-en-v1.5` generating 384-dimensional dense semantic vectors in $<6\text{ms}$ on CPU with zero network dependencies.
  - Implemented true cosine vector search via Qdrant's `query_points` API over local disk storage (`qdrant_storage/`).
  - Added thread-safe singleton embedder caching to prevent duplicate model initializations.
- **Enhanced Document Ingestion Pipeline** (`app/rag/ingest.py`):
  - Voice-optimized semantic chunking (150-250 tokens) with paragraph preservation and header grounding.
  - CLI and programmatic ingestion supporting files (`.md`, `.txt`) and recursive directory traversal.
  - Automatically indexed internal architecture documentation (`docs/` and `README.md`) into `sahayak_kb`.
- **Visual Speculative Trajectory Fan Canvas** (`app/static/index.html`):
  - Interactive next-token branching tree visualizer rendered via HTML5 Canvas.
  - Dynamic committed path (`◯`) and pruned route (`⨂`) badges.
  - Dual view switcher between Speculative Trajectory Fan and Pipeline Architecture DAG.

### Removed
- **Hardcoded Citizen Welfare Scheme Fallback**:
  - Purged hardcoded PM Kisan, Ayushman Bharat, and fertilizer subsidy text from `vector_store_qdrant.py`, replacing it with a clean, domain-neutral platform knowledge base.

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
