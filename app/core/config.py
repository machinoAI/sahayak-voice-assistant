"""
Application configuration management using Pydantic Settings.
"""

from typing import Optional, List, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server & Execution Profile
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    VOICE_PROFILE: str = "production"  # "production" | "local"

    # Multi-Provider Active Defaults & Failover Chains
    ACTIVE_STT_PROVIDER: str = "deepgram"
    ACTIVE_LLM_PROVIDER: str = "groq"
    ACTIVE_TTS_PROVIDER: str = "cartesia"
    TTS_PROVIDER: str = "cartesia"  # Legacy backward-compatibility alias

    LLM_FAILOVER_CHAIN: List[str] = ["groq", "gemini", "openai"]
    TTS_FAILOVER_CHAIN: List[str] = ["cartesia", "elevenlabs", "edge"]
    STT_FAILOVER_CHAIN: List[str] = ["deepgram", "sarvam"]

    FAILOVER_COOLDOWN_SECONDS: float = 60.0
    FAILOVER_MAX_RETRIES: int = 2

    # STT Provider: Deepgram
    DEEPGRAM_API_KEY: Optional[str] = None
    DEEPGRAM_MODEL: str = "nova-2"
    DEEPGRAM_LANGUAGE: str = "en-IN"
    DEFAULT_LANGUAGE: str = "auto"
    DEEPGRAM_LANGUAGE_MODELS: Dict[str, str] = {
        "en": "language=en-IN&model=nova-2",
        "hi": "language=hi&model=nova-2",
        "auto": "language=multi&model=nova-2",
    }

    # STT Provider: Sarvam AI & Local Whisper
    SARVAM_API_KEY: Optional[str] = None
    LOCAL_WHISPER_MODEL: str = "base"

    # LLM Providers
    # 1. Groq
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    # 2. Google Gemini
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3-flash-preview"
    # 3. OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: Optional[str] = None
    # 4. Anthropic Claude
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-haiku-20241022"
    # 5. Local / Ollama (OpenAI-compatible)
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3.2"

    # TTS Providers
    # 1. Cartesia Sonic
    CARTESIA_API_KEY: Optional[str] = None
    CARTESIA_VOICE_ID: Optional[str] = None
    # 2. Microsoft Edge-TTS
    EDGE_VOICE: str = "en-IN-NeerjaNeural"
    EDGE_TTS_INDIC_VOICE: str = "hi-IN-SwaraNeural"
    # 3. ElevenLabs
    ELEVENLABS_API_KEY: Optional[str] = None
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Default Rachel voice
    ELEVENLABS_MODEL_ID: str = "eleven_turbo_v2_5"

    # Vector DB (Qdrant) & Embeddings
    QDRANT_URL: Optional[str] = None  # None defaults to local disk path (qdrant_storage) or :memory:
    QDRANT_PATH: Optional[str] = "qdrant_storage"
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "sahayak_kb"
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384

    # External Web Search (Tavily) & CRAG Routing
    TAVILY_API_KEY: Optional[str] = None
    WEB_SEARCH_ENABLED: bool = True
    WEB_SEARCH_MAX_RESULTS: int = 2
    WEB_SEARCH_TIMEOUT_SECONDS: float = 4.0
    CRAG_HIGH_THRESHOLD: float = 0.82
    CRAG_LOW_THRESHOLD: float = 0.55
    SEMANTIC_ROUTER_ENABLED: bool = True

settings = Settings()
