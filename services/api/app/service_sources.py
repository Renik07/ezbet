from __future__ import annotations

from fastapi import HTTPException
import psycopg
from .ai_client import OpenAIEditorialClient
from .ingestion import (
    _capability_supports_adapter,
    ingest_sources as collect_source_items,
    probe_source_auto,
    probe_source,
)
from .models import (
    SourceCreateRequest,
    SourceCapability,
    SourceCapabilityListResponse,
    SourceListResponse,
    SourceProbeResponse,
    SourceUpdateRequest,
    SourceSyncStateListResponse,
    SourceItem,
)
from . import runtime
from .runtime import logger


def _raise_source_http_error(exc: Exception) -> None:
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, psycopg.Error):
        detail = getattr(exc.diag, "message_primary", None) or str(exc)
        raise HTTPException(status_code=400, detail=detail) from exc
    raise exc


def list_sources() -> SourceListResponse:
    return SourceListResponse(items=runtime.repository.list_source_configs())


def create_source(payload: SourceCreateRequest) -> SourceListResponse:
    try:
        source_type = payload.resolved_source_type or payload.source_type
        _validate_source_create_request(payload, source_type)
        source = SourceItem(
            key=payload.key,
            title=payload.title,
            url=payload.url,
            category=payload.category,
            source_type=source_type,
            status=payload.status,
            notes=payload.notes,
        )

        if payload.probe_ok:
            draft_source = source.model_copy(update={"status": "draft"})
            runtime.repository.create_source_config(draft_source)
            runtime.repository.record_source_probe(
                draft_source,
                ok=payload.probe_ok,
                item_count=payload.probe_item_count,
                message="Preflight сохранен из UI перед активацией источника.",
                readiness=payload.probe_readiness,
                preferred_adapter=payload.resolved_source_type or source_type,
                preferred_adapter_url=payload.resolved_source_url or payload.url,
                supports_rss=payload.supports_rss,
                supports_news_sitemap=payload.supports_news_sitemap,
                supports_sitemap=payload.supports_sitemap,
                supports_scraping=payload.supports_scraping,
                full_text_ok=payload.full_text_ok,
                lead_ok=payload.lead_ok,
                tags_count=payload.tags_count,
                sample_title=payload.sample_title,
                sample_url=payload.sample_url,
            )
            runtime.repository.update_source_config(draft_source.model_copy(update={"status": "active"}))
        else:
            runtime.repository.create_source_config(source)
    except Exception as exc:
        _raise_source_http_error(exc)
    return SourceListResponse(items=runtime.repository.list_source_configs())


def update_source(source_key: str, payload: SourceUpdateRequest) -> SourceListResponse:
    try:
        runtime.repository.update_source_config(
            SourceItem(
                key=source_key,
                title=payload.title,
                url=payload.url,
                category=payload.category,
                source_type=payload.source_type,
                status=payload.status,
                notes=payload.notes,
            )
        )
    except Exception as exc:
        _raise_source_http_error(exc)
    return SourceListResponse(items=runtime.repository.list_source_configs())


def delete_source(source_key: str) -> SourceListResponse:
    try:
        runtime.repository.delete_source_config(source_key)
    except Exception as exc:
        _raise_source_http_error(exc)
    return SourceListResponse(items=runtime.repository.list_source_configs())


def probe_source_draft(payload: SourceCreateRequest) -> SourceProbeResponse:
    try:
        source = SourceItem(
            key=payload.key or "source-draft",
            title=payload.title,
            url=payload.url,
            category=payload.category,
            source_type=payload.source_type,
            status="draft",
            notes=payload.notes,
        )
        return _probe_source_item(source, persist=False, auto_detect=payload.source_type == "auto")
    except Exception as exc:
        _raise_source_probe_http_error(exc)


def probe_source_config(source_key: str) -> SourceProbeResponse:
    try:
        source = runtime.repository.get_source_config(source_key)
        return _probe_source_item(source, persist=True)
    except Exception as exc:
        _raise_source_probe_http_error(exc)


