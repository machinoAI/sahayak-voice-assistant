# Sahayak Documentation Hub

Welcome to the comprehensive technical documentation for **Sahayak**, an ultra-low latency streaming Voice Retrieval-Augmented Generation (Voice RAG) assistant.

---

## Documentation Index

### Core Architecture & Engineering Guides

| Document | Description |
| :--- | :--- |
| **[Architecture & System Design](ARCHITECTURE.md)** | End-to-end voice pipeline, sub-1.2s latency budget, decoupled async consumer/producer queues, automatic barge-in, multi-turn session persistence, and pluggable multi-provider framework. |
| **[Intent Routing & Classification](ROUTING_AND_CLASSIFICATION.md)** | Outcome-Aware Semantic Router (OATS), sparse dual n-gram feature extraction, centroid math, Indic transliteration robustness, and sub-millisecond CPU classification. |
| **[Knowledge Retrieval & Corrective RAG (CRAG)](RETRIEVAL_AND_CRAG.md)** | Qdrant hybrid retrieval, CRAG tri-state confidence arbitration (`CORRECT`, `AMBIGUOUS`, `INCORRECT`), and hallucination suppression. |
| **[Speculative Web Search & Concurrency](WEB_SEARCH_AND_SPECULATION.md)** | Speculative concurrent retrieval (RaLMSpec), zero-lag Tavily web search dispatch at $t=1\text{ms}$, and early task cancellation. |
| **[Streaming Voice Pipeline](STREAMING_AND_VOICE_PIPELINE.md)** | Pluggable STT/LLM/TTS streaming, rolling memory with Indic pronoun resolution, danda-guarded sentence splitting, prefix continuation failover, and connection-scoped session contexts. |
| **[Real-Time Telemetry & Inspector UI](TELEMETRY_AND_UI.md)** | FastAPI-served testing SPA at `http://localhost:8000/`, WebSocket protocol specification, dynamic language and provider selector controls, Bézier spline neural decision tree canvas, and Web Audio API engine. |

### Technical Design Specifications

| Design Document | Status | Description |
| :--- | :--- | :--- |
| **[Indic & Multilingual Speech Support](designs/indic_multilingual_speech_support.md)** | Implemented (`v0.2.0`) | Architectural specification for Hindi & Hinglish voice support: Deepgram parameterization, Devanagari prompt steering, and dual-tier TTS dispatch. |
| **[Multi-Turn Voice Session Persistence](designs/multi_turn_voice_session_persistence.md)** | Implemented (`v0.2.1`) | Architectural specification for persistent streaming STT sessions: proactive 5s KeepAlive heartbeats, lazy auto-reconnection guards, and Web Audio zero-gain isolation. |
| **[Pluggable Multi-Provider Architecture](designs/multi_provider_architecture.md)** | Implemented (`v0.3.0`) | Architectural specification for pluggable multi-provider model framework across STT, LLM, and TTS with automated tiered failover, prefix continuation, and runtime switching. |

---

## Quick Reference Commands

### Start the Live Server
```bash
../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Access the Real-Time UI
Open **[http://localhost:8000/](http://localhost:8000/)** in any modern web browser.

### Run Automated Tests
```bash
../.venv/bin/pytest tests/
```

### View Live Execution Logs
```bash
tail -f logs/sahayak.log
```
