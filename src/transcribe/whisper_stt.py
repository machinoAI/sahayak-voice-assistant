"""Local faster-whisper STT tuned for this machine's CPU."""

from loguru import logger
from pipecat.services.whisper.stt import WhisperSTTService

from core.config import CPU_THREADS


class _GreedyTranscribe:
    """Wraps a WhisperModel to force beam_size=1 (greedy) on every call.

    Greedy decoding is the recommended setting for distil checkpoints and is
    measurably faster than faster-whisper's beam_size=5 default.
    """

    def __init__(self, inner):
        self._inner = inner

    def transcribe(self, audio, **kwargs):
        # condition_on_previous_text=False stops hallucination carryover
        # across VAD-chunked segments (observed once live: bot's own phrase
        # reappearing as a phantom user turn).
        return self._inner.transcribe(
            audio, beam_size=1, condition_on_previous_text=False, **kwargs
        )


class FastDistilWhisperSTT(WhisperSTTService):
    """WhisperSTTService tuned for this machine's CPU.

    Overrides only model construction: the stock _load() builds WhisperModel
    without cpu_threads, leaving CTranslate2 badly under-threaded here.
    """

    def _load(self):
        from faster_whisper import WhisperModel

        logger.debug(f"Loading {self._settings.model} (cpu_threads={CPU_THREADS})...")
        self._model = _GreedyTranscribe(
            WhisperModel(
                self._settings.model,
                device=self._device,
                compute_type=self._compute_type,
                cpu_threads=CPU_THREADS,
            )
        )
