# Sahayak Documentation Hub

Welcome to the comprehensive technical documentation for **Sahayak**, an ultra-low latency streaming Voice Retrieval-Augmented Generation (Voice RAG) assistant.

---

## Documentation Index

| Document | Description |
| :--- | :--- |
| **[Architecture & System Design](ARCHITECTURE.md)** | End-to-end voice pipeline, sub-1.2s latency budget, decoupled async consumer/producer queues, and automatic barge-in handling. |
| **[Intent Routing & Classification](ROUTING_AND_CLASSIFICATION.md)** | Outcome-Aware Semantic Router (OATS), sparse dual n-gram feature extraction, centroid math, and sub-millisecond CPU classification. |
| **[Knowledge Retrieval & Corrective RAG (CRAG)](RETRIEVAL_AND_CRAG.md)** | Qdrant hybrid retrieval, CRAG tri-state confidence arbitration (`CORRECT`, `AMBIGUOUS`, `INCORRECT`), and hallucination suppression. |
| **[Speculative Web Search & Concurrency](WEB_SEARCH_AND_SPECULATION.md)** | Speculative concurrent retrieval (RaLMSpec), zero-lag Tavily web search dispatch at $t=1\text{ms}$, and early task cancellation. |
| **[Streaming Voice Pipeline](STREAMING_AND_VOICE_PIPELINE.md)** | Deepgram streaming STT, rolling conversational memory (`SessionMemory`), honorific-guarded sentence boundary splitter, Groq LPU LLM streaming, and Cartesia Sonic TTS. |
| **[Real-Time Telemetry & Inspector UI](TELEMETRY_AND_UI.md)** | FastAPI-served testing SPA at `http://localhost:8000/`, WebSocket protocol specification, Bézier spline neural decision tree canvas, and Web Audio API engine. |

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
