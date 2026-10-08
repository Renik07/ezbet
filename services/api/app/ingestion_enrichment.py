from __future__ import annotations

import re
from .news_budget import claim_news_stage
from .news_candidates import news_rejection_reason
from .ai_client import OpenAIEditorialClient
from .models import RawItem
from .ingestion_article_extraction import _extract_article_enrichment_from_html
from .ingestion_network import fetch_remote_document
from .ingestion_text import (
    _is_usable_full_text,
    _looks_like_translit_slug_title,
    _merge_tags,
)
from .ingestion_types import ArticleEnrichmentResult
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .repository import NewsRepository


def enrich_raw_item_content(
    repository: "NewsRepository",
    raw_item: RawItem,
    *,
    allow_web_search_fallback: bool = True,
) -> RawItem:
    if news_rejection_reason(raw_item):
        return raw_item
    existing_full_text = (raw_item.full_text or "").strip()
    has_usable_full_text = _is_usable_full_text(
        existing_full_text,
        raw_item.title,
        raw_item.summary,
        raw_item.lead,
    )
    if (
        has_usable_full_text
        and ((raw_item.lead or "").strip() or raw_item.tags)
    ) or not raw_item.url:
        return raw_item

    html = fetch_remote_document(raw_item.url, timeout=10)
    direct_enrichment = _extract_article_enrichment_from_html(raw_item.url, html) if html else None
    if direct_enrichment is not None and _is_usable_full_text(
        direct_enrichment.full_text,
        raw_item.title,
        raw_item.summary,
        direct_enrichment.lead,
    ):
        return _persist_raw_item_enrichment(
            repository,
            raw_item,
            title=direct_enrichment.title,
            full_text=direct_enrichment.full_text,
            lead=direct_enrichment.lead,
            tags=direct_enrichment.tags,
            full_text_source_url=raw_item.url,
            full_text_source_title=raw_item.source_title,
            reference_urls=[],
            extraction_mode="direct_html",
            enrichment_status="direct_html_ok",
        )

    ai_client = OpenAIEditorialClient()
    if ai_client.enabled and not claim_news_stage(repository, raw_item.id, 'enrichment'):
        return raw_item
    ai_html_enrichment = (
        ai_client.extract_article_enrichment(
            url=raw_item.url,
            source_title=raw_item.source_title,
            raw_title=raw_item.title,
            raw_summary=raw_item.summary,
            html=html,
            allow_web_search=False,
        )
        if ai_client.enabled and html
        else None
    )
    if ai_html_enrichment is not None and _is_usable_full_text(
        ai_html_enrichment.full_text,
        raw_item.title,
        raw_item.summary,
        ai_html_enrichment.lead,
    ):
        return _persist_raw_item_enrichment(
            repository,
            raw_item,
            title=direct_enrichment.title if direct_enrichment is not None else None,
            full_text=ai_html_enrichment.full_text,
            lead=ai_html_enrichment.lead or (direct_enrichment.lead if direct_enrichment is not None else None),
            tags=_merge_tags(
                direct_enrichment.tags if direct_enrichment is not None else [],
                ai_html_enrichment.tags,
            ),
            full_text_source_url=ai_html_enrichment.source_url or raw_item.url,
            full_text_source_title=ai_html_enrichment.source_title or raw_item.source_title,
            reference_urls=ai_html_enrichment.reference_urls,
            extraction_mode=ai_html_enrichment.generation_mode,
            enrichment_status="ai_html_ok",
        )

    local_partial = _choose_best_local_partial_enrichment(
        direct_enrichment=direct_enrichment,
        ai_html_enrichment=ai_html_enrichment,
    )
    if not ai_client.enabled:
        if local_partial is None:
            return raw_item
        return _persist_raw_item_enrichment(
            repository,
            raw_item,
            title=local_partial["title"],
            full_text=local_partial["full_text"],
            lead=local_partial["lead"],
            tags=local_partial["tags"],
            full_text_source_url=raw_item.url,
            full_text_source_title=raw_item.source_title,
            reference_urls=[],
            extraction_mode=local_partial["extraction_mode"],
            enrichment_status=local_partial["enrichment_status"],
        )

    if not allow_web_search_fallback:
        if local_partial is not None:
            return _persist_raw_item_enrichment(
                repository,
                raw_item,
                title=local_partial["title"],
                full_text=local_partial["full_text"],
                lead=local_partial["lead"],
                tags=local_partial["tags"],
                full_text_source_url=raw_item.url,
                full_text_source_title=raw_item.source_title,
                reference_urls=[],
                extraction_mode=local_partial["extraction_mode"],
                enrichment_status="search_skipped_run_cap",
            )
        return (
            repository.update_raw_item_enrichment(
                raw_item.id,
                enrichment_status="search_skipped_run_cap",
                enrichment_error=(
                    "web_search fallback пропущен: в этом enrichment batch уже исчерпан лимит "
                    "внешнего поиска."
                ),
            )
            or raw_item
        )

    if not _should_allow_web_search_fallback(raw_item):
        if local_partial is not None:
            return _persist_raw_item_enrichment(
                repository,
                raw_item,
                title=local_partial["title"],
                full_text=local_partial["full_text"],
                lead=local_partial["lead"],
                tags=local_partial["tags"],
                full_text_source_url=raw_item.url,
                full_text_source_title=raw_item.source_title,
                reference_urls=[],
                extraction_mode=local_partial["extraction_mode"],
                enrichment_status="search_skipped_budget",
            )
        return (
            repository.update_raw_item_enrichment(
                raw_item.id,
                enrichment_status="search_skipped_budget",
                enrichment_error=(
                    "web_search fallback пропущен по budget-правилу: для low-priority новости "
                    "сначала используем только локальный extraction."
                ),
            )
            or raw_item
        )

    ai_search_enrichment = ai_client.extract_article_enrichment_via_search(
        url=raw_item.url,
        source_title=raw_item.source_title,
        raw_title=raw_item.title,
        raw_summary=raw_item.summary,
    )
    if ai_search_enrichment is None:
        if local_partial is not None:
            return _persist_raw_item_enrichment(
                repository,
                raw_item,
                title=local_partial["title"],
                full_text=local_partial["full_text"],
                lead=local_partial["lead"],
                tags=local_partial["tags"],
                full_text_source_url=raw_item.url,
                full_text_source_title=raw_item.source_title,
                reference_urls=[],
                extraction_mode=local_partial["extraction_mode"],
                enrichment_status=local_partial["enrichment_status"],
            )
        return (
            repository.update_raw_item_enrichment(
                raw_item.id,
                enrichment_status="search_no_match",
                enrichment_error="Ни direct parser, ни AI extraction по HTML, ни web_search fallback не дали пригодный текст этой новости.",
            )
            or raw_item
        )

    return (
        _persist_raw_item_enrichment(
            repository,
            raw_item,
            title=(direct_enrichment.title if direct_enrichment is not None else None),
            full_text=ai_search_enrichment.full_text,
            lead=ai_search_enrichment.lead or (local_partial["lead"] if local_partial is not None else None),
            tags=_merge_tags(
                local_partial["tags"] if local_partial is not None else [],
                ai_search_enrichment.tags,
            ),
            full_text_source_url=ai_search_enrichment.source_url,
            full_text_source_title=ai_search_enrichment.source_title,
            reference_urls=ai_search_enrichment.reference_urls,
            extraction_mode=ai_search_enrichment.generation_mode,
            enrichment_status=(
                "web_search_brief_ok" if ai_search_enrichment.full_text else "search_partial_only"
            ),
        )
        or raw_item
    )


