from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # LLM
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    # GCP
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"

    # Postgres
    postgres_dsn: str = "postgresql://agent:agent@localhost:5432/agent"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Budgets (Invariant 7)
    max_repair_attempts: int = 3
    max_llm_calls: int = 8
    max_bytes_scanned: int = 15 * 1024 * 1024 * 1024  # 15 GB

    log_level: str = "INFO"


settings = Settings()
