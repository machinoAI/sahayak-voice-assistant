"""
Failover orchestration for TTS providers with circuit breaker cooldowns and turn stickiness.
"""

import time
import logging
from typing import AsyncGenerator, List, Dict, Optional, Tuple

from app.interfaces.adapters import TTSClientProtocol

logger = logging.getLogger(__name__)

class FailoverTTSAdapter:
    """Orchestrates an ordered chain of TTS adapters with turn-sticky failover."""

    def __init__(
        self,
        adapters: List[Tuple[str, TTSClientProtocol]],
        cooldown_seconds: float = 60.0,
    ):
        if not adapters:
            raise ValueError("FailoverTTSAdapter requires at least one adapter.")
        self.adapters = adapters
        self.cooldown_seconds = cooldown_seconds
        self.cooldowns: Dict[str, float] = {}
        # Stickiness for the current conversational turn
        self.active_turn_provider: Optional[str] = None
        self.failover_occurred: bool = False

    def reset_turn(self) -> None:
        """Resets turn stickiness boundary at the end of a conversational turn."""
        self.active_turn_provider = None
        self.failover_occurred = False

    def _is_cooling_down(self, provider_name: str) -> bool:
        expiry = self.cooldowns.get(provider_name, 0.0)
        return time.time() < expiry

    def _mark_failed(self, provider_name: str, error: Exception) -> None:
        logger.warning(
            f"[FAILOVER-TTS] Provider '{provider_name}' failed with {type(error).__name__}: {error}. "
            f"Placing on cooldown for {self.cooldown_seconds:.1f}s."
        )
        self.cooldowns[provider_name] = time.time() + self.cooldown_seconds

    async def synthesize_stream(
        self,
        text: str,
        voice_override: Optional[str] = None,
        language: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Synthesizes speech with fallback and turn stickiness."""
        # If a provider was already selected during this turn, try it first
        start_index = 0
        if self.active_turn_provider:
            for idx, (name, _) in enumerate(self.adapters):
                if name == self.active_turn_provider and not self._is_cooling_down(name):
                    start_index = idx
                    break

        ordered_adapters = self.adapters[start_index:] + self.adapters[:start_index]
        last_exception: Optional[Exception] = None

        for name, adapter in ordered_adapters:
            if self._is_cooling_down(name):
                continue

            try:
                chunk_count = 0
                async for chunk in adapter.synthesize_stream(text, voice_override=voice_override, language=language):
                    chunk_count += 1
                    yield chunk

                if chunk_count > 0:
                    # Successfully synthesized; stick to this provider for the remainder of the turn
                    self.active_turn_provider = name
                    self.failover_occurred = (name != self.adapters[0][0])
                    return

                # If 0 chunks yielded without exception, consider it a failure
                raise RuntimeError(f"TTS provider '{name}' yielded 0 audio bytes")

            except Exception as e:
                last_exception = e
                self._mark_failed(name, e)
                # Clear active provider to permit fallback
                self.active_turn_provider = None

        logger.error(f"[FAILOVER-TTS] All TTS providers exhausted. Last error: {last_exception}")
        if last_exception:
            raise last_exception
        raise RuntimeError("All TTS providers in failover chain are currently cooling down.")
