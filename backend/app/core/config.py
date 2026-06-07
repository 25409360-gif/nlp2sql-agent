import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _get_csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "NLP2SQL Agent API")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://nlp2sql:nlp2sql_password@localhost:5432/nlp2sql_demo",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_key_prefix: str = os.getenv("REDIS_KEY_PREFIX", "nlp2sql")
    redis_default_ttl_seconds: int = int(os.getenv("REDIS_DEFAULT_TTL_SECONDS", "3600"))
    db_schema: str = os.getenv("DB_SCHEMA", "public")
    vector_store_provider: str = os.getenv("VECTOR_STORE_PROVIDER", "chroma")
    chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8001"))
    chroma_collection_name: str = os.getenv("CHROMA_COLLECTION_NAME", "nlp2sql_schema")
    vector_store_startup_retries: int = int(os.getenv("VECTOR_STORE_STARTUP_RETRIES", "10"))
    vector_store_startup_retry_delay_seconds: float = float(
        os.getenv("VECTOR_STORE_STARTUP_RETRY_DELAY_SECONDS", "1.5")
    )
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "local")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "local-hash-v1")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "384"))
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
    embedding_timeout_seconds: float = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "10"))
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    llm_api_base_url: str = os.getenv("LLM_API_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "mock-llm")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
    llm_retry_backoff_seconds: float = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "1"))
    sql_default_limit: int = int(os.getenv("SQL_DEFAULT_LIMIT", "100"))
    sql_max_limit: int = int(os.getenv("SQL_MAX_LIMIT", "500"))
    sql_statement_timeout_ms: int = int(os.getenv("SQL_STATEMENT_TIMEOUT_MS", "5000"))
    sql_executor_max_rows: int = int(os.getenv("SQL_EXECUTOR_MAX_ROWS", "500"))
    cors_origins: list[str] = field(
        default_factory=lambda: _get_csv_env(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://localhost:8080",
        )
    )


settings = Settings()
