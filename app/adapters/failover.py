"""
Failover orchestration for LLM providers with circuit breaker cooldowns and prefix continuation.
"""

import time
import logging
from typing import AsyncGenerator, List, Dict, Optional, Union, Tuple, Any

from app.interfaces.adapters import LLMClientProtocol, LLMMessage

logger = logging.getLogger(__name__)

class FailoverLLMAdapter:
    """Orchestrates an ordered chain of LLM adapters with automated failover and prefix continuation."""

    def __init__(
        self,
        adapters: List[Tuple[str, LLMClientProtocol]],
        cooldown_seconds: float = 60.0,
    ):
        if not adapters:
            raise ValueError("FailoverLLMAdapter requires at least one adapter.")
        self.adapters = adapters
        self.cooldown_seconds = cooldown_seconds
        # provider_name -> unix timestamp until which it is suspended
        self.cooldowns: Dict[str, float] = {}

    @property
    def model(self) -> str:
        # Return the model of the first available provider
        for name, adapter in self.adapters:
            if not self._is_cooling_down(name):
                return f"{name}:{adapter.model}"
        return f"{self.adapters[0][0]}:{self.adapters[0][1].model}"

    def _is_cooling_down(self, provider_name: str) -> bool:
        expiry = self.cooldowns.get(provider_name, 0.0)
        return time.time() < expiry

    def _mark_failed(self, provider_name: str, error: Exception) -> None:
        cooldown = self.cooldown_seconds
        # Check if error has Retry-After attribute or response headers
        if hasattr(error, "response") and getattr(error, "response") is not None:
            headers = getattr(error.response, "headers", {})
            retry_after = headers.get("retry-after") or headers.get("Retry-After")
            if retry_after:
                try:
                    cooldown = max(float(retry_after), 5.0)
                except ValueError:
                    pass
        logger.warning(
            f"[FAILOVER-LLM] Provider '{provider_name}' failed with {type(error).__name__}: {error}. "
            f"Placing on cooldown for {cooldown:.1f}s."
        )
        self.cooldowns[provider_name] = time.time() + cooldown

    def _prepare_continuation(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        accumulated_text: str,
    ) -> List[Dict[str, str]]:
        """Constructs message history with partial generated text for prefix continuation."""
        messages: List[Dict[str, str]] = []
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        elif isinstance(prompt, list):
            for item in prompt:
                if isinstance(item, LLMMessage):
                    messages.append({"role": item.role, "content": item.content})
                elif isinstance(item, dict):
                    messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})
                else:
                    messages.append({"role": "user", "content": str(item)})

        if accumulated_text.strip():
            messages.append({"role": "assistant", "content": accumulated_text})
            # Add directive for assistant to finish the thought seamlessly
            messages.append({
                "role": "user",
                "content": "Please continue and complete the previous thought or sentence directly from where you left off without repeating."
            })

        return messages

    async def stream_tokens(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams tokens with failover and prefix continuation."""
        last_exception: Optional[Exception] = None
        accumulated_text = ""
        current_prompt = prompt

        for name, adapter in self.adapters:
            if self._is_cooling_down(name):
                logger.info(f"[FAILOVER-LLM] Skipping '{name}' (in cooldown).")
                continue

            try:
                logger.info(f"[FAILOVER-LLM] Attempting generation with '{name}' (model: {adapter.model}).")
                async for token in adapter.stream_tokens(current_prompt, system_prompt=system_prompt):
                    accumulated_text += token
                    yield token
                # Success - return once generator exhausts cleanly
                return

            except Exception as e:
                last_exception = e
                self._mark_failed(name, e)

                # Prepare prefix continuation for the next fallback in chain
                if accumulated_text:
                    logger.info(f"[FAILOVER-LLM] Switching to next provider with prefix continuation ({len(accumulated_text)} chars generated).")
                    current_prompt = self._prepare_continuation(prompt, accumulated_text)

        # If all available providers failed
        logger.error(f"[FAILOVER-LLM] All LLM providers in chain exhausted. Last error: {last_exception}")
        if last_exception:
            raise last_exception
        raise RuntimeError("All LLM providers in failover chain are currently cooling down.")
