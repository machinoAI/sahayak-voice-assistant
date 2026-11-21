"""
Consolidated OpenAI-compatible LLM streaming adapter.
Supports Groq, OpenAI, Google Gemini (OpenAI endpoint), and local Ollama/vLLM endpoints.
"""

import asyncio
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional, Union
from openai import AsyncOpenAI

from app.interfaces.adapters import LLMMessage

logger = logging.getLogger(__name__)

class OpenAICompatibleLLMAdapter:
    """Async streaming LLM adapter using the standard OpenAI completions API."""

    def __init__(
        self,
        provider: str = "openai",
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 512,
        timeout: float = 15.0,
    ):
        self.provider = provider.lower()
        self._model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.base_url = base_url

        self._client: Optional[AsyncOpenAI] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def client(self) -> Optional[AsyncOpenAI]:
        if not self.api_key and self.provider != "ollama":
            return None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._client is None or (current_loop and self._client_loop != current_loop):
            effective_key = self.api_key or "ollama"
            self._client = AsyncOpenAI(
                api_key=effective_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            self._client_loop = current_loop
        return self._client

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._model = value

    def _normalize_messages(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

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

        return messages

    async def stream_tokens(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams text completion tokens incrementally."""
        if not self.client:
            # Fallback mock streaming if no API key is configured
            mock_response = [
                "Namaste! ", "I am Sahayak, ", "your voice assistant. ",
                f"Please configure {self.provider.upper()}_API_KEY ", "in your .env file ",
                "to connect live LLM inference."
            ]
            for token in mock_response:
                yield token
            return

        messages = self._normalize_messages(prompt, system_prompt)

        try:
            extra_body = {}
            if self.provider == "groq" and ("gpt-oss" in self._model or "reason" in self._model):
                extra_body["reasoning_format"] = "hidden"

            response = await self.client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore
                stream=True,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=extra_body if extra_body else None,
            )

            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"[{self.provider.upper()}] Error streaming tokens for model {self._model}: {e}")
            raise