def _choose_best_local_partial_enrichment(
    *,
    direct_enrichment: ArticleEnrichmentResult | None,
    ai_html_enrichment,
) -> dict[str, str | list[str] | None] | None:
    ai_lead = ai_html_enrichment.lead if ai_html_enrichment is not None else None
    ai_tags = ai_html_enrichment.tags if ai_html_enrichment is not None else []
    direct_title = direct_enrichment.title if direct_enrichment is not None else None
    direct_full_text = direct_enrichment.full_text if direct_enrichment is not None else None
    direct_lead = direct_enrichment.lead if direct_enrichment is not None else None
    direct_tags = direct_enrichment.tags if direct_enrichment is not None else []

    if ai_html_enrichment is not None and (
        (ai_html_enrichment.full_text or "").strip() or (ai_lead or "").strip() or ai_tags
    ):
        return {
            "title": direct_title,
            "full_text": ai_html_enrichment.full_text,
            "lead": ai_lead or direct_lead,
            "tags": _merge_tags(direct_tags, ai_tags),
            "extraction_mode": ai_html_enrichment.generation_mode,
            "enrichment_status": "ai_html_partial_only",
        }

    if direct_enrichment is not None and (
        (direct_full_text or "").strip() or (direct_lead or "").strip() or direct_tags
    ):
        return {
            "title": direct_title,
            "full_text": direct_full_text,
            "lead": direct_lead,
            "tags": direct_tags,
            "extraction_mode": "direct_html",
            "enrichment_status": "direct_html_partial_only",
        }

    return None


