import os


class Config:
    APP_NAME: str  = "RabbitOS"
    VERSION: str   = "1.0.0"
    DEBUG: bool    = os.getenv("DEBUG", "false").lower() == "true"
    HOST: str      = os.getenv("HOST", "0.0.0.0")
    PORT: int      = int(os.getenv("PORT", "8000"))

    # LLM
    LLM_PROVIDER: str     = os.getenv("LLM_PROVIDER", "mock")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    OPENAI_API_KEY: str   = os.getenv("OPENAI_API_KEY", "")
    OLLAMA_URL: str       = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "rabbit_os.db")

    # Security
    SECRET_KEY: str        = os.getenv("SECRET_KEY", "change-me-in-production")
    JWT_ALGORITHM: str     = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

    # Telemetry
    TELEMETRY_ENABLED: bool = os.getenv("TELEMETRY_ENABLED", "true").lower() == "true"


cfg = Config()
