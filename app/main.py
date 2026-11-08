"""
Sahayak Voice Assistant FastAPI Application Entrypoint.
"""

from fastapi import FastAPI
from app.services.voice_orchestrator import VoiceRAGOrchestrator
from app.api.websocket_endpoint import get_voice_router
from app.interfaces.adapters import (
    RetrievedDocument,
    STTClientProtocol,
    VectorStoreProtocol,
    LLMClientProtocol,
    TTSClientProtocol,
)
from typing import AsyncGenerator, List

# Default Mock / In-Memory Adapters for baseline testing & startup
class MockSTT:
    async def stream_audio_frames(self, audio_generator: AsyncGenerator[bytes, None]) -> AsyncGenerator[str, None]:
        yield "Hello Sahayak"

class MockVectorStore:
    async def hybrid_search(self, query: str, top_k: int = 2) -> List[RetrievedDocument]:
        return [
            RetrievedDocument(id="doc-1", text="Sahayak is a voice RAG assistant for multilingual queries.", score=0.92)
        ]

class MockLLM:
    async def stream_tokens(self, prompt: str) -> AsyncGenerator[str, None]:
        tokens = ["Namaste! ", "I am ", "Sahayak, ", "ready to ", "assist you."]
        for token in tokens:
            yield token

class MockTTS:
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        # Yield 3 dummy 20ms frames (640 bytes each)
        for _ in range(3):
            yield b"\x00" * 640

def create_app() -> FastAPI:
    app = FastAPI(
        title="Sahayak Voice Assistant API",
        version="0.1.0",
        description="High-performance async streaming Voice RAG backend.",
    )

    orchestrator = VoiceRAGOrchestrator(
        stt=MockSTT(),
        vdb=MockVectorStore(),
        llm=MockLLM(),
        tts=MockTTS(),
    )

    voice_router = get_voice_router(orchestrator)
    app.include_router(voice_router)

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "service": "sahayak-voice-assistant"}

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
