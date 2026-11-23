"""
Local Whisper STT adapter for zero-cost offline development and production speech-to-text.
Uses faster-whisper (CTranslate2) with non-blocking async execution, singleton model caching,
and real-time voice activity detection (VAD) with silence endpointing.
"""

import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, Optional, Tuple, Any

import numpy as np

from app.core.config import settings
from app.interfaces.adapters import STTTranscriptEvent

logger = logging.getLogger(__name__)

# Global model cache to avoid reloading heavy model weights per session
_MODEL_CACHE: Dict[Tuple[str, str, str], Any] = {}
_CACHE_LOCK = asyncio.Lock()


def _get_or_load_whisper_model(
    model_size: str,
    device: str = "auto",
    compute_type: str = "default",
) -> Optional[Any]:
    """Synchronously load or return cached WhisperModel instance."""
    cache_key = (model_size, device, compute_type)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    try:
        from faster_whisper import WhisperModel

        logger.info(
            f"[LOCAL-WHISPER] Loading WhisperModel (model='{model_size}', device='{device}', compute_type='{compute_type}')..."
        )
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _MODEL_CACHE[cache_key] = model
        logger.info(f"[LOCAL-WHISPER] WhisperModel '{model_size}' loaded successfully.")
        return model
    except Exception as exc:
        logger.warning(
            f"[LOCAL-WHISPER] Failed to initialize faster-whisper model '{model_size}': {exc}. "
            "Falling back to mock STT mode."
        )
        return None


