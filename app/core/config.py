"""
Application configuration management using Pydantic Settings.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # STT Provider (Deepgram / Sarvam)
    DEEPGRAM_API_KEY: Optional[str] = None
    DEEPGRAM_MODEL: str = "nova-2"
    DEEPGRAM_LANGUAGE: str = "en-IN"
    SARVAM_API_KEY: Optional[str] = None

    # LLM Provider (Groq / Gemini)
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Vector DB (Qdrant)
    QDRANT_URL: str = ":memory:"  # In-memory by default for zero-friction local testing
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "sahayak_kb"

    # TTS Provider
    TTS_PROVIDER: str = "edge"  # "edge" (free) or "cartesia"
    CARTESIA_API_KEY: Optional[str] = None
    CARTESIA_VOICE_ID: Optional[str] = None
    EDGE_VOICE: str = "en-IN-NeerjaNeural"  # e.g., "en-IN-NeerjaNeural", "hi-IN-SwaraNeural"

    # External Web Search (Tavily)
    TAVILY_API_KEY: Optional[str] = None
    WEB_SEARCH_ENABLED: bool = True
    WEB_SEARCH_MAX_RESULTS: int = 2
    WEB_SEARCH_TIMEOUT_SECONDS: float = 2.5

settings = Settings()
