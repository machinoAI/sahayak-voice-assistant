# Project: Sahayak — a voice agent

## What this is
**Sahayak** is a voice agent that sits in on a mock/practice job interview
between a real human interviewer and a candidate, listens to both sides, and
gives the candidate live feedback on each answer after they finish speaking —
what was good, what could improve — as text and spoken audio, delivered to
the candidate only.

An earlier RAG-based company-data direction for Sahayak has been dropped, not
paused. There is no vector store, no RAG, no "company data" in this version.
Do not resurrect that architecture or its assumptions — this version is built
from scratch around the live interview-feedback loop.

## Explicit scope assumption
This is for **mock/practice interviews** (friend, mentor, or coach playing
interviewer), not live-assisting during an actual hiring interview. That
assumption shapes the audio routing rule below — confirm with the user
before building anything that would make sense only for real, live-assisted
interviews.

## Step 0 — walking skeleton (build this first, before anything below)
Before any interview-specific logic exists, prove the basic voice loop
works end to end on this machine:

Voice Input (single mic) -> API Gateway -> STT -> LLM (plain conversational
reply, not interview feedback) -> TTS -> Voice Output

Deliberately NOT included in Step 0: a second audio stream, VAD-based turn
detection tuning (default settings are fine), interview question/answer
context, feedback evaluation logic, audio-routing rules (there's only one
output, so the routing rule doesn't apply yet). Those all get added on top
of this skeleton once it's proven to work — don't build them alongside it.

Step 0 is done when: you can speak into the mic, get a transcribed query,
get a spoken response back, with no crashes and roughly-reasonable latency.
That's it. Move to the dual-stream interview-specific version (below) only
after this works.

## Step 1 — the actual interview coach (do not start until Step 0 works)
Real human interviewer + real candidate, two separate audio streams (no
speaker diarization needed — see below), feedback after each answer.

Voice capture (candidate mic + interviewer audio) -> per-stream VAD/turn
detection -> STT (both streams) -> LLM evaluates the latest answer against
the latest question -> feedback delivered as text + spoken audio to the
candidate only

See docs/core_architecture.mermaid for the diagram.

## The turn-detection problem — read this before touching VAD code
Plain VAD (silence-based) cannot distinguish "candidate is pausing to
think" from "candidate has finished the answer." v1 uses a tuned silence
threshold (~1.2-1.5s, longer than casual-conversation defaults, because
interview answers involve more thinking pauses) as a first approximation.
This will cut people off sometimes — that's an accepted v1 limitation, not
a bug to chase down. The real fix (semantic/contextual turn detection,
e.g. Pipecat's Smart Turn model, which looks at the partial transcript and
prosody, not just silence) is the natural v1.1 upgrade once cutoff
frequency is actually measured and judged too high — don't build it
preemptively.

## Two audio streams, not one, and no diarization in v1
Capture the candidate's mic and the interviewer's audio (system/loopback
audio from the call, or a second mic if in person) as two separate streams.
Do not attempt to separate speakers from a single mixed stream (speaker
diarization) — that's a real ML problem with its own failure modes and
buys nothing here since two clean streams are available for free in the
mock-interview setup.

## Audio routing rule (hard rule, not a suggestion)
Spoken feedback must never be audible to the interviewer or enter any
shared call audio. It plays to the candidate's own output (headphones)
between turns, after the candidate's answer is evaluated and before the
interviewer's next question. If a future task would route feedback audio
anywhere else, stop and confirm before building it.

## Recording and consent
This app records and transcribes a real person's (the interviewer's) voice.
Before building anything that persists audio/transcripts beyond the live
session, flag it — recording another person without consent has real legal
implications that vary by jurisdiction (many US states require two-party
consent, for example). v1 can process audio in memory for the live
feedback loop without persisting it; treat persistence as a separate,
explicitly-confirmed decision, not a default.

## Dev tech stack
- Orchestration: Pipecat (VAD via Silero, bundled)
- STT: distil-whisper/distil-large-v3 (Hugging Face) for both streams
- LLM: OpenRouter z-ai/glm-5.2:free for iteration; Claude API for quality checks
- TTS: hexgrad/Kokoro-82M (Apache 2.0), routed to candidate output only
- No vector store, no embeddings, no RAG in this version.