def _persist_raw_item_enrichment(
    repository: "NewsRepository",
    raw_item: RawItem,
    *,
    title: str | None,
    full_text: str | None,
    lead: str | None,
    tags: list[str],
    full_text_source_url: str | None,
    full_text_source_title: str | None,
    reference_urls: list[str],
    extraction_mode: str,
    enrichment_status: str,
) -> RawItem:
    normalized_title, normalized_summary = _resolve_enriched_raw_headline(
        raw_item.title,
        raw_item.summary,
        title,
        lead,
        full_text,
    )
    return (
        repository.update_raw_item_enrichment(
            raw_item.id,
            title=normalized_title,
            summary=normalized_summary,
            full_text=full_text,
            lead=lead,
            full_text_source_url=full_text_source_url,
            full_text_source_title=full_text_source_title,
            reference_urls=reference_urls,
            extraction_mode=extraction_mode,
            enrichment_status=enrichment_status,
            tags=tags,
        )
        or raw_item
    )


def _should_allow_web_search_fallback(raw_item: RawItem) -> bool:
    return raw_item.triage_label in {"high", "medium"} and raw_item.importance_score >= 48


def _resolve_enriched_raw_headline(
    current_title: str,
    current_summary: str,
    extracted_title: str | None,
    extracted_lead: str | None,
    extracted_full_text: str | None,
) -> tuple[str | None, str | None]:
    current_title_has_cyrillic = bool(re.search(r"[А-Яа-я]", current_title or ""))
    current_summary_has_cyrillic = bool(re.search(r"[А-Яа-я]", current_summary or ""))
    if current_title_has_cyrillic and current_summary_has_cyrillic:
        return None, None

    candidate_title = (extracted_title or "").strip()
    candidate_lead = (extracted_lead or "").strip()
    candidate_full_text = (extracted_full_text or "").strip()

    if candidate_title and re.search(r"[А-Яа-я]", candidate_title):
        resolved_title = candidate_title
    elif candidate_lead and re.search(r"[А-Яа-я]", candidate_lead):
        resolved_title = candidate_lead.split(". ", 1)[0].strip().rstrip(".")
    elif candidate_full_text and re.search(r"[А-Яа-я]", candidate_full_text):
        resolved_title = candidate_full_text.split(". ", 1)[0].strip().rstrip(".")
    else:
        return None, None

    if len(resolved_title) < 12:
        return None, None

    resolved_summary = candidate_lead or resolved_title

    next_title = resolved_title if not current_title_has_cyrillic or _looks_like_translit_slug_title(current_title) else None
    next_summary = resolved_summary if not current_summary_has_cyrillic or current_summary.strip() == current_title.strip() else None
    return next_title, next_summary

