# Development Workflow — Sahayak

How to actually work on Sahayak (a voice agent) with Claude Code, session to session.

## 1. Spec before code
For anything beyond a trivial fix, ask Claude to work in plan mode first:
state what the feature does, its inputs/outputs, and what "done" means,
before touching files. This is the practical form of "Think Before Coding" —
catch a wrong assumption in a one-paragraph spec, not after 200 lines.

## 2. Small, surgical diffs
One module or feature per change. If a task naturally spans STT and
retrieval, say so explicitly up front rather than letting scope creep in
mid-task. Review each diff before moving to the next piece of work.

## 3. Eval loop, not vibes
`tests/eval/` holds a fixed set of (question, answer, expected feedback
direction) triples — e.g. a strong answer that should get positive
feedback, a rambling answer that should get "be more concise," an answer
that dodges the question entirely. After any change to the feedback
prompt or LLM:
- Run every case through the feedback step (text-only, no audio needed to
  check this) and compare the direction of the feedback to expected.
- Compare to the last recorded result in `docs/PROGRESS.md`.
- A regression is a stop-and-fix signal, not a "note it and continue" signal.

This is the "Goal-Driven Execution" principle made concrete: success
criteria are a checkable result, not a feeling that the change "should"
help.

## 4. Human checkpoints
Confirm with a human before:
- Persisting any audio or transcript beyond the live in-memory session
- Routing feedback audio anywhere other than the candidate's own output
- Deploying anything, anywhere

These are called out in `CLAUDE.md`'s permission boundary too — this is not
optional even under time pressure.

## 5. Phase gates
Don't start the next phase until the current one works reliably in testing:
- **v1** — real interviewer + candidate, two audio streams, VAD-based turn
  detection, text + spoken feedback after each answer. Gate: turn detection
  doesn't cut off answers constantly, feedback is directionally correct on
  the eval set, feedback never leaks into shared audio.
- **v2** — candidate ideas so far: semantic turn detection (Smart Turn) to
  fix cutoffs properly, feedback that references earlier answers in the
  same session (not just the latest one), a summary at the end of the mock
  interview. Don't start these until v1's own limitations are actually felt
  in testing, not assumed in advance.

Building v2 features while v1 is still shaky is the most common way this
kind of project stalls — resist it even if a v2 idea seems easy to sneak
in early.

## 6. Session structure
- **Start of session:** read `CLAUDE.md` and `docs/PROGRESS.md` before
  starting work, so context isn't re-explained from scratch each time.
- **During long or multi-step tasks:** checkpoint after each significant
  step — what was done, what's verified, what remains — before continuing.
  If a step fails verification, stop there rather than building the next
  step on top of an unverified one.
- **Budget awareness:** if a debugging loop is running long without
  converging (rough guide: a single task pushing well past what a focused
  session should take), stop, summarize what's been tried and ruled out,
  and start a fresh, scoped session rather than continuing to accumulate
  context. Restate what's already been tried in the new session so it isn't
  re-attempted.
- **End of session:** update `docs/PROGRESS.md` — what was done, what's
  verified working, what's known-broken, what's next. This file is the
  project's real memory across sessions, not the chat history.

## 7. Skills and subagents available
- `security-review` — checklist for audio routing, recording consent, and
  transcript persistence
- `voice-pipeline-debug` — isolating turn-detection cutoffs, latency, or STT
  accuracy issues across the two audio streams
- `security-reviewer` (subagent) — runs security-review in an isolated context