## Directory structure
```
data/                  # non-code artifacts only (never put app logic here)
  samples/             # committed fixtures / synthetic clips for tests
  local/               # machine-local scratch (gitignored contents)
src/                   # all application code
  voice_loop.py        # Step 0 entry: single-mic conversational voice loop
  core/                # shared config and cross-cutting primitives
  types/               # dataclasses / TypedDicts / schemas (no I/O)
  database/            # persistence (empty until human-approved)
  prompts/             # LLM system/user prompt text
  audio/               # dual-stream capture, VAD/turn detection (Step 1)
  transcribe/          # STT wrapper, shared by both streams
  feedback/            # answer evaluation + LLM client (Step 1)
  voice_out/           # TTS + candidate-only output routing (Step 1)
tests/
  selftest.py          # component checks (TTS / STT / LLM), no mic needed
  eval/                # fixed (question, answer, expected feedback direction) pairs
docs/
  PROGRESS.md
  core_architecture.mermaid
requirements.txt
```

`data/` holds files, not code. Do not store live interview audio/transcripts
in `data/` (or anywhere) without an explicit human checkpoint — v1 stays
in-memory for the live loop.
## Working principles
These are adapted from Andrej Karpathy's publicly shared observations about
where Claude Code tends to fail, distilled by the community into a widely
used four-rule CLAUDE.md format. Same four rules, applied to this project:

### 1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.
- Before writing pipeline code, state the assumption out loud (audio format,
  sample rate, expected latency budget, chunk size) rather than picking one
  silently.
- If a request is ambiguous (e.g. "add retrieval" without specifying top-k),
  ask or state the default you're using and why.
- If a simpler approach exists than the one implied by the request, say so.

### 2. Simplicity First
Minimum code that solves the problem. Nothing speculative.
- v1 stays a single linear loop. Do not add multi-tenancy, RBAC, a plugin
  system, or config abstractions "for later" — later has its own phase.
- No error handling for scenarios that can't occur in the current phase
  (e.g. don't handle multi-tenant namespace collisions in v1, there's one
  tenant).

### 3. Surgical Changes
Touch only what you must. Clean up only your own mess.
- STT, LLM, and TTS are separate modules. A change to one should not
  touch the others unless the task explicitly spans both.
- Don't refactor working code you weren't asked to change, even if you'd do
  it differently.
- If you notice unrelated dead code or a real problem outside scope, mention
  it in your response — don't fix it silently.

### 4. Goal-Driven Execution
Define success criteria before starting. Loop until verified, then stop.
- Every new pipeline component needs a runnable check before being called
  done: a sample audio file in, an expected transcript/answer shape out.
- After any change to retrieval or prompting, re-run tests/eval/ and report
  the pass rate — don't just say "should work now."
- On multi-step tasks, checkpoint after each significant step: what was
  done, what's verified, what remains. Don't push forward on top of a step
  that didn't verify.

## Permission boundary (hard rules — do not proceed without asking if unsure)
```
READ:  src/**, tests/**, docs/**, data/**
WRITE: src/**, tests/**, docs/**, data/**
NEVER: .env*, credentials/**, any persisted real interview audio/transcript
HUMAN CHECKPOINT before:
  - persisting any audio or transcript beyond the live in-memory session
  - writing anything under data/ that came from a real interview session
  - routing feedback audio anywhere other than the candidate's own output
  - deploying anything
```

## Privacy and audio-routing rules (non-negotiable)
- Never route spoken feedback into shared/call audio — candidate output
  only. This is the core trust boundary of the whole product; treat it like
  the RBAC boundary would be treated in a company-data product.
- Never log full transcripts or audio content in plaintext beyond what's
  needed for the live session. If persistence is added later, it needs an
  explicit human decision, not a default.
- Any code touching audio routing, recording, or persistence must pass the
  `security-review` skill before being marked done.

## Build & test
Package manager: pip + a repo-root `.venv` (Python 3.11+).

```bash
# one-time setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# create a repo-root .env yourself with OPENROUTER_API_KEY=sk-or-...
# (this repo never writes .env files)

# component selftest (no mic)
PYTHONPATH=src .venv/bin/python tests/selftest.py

# live Step 0 voice loop
PYTHONPATH=src .venv/bin/python src/voice_loop.py

# useful overrides
OPENROUTER_MODEL=minimax/minimax-m3:free PYTHONPATH=src .venv/bin/python src/voice_loop.py
STT_MODEL=Systran/faster-distil-whisper-large-v3 PYTHONPATH=src .venv/bin/python src/voice_loop.py
```

Eval set (`tests/eval/`): not populated until Step 1 feedback logic exists.
