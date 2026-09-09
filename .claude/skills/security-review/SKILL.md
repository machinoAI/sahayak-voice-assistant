---
name: security-review
description: Use before marking any change done that touches audio routing, recording, transcript persistence, or where feedback audio/text is sent. Also use when explicitly asked to review a diff for privacy issues.
allowed-tools: Read Grep Glob Bash
---

# Security & Privacy Review

This project's core trust boundary is audio routing, not access control:
feedback must never leak into shared call audio, and a real third party's
(the interviewer's) voice is being recorded and transcribed. Check every
item below before marking a change done.

## Checklist

1. **Feedback audio only ever routes to the candidate's own output.**
   Trace any new TTS/audio-output code path. If there's any route by which
   spoken feedback could reach shared/call audio (even conditionally, even
   in a code path meant for testing), that's a fail.

2. **No persistence by default.**
   Audio and transcripts should exist in memory for the live session only.
   If a change writes audio/transcript to disk, a database, or a log file,
   that's a fail unless it was an explicit, confirmed human decision — check
   docs/PROGRESS.md or the task description for that confirmation before
   assuming it's fine.

3. **No plaintext transcript content in application logs.**
   Debug logs should reference timing, stream IDs, or lengths — not the
   actual words spoken by either party.

4. **Interviewer's stream is treated with the same care as the candidate's.**
   The interviewer didn't necessarily consent to being fed into an LLM.
   Anything beyond "transcribe their question to give it as context to the
   feedback LLM" (e.g. storing it, analyzing it independently, sending it
   anywhere else) needs explicit confirmation first.

## Output format
Report each item as pass/fail with a one-line reason and file/line
references for any failure. If anything fails, stop and report the fix
needed rather than proceeding.
