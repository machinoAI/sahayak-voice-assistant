# Progress Log

The project's real memory across sessions. Read this at the start of every
session. Update it at the end of every session, or after any significant
step within one. Newest entries at the top.

Keep entries short and factual: what changed, what's verified, what isn't,
what's next. Not a diary — a handoff note to the next session (which might
be you, might be a teammate).

---

### 2026-09-08 — Turn-stage timing records
**Done:**
- Added dependency-free, context-manager timing records for VAD, STT, LLM, and TTS stages.
- The voice loop prints one metadata-only JSON record after each completed or interrupted turn.

**Verified:**
- Component selftest covers timing-record schema and JSON serialization.

**Known issues / not yet done:**
- `total_ms` includes caller speech and the VAD silence wait. It represents full turn elapsed time, not perceived response latency.

**Next:**
- Run one spoken live-loop turn and inspect the emitted timing JSON.

---

### 2026-09-08 — Replaced retired OpenRouter default
**Done:**
- Changed the default LLM from `z-ai/glm-5.2:free` to `inclusionai/ling-3.0-flash-sante:free` after the former returned HTTP 404.

**Verified:**
- Component selftest: 6/6 passed with the new model.
- Live loop initialized its local Smart Turn, STT, LLM, TTS, and audio pipeline successfully.

**Known issues / not yet done:**
- A human microphone/speaker conversation has not been performed in this session.

**Next:**
- Run one spoken live-loop turn and confirm the generated reply is audible.

---

## Template for a new entry

### YYYY-MM-DD — short title
**Done:**
-

**Verified:**
- Eval pass rate: X/N (compare to previous entry)
- Latency: (if measured)

**Known issues / not yet done:**
-

**Next:**
-

---

## 2026-08-26 — Org-style layout: data/ + core/types/database
**Done:**
- Added `data/samples/` (committable fixtures) and `data/local/` (gitignored scratch).
- Added `src/core/` (moved `config.py` here), `src/types/`, `src/database/` (empty; persistence gated).
- Imports updated to `core.config`; CLAUDE.md tree + permission boundary updated.

**Verified:**
- Structure-only; pipeline not re-run.

**Next:**
- Live retest: `PYTHONPATH=src .venv/bin/python src/voice_loop.py`

---

## 2026-08-26 — Project branded as Sahayak, a voice agent
**Done:**
- Renamed product identity everywhere to **Sahayak — a voice agent** (CLAUDE.md, WORKFLOW.md, prompts, module docs, architecture diagram title).
- Fixed architecture doc reference to `docs/core_architecture.mermaid`.
- Conversational system prompt now identifies as Sahayak.

**Verified:**
- Naming-only / docs+prompt change; no pipeline behavior change beyond the spoken identity string.

**Known issues / not yet done:**
- Same as prior Step 0 notes.

**Next:**
- Live retest: `OPENROUTER_MODEL=minimax/minimax-m3:free PYTHONPATH=src .venv/bin/python src/voice_loop.py`
- On pass: begin Step 1 dual-stream design.

---

## 2026-08-26 — Graduated step0/ into standard src/ layout
**Done:**
- Removed `step0/`; code now lives under `src/` per CLAUDE.md (`bot.py`, `config.py`, `transcribe/`, plus empty `audio/`, `feedback/`, `voice_out/` packages for Step 1).
- `tests/selftest.py` + empty `tests/eval/`; `requirements.txt` and `.venv` at repo root.
- CLAUDE.md Build & test section filled with run commands.

**Verified:**
- New modules parse cleanly under system Python 3.12.
- Full selftest/live loop not re-run in this restructure — behavior unchanged from prior pass.
- Note: existing `.venv` is broken on this machine (symlinks to `/Users/amankumar/.pyenv/...`); recreate before next live run.

**Known issues / not yet done:**
- Same as previous Step 0 entry (STT latency, free-tier OpenRouter flakiness, etc.).

**Next:**
- Live retest from new paths: `OPENROUTER_MODEL=minimax/minimax-m3:free PYTHONPATH=src .venv/bin/python src/voice_loop.py`
- On pass: begin Step 1 dual-stream design.

---

## 2026-08-26 — Step 0 walking skeleton built, component-verified
**Done:**
- `step0/bot.py`: mic → Silero VAD → distil-large-v3 STT (local) → OpenRouter chat LLM → Kokoro-82M TTS (local) → speakers. Plain conversational prompt, nothing interview-specific.
- `step0/selftest.py`: per-component checks (TTS synth → STT round-trip → LLM ping), no mic needed.
- Deps pinned in `step0/requirements.txt` with reasons in comments.

