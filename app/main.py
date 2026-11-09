"""
Sahayak Voice Assistant FastAPI Application Entrypoint.
Connects concrete adapters: Edge-TTS, Groq LLM, Qdrant Vector Store, and Deepgram STT.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.services.voice_orchestrator import VoiceRAGOrchestrator
from app.api.websocket_endpoint import get_voice_router
from app.adapters.tts_edge import EdgeTTSAdapter
from app.adapters.tts_cartesia import CartesiaTTSAdapter
from app.adapters.llm_groq import GroqLLMAdapter
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter
from app.adapters.stt_deepgram import DeepgramSTTAdapter
from app.adapters.search_tavily import TavilySearchAdapter
from app.adapters.semantic_router import SemanticRouterAdapter
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
    search_adapter = (
        TavilySearchAdapter(api_key=settings.TAVILY_API_KEY)
        if settings.WEB_SEARCH_ENABLED
        else None
    )
    router_adapter = (
        SemanticRouterAdapter()
        if settings.SEMANTIC_ROUTER_ENABLED
        else None
    )

    # Wire into async orchestrator
    orchestrator = VoiceRAGOrchestrator(
        stt=stt_adapter,
        vdb=vdb_adapter,
        llm=llm_adapter,
        tts=tts_adapter,
        search=search_adapter,
        router=router_adapter,
    )

    voice_router = get_voice_router(orchestrator)
    app.include_router(voice_router)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
    async def serve_index():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Sahayak Voice Assistant</h1><p>UI loading...</p>")

    @app.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "service": "sahayak-voice-assistant",
            "tts_provider": tts_provider_name,
            "voice": settings.CARTESIA_VOICE_ID if settings.CARTESIA_API_KEY else settings.EDGE_VOICE,
            "llm_model": settings.GROQ_MODEL,
            "vector_db": settings.QDRANT_URL,
            "web_search_enabled": bool(settings.TAVILY_API_KEY and settings.WEB_SEARCH_ENABLED),
            "semantic_router_enabled": bool(router_adapter and settings.SEMANTIC_ROUTER_ENABLED),
        }

    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
