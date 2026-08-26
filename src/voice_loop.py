"""Sahayak Step 0 — single-mic conversational voice loop.

mic -> Silero VAD (+ Smart Turn) -> local Whisper STT -> OpenRouter chat LLM
-> Kokoro TTS (local) -> speakers.

Plain conversational loop only — nothing interview-specific, nothing persisted.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from loguru import logger

# Repo-root .env (never committed). Safe no-op if the file is absent.
load_dotenv()

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.kokoro.tts import KokoroTTSService
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

from core.config import OPENROUTER_MODEL, STT_MODEL
from prompts import SYSTEM_PROMPT
from transcribe import FastDistilWhisperSTT


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
            system_instruction=SYSTEM_PROMPT,
        ),
    )


def _build_pipeline() -> Pipeline:
    transport = _build_transport()
    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
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
    task = PipelineTask(_build_pipeline(), params=PipelineParams(enable_metrics=True))
    await PipelineRunner(handle_sigint=True).run(task)


def main() -> None:
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
