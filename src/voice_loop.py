"""Sahayak Step 0 — single-mic conversational voice loop.

mic -> Silero VAD (+ Smart Turn) -> local Whisper STT -> OpenRouter chat LLM
-> Kokoro TTS (local) -> speakers.

Plain conversational loop only — nothing interview-specific, nothing persisted.
"""

from __future__ import annotations

import asyncio
from collections import deque
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from loguru import logger

# Repo-root .env (never committed). Safe no-op if the file is absent.
load_dotenv()

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    LLMFullResponseEndFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

from core.config import OPENROUTER_MAX_TOKENS, OPENROUTER_MODEL, STT_MODEL
from core.timing import TurnTiming
from prompts import SYSTEM_PROMPT
from transcribe import FastDistilWhisperSTT

TIMING_LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "local" / "turn_timings.jsonl"


class TurnTimingObserver(BaseObserver):
    """Bridge Pipecat turn frames to the dependency-free ``TurnTiming`` API."""

    def __init__(self, timing_log_path: Path | None = None) -> None:
        super().__init__()
        self._timing_log_path = timing_log_path
        self._turn: TurnTiming | None = None
        self._active_stage: object | None = None
        self._active_stage_name: str | None = None
        self._seen_frame_ids: deque[str] = deque(maxlen=100)

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if frame.id in self._seen_frame_ids:
            return
        self._seen_frame_ids.append(frame.id)

        # VAD boundaries drive segmented Whisper. UserStartedSpeakingFrame is
        # also broadcast for the same turn and is followed by an ordinary
        # interruption broadcast, so it is not a stable timing boundary.
        if isinstance(frame, VADUserStartedSpeakingFrame):
            if self._active_stage_name == "vad":
                return
            self._emit_turn()
            self._turn = TurnTiming()
            self._start_stage("vad")
            return

        if self._turn is None:
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            if self._active_stage_name == "vad":
                self._finish_stage()
                self._start_stage("stt")
            return

        if isinstance(frame, TranscriptionFrame):
            if self._active_stage_name == "stt":
                self._finish_stage()
                self._start_stage("llm")
            return

        if isinstance(frame, (LLMFullResponseEndFrame, TTSStartedFrame)):
            if self._active_stage_name == "llm":
                self._finish_stage()
                self._start_stage("tts")
            return

        if isinstance(frame, TTSStoppedFrame):
            if self._active_stage_name == "tts":
                self._finish_stage()
            self._emit_turn()
            return

        if isinstance(frame, (CancelFrame, EndFrame)):
            self._emit_turn()

    def _start_stage(self, name: str) -> None:
        if self._turn is None:
            return
        stage = self._turn.stage(name)
        stage.__enter__()
        self._active_stage = stage
        self._active_stage_name = name

    def _finish_stage(self) -> None:
        if self._active_stage is None:
            return
        self._active_stage.__exit__(None, None, None)
        self._active_stage = None
        self._active_stage_name = None

    def _emit_turn(self) -> None:
        if self._turn is None:
            return
        self._finish_stage()
        print(self._turn.to_json())
        if self._timing_log_path is not None:
            self._timing_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._timing_log_path.open("a", encoding="utf-8") as timing_log:
                timing_log.write(self._turn.to_json() + "\n")
        self._turn = None


def _build_transport() -> LocalAudioTransport:
    return LocalAudioTransport(
        params=LocalAudioTransportParams(audio_in_enabled=True, audio_out_enabled=True)
    )


def _build_stt() -> FastDistilWhisperSTT:
    return FastDistilWhisperSTT(
        device="cpu",
        compute_type="int8",
        settings=FastDistilWhisperSTT.Settings(
            model=STT_MODEL,
            language=Language.EN,  # skip auto-detect: faster, avoids misfires on pauses
        ),
    )


def _build_tts() -> KokoroTTSService:
    return KokoroTTSService(settings=KokoroTTSService.Settings(voice="af_heart"))


def _build_llm() -> OpenRouterLLMService:
    return OpenRouterLLMService(
        api_key=os.environ["OPENROUTER_API_KEY"],
        settings=OpenRouterLLMService.Settings(
            model=OPENROUTER_MODEL,
            max_tokens=OPENROUTER_MAX_TOKENS,
            system_instruction=SYSTEM_PROMPT,
        ),
    )


def _build_pipeline() -> Pipeline:
    transport = _build_transport()
    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        # WhisperSTTService is segmented: it needs VAD start/stop frames to
        # know when to transcribe the buffered microphone audio. Keep Silero's
        # default parameters here; Step 0 does not tune VAD thresholds.
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    return Pipeline(
        [
            transport.input(),   # mic frames (16 kHz)
            _build_stt(),        # Whisper STT, local checkpoint
            user_aggregator,     # VAD + Smart Turn decide when your turn ends
            _build_llm(),        # plain conversational reply
            _build_tts(),        # Kokoro-82M, local (24 kHz)
            transport.output(),  # speakers
            assistant_aggregator,
        ]
    )


async def run_voice_loop() -> None:
    task = PipelineTask(
        _build_pipeline(),
        params=PipelineParams(enable_metrics=True),
        observers=[TurnTimingObserver(TIMING_LOG_PATH)],
    )
    await PipelineRunner(handle_sigint=True).run(task)


def main() -> None:
    # Pipecat debug output includes transcripts. Timing records are written
    # separately as metadata-only JSONL under data/local/.
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    if not os.environ.get("OPENROUTER_API_KEY"):
        logger.error(
            "OPENROUTER_API_KEY is not set. Export it, or create a .env at the "
            "repo root yourself containing OPENROUTER_API_KEY=sk-or-..."
        )
        sys.exit(1)
    try:
        asyncio.run(run_voice_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
