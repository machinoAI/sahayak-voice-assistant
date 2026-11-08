"""
Groq LLM streaming adapter implementing LLMClientProtocol.
Provides ~100-150ms Time-To-First-Token (TTFT) for low-latency conversational voice.
"""

from typing import AsyncGenerator
from groq import AsyncGroq
from app.core.config import settings

class GroqLLMAdapter:
    def __init__(self, api_key: str = settings.GROQ_API_KEY, model: str = settings.GROQ_MODEL):
        self.api_key = api_key
        self.model = model
        self.client = AsyncGroq(api_key=api_key) if api_key else None

    async def stream_tokens(self, prompt: str) -> AsyncGenerator[str, None]:
        if not self.client:
            # Fallback mock streaming if no API key is configured
            mock_response = [
                "Namaste! ", "I am Sahayak, ", "your voice assistant. ",
                "Please configure GROQ_API_KEY ", "in your .env file ",
                "to connect live LLM inference."
            ]
            for token in mock_response:
                yield token
            return

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=250,
            stream=True,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
