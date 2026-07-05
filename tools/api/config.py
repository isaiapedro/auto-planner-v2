from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/pios"
    ollama_host: str = "http://localhost:11434"
    ollama_extract_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"
    # Scheduling/allocation needs more reliable constrained reasoning than
    # per-memo feature extraction — llama3.2 (3B) returned empty, self-
    # contradictory plans on real goal data. qwen3:8b is already pulled locally.
    ollama_planning_model: str = "qwen3:8b"
    evidence_vault_path: str = "./evidence_vault"
    master_wiki_path: str = "./master_wiki"
    whisper_model: str = "large-v3"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    google_credentials_path: str = "./credentials/google_client_secret.json"
    google_token_path: str = "./credentials/google_token.json"
    # First entry is the write target (DEFAULT_CALENDAR_ID) — only isaiacontato@gmail.com
    # has writer access under the current OAuth grant; the others are read-only context.
    google_calendar_ids: str = (
        "isaiacontato@gmail.com,pedro.souza@petlove.com.br,pedrosouza@estudante.ufscar.br"
    )


settings = Settings()
