"""
Abstract component interfaces enforcing contracts across providers (STT, RAG, LLM, TTS).
"""

from typing import AsyncGenerator, Protocol, List
from enum import Enum
from pydantic import BaseModel

class QueryIntent(str, Enum):
    LOCAL_SCHEME_FAQ = "local_scheme_faq"
    REALTIME_TEMPORAL = "realtime_temporal"
    OUT_OF_DOMAIN = "out_of_domain"

class RetrievedDocument(BaseModel):
    id: str
    text: str
    score: float

class SemanticRouterProtocol(Protocol):
    def classify_intent(self, query: str) -> QueryIntent:
        """Classifies query intent into pre-defined routing categories in <1ms."""
        ...

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

class WebSearchProtocol(Protocol):
    async def search(self, query: str, max_results: int = 2) -> List[RetrievedDocument]:
        """Executes live web search and returns retrieved document snippets."""
        ...
