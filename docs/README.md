# Sahayak Documentation Hub

Welcome to the comprehensive technical documentation for **Sahayak**, an ultra-low latency streaming Voice Retrieval-Augmented Generation (Voice RAG) assistant.

---

## Documentation Index

### Core Architecture & Engineering Guides

| Document | Description |
| :--- | :--- |
| **[Architecture & System Design](ARCHITECTURE.md)** | End-to-end voice pipeline, sub-1.2s latency budget, decoupled async consumer/producer queues, automatic barge-in, multi-turn session persistence, pluggable multi-provider framework, knowledge ingestion, and containerization. |
| **[Intent Routing & Classification](ROUTING_AND_CLASSIFICATION.md)** | Outcome-Aware Semantic Router (OATS), sparse dual n-gram feature extraction, centroid math, Indic transliteration robustness, and sub-millisecond CPU classification. |
| **[Knowledge Retrieval & Corrective RAG (CRAG)](RETRIEVAL_AND_CRAG.md)** | Qdrant hybrid retrieval, 6 seed citizen welfare datasets (`data/knowledge_base/`), CRAG tri-state confidence arbitration (`CORRECT`, `AMBIGUOUS`, `INCORRECT`), and hallucination suppression. |
| **[Speculative Web Search & Concurrency](WEB_SEARCH_AND_SPECULATION.md)** | Speculative concurrent retrieval (RaLMSpec), zero-lag Tavily web search dispatch at $t=1\text{ms}$, and early task cancellation. |
| **[Streaming Voice Pipeline](STREAMING_AND_VOICE_PIPELINE.md)** | Pluggable STT/LLM/TTS streaming, rolling memory with Indic pronoun resolution, danda-guarded sentence splitting, prefix continuation failover, loop-aware client pools, and connection-scoped session contexts. |
| **[Real-Time Telemetry & Inspector UI](TELEMETRY_AND_UI.md)** | FastAPI-served testing SPA at `http://localhost:8000/`, WebSocket protocol specification, dynamic language and provider selector controls, Bézier spline neural decision tree canvas, inline SVG favicon, and Web Audio API engine. |
| **[Multi-Provider Latency Benchmarks](BENCHMARKS.md)** | Automated empirical benchmark results measuring Time-to-First-Token (TTFT), Time-to-First-Audio-Byte (TTFAB), token velocity, and end-to-end voice budget compliance across cloud and local providers. |

### Technical Design Specifications

| Design Document | Status | Description |
| :--- | :--- | :--- |
| **[Indic & Multilingual Speech Support](designs/indic_multilingual_speech_support.md)** | Implemented (`v0.2.0`) | Architectural specification for Hindi & Hinglish voice support: Deepgram parameterization, Devanagari prompt steering, and dual-tier TTS dispatch. |
| **[Multi-Turn Voice Session Persistence](designs/multi_turn_voice_session_persistence.md)** | Implemented (`v0.2.1`) | Architectural specification for persistent streaming STT sessions: proactive 5s KeepAlive heartbeats, lazy auto-reconnection guards, and Web Audio zero-gain isolation. |
| **[Pluggable Multi-Provider Architecture](designs/multi_provider_architecture.md)** | Implemented (`v0.3.0`) | Architectural specification for pluggable multi-provider model framework across STT, LLM, and TTS with automated tiered failover, prefix continuation, and runtime switching. |

### Automated Project Guardian Skill

| Skill | Path | Description |
| :--- | :--- | :--- |
| **Sahayak Tasks Skill** | [`.agents/skills/sahayak-tasks/SKILL.md`](../.agents/skills/sahayak-tasks/SKILL.md) | Enforces strict project boundaries (backend-first rule, PR protocol, sub-1200ms voice budget, Qdrant file lock isolation, and 6-gate pre-commit verification checklist). |

---

## Quick Reference Commands

All primary developer tasks are automated through the root [`Makefile`](../Makefile):

### Start the Development Server
```bash
make dev
# Equivalent to: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Ingest Knowledge Base into Qdrant
```bash
make ingest
# Equivalent to: python scripts/ingest_knowledge.py
```

### Run Automated Tests (In-Memory Isolated)
```bash
make test
# Equivalent to: QDRANT_PATH=":memory:" pytest tests/
```

### Run Provider Latency Benchmarking Suite
```bash
make benchmark
# Equivalent to: python scripts/benchmark_providers.py --include-mock --runs 2
```

### Run Fast Code Quality Linting
```bash
make lint
# Equivalent to: ruff check app/ scripts/ tests/
```

### Docker Container Stack
```bash
# Start FastAPI and standalone Qdrant container
make docker-up

# Stop container stack
make docker-down
```

### Access the Web Inspector UI
Open **[http://localhost:8000/](http://localhost:8000/)** in Google Chrome or Microsoft Edge.
