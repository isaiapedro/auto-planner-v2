from pathlib import Path

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_knowledge_root() -> str:
    api_dir = Path(__file__).resolve().parent
    try:
        # config.py lives at services/planner/implementation/tools/api/.  The
        # workspace root is five parents up (not four, which is services/).
        repo_root = api_dir.parents[5]
        candidate = repo_root / "knowledge"
        if candidate.is_dir():
            return str(candidate)
    except IndexError:
        pass
    return "/knowledge"


def _workspace_file(relative_path: str) -> str:
    """Return a local-workspace contract path; Compose overrides these paths."""
    api_dir = Path(__file__).resolve().parent
    try:
        return str(api_dir.parents[5] / relative_path)
    except IndexError:
        return relative_path


def _default_personal_transcripts() -> str:
    api_dir = Path(__file__).resolve().parent
    try:
        repo_root = api_dir.parents[5]
        candidate = repo_root / "personal" / "planner" / "memos" / "transcripts"
        candidate.mkdir(parents=True, exist_ok=True)
        return str(candidate)
    except IndexError:
        pass
    return "./personal/planner/memos/transcripts"


def _default_personal_memos() -> str:
    api_dir = Path(__file__).resolve().parent
    try:
        repo_root = api_dir.parents[5]
        candidate = repo_root / "personal" / "planner" / "memos"
        candidate.mkdir(parents=True, exist_ok=True)
        return str(candidate)
    except IndexError:
        pass
    return "./personal/planner/memos"


def _default_personal_insights() -> str:
    api_dir = Path(__file__).resolve().parent
    try:
        repo_root = api_dir.parents[5]
        candidate = repo_root / "personal" / "planner" / "insights"
        if candidate.is_dir():
            return str(candidate)
    except IndexError:
        pass
    return "./personal/planner/insights"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/pios"
    # Required for any LAN-accessible API. Keep this only in untracked local
    # environment configuration; never put it in mobile source code.
    pios_api_token: SecretStr
    api_allowed_origins: str = ""
    ollama_host: str = "http://localhost:11434"
    # Scheduling/allocation needs more reliable constrained reasoning than
    # per-memo feature extraction — llama3.2 (3B) returned empty, self-
    # contradictory plans on real goal data. qwen3:8b is already pulled locally.
    ollama_planning_model: str = "qwen3:8b"
    personal_transcripts_path: str = _default_personal_transcripts()
    personal_memos_path: str = _default_personal_memos()
    personal_insights_path: str = _default_personal_insights()
    # `large-v3` on CPU makes even short memos feel stalled.  `small` is a
    # good local default and can be overridden for accuracy-sensitive work.
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    memo_max_upload_bytes: int = 536_870_912  # 512 MiB; duration is unlimited
    memo_worker_poll_seconds: float = 0.5
    memo_worker_max_attempts: int = 3
    memo_worker_retry_seconds: int = 15
    google_credentials_path: str = "./credentials/google_client_secret.json"
    google_token_path: str = "./credentials/google_token.json"
    # First entry is the write target (DEFAULT_CALENDAR_ID) — only isaiacontato@gmail.com
    # has writer access under the current OAuth grant; the others are read-only context.
    google_calendar_ids: str = (
        "isaiacontato@gmail.com,pedro.souza@petlove.com.br,pedrosouza@estudante.ufscar.br"
    )
    knowledge_root_path: str = _default_knowledge_root()
    # In containers these point to three explicitly mounted Registry contracts,
    # not to the host workspace root. The catalog service only resolves targets
    # inside the existing /personal and /knowledge mounts.
    account_workspace_manifest_path: str = _workspace_file("manifest.yaml")
    account_catalog_path: str = _workspace_file("registry/account_catalog.yaml")
    account_repository_registry_path: str = _workspace_file("registry/repositories.yaml")
    planning_horizon_days: int = 7
    max_daily_exploration_minutes: int = 240
    planning_repair_attempts: int = 3

    @model_validator(mode="after")
    def validate_personal_planner_boundary(self) -> "Settings":
        """Keep every Planner-owned Personal path under one declared root.

        The API has no generic Personal-filesystem capability.  An environment
        override may relocate the mounted Personal directory, but it may not
        split memos, transcripts, and insights across unrelated directories.
        """
        memos = Path(self.personal_memos_path).resolve()
        transcripts = Path(self.personal_transcripts_path).resolve()
        insights = Path(self.personal_insights_path).resolve()
        planner = memos.parent
        if (
            memos.name != "memos"
            or transcripts != memos / "transcripts"
            or insights != planner / "insights"
            or planner.name != "planner"
            or planner.parent.name != "personal"
        ):
            raise ValueError(
                "Planner Personal paths must remain under personal/planner "
                "(memos/, memos/transcripts/, insights/)"
            )
        return self


settings = Settings()
