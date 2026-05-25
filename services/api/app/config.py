from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


_DOTENV_LOADED = False


def _load_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return

    candidate_paths: list[Path] = []
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        candidate_paths.append(parent / ".env")
    candidate_paths.append(Path.cwd() / ".env")

    env_path = next((path for path in candidate_paths if path.exists()), None)
    if env_path is None:
        _DOTENV_LOADED = True
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)

    _DOTENV_LOADED = True


def _get_env(name: str, default: str | None = None) -> str | None:
    _load_dotenv()
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    if not stripped:
        return default
    return stripped


def get_database_url() -> str:
    return _get_env("DATABASE_URL", "postgresql://ezbet:ezbet@localhost:5433/ezbet") or (
        "postgresql://ezbet:ezbet@localhost:5433/ezbet"
    )


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str | None
    editorial_model: str
    search_model: str
    base_url: str
    timeout_seconds: int
    api_style: str
    provider_label: str
    web_search_enabled: bool
    web_search_live: bool
    web_search_context_size: str

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def get_openai_settings() -> OpenAISettings:
    default_model = _get_env("OPENAI_MODEL", "gpt-5-mini") or "gpt-5-mini"
    return OpenAISettings(
        api_key=_get_env("OPENAI_API_KEY"),
        editorial_model=_get_env("OPENAI_EDITORIAL_MODEL", default_model) or default_model,
        search_model=_get_env("OPENAI_SEARCH_MODEL", default_model) or default_model,
        base_url=_get_env("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1",
        timeout_seconds=int(_get_env("OPENAI_TIMEOUT_SECONDS", "45") or "45"),
        api_style=_get_env("OPENAI_API_STYLE", "responses") or "responses",
        provider_label=_get_env("OPENAI_PROVIDER_LABEL", "OpenAI") or "OpenAI",
        web_search_enabled=(_get_env("OPENAI_WEB_SEARCH_ENABLED", "true") or "true").lower()
        in {"1", "true", "yes", "on"},
        web_search_live=(_get_env("OPENAI_WEB_SEARCH_LIVE", "true") or "true").lower()
        in {"1", "true", "yes", "on"},
        web_search_context_size=_get_env("OPENAI_WEB_SEARCH_CONTEXT_SIZE", "medium") or "medium",
    )
