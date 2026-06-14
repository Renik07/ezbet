from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg

from .config import get_database_url


WEB_SEARCH_CALL_PRICE_USD = 0.01


@dataclass(frozen=True)
class AiUsageEvent:
    operation: str
    usage_group: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    web_search_calls: int
    estimated_cost_usd: float
    related_id: str | None
    rate_source: str
    created_at: datetime


def record_ai_usage_event(
    *,
    operation: str,
    model: str,
    usage: dict[str, Any] | None,
    related_id: str | None = None,
    used_web_search: bool = False,
    web_search_calls: int | None = None,
) -> None:
    if not usage:
        return

    input_tokens = _int_value(usage.get("input_tokens"), usage.get("prompt_tokens"))
    output_tokens = _int_value(usage.get("output_tokens"), usage.get("completion_tokens"))
    cached_input_tokens = _extract_cached_input_tokens(usage)
    resolved_web_search_calls = max(0, int(web_search_calls or 0))
    if resolved_web_search_calls == 0 and used_web_search:
        resolved_web_search_calls = 1

    if input_tokens <= 0 and output_tokens <= 0 and cached_input_tokens <= 0 and resolved_web_search_calls <= 0:
        return

    event = AiUsageEvent(
        operation=operation,
        usage_group=_usage_group_for_operation(operation),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        web_search_calls=resolved_web_search_calls,
        estimated_cost_usd=estimate_ai_cost_usd(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            web_search_calls=resolved_web_search_calls,
        ),
        related_id=related_id,
        rate_source="openai_pricing_2026_06_plus_web_search",
        created_at=datetime.now(timezone.utc),
    )

    try:
        _insert_ai_usage_event(event)
    except psycopg.Error:
        # Usage accounting should never break publishing or enrichment.
        return


def estimate_ai_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int,
    web_search_calls: int = 0,
) -> float:
    rates = _rates_for_model(model)
    billable_input_tokens = max(0, input_tokens - cached_input_tokens)
    token_cost = (
        billable_input_tokens * rates["input"]
        + cached_input_tokens * rates["cached_input"]
        + output_tokens * rates["output"]
    ) / 1_000_000
    return round(token_cost + web_search_calls * WEB_SEARCH_CALL_PRICE_USD, 8)


def _insert_ai_usage_event(event: AiUsageEvent) -> None:
    statement = """
        INSERT INTO ai_usage_events (
            operation,
            usage_group,
            model,
            input_tokens,
            output_tokens,
            cached_input_tokens,
            total_tokens,
            web_search_calls,
            estimated_cost_usd,
            related_id,
            rate_source,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with psycopg.connect(get_database_url()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                statement,
                (
                    event.operation,
                    event.usage_group,
                    event.model,
                    event.input_tokens,
                    event.output_tokens,
                    event.cached_input_tokens,
                    event.input_tokens + event.output_tokens,
                    event.web_search_calls,
                    event.estimated_cost_usd,
                    event.related_id,
                    event.rate_source,
                    event.created_at,
                ),
            )
        connection.commit()


def _rates_for_model(model: str) -> dict[str, float]:
    normalized = model.lower()
    if "gpt-5-nano" in normalized:
        return {"input": 0.05, "cached_input": 0.005, "output": 0.40}
    if "gpt-5-mini" in normalized:
        return {"input": 0.25, "cached_input": 0.025, "output": 2.00}
    if "gpt-5.4-mini" in normalized:
        return {"input": 0.75, "cached_input": 0.075, "output": 4.50}
    if "gpt-5.4" in normalized:
        return {"input": 2.50, "cached_input": 0.25, "output": 15.00}
    if "gpt-5.5" in normalized:
        return {"input": 5.00, "cached_input": 0.50, "output": 30.00}
    return {"input": 0.25, "cached_input": 0.025, "output": 2.00}


def _usage_group_for_operation(operation: str) -> str:
    if operation.startswith("guide_"):
        return "guides"
    if operation.startswith("news_"):
        return "news"
    if operation.startswith("enrichment_") or operation.startswith("source_"):
        return "enrichment"
    if operation.startswith("content_plan"):
        return "planning"
    return "other"


def _extract_cached_input_tokens(usage: dict[str, Any]) -> int:
    direct = _int_value(usage.get("cached_input_tokens"))
    if direct:
        return direct

    input_details = usage.get("input_tokens_details")
    if isinstance(input_details, dict):
        return _int_value(input_details.get("cached_tokens"))

    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        return _int_value(prompt_details.get("cached_tokens"))

    return 0


def _int_value(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0
