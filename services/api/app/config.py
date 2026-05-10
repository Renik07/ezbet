from __future__ import annotations

import os
from dataclasses import dataclass


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://ezbet:ezbet@localhost:5433/ezbet")


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
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("OPENAI_MODEL", "gpt-5"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=int(os.getenv("OPENAI_TIMEOUT_SECONDS", "45")),
        api_style=os.getenv("OPENAI_API_STYLE", "responses"),
        provider_label=os.getenv("OPENAI_PROVIDER_LABEL", "OpenAI"),
        web_search_enabled=os.getenv("OPENAI_WEB_SEARCH_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        web_search_live=os.getenv("OPENAI_WEB_SEARCH_LIVE", "true").lower() in {"1", "true", "yes", "on"},
        web_search_context_size=os.getenv("OPENAI_WEB_SEARCH_CONTEXT_SIZE", "medium"),
    )
