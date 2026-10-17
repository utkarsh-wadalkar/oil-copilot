from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The API and worker may run with the working directory set to backend/ or the
# repository root. Load the repository-root .env by absolute path so secrets are
# found regardless of cwd; real environment variables still take precedence.
_PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(_PROJECT_ENV), ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://copilot:copilot-dev-only@localhost:5432/copilot"
    dataset_root: str = "./dataset"
    analysis_date: str = "2026-10-17"
    ollama_api_key: str = ""
    ollama_base_url: str = "https://ollama.com"
    ollama_model: str = "gemma4:31b"
    embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "copilot-dev-only"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Projection worker / durable leases
    worker_poll_seconds: float = 2.0
    worker_lease_seconds: int = 120
    worker_max_attempts: int = 8
    worker_backoff_base_seconds: float = 5.0
    worker_backoff_max_seconds: float = 900.0
    worker_batch_limit: int = 25
    worker_id: str = ""

    # Self-hosted Mem0 semantic memory
    mem0_enabled: bool = True
    mem0_history_path: str = "/data/mem0/history.db"
    mem0_collection: str = "copilot_memories"
    mem0_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    mem0_embedding_dims: int = 384

    # Local CPU embeddings for document chunks
    embeddings_enabled: bool = True
    embeddings_max_tokens: int = 256

    # nao analytics sidecar (Task 3N)
    nao_enabled: bool = False
    nao_base_url: str = "http://nao:5005"
    nao_project_id: str = ""
    nao_chat_timeout_seconds: float = 45.0
    nao_poll_seconds: float = 1.0
    copilot_mcp_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
