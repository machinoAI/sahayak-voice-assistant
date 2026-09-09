---
name: voice-pipeline-debug
description: Use when debugging turn-detection cutoffs, latency, or transcription accuracy issues in the dual-stream capture, VAD, STT, and feedback loop.
allowed-tools: Read Bash Grep
---

# Voice Pipeline Debug

v1 has two parallel audio streams (candidate mic, interviewer audio), each
with its own VAD/turn detection and STT, feeding into a shared feedback
step. Most reported problems are one of: a specific stream, the
turn-detection threshold, or the feedback LLM step — isolate before
assuming it's "the whole pipeline."

## Step 1: Isolate the stream
Log timestamps per stream at: audio received -> VAD turn-end fired -> STT
complete. Check candidate and interviewer streams independently — a
problem in one doesn't imply a problem in the other, they're separate
pipelines that happen to share a feedback step downstream.

## Step 2: Diagnose cutoffs specifically
If the candidate is being cut off mid-answer, that's the known v1
limitation described in CLAUDE.md (silence-threshold VAD can't distinguish
thinking pauses from completion) — first check whether the silence
threshold (~1.2-1.5s) is actually configured as intended, not something
else. Don't jump straight to "we need Smart Turn" without confirming the
basic threshold is even being respected.

## Step 3: Test stages independently
- **VAD in isolation:** feed a known sample WAV with a deliberate pause
  partway through; confirm turn-end doesn't fire during the pause but does
  fire after the real end, given the current threshold.
- **STT in isolation:** feed a known sample WAV directly to the STT model,
  compare transcript to expected, for both streams' audio characteristics
  (mic vs. system/loopback audio may differ in quality).
- **Feedback LLM in isolation:** send a known (question, answer) text pair
  directly, skip audio entirely, confirm the feedback is reasonable before
  suspecting the audio pipeline.

## Common pitfalls to check first
- Interviewer's audio (often lower quality if it's loopback/system audio)
  producing worse STT accuracy than the candidate's direct mic — don't
  assume both streams behave the same.
- Feedback TTS starting before the candidate's turn-end is fully confirmed,
  cutting into what might still be the candidate speaking.
- Feedback audio routing checked separately — see the security-review skill
  for the hard rule that it must never reach shared call audio.
