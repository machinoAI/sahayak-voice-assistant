"""
Anthropic Claude streaming LLM adapter.
"""

import logging
from typing import AsyncGenerator, List, Dict, Optional, Union
from anthropic import AsyncAnthropic

from app.interfaces.adapters import LLMMessage

logger = logging.getLogger(__name__)

class AnthropicClaudeAdapter:
    """Async streaming adapter for Anthropic Claude models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-haiku-20241022",
        temperature: float = 0.2,
        max_tokens: int = 512,
        timeout: float = 15.0,
    ):
        self._model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.client = AsyncAnthropic(
            api_key=api_key or "",
            timeout=timeout,
        )

    @property
    def model(self) -> str:
        return self._model

    def _prepare_payload(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        system_prompt: Optional[str] = None,
    ) -> tuple[Optional[str], List[Dict[str, str]]]:
        system_content = system_prompt
        messages: List[Dict[str, str]] = []

        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        elif isinstance(prompt, list):
            for item in prompt:
                role = item.role if isinstance(item, LLMMessage) else item.get("role", "user")
                content = item.content if isinstance(item, LLMMessage) else item.get("content", "")
                if role == "system":
                    system_content = f"{system_content}\n{content}" if system_content else content
                else:
                    messages.append({"role": role, "content": content})

        if not messages:
            messages.append({"role": "user", "content": "Hello"})

        return system_content, messages

    async def stream_tokens(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams text completion tokens incrementally from Anthropic."""
        system_content, messages = self._prepare_payload(prompt, system_prompt)

        try:
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "max_tokens": self.max_tokens,
            }
            if self.temperature is not None:
                kwargs["extra_body"] = {"temperature": self.temperature}
            if system_content:
                kwargs["system"] = system_content

            async with self.client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            logger.error(f"[ANTHROPIC] Error streaming tokens for model {self._model}: {e}")
            raise
