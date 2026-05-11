from __future__ import annotations

import os
from dataclasses import dataclass


def _get_env(name: str, default: str | None = None) -> str | None:
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
    model: str
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
    return OpenAISettings(
        api_key=_get_env("OPENAI_API_KEY"),
        model=_get_env("OPENAI_MODEL", "gpt-5") or "gpt-5",
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