**Verified:**
- Eval pass rate: n/a (no interview logic yet)
- selftest 4/4: TTS 2.67s audio in ~4s @24kHz; STT round-trip transcript exact match; LLM ping replies.
- Pipeline boots to "pipeline is now ready", zero errors/deprecation warnings; full chain links mic→STT→aggregator→LLM→TTS→output.
- **LIVE TEST (human, 2026-08-26): loop works end-to-end.** Speech transcribed accurately ("Hello", "Thank you"), conversational replies synthesized and audible, interruption handling active and recovering, clean Ctrl+C shutdown.

**Latency research (2026-08-26, measured):**
- STT overhead is fixed-cost dominated, not per-audio-second: 2.7s clip = 4.6s, 19.4s answer = 5.1s on distil-medium.en (0.26× realtime). base.en: 1.1s for the same 19.4s clip (0.06×), identical transcript on test material.
- Paid LLM pricing (OpenRouter API, live): glm-5.2 ~$0.04/hr at 40 turns/hr; minimax-m3 ~$0.01/hr. Free-tier TTFB variance (2.3–9.4s) disappears on paid tier.
- Hosted reference point: Deepgram Nova-3 streams sub-300ms (200–500ms end-to-end) — benchmark for any future STT decision.
- Projected round trips for a ~20s answer: medium.en+free ~10–17s; medium.en+paid ~8–9s; base.en+paid ~4–6s; hosted+paid ~2–4s. Streaming/incremental STT (overlap transcription with speech) is the remaining structural win — Step 1 scope.

**Known issues / not yet done:**
- STT checkpoint swapped by user decision (2026-08-26 live benchmark): default is now `Systran/faster-distil-whisper-medium.en` — 4.5s vs 7.7–9.7s (distil-large-v3) vs 11.9s (large-v3-turbo, encoder-bound on CPU). Both `STT_MODEL` and `OPENROUTER_MODEL` are env-overridable without code edits. CLAUDE.md's distil-large-v3 pin intentionally deviated; revisit for Step 1.
- Whisper hallucination observed once live ("You're welcome." appearing as a user turn right after the bot spoke it; headphones were on, so not speaker bleed). Mitigation added: `condition_on_previous_text=False` in the STT wrapper. If phantom turns recur in retest, next knobs: `no_speech_prob` threshold, VAD `min_volume`.
- Live-measured latency (with old checkpoint): STT TTFB 8.3–9.1s, free-tier LLM TTFB 2.3–9.4s (pool-dependent), Kokoro TTFB 0.6–2.3s → ~25s perceived. With medium.en expect STT ~4.5s → roughly ~12–15s perceived. Needs re-measurement live.
- Free-tier OpenRouter is flaky: `z-ai/glm-5.2:free` 429s most of the day; `minimax/minimax-m3:free` verified working; most other legacy `:free` slugs retired (404).
- This machine is Intel (i7-9750H): pipecat 1.x unusable (onnxruntime~=1.24.3 has no macOS x86_64 wheels) → pinned `pipecat-ai==0.0.108`; `numba<0.62` and explicit `websockets` for same platform reasons.
- STT latency: ~8s transcribe per ~10s of speech even tuned (`cpu_threads=6`, beam_size=1 via `FastDistilWhisperSTT` subclass in bot.py). distil-large-v3 is heavy for this CPU. Options if unacceptable: smaller checkpoint or hosted STT (CLAUDE.md decision needed).
- `z-ai/glm-5.2:free` intermittently 429s (pool saturation, verified). Override without code edits: `OPENROUTER_MODEL=<slug>` (e.g. `minimax/minimax-m3:free` verified working 2026-08-26).
- Pipecat's user aggregator enables Local Smart Turn v3 by default alongside Silero VAD — better turn-end detection than plain silence, relevant to CLAUDE.md's VAD notes. Untuned so far.
- pipecat 0.0.108 logs `RuntimeWarning: coroutine 'TurnAnalyzerUserTurnStopStrategy._timeout_handler' was never awaited` on turn stops — library-internal, non-fatal.

**Next:**
- Live retest with the faster checkpoint (headphones on): `cd step0 && OPENROUTER_MODEL=minimax/minimax-m3:free .venv/bin/python bot.py`. Compare latency vs first run; watch whether phantom turns recur.
- On pass: graduate pieces into `src/` layout, begin Step 1 dual-stream design (do not start until then).

---

## 2025-01-01 — Project scaffolded (example entry, replace with real ones)
**Done:**
- Repo structure created per CLAUDE.md
- Sample company docs placed in data/sample/

**Verified:**
- N/A — no pipeline code yet

**Known issues / not yet done:**
- STT, retrieval, LLM, TTS modules not yet implemented
- No eval set yet

**Next:**
- Build the v1 loop end to end per docs/voice_agent_v1_architecture.mermaid
- Write the first 5-10 eval questions against data/sample/
