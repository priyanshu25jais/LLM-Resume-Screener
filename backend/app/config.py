"""Application settings, read from environment variables / backend/.env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Settings:
    APP_NAME = "LLM Resume Screening System"
    VERSION = "1.0.0"

    DATA_DIR = Path(_env("DATA_DIR") or BASE_DIR / "data")
    DATABASE_URL = _env("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'screener.db').as_posix()}"
    UPLOAD_DIR = DATA_DIR / "uploads"
    MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 10)

    # LLM provider: auto | gemini | openai | groq | ollama | offline
    LLM_PROVIDER = _env("LLM_PROVIDER", "auto").lower()
    # Backup providers tried in order when the main one fails or runs out of quota:
    # auto = every other provider that has a key | none | a list such as "groq,openai"
    LLM_FALLBACKS = _env("LLM_FALLBACKS", "auto").lower()
    LLM_TEMPERATURE = _float("LLM_TEMPERATURE", 0.1)
    LLM_TIMEOUT = _float("LLM_TIMEOUT", 90)
    MAX_CONCURRENCY = _int("MAX_CONCURRENCY", 3)
    LLM_REQUESTS_PER_MINUTE = _int("LLM_REQUESTS_PER_MINUTE", 0)
    LLM_MAX_OUTPUT_TOKENS = _int("LLM_MAX_OUTPUT_TOKENS", 4096)
    LLM_REASONING_EFFORT = _env("LLM_REASONING_EFFORT", "low").lower()

    GEMINI_API_KEY = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
    GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_EMBED_MODEL = _env("GEMINI_EMBED_MODEL", "gemini-embedding-001")

    OPENAI_API_KEY = _env("OPENAI_API_KEY")
    OPENAI_BASE_URL = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-5-mini")
    OPENAI_EMBED_MODEL = _env("OPENAI_EMBED_MODEL", "text-embedding-3-small")

    GROQ_API_KEY = _env("GROQ_API_KEY")
    GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-120b")

    OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3.1:8b")
    OLLAMA_EMBED_MODEL = _env("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # Embeddings: auto | gemini | openai | ollama | local | tfidf
    EMBEDDING_PROVIDER = _env("EMBEDDING_PROVIDER", "auto").lower()
    LOCAL_EMBED_MODEL = _env("LOCAL_EMBED_MODEL", "all-MiniLM-L6-v2")

    SESSION_DAYS = _int("SESSION_DAYS", 7)
    ALLOW_REGISTRATION = _bool("ALLOW_REGISTRATION", True)
    REQUIRE_APPROVAL = _bool("REQUIRE_APPROVAL", True)
    DEMO_LOGIN = _bool("DEMO_LOGIN", True)

    DELETION_GRACE_DAYS = _int("DELETION_GRACE_DAYS", 30)
    AUDIT_RETENTION_DAYS = _int("AUDIT_RETENTION_DAYS", 365)

    FLAG_UPLOADS_PER_HOUR = _int("FLAG_UPLOADS_PER_HOUR", 100)
    FLAG_DUPLICATES_PER_DAY = _int("FLAG_DUPLICATES_PER_DAY", 10)
    FLAG_FOREIGN_ACCESS = _int("FLAG_FOREIGN_ACCESS", 5)

    CORS_ORIGINS = [o.strip() for o in _env(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if o.strip()]


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
