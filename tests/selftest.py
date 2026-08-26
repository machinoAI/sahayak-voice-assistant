"""Sahayak component checks — no mic permissions needed.

Verifies each piece of the live loop independently:
  1. TTS   — Kokoro-82M (ONNX) synthesizes a fixed phrase -> out.wav
  2. STT   — local Whisper (faster-whisper, int8, CPU) transcribes that wav
  3. Round-trip — transcript matches the phrase
  4. LLM   — one OpenRouter chat completion with the live-loop model+prompt
             (skipped if OPENROUTER_API_KEY is not set)

Run from repo root:
    PYTHONPATH=src .venv/bin/python tests/selftest.py
First run downloads models (~1.6 GB total) into the shared caches.
"""

import os
import re
import sys
import time
from pathlib import Path

import httpx
import soundfile as sf
from dotenv import load_dotenv

load_dotenv()

from core.config import CPU_THREADS, OPENROUTER_MODEL, STT_MODEL
from prompts import SYSTEM_PROMPT

PHRASE = "The quick brown fox jumps over the lazy dog."
OUT_WAV = Path(__file__).parent / "out.wav"

# Same cache location and URLs pipecat's KokoroTTSService uses.
KOKORO_DIR = Path.home() / ".cache" / "kokoro-onnx"
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def norm(text: str) -> str:
    return re.sub(r"[^a-z ]", "", text.lower()).strip()


def ensure_kokoro_files() -> None:
    """Download the ONNX model/voices if missing, via pipecat's own URLs."""
    import requests
    from pipecat.services.kokoro.tts import KOKORO_MODEL_URL, KOKORO_VOICES_URL

    for path, url in [(KOKORO_MODEL, KOKORO_MODEL_URL), (KOKORO_VOICES, KOKORO_VOICES_URL)]:
        if path.exists():
            continue
        print(f"downloading {url} -> {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    f.write(chunk)


def test_tts() -> None:
    print(f"[1] TTS: synthesizing {PHRASE!r}")
    ensure_kokoro_files()
    from kokoro_onnx import Kokoro

    t0 = time.time()
    kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    samples, rate = kokoro.create(PHRASE, voice="af_heart", lang="en-us")
    synth_s = time.time() - t0
    sf.write(OUT_WAV, samples, rate)
    duration = len(samples) / rate
    check(
        "tts.synthesize",
        1.0 < duration < 15.0,
        f"{duration:.2f}s audio in {synth_s:.1f}s @ {rate}Hz -> {OUT_WAV}",
    )


def test_stt() -> tuple[bool, str]:
    print(f"[2] STT: transcribing out.wav with {STT_MODEL} (int8, cpu, {CPU_THREADS} threads)")
    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(
        STT_MODEL, device="cpu", compute_type="int8", cpu_threads=CPU_THREADS
    )
    load_s = time.time() - t0

    t0 = time.time()
    segments, info = model.transcribe(str(OUT_WAV), beam_size=1, language="en")
    text = " ".join(seg.text for seg in segments).strip()
    stt_s = time.time() - t0
    check("stt.transcribe", bool(text), f"load {load_s:.1f}s, transcribe {stt_s:.1f}s: {text!r}")
    return norm(text) == norm(PHRASE), text


def test_llm() -> None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("[3] LLM: SKIPPED (OPENROUTER_API_KEY not set)")
        return
    print(f"[3] LLM: pinging OpenRouter {OPENROUTER_MODEL}")
    try:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": OPENROUTER_MODEL,
                "max_tokens": 80,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Say hello in one short sentence."},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        check("llm.ping", bool(content), repr(content[:140]))
    except Exception as exc:  # noqa: BLE001 — selftest reports any failure shape
        check("llm.ping", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    test_tts()
    matched, transcript = test_stt()
    check("roundtrip.match", matched)
    test_llm()

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)