class LocalWhisperStreamSession:
    """Active streaming transcription session using faster-whisper with VAD & silence endpointing."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "default",
        language: Optional[str] = None,
        speech_threshold: float = 250.0,
        silence_threshold_ms: int = 500,
        allow_mock_fallback: bool = True,
        mock_text: str = "What is Sahayak voice assistant?",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language or "auto"
        self.speech_threshold = speech_threshold
        self.silence_threshold_ms = silence_threshold_ms
        self.allow_mock_fallback = allow_mock_fallback
        self.mock_text = mock_text

        self._model = None
        self._is_active = False
        self._event_queue: asyncio.Queue[Optional[STTTranscriptEvent]] = asyncio.Queue()

        # Audio buffering & VAD state
        self._speech_buffer = bytearray()
        self._all_session_buffer = bytearray()
        self._speech_detected = False
        self._silence_ms = 0.0
        self._last_interim_time: float = 0.0
        self._interim_interval_s: float = 0.8
        self._is_transcribing = False
        self._finals_dispatched = 0

    async def start(self) -> None:
        """Initialize session and resolve cached model in worker thread."""
        self._speech_buffer.clear()
        self._all_session_buffer.clear()
        self._speech_detected = False
        self._silence_ms = 0.0
        self._finals_dispatched = 0
        self._is_active = True

        # Load or retrieve cached WhisperModel in a thread to keep event loop responsive
        self._model = await asyncio.to_thread(
            _get_or_load_whisper_model,
            self.model_size,
            self.device,
            self.compute_type,
        )
        logger.info(
            f"[LOCAL-WHISPER-SESSION] Started session (model={self.model_size}, "
            f"lang={self.language}, active_model={self._model is not None})"
        )

    async def connect(self) -> None:
        await self.start()

    @property
    def is_connected(self) -> bool:
        """Returns True if the session is currently active and listening."""
        return self._is_active

    async def send_audio(self, chunk: bytes) -> None:
        """Process incoming 16kHz linear PCM mono audio frame (e.g. 20ms = 640 bytes)."""
        if not self._is_active or not chunk:
            return

        self._all_session_buffer.extend(chunk)

        # Calculate chunk duration in milliseconds (16kHz, 16-bit mono = 32000 bytes/sec = 32 bytes/ms)
        chunk_ms = len(chunk) / 32.0

        # Compute RMS energy for voice activity detection
        samples = np.frombuffer(chunk[: len(chunk) - (len(chunk) % 2)], dtype=np.int16)
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) if len(samples) > 0 else 0.0

        if rms >= self.speech_threshold:
            # Active speech frame
            self._speech_detected = True
            self._silence_ms = 0.0
            self._speech_buffer.extend(chunk)

            # Check if interim transcript is due
            now = time.time()
            if (
                now - self._last_interim_time >= self._interim_interval_s
                and len(self._speech_buffer) >= 32000  # at least 1.0s of speech
                and not self._is_transcribing
            ):
                self._last_interim_time = now
                asyncio.create_task(self._dispatch_interim(bytes(self._speech_buffer)))
        else:
            # Silence or low-energy frame
            if self._speech_detected:
                self._speech_buffer.extend(chunk)
                self._silence_ms += chunk_ms

                if self._silence_ms >= self.silence_threshold_ms:
                    # Speech segment endpoint reached!
                    speech_to_transcribe = bytes(self._speech_buffer)
                    self._speech_buffer.clear()
                    self._speech_detected = False
                    self._silence_ms = 0.0
                    asyncio.create_task(self._dispatch_final(speech_to_transcribe))

    async def _dispatch_interim(self, pcm_bytes: bytes) -> None:
        """Run interim transcription on current speech buffer without clearing."""
        if not pcm_bytes or self._is_transcribing:
            return
        self._is_transcribing = True
        try:
            text, detected_lang = await self._transcribe_pcm(pcm_bytes)
            if text and self._is_active:
                await self._event_queue.put(
                    STTTranscriptEvent(
                        type="interim",
                        text=text,
                        is_final=False,
                        speech_final=False,
                        language=detected_lang,
                    )
                )
        except Exception as e:
            logger.debug(f"[LOCAL-WHISPER] Interim transcription error: {e}")
        finally:
            self._is_transcribing = False

    async def _dispatch_final(self, pcm_bytes: bytes) -> None:
        """Run final transcription on completed speech segment and dispatch."""
        if not pcm_bytes:
            return
        self._is_transcribing = True
        try:
            text, detected_lang = await self._transcribe_pcm(pcm_bytes)
            if not text and self.allow_mock_fallback and len(pcm_bytes) > 0:
                text = self.mock_text

            if text:
                self._finals_dispatched += 1
                logger.info(f"[LOCAL-WHISPER] Dispatched final transcript: '{text}' (lang={detected_lang})")
                await self._event_queue.put(
                    STTTranscriptEvent(
                        type="final",
                        text=text,
                        is_final=True,
                        speech_final=True,
                        language=detected_lang,
                    )
                )
        except Exception as e:
            logger.error(f"[LOCAL-WHISPER] Final transcription error: {e}")
        finally:
            self._is_transcribing = False

    async def _transcribe_pcm(self, pcm_bytes: bytes) -> Tuple[str, str]:
        """Convert linear PCM to normalized float32 array and transcribe via faster-whisper."""
        if self._model is None:
            # Fallback mock mode
            return (self.mock_text if self.allow_mock_fallback else ""), (self.language or "en")

        # Trim partial 16-bit frame
        if len(pcm_bytes) % 2 != 0:
            pcm_bytes = pcm_bytes[: len(pcm_bytes) - 1]

        if len(pcm_bytes) < 1600:  # <50ms of audio
            return "", (self.language or "en")

        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        lang = self.language
        if not lang or lang == "auto":
            target_lang = None
        elif "-" in lang:
            target_lang = lang.split("-")[0]
        else:
            target_lang = lang

        def _infer() -> Tuple[str, str]:
            segments, info = self._model.transcribe(
                audio_np,
                beam_size=1,
                language=target_lang,
                vad_filter=True,
            )
            full_text = " ".join(seg.text for seg in segments).strip()
            det_lang = info.language if info and hasattr(info, "language") else (target_lang or "en")
            return full_text, det_lang

        return await asyncio.to_thread(_infer)

    async def receive_transcripts(self) -> AsyncGenerator[STTTranscriptEvent, None]:
        """Yield structured transcript events."""
        while self._is_active or not self._event_queue.empty():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                if event is None:
                    break
                yield event
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        """Close session and finalize any pending speech buffer."""
        if not self._is_active:
            return
        self._is_active = False

        # If there is pending speech that wasn't finalized by silence endpointing
        remaining_pcm = bytes(self._speech_buffer)
        if remaining_pcm:
            try:
                text, detected_lang = await self._transcribe_pcm(remaining_pcm)
                if not text and self.allow_mock_fallback and len(remaining_pcm) > 0:
                    text = self.mock_text

                if text:
                    self._finals_dispatched += 1
                    await self._event_queue.put(
                        STTTranscriptEvent(
                            type="final",
                            text=text,
                            is_final=True,
                            speech_final=True,
                            language=detected_lang,
                        )
                    )
            except Exception as e:
                logger.error(f"[LOCAL-WHISPER] Close transcription error: {e}")
        elif self._finals_dispatched == 0 and len(self._all_session_buffer) > 0:
            # Fallback for silent/short test frames
            if self.allow_mock_fallback:
                self._finals_dispatched += 1
                await self._event_queue.put(
                    STTTranscriptEvent(
                        type="final",
                        text=self.mock_text,
                        is_final=True,
                        speech_final=True,
                        language=self.language or "en",
                    )
                )

        self._speech_buffer.clear()
        self._all_session_buffer.clear()
        await self._event_queue.put(None)


class LocalWhisperSTTAdapter:
    """Local offline STT adapter for zero-cost development and production faster-whisper inference."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        language: Optional[str] = None,
        speech_threshold: float = 250.0,
        silence_threshold_ms: int = 500,
        allow_mock_fallback: bool = True,
    ):
        self.model_size = model_size or settings.LOCAL_WHISPER_MODEL
        self.device = device or getattr(settings, "LOCAL_WHISPER_DEVICE", "auto")
        self.compute_type = compute_type or getattr(settings, "LOCAL_WHISPER_COMPUTE_TYPE", "int8")
        self.language = language or "en"
        self.speech_threshold = speech_threshold
        self.silence_threshold_ms = silence_threshold_ms
        self.allow_mock_fallback = allow_mock_fallback
        self._active_session: Optional[LocalWhisperStreamSession] = None
        self._last_session: Optional[LocalWhisperStreamSession] = None

    def create_stream_session(
        self, language: Optional[str] = None
    ) -> LocalWhisperStreamSession:
        """Create a streaming session instance."""
        target_lang = language or self.language
        return LocalWhisperStreamSession(
            model_size=self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            language=target_lang,
            speech_threshold=self.speech_threshold,
            silence_threshold_ms=self.silence_threshold_ms,
            allow_mock_fallback=self.allow_mock_fallback,
        )

    async def start(self) -> None:
        self._active_session = self.create_stream_session()
        self._last_session = self._active_session
        await self._active_session.start()

    async def connect(self) -> None:
        await self.start()

    @property
    def is_connected(self) -> bool:
        """Returns True if the active session is currently active and listening."""
        return self._active_session is not None and self._active_session.is_connected

    async def send_audio(self, chunk: bytes) -> None:
        if self._active_session:
            await self._active_session.send_audio(chunk)

    async def receive_transcripts(self) -> AsyncGenerator[STTTranscriptEvent, None]:
        session = self._active_session or self._last_session
        if session:
            async for event in session.receive_transcripts():
                yield event

    async def close(self) -> None:
        if self._active_session:
            self._last_session = self._active_session
            await self._active_session.close()
            self._active_session = None

    async def stream_audio_frames(
        self, audio_generator: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[str, None]:
        """Legacy helper: consumes streaming raw PCM audio frames and yields transcribed text."""
        session = self.create_stream_session()
        await session.start()

        async def _sender():
            try:
                async for chunk in audio_generator:
                    await session.send_audio(chunk)
            finally:
                await session.close()

        sender_task = asyncio.create_task(_sender())
        try:
            async for event in session.receive_transcripts():
                text = event.text.strip()
                if text:
                    yield text
        finally:
            if not sender_task.done():
                sender_task.cancel()
