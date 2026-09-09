"""No-mic latency harness for Sahayak's Step 0 backend services.

This uses synthetic speech in memory and prints metadata only. It measures the
same Whisper model, OpenRouter streaming request, and Kokoro streaming output
as the live loop, but it does not exercise microphone VAD or audible barge-in.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from typing import Any

import httpx
import numpy as np
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from kokoro_onnx import Kokoro

from core.config import CPU_THREADS, OPENROUTER_MAX_TOKENS, OPENROUTER_MODEL, STT_MODEL
from core.timing import TurnTiming
from prompts import SYSTEM_PROMPT

load_dotenv()

KOKORO_DIR = os.path.expanduser("~/.cache/kokoro-onnx")
KOKORO_MODEL = os.path.join(KOKORO_DIR, "kokoro-v1.0.onnx")
KOKORO_VOICES = os.path.join(KOKORO_DIR, "voices-v1.0.bin")

CASES = {
    "short": ("Could you explain that again?", 0.0),
    "long_with_pause": (
        "I led a small project that had an unclear deadline and several competing priorities. "
        "I first clarified the goal with the team, then divided the work into smaller milestones. "
        "After checking progress each day, we shipped the most important part on time.",
        1.3,
    ),
    "silence": ("", 0.0),
}


def synthetic_audio(kokoro: Kokoro, text: str, pause_seconds: float) -> np.ndarray:
    """Create synthetic input audio in memory; no audio file is written."""
    if not text:
        return np.zeros(16_000 * 2, dtype=np.float32)

    if not pause_seconds:
        samples, rate = kokoro.create(text, voice="af_heart", lang="en-us")
        return resample_to_stt_rate(samples, rate)

    first, second = text.split(". ", 1)
    first_samples, rate = kokoro.create(first + ".", voice="af_heart", lang="en-us")
    second_samples, _ = kokoro.create(second, voice="af_heart", lang="en-us")
    samples = np.concatenate(
        [first_samples, np.zeros(int(rate * pause_seconds), dtype=np.float32), second_samples]
    )
    return resample_to_stt_rate(samples, rate)


def resample_to_stt_rate(samples: np.ndarray, source_rate: int) -> np.ndarray:
    """Convert generated 24 kHz test speech to Whisper's expected 16 kHz."""
    target_length = round(len(samples) * 16_000 / source_rate)
    source_positions = np.arange(len(samples))
    target_positions = np.linspace(0, len(samples) - 1, target_length)
    return np.interp(target_positions, source_positions, samples).astype(np.float32)


def transcribe(model: WhisperModel, audio: np.ndarray) -> str:
    segments, _ = model.transcribe(
        audio,
        beam_size=1,
        language="en",
        condition_on_previous_text=False,
    )
    return " ".join(segment.text for segment in segments).strip()


def stream_llm(transcript: str) -> tuple[str, float | None]:
    """Return streamed content and time from request start to first text token."""
    key = os.environ["OPENROUTER_API_KEY"]
    parts: list[str] = []
    first_token_ms: float | None = None
    started = time.monotonic()
    with httpx.stream(
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": OPENROUTER_MODEL,
            "stream": True,
            "max_tokens": OPENROUTER_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
        },
        timeout=120,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            content = json.loads(payload)["choices"][0].get("delta", {}).get("content")
            if content:
                if first_token_ms is None:
                    first_token_ms = round((time.monotonic() - started) * 1000, 2)
                parts.append(content)
    return "".join(parts).strip(), first_token_ms


async def stream_tts(kokoro: Kokoro, text: str) -> float | None:
    """Return time from synthesis start to Kokoro's first generated chunk."""
    started = time.monotonic()
    first_audio_ms: float | None = None
    async for _samples, _rate in kokoro.create_stream(
        text, voice="af_heart", lang="en-us", speed=1.0
    ):
        if first_audio_ms is None:
            first_audio_ms = round((time.monotonic() - started) * 1000, 2)
    return first_audio_ms


def run_case(
    name: str,
    text: str,
    pause_seconds: float,
    model: WhisperModel,
    input_kokoro: Kokoro,
    output_kokoro: Kokoro,
) -> dict[str, Any]:
    audio = synthetic_audio(input_kokoro, text, pause_seconds)
    turn = TurnTiming()

    with turn.stage("stt"):
        transcript = transcribe(model, audio)

    result: dict[str, Any] = {
        "case": name,
        "input_audio_seconds": round(len(audio) / 16_000, 2),
        "transcript_chars": len(transcript),
        "transcript_sha256": hashlib.sha256(transcript.encode()).hexdigest()[:12],
        "timing": turn.to_dict(),
    }
    if not transcript:
        result["outcome"] = "no_transcript_no_response"
        return result

    with turn.stage("llm"):
        reply, first_token_ms = stream_llm(transcript)
    with turn.stage("tts"):
        first_audio_ms = asyncio.run(stream_tts(output_kokoro, reply)) if reply else None

    result.update(
        {
            "outcome": "responded" if reply and first_audio_ms is not None else "response_failed",
            "llm_first_token_ms": first_token_ms,
            "tts_first_audio_ms": first_audio_ms,
            "timing": turn.to_dict(),
        }
    )
    return result


def main() -> None:
    requested_case = os.environ.get("LATENCY_CASE")
    cases = (
        {requested_case: CASES[requested_case]}
        if requested_case
        else CASES
    )
    model = WhisperModel(STT_MODEL, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS)
    input_kokoro = Kokoro(KOKORO_MODEL, KOKORO_VOICES)
    output_kokoro = Kokoro(KOKORO_MODEL, KOKORO_VOICES)
    for name, (text, pause_seconds) in cases.items():
        print(
            json.dumps(
                run_case(
                    name, text, pause_seconds, model, input_kokoro, output_kokoro
                )
            )
        )


if __name__ == "__main__":
    main()
