"""
Sahayak Voice Assistant FastAPI Application Entrypoint.
Connects concrete adapters: Edge-TTS, Groq LLM, Qdrant Vector Store, and Deepgram STT.
"""

from fastapi import FastAPI
from app.services.voice_orchestrator import VoiceRAGOrchestrator
from app.api.websocket_endpoint import get_voice_router
from app.adapters.tts_edge import EdgeTTSAdapter
from app.adapters.tts_cartesia import CartesiaTTSAdapter
from app.adapters.llm_groq import GroqLLMAdapter
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter
from app.adapters.stt_deepgram import DeepgramSTTAdapter
from app.core.config import settings

def create_app() -> FastAPI:
    app = FastAPI(
        title="Sahayak Voice Assistant API",
        version="0.1.0",
        description="High-performance async streaming Voice RAG backend.",
    )

    # Initialize concrete adapters (prefer Cartesia if key is configured, fallback to Edge-TTS)
    if settings.CARTESIA_API_KEY:
        tts_adapter = CartesiaTTSAdapter(
            api_key=settings.CARTESIA_API_KEY,
            voice_id=settings.CARTESIA_VOICE_ID,
        )
        tts_provider_name = "cartesia-sonic"
    else:
        tts_adapter = EdgeTTSAdapter(voice=settings.EDGE_VOICE)
        tts_provider_name = "edge-tts"

    llm_adapter = GroqLLMAdapter(api_key=settings.GROQ_API_KEY, model=settings.GROQ_MODEL)
    vdb_adapter = QdrantVectorStoreAdapter(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        collection_name=settings.QDRANT_COLLECTION,
    )
    stt_adapter = DeepgramSTTAdapter(api_key=settings.DEEPGRAM_API_KEY)

    # Wire into async orchestrator
    orchestrator = VoiceRAGOrchestrator(
        stt=stt_adapter,
        vdb=vdb_adapter,
        llm=llm_adapter,
        tts=tts_adapter,
    )

    voice_router = get_voice_router(orchestrator)
    app.include_router(voice_router)

    @app.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "service": "sahayak-voice-assistant",
            "tts_provider": tts_provider_name,
            "voice": settings.CARTESIA_VOICE_ID if settings.CARTESIA_API_KEY else settings.EDGE_VOICE,
            "llm_model": settings.GROQ_MODEL,
            "vector_db": settings.QDRANT_URL,
        }

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
