from __future__ import annotations

import json
from time import sleep
from typing import Any
from urllib.parse import urlsplit
from urllib.request import (
    Request,
    urlopen,
)
from .ai_usage import record_ai_usage_event
from .config import (
    OpenAISettings,
    get_openai_settings,
)
from .ai_response_helpers import (
    _count_web_search_calls,
    _extract_chat_completion_text,
    _extract_output_text,
    _extract_response_citation_urls,
)
from .ai_types import LLM_TRANSIENT_EXCEPTIONS


class TransportAIClient:
    def __init__(self, settings: OpenAISettings | None = None) -> None:
        self.settings = settings or get_openai_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def _create_response(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        include: list[str] | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        text_format: dict[str, Any] | None = None,
        citation_urls: list[str] | None = None,
        operation: str = "unknown",
        related_id: str | None = None,
    ) -> str:
        if self.settings.api_style == "chat_completions":
            return self._create_chat_completion(
                instructions=instructions,
                input_text=input_text,
                model=model or self.settings.editorial_model,
                operation=operation,
                related_id=related_id,
            )
        return self._create_responses_completion(
            instructions=instructions,
            input_text=input_text,
            model=model or self.settings.editorial_model,
            tools=tools,
            include=include,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            text_format=text_format,
            citation_urls=citation_urls,
            operation=operation,
            related_id=related_id,
        )

    def _create_responses_completion(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        include: list[str] | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        text_format: dict[str, Any] | None = None,
        citation_urls: list[str] | None = None,
        operation: str,
        related_id: str | None = None,
    ) -> str:
        payload_body: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input_text,
        }
        if tools:
            payload_body["tools"] = tools
            payload_body["tool_choice"] = "auto"
        if include:
            payload_body["include"] = include
        if max_output_tokens is not None:
            payload_body["max_output_tokens"] = max_output_tokens
        if reasoning_effort is not None:
            payload_body["reasoning"] = {"effort": reasoning_effort}
        if text_format is not None:
            payload_body["text"] = {"format": text_format}

        request_body = json.dumps(payload_body).encode("utf-8")
        request = Request(
            url=f"{self.settings.base_url.rstrip('/')}/responses",
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.api_key}",
            },
            method="POST",
        )

        for attempt in range(2):
            try:
                with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except LLM_TRANSIENT_EXCEPTIONS:
                if attempt >= 1:
                    raise
                sleep(1)

        record_ai_usage_event(
            operation=operation,
            model=model,
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
            related_id=related_id,
            web_search_calls=_count_web_search_calls(payload),
        )
        if citation_urls is not None:
            citation_urls.extend(_extract_response_citation_urls(payload))
        return _extract_output_text(payload)

    def _should_enable_web_search_for_request(self) -> bool:
        return (
            self.settings.web_search_enabled
            and self.settings.api_style == "responses"
            and "openai.com" in self.settings.base_url
        )

    def _build_web_search_tools(self, url: str, restrict_to_source_domain: bool = True) -> list[dict[str, Any]] | None:
        if not self._should_enable_web_search_for_request():
            return None

        host = urlsplit(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        tool: dict[str, Any] = {
            "type": "web_search",
            "external_web_access": self.settings.web_search_live,
            "search_context_size": self.settings.web_search_context_size,
        }
        if restrict_to_source_domain and host:
            tool["filters"] = {
                "allowed_domains": [host],
            }
        return [tool]

    def _build_guide_web_search_tools(self, context_size: str = "low") -> list[dict[str, Any]] | None:
        if not self._should_enable_web_search_for_request():
            return None

        safe_context_size = context_size if context_size in {"low", "medium", "high"} else "low"
        return [
            {
                "type": "web_search",
                "external_web_access": self.settings.web_search_live,
                "search_context_size": safe_context_size,
            }
        ]

    def _create_chat_completion(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str,
        operation: str,
        related_id: str | None = None,
    ) -> str:
        request_body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": input_text},
                ],
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = Request(
            url=f"{self.settings.base_url.rstrip('/')}/chat/completions",
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.api_key}",
            },
            method="POST",
        )

        with urlopen(request, timeout=self.settings.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        record_ai_usage_event(
            operation=operation,
            model=model,
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
            related_id=related_id,
            used_web_search=False,
        )
        return _extract_chat_completion_text(payload)

