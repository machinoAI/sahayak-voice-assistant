---
name: sahayak-tasks
description: >-
  Systematic project hygiene, verification, and constraints guardian for Sahayak Voice Assistant.
  Use whenever completing a feature, creating a PR, or performing maintenance on Sahayak to ensure
  environment sync (.env.example), dependency pinning (requirements.txt), data ingestion verification,
  backend-first boundaries, and sub-1200ms voice budget enforcement.
---

# Sahayak Project Hygiene & Constraints Guardian

## Overview
This skill acts as the automated quality and architectural guardian for the **Sahayak Voice Assistant** repository. While major architectural features (e.g. streaming WebSocket pipelines, multi-provider LLM/TTS/STT adapters, and failover circuits) receive deep design focus, basic project foundations often get overlooked. This skill systematically verifies and enforces all project-level constraints and hygiene requirements.

---

## Core Constraints & Guardrails

### 1. Backend-First Boundary (Strict)
* **Rule**: Do NOT modify, refactor, or write frontend code (HTML, CSS, JavaScript in `app/static/` or templates) unless the user explicitly requests it.
* **Scope**: Default focus is strictly backend logic, async streaming protocols, vector search, and API design.

### 2. Editing & PR Protocol
* **Rule**: When investigating issues or running diagnostics, default to read-only actions.
* **Action**: When fixing bugs or implementing features, create a dedicated git branch (`feature/...` or `fix/...`) and raise a Pull Request (PR) unless explicitly instructed to edit production directly.

### 3. Voice Latency Budget
* **Budget**: End-to-end Time-to-First-Audio-Byte (TTFAB) must remain **sub-1200ms** across cloud configurations.
* **Audio Format**: Standardize on **16kHz linear mono PCM** (chunked into 20ms / 640-byte frames) across all adapters.
* **Decoupled Pipelines**: Sentence extraction and TTS audio synthesis must run in decoupled asynchronous queues (`asyncio.Queue`) so the WebSocket reader pump is never blocked.

### 4. Qdrant Storage Concurrency & Test Isolation
* **Storage Lock Rule**: Local embedded Qdrant (`qdrant_storage/.lock`) uses exclusive file locking. Never run concurrent clients against the same local folder while the server is active.
* **Test Isolation Rule**: Always execute automated tests using an isolated in-memory instance:
  ```bash
  QDRANT_PATH=":memory:" pytest tests/
  ```

---

## Hygiene Verification Checklist (Run Before Commit / PR)

Whenever completing a task, execute these 6 verification gates:

### Gate 1: Environment & Secrets Synchronization
Compare `app/core/config.py` with `.env.example`:
- Verify all newly introduced settings, active provider defaults (`ACTIVE_STT_PROVIDER`, `ACTIVE_LLM_PROVIDER`, `ACTIVE_TTS_PROVIDER`), failover chains, and models have corresponding entries in `.env.example`.
- Ensure `.env.example` contains clear explanatory comments, valid defaults, and no actual API secret values.

### Gate 2: Dependency Pinning
Scan all imports across `app/`, `scripts/`, and `tests/`:
- Ensure every imported third-party package (e.g., `tabulate`, `certifi`, `portalocker`, `fastembed`) is explicitly declared in `requirements.txt` with compatible version bounds.
- Development-only tools (e.g., `ruff`, `pytest`, `pytest-asyncio`) belong in `requirements-dev.txt`.

### Gate 3: Documentation & CLI Command Verifiability
- Never document hypothetical or phantom commands in `README.md`.
- Verify every documented command actually runs without error (e.g., `make dev`, `make test`, `make ingest`, `make benchmark`).

### Gate 4: Knowledge Base & Ingestion Integrity
- Ensure `data/knowledge_base/` contains valid JSON seed documents for citizen welfare schemes.
- Verify `scripts/ingest_knowledge.py` can parse and index documents into Qdrant cleanly.

### Gate 5: Code Quality & Linting
Run Ruff focused checks to catch undefined variables, syntax errors, and missing imports:
```bash
ruff check app/ scripts/ tests/
```

### Gate 6: Automated Test Verification
Run the complete test suite with in-memory Qdrant isolation:
```bash
make test
# Equivalent to: QDRANT_PATH=":memory:" pytest tests/
```
Ensure 100% of tests pass without deprecation warnings or unhandled exceptions.

---

## Common Mistakes & Pitfalls

1. **Forgetting `QDRANT_PATH=":memory:"` during pytest**:
   - Running bare `pytest tests/` while a local uvicorn process is running results in `BlockingIOError: Resource temporarily unavailable` on `qdrant_storage/.lock`.
2. **Missing `/favicon.ico` Route in FastAPI**:
   - Web browsers automatically request `/favicon.ico` on load. Always ensure `app/main.py` serves an inline SVG or asset to avoid 404 log spam.
3. **Cartesia HTTP 402 Fallback Audio Format**:
   - Cartesia outputs linear PCM, while Edge-TTS outputs MP3 audio. Always pass fallback audio through `convert_mp3_to_pcm16k` when downstream consumers expect linear16 frames.
4. **Unset Pytest Asyncio Loop Scope**:
   - Ensure `pyproject.toml` defines `asyncio_default_fixture_loop_scope = "function"` to prevent deprecation warnings.
