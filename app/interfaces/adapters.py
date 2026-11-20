"""
Abstract component interfaces enforcing contracts across providers (STT, RAG, LLM, TTS).
"""

from typing import AsyncGenerator, Protocol, List, Optional, Union, Dict, Any, runtime_checkable
from enum import Enum
from pydantic import BaseModel, Field

class QueryIntent(str, Enum):
    LOCAL_SCHEME_FAQ = "local_scheme_faq"
    REALTIME_TEMPORAL = "realtime_temporal"
    OUT_OF_DOMAIN = "out_of_domain"

class RetrievedDocument(BaseModel):
    id: str
    text: str
    score: float

class STTTranscriptEvent(BaseModel):
    """Normalized STT transcript event structure."""
    type: str = "transcript"  # "transcript", "speech_started", "speech_final", "utterance_end"
    text: str = ""
    is_final: bool = False
    speech_final: bool = False
    confidence: float = 1.0
    language: str = "en"
    words: List[Dict[str, Any]] = Field(default_factory=list)

    # Backward compatibility with dictionary access:
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

class LLMMessage(BaseModel):
    """Standard message payload for LLM completions."""
    role: str
    content: str

class SemanticRouterProtocol(Protocol):
    def classify_intent(self, query: str) -> QueryIntent:
        """Classifies query intent into pre-defined routing categories in <1ms."""
        ...

@runtime_checkable
class StreamingSTTProtocol(Protocol):
    """Full-duplex streaming Speech-to-Text session protocol."""
    async def start(self) -> None:
        """Initialize connection/session with the upstream STT provider."""
        ...

    async def send_audio(self, chunk: bytes) -> None:
        """Stream raw 16kHz PCM audio bytes."""
        ...

    async def receive_transcripts(self) -> AsyncGenerator[STTTranscriptEvent, None]:
        """Yield structured transcript events."""
        ...

    async def close(self) -> None:
        """Gracefully terminate STT stream and release resources."""
        ...

# Legacy & generic STT protocol compatibility:
class STTClientProtocol(Protocol):
    async def stream_audio_frames(self, audio_generator: AsyncGenerator[bytes, None]) -> AsyncGenerator[Union[str, STTTranscriptEvent], None]:
        """Consumes raw PCM audio bytes and yields partial and final transcript strings/events."""
        ...

class VectorStoreProtocol(Protocol):
    async def hybrid_search(self, query: str, top_k: int = 2) -> List[RetrievedDocument]:
        """Executes hybrid dense + sparse vector search with Reciprocal Rank Fusion."""
        ...

@runtime_checkable
class LLMClientProtocol(Protocol):
    """Streaming Large Language Model interface."""
    @property
    def model(self) -> str:
        """Identifier of the active underlying model."""
        ...

    async def stream_tokens(
        self,
        prompt: Union[str, List[LLMMessage], List[Dict[str, str]]],
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams text completion tokens incrementally."""
        ...

@runtime_checkable
class TTSClientProtocol(Protocol):
    """Streaming Text-to-Speech synthesis interface."""
    async def synthesize_stream(
        self,
        text: str,
        voice_override: Optional[str] = None,
        language: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """Streams audio bytes (16kHz PCM or MP3 chunks) for a text sentence or clause."""
        ...

class WebSearchProtocol(Protocol):
    async def search(self, query: str, max_results: int = 2) -> List[RetrievedDocument]:
        """Executes live web search and returns retrieved document snippets."""
        ...
