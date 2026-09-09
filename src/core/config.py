"""Shared runtime config for Sahayak's voice loop.

Env overrides only — no secrets written here. Load .env from the repo root
via python-dotenv before reading these.
"""

import os

# Default STT checkpoint: Systran's CTranslate2 build of distil-whisper
# medium.en. Chosen by live benchmark on this i7-9750H (2026-08-26),
# deviating from CLAUDE.md's distil-large-v3 pin with user sign-off:
# medium.en transcribed the test clip in 4.5s vs 7.7-9.7s for
# distil-large-v3, while large-v3-turbo measured slower still (11.9s;
# encoder-bound on CPU). Override without code edits, e.g.
# STT_MODEL=Systran/faster-distil-whisper-large-v3
STT_MODEL = os.environ.get("STT_MODEL", "Systran/faster-distil-whisper-medium.en")

# Physical cores of this i7-9750H. CTranslate2's default threading measures
# ~51s to transcribe a 2.7s utterance here; cpu_threads=6 measures ~9.7s.
# Hyperthreads (12) make no further difference.
CPU_THREADS = 6

# The former default, z-ai/glm-5.2:free, returned HTTP 404 from OpenRouter on
# 2026-09-08. This replacement was verified to return a short chat response.
# Override via OPENROUTER_MODEL without editing code.
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "inclusionai/ling-3.0-flash-sante:free"
)

# This model can spend tokens on internal reasoning before emitting speakable
# text. 256 leaves room for the concise response requested by SYSTEM_PROMPT.
OPENROUTER_MAX_TOKENS = int(os.environ.get("OPENROUTER_MAX_TOKENS", "256"))
