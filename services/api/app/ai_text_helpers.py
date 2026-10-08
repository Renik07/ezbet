from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlsplit


def _validate_match_research_facts(
    value: Any,
    *,
    cutoff_date: date,
    cited_urls: list[str],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    if not any(_is_public_http_url(url) for url in cited_urls):
        return []
    accepted: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    allowed_kinds = {"home_result", "away_result", "head_to_head", "squad_news"}
    for item in value:
        if not isinstance(item, dict) or item.get("confidence") not in {"high", "medium"}:
            continue
        statement = _clean_text(item.get("statement"))
        source_url = _clean_text(item.get("source_url"))
        source_title = _clean_text(item.get("source_title"))
        event_date_text = _clean_text(item.get("event_date"))
        kind = _clean_text(item.get("kind"))
        if not all((statement, source_url, source_title)) or kind not in allowed_kinds:
            continue
        if len(statement) < 30 or _is_internal_citation_text(statement):
            continue
        if not _is_public_http_url(source_url):
            continue
        if event_date_text:
            try:
                event_date = date.fromisoformat(event_date_text)
            except ValueError:
                continue
            if event_date > cutoff_date:
                continue
        key = (statement.casefold(), source_url)
        if key in seen:
            continue
        seen.add(key)
        accepted.append(
            {
                "statement": statement,
                "source_url": source_url,
                "source_title": source_title,
                "event_date": event_date_text or "дата не указана",
                "kind": kind,
            }
        )
    return accepted


def _is_public_http_url(value: str) -> bool:
    if _is_internal_citation_text(value):
        return False
    parts = urlsplit(value)
    host = parts.netloc.casefold().removeprefix("www.")
    denied_hosts = {
        "flashscore.com",
        "flashscore.com.ar",
        "predictz.com",
        "sofascore.com",
        "bet365.com",
        "oddsportal.com",
    }
    return (
        parts.scheme in {"http", "https"}
        and bool(host)
        and "." in host
        and host not in denied_hosts
        and not any(host.endswith(f".{denied}") for denied in denied_hosts)
        and len(parts.path.strip("/")) >= 4
        and not parts.path.rstrip("/").endswith("/gameId")
    )


def _is_internal_citation_text(value: str) -> bool:
    return bool(re.search(r"\bturn\d+(?:search|fetch|view)\d+\b", value.casefold()))


def _source_publisher_tokens(value: str) -> set[str]:
    generic_labels = {"www", "com", "org", "net", "gob", "gov", "ar", "mx", "cl", "co", "uk"}
    host = urlsplit(value).netloc.casefold()
    return {label for label in host.split(".") if len(label) >= 4 and label not in generic_labels}


def _clean_article_text(value: Any) -> str | None:
    cleaned = _clean_text(value) or None
    if cleaned is None:
        return None

    normalized = cleaned.lower()
    refusal_markers = (
        "не удалось получить html",
        "не найдено копий этой новости",
        "не могу предоставить текст статьи",
        "я ограничен результатами",
        "html исходной страницы недоступен",
        "не найдено подтверждений",
        "не нашли подтверждений",
        "проверка сайта не выявила публикации",
        "проверка сайта не выявила",
        "рекомендуется уточнить заголовок",
        "расширить поиск на внешние источники",
        "прислать ссылку на первоисточник",
        "i can't provide the article text",
        "could not retrieve html",
    )
    if any(marker in normalized for marker in refusal_markers):
        return None
    return cleaned


def _clean_lead_text(value: Any) -> str | None:
    cleaned = _clean_text(value) or None
    if cleaned is None:
        return None

    normalized = cleaned.lower()
    refusal_markers = (
        "извините",
        "не могу предоставить",
        "не удалось получить",
        "не найдено копий",
        "краткое содержание",
        "summary:",
        "i can't provide",
        "sorry",
    )
    if any(marker in normalized for marker in refusal_markers):
        return None
    return cleaned


def _clean_url_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        url = _clean_text(item)
        if not url or not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned[:5]


def _is_mostly_russian_text(value: str) -> bool:
    cyrillic_count = len(re.findall(r"[А-Яа-яЁё]", value))
    latin_count = len(re.findall(r"[A-Za-z]", value))
    if cyrillic_count == 0:
        return False
    if latin_count == 0:
        return True
    return cyrillic_count >= latin_count * 1.5


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalize_guide_body(value: str) -> str:
    replacements = {
        "групповго": "группового",
        "чемпионом победа": "чемпиона победа",
        "выгодu": "выгоду",
        "тп.": "т. п.",
        " тп": " т. п.",
        "из за": "из-за",
    }
    normalized = value
    for raw, replacement in replacements.items():
        normalized = re.sub(re.escape(raw), replacement, normalized, flags=re.IGNORECASE)
    return _strip_markdown_links(normalized).strip()


def _strip_markdown_links(value: str) -> str:
    cleaned = re.sub(r"\s*\(\[[^\]]+\]\([^)]+\)\)", "", value)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip()


def _coerce_research_brief(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, str):
                lines.append(item.strip())
            elif isinstance(item, dict):
                parts = [_clean_text(part) for part in item.values()]
                lines.append("; ".join(part for part in parts if part))
        return "\n".join(line for line in lines if line)

    if isinstance(value, dict):
        for key in ("research_brief", "facts", "items", "bullets"):
            if key in value:
                return _coerce_research_brief(value[key])
        parts = [_clean_text(part) for part in value.values()]
        return "\n".join(part for part in parts if part)

    return ""


def _replace_yo(value: str) -> str:
    return value.replace("ё", "е").replace("Ё", "Е")


def _normalize_editor_decision(
    decision: str,
    revised_title: str | None,
    revised_dek: str | None,
    revised_body: str | None,
) -> str:
    normalized = decision.strip().lower()
    if normalized in {"approve", "light_edit", "rewrite"}:
        return normalized
    if revised_title and revised_dek and revised_body:
        return "light_edit"
    return "approve"