def _raise_source_probe_http_error(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.exception("source_probe_failed")
    raise HTTPException(status_code=502, detail=f"Source probe failed: {exc}") from exc


def _probe_source_item(source: SourceItem, *, persist: bool, auto_detect: bool = False) -> SourceProbeResponse:
    result = probe_source_auto(source) if auto_detect else probe_source(source)
    resolved_source = source.model_copy(update={"source_type": result.resolved_source_type or source.source_type})
    if (
        result.ok
        and result.readiness not in {"ready", "ready_ai"}
    ):
        ai_client = OpenAIEditorialClient()
        if ai_client.enabled:
            probe_candidates = [
                item for item in collect_source_items([resolved_source], limit=5) if item.url
            ][:5]
            for candidate in probe_candidates:
                ai_enrichment = ai_client.extract_article_enrichment_via_search(
                    url=candidate.url,
                    source_title=source.title,
                    raw_title=candidate.title or result.sample_title or source.title,
                    raw_summary=candidate.summary,
                )
                if ai_enrichment is None:
                    continue
                if ai_enrichment.full_text and len(ai_enrichment.full_text.strip()) >= 120:
                    result.readiness = "ready_ai"
                    result.full_text_ok = True
                    result.full_text_method = "web_search"
                    result.lead_ok = result.lead_ok or bool(ai_enrichment.lead)
                    result.tags_count = max(result.tags_count, len(ai_enrichment.tags))
                    result.sample_title = candidate.title
                    result.sample_url = candidate.url
                    result.message = (
                        f"Найдено {result.item_count} элементов. Deterministic extraction слабый, "
                        "но web_search fallback успешно собрал текст у одной из sample-новостей."
                    )
                    break
                if ai_enrichment.lead or ai_enrichment.tags:
                    result.readiness = "partial"
                    result.lead_ok = result.lead_ok or bool(ai_enrichment.lead)
                    result.tags_count = max(result.tags_count, len(ai_enrichment.tags))
                    result.sample_title = candidate.title
                    result.sample_url = candidate.url
                    result.message = (
                        f"Найдено {result.item_count} элементов. Deterministic extraction слабый, "
                        "но web_search fallback смог поднять только часть enrichment-данных."
                    )
    if persist:
        runtime.repository.record_source_probe(
            source,
            ok=result.ok,
            item_count=result.item_count,
            message=result.message,
            readiness=result.readiness,
            preferred_adapter=result.resolved_source_type,
            preferred_adapter_url=result.resolved_source_url,
            supports_rss=result.supports_rss,
            supports_news_sitemap=result.supports_news_sitemap,
            supports_sitemap=result.supports_sitemap,
            supports_scraping=result.supports_scraping,
            full_text_ok=result.full_text_ok,
            full_text_method=result.full_text_method,
            lead_ok=result.lead_ok,
            tags_count=result.tags_count,
            sample_title=result.sample_title,
            sample_url=result.sample_url,
        )
    return SourceProbeResponse(
        source_key=source.key,
        ok=result.ok,
        item_count=result.item_count,
        message=result.message,
        readiness=result.readiness,
        resolved_source_type=result.resolved_source_type,
        resolved_source_url=result.resolved_source_url,
        supports_rss=result.supports_rss,
        supports_news_sitemap=result.supports_news_sitemap,
        supports_sitemap=result.supports_sitemap,
        supports_scraping=result.supports_scraping,
        full_text_ok=result.full_text_ok,
        full_text_method=result.full_text_method,
        lead_ok=result.lead_ok,
        tags_count=result.tags_count,
        sample_title=result.sample_title,
        sample_url=result.sample_url,
    )


def list_source_states() -> SourceSyncStateListResponse:
    return SourceSyncStateListResponse(items=runtime.repository.list_source_sync_states())


def list_source_capabilities() -> SourceCapabilityListResponse:
    sources = runtime.repository.list_source_configs()
    states = runtime.repository.list_source_sync_states()
    state_map = {state.source_key: state for state in states}
    items = [_build_source_capability(source, state_map.get(source.key)) for source in sources]
    return SourceCapabilityListResponse(items=items)


def _validate_source_create_request(payload: SourceCreateRequest, source_type: str) -> None:
    if not source_type or source_type == "auto":
        raise ValueError("Проверка не подтвердила подходящий тип источника. Сначала выполните preflight.")
    if source_type == "sitemap":
        raise ValueError(
            "Обычный sitemap больше не используется в автоматическом новостном pipeline. "
            "Нужен RSS, news sitemap, scraping или ai search."
        )
    if source_type not in {"rss", "news_sitemap", "scraping", "ai_research"}:
        raise ValueError(f"Источник типа {source_type} нельзя активировать в текущем pipeline.")
    if not payload.probe_ok:
        raise ValueError("Сначала выполните успешную проверку источника.")
    if payload.probe_item_count <= 0:
        raise ValueError("Проверка источника не подтвердила ни одной новости.")

    readiness = payload.probe_readiness or "unknown"
    if source_type == "rss":
        if not payload.supports_rss and payload.resolved_source_type != "rss":
            raise ValueError("Проверка не подтвердила, что источник действительно отдает рабочий RSS.")
        if readiness not in {"ready", "ready_ai", "partial", "feed_only"}:
            raise ValueError(
                "RSS-источник не прошел preflight: лента читается, но sample-новости пока выглядят слишком слабо."
            )
        return

    if source_type == "news_sitemap":
        if not payload.supports_news_sitemap and payload.resolved_source_type != "news_sitemap":
            raise ValueError("Проверка не подтвердила рабочий news sitemap.")
        if readiness not in {"ready", "ready_ai", "partial", "feed_only"}:
            raise ValueError(
                "News sitemap не прошел preflight: sample-новости не выглядят пригодными для auto-pipeline."
            )
        return

    if source_type == "scraping":
        if not payload.supports_scraping and payload.resolved_source_type != "scraping":
            raise ValueError("Проверка не подтвердила рабочий scraping-источник.")
        if readiness not in {"ready", "ready_ai", "partial"}:
            raise ValueError(
                "Scraping-источник не прошел preflight: страница пока больше похожа на хаб, ленту или служебный раздел."
            )
        return

    if source_type == "ai_research" and readiness not in {"ready_ai", "partial"}:
        raise ValueError(
            "AI search-источник не прошел preflight: даже fallback-режим не подтвердил, что из него получится собирать новости."
        )


def _build_source_capability(source: SourceItem, state) -> SourceCapability:
    readiness = state.last_probe_readiness if state is not None else "unknown"
    preferred_adapter = state.preferred_adapter if state is not None else None
    preferred_adapter_url = state.preferred_adapter_url if state is not None else None

    effective_adapter = source.source_type
    if state is not None:
        if preferred_adapter and _capability_supports_adapter(state, preferred_adapter):
            effective_adapter = preferred_adapter
        elif _capability_supports_adapter(state, source.source_type):
            effective_adapter = source.source_type
        else:
            for adapter in ("rss", "news_sitemap", "scraping", "ai_research"):
                if _capability_supports_adapter(state, adapter):
                    effective_adapter = adapter
                    break

    effective_url = (
        preferred_adapter_url
        if preferred_adapter_url and effective_adapter == preferred_adapter
        else source.url
    )

    return SourceCapability(
        source_key=source.key,
        source_title=source.title,
        configured_source_type=source.source_type,
        configured_url=source.url,
        preferred_adapter=preferred_adapter,
        preferred_adapter_url=preferred_adapter_url,
        effective_adapter=effective_adapter,
        effective_url=effective_url,
        readiness=readiness,
        supports_rss=state.supports_rss if state is not None else False,
        supports_news_sitemap=state.supports_news_sitemap if state is not None else False,
        supports_sitemap=state.supports_sitemap if state is not None else False,
        supports_scraping=state.supports_scraping if state is not None else False,
        full_text_ok=state.last_probe_full_text_ok if state is not None else False,
        lead_ok=state.last_probe_lead_ok if state is not None else False,
        tags_count=state.last_probe_tags_count if state is not None else 0,
        sample_title=state.last_probe_sample_title if state is not None else None,
        sample_url=state.last_probe_sample_url if state is not None else None,
    )

