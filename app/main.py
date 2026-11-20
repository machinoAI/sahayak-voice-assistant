"""
Sahayak Voice Assistant FastAPI Application Entrypoint.
Connects concrete adapters: Edge-TTS, Cartesia, Groq LLM, Qdrant Vector Store, Deepgram STT, etc.
via centralized multi-provider factories.
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.services.voice_orchestrator import VoiceRAGOrchestrator
from app.api.websocket_endpoint import get_voice_router
from app.adapters.registry import (
    get_stt_adapter,
    get_llm_adapter,
    get_tts_adapter,
    list_supported_providers,
)
from app.adapters.vector_store_qdrant import QdrantVectorStoreAdapter
from app.adapters.search_tavily import TavilySearchAdapter
from app.adapters.semantic_router import SemanticRouterAdapter
from app.core.config import settings

def create_app() -> FastAPI:
    app = FastAPI(
        title="Sahayak Voice Assistant API",
        version="0.2.0",
        description="High-performance async streaming Voice RAG backend with multi-provider architecture.",
    )

    # Initialize concrete adapters via centralized registry
    tts_adapter = get_tts_adapter()
    indic_tts_adapter = get_tts_adapter("edge")
    llm_adapter = get_llm_adapter()
    stt_adapter = get_stt_adapter()

    vdb_adapter = QdrantVectorStoreAdapter(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        collection_name=settings.QDRANT_COLLECTION,
    )
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
        indic_tts=indic_tts_adapter,
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
            "voice_profile": settings.VOICE_PROFILE,
            "active_providers": {
                "stt": settings.ACTIVE_STT_PROVIDER,
                "llm": settings.ACTIVE_LLM_PROVIDER,
                "tts": settings.ACTIVE_TTS_PROVIDER or settings.TTS_PROVIDER,
            },
            "supported_providers": list_supported_providers(),
            "tts_provider": settings.ACTIVE_TTS_PROVIDER or settings.TTS_PROVIDER,
            "voice": settings.CARTESIA_VOICE_ID if settings.CARTESIA_API_KEY else settings.EDGE_VOICE,
            "indic_tts_voice": settings.EDGE_TTS_INDIC_VOICE,
            "default_language": settings.DEFAULT_LANGUAGE,
            "llm_model": settings.GROQ_MODEL,
            "vector_db": settings.QDRANT_URL,
            "web_search_enabled": bool(settings.TAVILY_API_KEY and settings.WEB_SEARCH_ENABLED),
            "semantic_router_enabled": bool(router_adapter and settings.SEMANTIC_ROUTER_ENABLED),
        }

    return app

app = create_app()
