"""Application configuration, loaded from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="REPOXRAY_", extra="ignore")

    # Storage
    data_dir: Path = Path("./data")

    # GitHub
    github_token: str = ""  # optional; raises API rate limit and enables private repos

    # Analysis limits (keep the server healthy on huge repos)
    max_files: int = 6000            # files scanned in detail
    max_file_bytes: int = 600_000    # files bigger than this are counted but not read
    max_repo_mb: int = 800           # abort clones bigger than this
    clone_depth: int = 400           # commits of history to fetch for activity stats
    clone_timeout: int = 240         # seconds
    check_outdated: bool = True      # query PyPI / npm for latest versions
    workers: int = 2                 # concurrent analyses

    # LLM defaults (can be changed at runtime from the Settings page)
    llm_provider: str = "ollama"     # ollama | groq | gemini | openai | anthropic | none
    llm_base_url: str = "http://localhost:11434"   # Ollama URL
    llm_model: str = "llama3.1:8b"
    llm_api_key: str = ""            # generic key for REPOXRAY_LLM_PROVIDER (prefer the specific ones below)
    groq_api_key: str = ""           # https://console.groq.com/keys
    gemini_api_key: str = ""         # https://aistudio.google.com/apikey
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    embed_model: str = "nomic-embed-text"
    llm_timeout: int = 180
    llm_context_chars: int = 24_000  # context budget sent to the LLM

    # CORS
    cors_origins: str = "*"

    @property
    def repos_dir(self) -> Path:
        return self.data_dir / "repos"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "repoxray.db"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.data_dir, s.repos_dir, s.index_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s
