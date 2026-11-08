"""
Abstract component interfaces enforcing contracts across providers (STT, RAG, LLM, TTS).
"""

from typing import AsyncGenerator, Protocol, List
from pydantic import BaseModel

class RetrievedDocument(BaseModel):
    id: str
    text: str
    score: float

class STTClientProtocol(Protocol):
    async def stream_audio_frames(self, audio_generator: AsyncGenerator[bytes, None]) -> AsyncGenerator[str, None]:
        """Consumes raw PCM audio bytes and yields partial and final transcript strings."""
        ...

class VectorStoreProtocol(Protocol):
    async def hybrid_search(self, query: str, top_k: int = 2) -> List[RetrievedDocument]:
        """Executes hybrid dense + sparse vector search with Reciprocal Rank Fusion."""
        ...

class LLMClientProtocol(Protocol):
    async def stream_tokens(self, prompt: str) -> AsyncGenerator[str, None]:
        """Streams text completion tokens incrementally."""
        ...

class TTSClientProtocol(Protocol):
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Streams 16kHz PCM audio bytes for a text sentence or clause."""
        ...
