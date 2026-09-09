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
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import httpx
import soundfile as sf
from dotenv import load_dotenv

load_dotenv()

from core.config import CPU_THREADS, OPENROUTER_MAX_TOKENS, OPENROUTER_MODEL, STT_MODEL
from core.timing import TurnTiming
from pipecat.frames.frames import (
    InterruptionFrame,
    LLMFullResponseEndFrame,
    TranscriptionFrame,
    TTSStoppedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection
from prompts import SYSTEM_PROMPT
from voice_loop import TurnTimingObserver, _build_pipeline

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
                "max_tokens": OPENROUTER_MAX_TOKENS,
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


def test_timing() -> None:
    import json

    print("[4] Timing: verifying dependency-free stage records")
    turn = TurnTiming(turn_id="test-turn")
    for stage_name in ("vad", "stt", "llm", "tts"):
        with turn.stage(stage_name):
            time.sleep(0.01)

    data = json.loads(turn.to_json())
    stages = data.get("stages", [])
    valid_schema = (
        data.get("turn_id") == "test-turn"
        and [stage.get("name") for stage in stages] == ["vad", "stt", "llm", "tts"]
        and data.get("total_ms", 0) > 0
        and all(
            isinstance(stage.get("start_timestamp"), str)
            and isinstance(stage.get("end_timestamp"), str)
            and datetime.fromisoformat(stage["start_timestamp"])
            and datetime.fromisoformat(stage["end_timestamp"])
            and stage.get("duration_ms", -1) >= 0
            and stage.get("gap_before_ms", -1) >= 0
            for stage in stages
        )
    )
    detail = f"{len(stages)} stages, total {data.get('total_ms', 0):.2f}ms"
    check("timing.turn_record_schema", valid_schema, detail)


def test_timing_observer() -> None:
    import asyncio
    import json

    print("[5] Timing: verifying voice-loop frame adapter")

    async def _run() -> list[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            timing_log_path = Path(temp_dir) / "turn_timings.jsonl"
            observer = TurnTimingObserver(timing_log_path)
            frames = [
                VADUserStartedSpeakingFrame(),
                UserStartedSpeakingFrame(),
                InterruptionFrame(),
                VADUserStartedSpeakingFrame(),
                VADUserStoppedSpeakingFrame(),
                UserStoppedSpeakingFrame(),
                TranscriptionFrame(
                    text="hello", user_id="user", timestamp="2026-09-08T00:00:00Z"
                ),
                LLMFullResponseEndFrame(),
                TTSStoppedFrame(),
            ]
            records: list[str] = []
            with patch("builtins.print", records.append):
                for frame in frames:
                    await observer.on_push_frame(
                        FramePushed(
                            source=None,
                            destination=None,
                            frame=frame,
                            direction=FrameDirection.DOWNSTREAM,
                            timestamp=0,
                        )
                    )
            stored_records = timing_log_path.read_text(encoding="utf-8").splitlines()
        return records + stored_records

    records = asyncio.run(_run())
    data = json.loads(records[0]) if len(records) == 2 else {}
    stage_names = [stage.get("name") for stage in data.get("stages", [])]
    check(
        "timing.voice_loop_adapter",
        len(records) == 2
        and records[0] == records[1]
        and stage_names == ["vad", "stt", "llm", "tts"],
        f"{len(records)} emitted/stored records, stages {stage_names}",
    )


def test_pipeline_vad() -> None:
    print("[6] Pipeline: verifying local VAD is configured")
    # Pipeline construction needs a key value, but this check never sends a
    # request; keep the local-only selftest runnable without a real key.
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        pipeline = _build_pipeline()
    user_aggregator = next(
        processor
        for processor in pipeline.processors
        if type(processor).__name__ == "LLMUserAggregator"
    )
    vad = user_aggregator._params.vad_analyzer
    check(
        "pipeline.vad_configured",
        vad is not None,
        type(vad).__name__ if vad is not None else "missing",
    )


if __name__ == "__main__":
    test_tts()
    matched, transcript = test_stt()
    check("roundtrip.match", matched)
    test_llm()
    test_timing()
    test_timing_observer()
    test_pipeline_vad()

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)
