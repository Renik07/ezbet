from __future__ import annotations

from dataclasses import dataclass
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import urlopen
from xml.etree import ElementTree

from .ai_client import OpenAIEditorialClient
from .models import NewsItem, PromptConfig, RawItem, SourceItem, SourceSyncState

SUPPORTED_ACTIVE_SOURCE_TYPES = {"rss", "scraping", "ai_research"}

POSITIVE_CONTAINER_TERMS = (
    "news",
    "article",
    "story",
    "post",
    "feed",
    "list",
    "items",
    "headline",
    "content",
    "main",
    "sport",
    "football",
    "hockey",
    "basketball",
    "tennis",
)

NEGATIVE_CONTAINER_TERMS = (
    "nav",
    "menu",
    "footer",
    "header",
    "sidebar",
    "banner",
    "promo",
    "advert",
    "login",
    "auth",
    "profile",
    "subscription",
    "subscribe",
)

BLOCKED_URL_SEGMENTS = {
    "video",
    "videos",
    "tv",
    "channel",
    "channels",
    "podcast",
    "subscription",
    "subscriptions",
    "subscribe",
    "auth",
    "login",
    "register",
    "profile",
    "account",
    "shop",
    "store",
    "about",
    "contacts",
    "contact",
    "advert",
    "promo",
}

PREFERRED_URL_SEGMENTS = {
    "news",
    "article",
    "articles",
    "story",
    "stories",
    "sport",
    "sports",
    "football",
    "hockey",
    "basketball",
    "tennis",
    "match",
}

ARTICLE_CONTAINER_TERMS = (
    "article",
    "story",
    "content",
    "entry",
    "post",
    "body",
    "text",
    "main",
    "news",
)

ARTICLE_NEGATIVE_TERMS = (
    "nav",
    "menu",
    "footer",
    "header",
    "banner",
    "promo",
    "share",
    "related",
    "recommend",
    "sidebar",
    "comment",
)

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("football", ("футбол", "football", "рпл", "лига чемпионов", "апл", "ла лига")),
    ("hockey", ("хоккей", "hockey", "кхл", "нхл", "nhl")),
    ("basketball", ("баскетбол", "basketball", "нба", "nba", "евролига")),
    ("tennis", ("теннис", "tennis", "atp", "wta")),
    ("betting", ("букмекер", "ставк", "bet", "коэффициент", "линия")),
]

HIGH_PRIORITY_TERMS = (
    "срочно",
    "официально",
    "эксклюзив",
    "exclusive",
    "breaking",
    "трансфер",
    "уволен",
    "травм",
    "финал",
    "чемпион",
)

MEDIUM_PRIORITY_TERMS = (
    "матч",
    "игра",
    "побед",
    "проигр",
    "турнир",
    "тренер",
    "команда",
)


@dataclass
class SourceIngestionResult:
    source: SourceItem
    items: list[RawItem]
    fetch_status: str
    parse_status: str
    error: str | None
    retry_count: int


class SourceFetchError(RuntimeError):
    pass


@dataclass
class ArticleEnrichmentResult:
    full_text: str | None
    lead: str | None
    tags: list[str]


@dataclass
class SourceProbeResult:
    ok: bool
    item_count: int
    message: str
    readiness: str
    full_text_ok: bool
    lead_ok: bool
    tags_count: int
    sample_title: str | None
    sample_url: str | None

MAJOR_EVENT_TERMS = (
    "лига чемпионов",
    "champions league",
    "плей-офф",
    "playoff",
    "финал",
    "final",
    "кубок",
    "world cup",
    "евро",
    "дерби",
    "ufc",
)

OFFICIAL_SIGNAL_TERMS = (
    "официально",
    "official",
    "объявил",
    "confirmed",
    "назначен",
    "подписал",
    "продлил",
    "disqualified",
)

SOURCE_REPUTATION_HINTS: dict[str, int] = {
    "sports.ru": 6,
    "sport-express": 7,
    "спорт-экспресс": 7,
    "championat": 6,
    "чемпионат": 6,
    "sovsport": 5,
    "советский спорт": 5,
}


def ingest_sources(
    sources: Iterable[SourceItem],
    source_states: dict[str, SourceSyncState] | None = None,
    timeout: int = 10,
    limit: int | None = None,
    limit_per_source: bool = False,
    ai_search_prompt: PromptConfig | None = None,
) -> list[RawItem]:
    collected, _ = ingest_sources_with_results(
        sources,
        source_states=source_states,
        timeout=timeout,
        limit=limit,
        limit_per_source=limit_per_source,
        ai_search_prompt=ai_search_prompt,
    )
    return collected


def ingest_sources_with_results(
    sources: Iterable[SourceItem],
    source_states: dict[str, SourceSyncState] | None = None,
    timeout: int = 10,
    limit: int | None = None,
    max_retries: int = 1,
    limit_per_source: bool = False,
    ai_search_prompt: PromptConfig | None = None,
) -> tuple[list[RawItem], list[SourceIngestionResult]]:
    collected: list[RawItem] = []
    results: list[SourceIngestionResult] = []
    seen_keys: set[str] = set()
    states = source_states or {}

    for source in sources:
        source_state = states.get(source.key)
        source_result = _collect_source_items_with_retry(
            source,
            timeout=timeout,
            max_retries=max_retries,
            ai_search_prompt=ai_search_prompt,
        )
        collected_items = source_result.items
        filtered_items = _filter_new_items(collected_items, source_state, source.source_type)
        if limit is not None and limit_per_source:
            filtered_items = filtered_items[:limit]
        for item in filtered_items:
            dedupe_key = item.dedupe_key
            if dedupe_key in seen_keys:
                item.is_duplicate = True
                item.duplicate_of = dedupe_key
            else:
                seen_keys.add(dedupe_key)
            collected.append(item)
        results.append(source_result)

    collected.sort(key=lambda item: (item.published_at, item.importance_score), reverse=True)
    if limit is not None and not limit_per_source:
        return collected[:limit], results
    return collected, results


def raw_items_to_news(raw_items: Iterable[RawItem]) -> list[NewsItem]:
    items: list[NewsItem] = []

    for raw in raw_items:
        if raw.is_duplicate:
            continue

        items.append(
            NewsItem(
                id=raw.external_id,
                title=raw.title,
                description=raw.summary,
                category=raw.normalized_category,
                published_at=raw.published_at,
                source=raw.source_title,
                link=raw.url,
                ai_reviewed=False,
            )
        )

    return items


def probe_source(source: SourceItem, timeout: int = 10) -> SourceProbeResult:
    try:
        items = _collect_source_items(source, timeout=timeout)
    except SourceFetchError as exc:
        return SourceProbeResult(False, 0, str(exc), "fetch_error", False, False, 0, None, None)
    if not items:
        if source.source_type == "scraping":
            return SourceProbeResult(False, 0, "Страница не прочитана или scraping-адаптер не нашел кандидатов.", "empty", False, False, 0, None, None)
        return SourceProbeResult(False, 0, "Фид не прочитан или не вернул элементов.", "empty", False, False, 0, None, None)

    if source.source_type == "ai_research":
        sample = next((item for item in items if item.url), items[0])
        full_text_ok = _is_usable_full_text(sample.full_text, sample.summary)
        lead_ok = _is_usable_lead(sample.lead)
        tags_count = len(sample.tags)

        if full_text_ok:
            readiness = "ready_ai"
            message = f"Найдено {len(items)} элементов. AI search сразу извлёк пригодный full text у sample-новости."
        elif lead_ok or tags_count:
            readiness = "partial"
            message = f"Найдено {len(items)} элементов. AI search вернул кандидатов, но full text пока слабый."
        else:
            readiness = "feed_only"
            message = (
                f"Найдено {len(items)} элементов, но AI search не смог сразу извлечь пригодный full text "
                "у sample-новости."
            )

        return SourceProbeResult(
            True,
            len(items),
            message,
            readiness,
            full_text_ok,
            lead_ok,
            tags_count,
            sample.title,
            sample.url,
        )

    samples = [item for item in items if item.url][:3] or items[:1]
    sample = samples[0]
    enrichment: ArticleEnrichmentResult | None = None
    full_text_ok = False
    lead_ok = False
    tags_count = 0

    for candidate in samples:
        candidate_enrichment = extract_article_enrichment(candidate.url, timeout=timeout) if candidate.url else None
        candidate_full_text_ok = _is_usable_full_text(
            candidate_enrichment.full_text if candidate_enrichment is not None else None,
            candidate.summary,
        )
        candidate_lead_ok = _is_usable_lead(candidate_enrichment.lead if candidate_enrichment is not None else None)
        candidate_tags_count = len(candidate_enrichment.tags) if candidate_enrichment else 0

        if candidate_full_text_ok:
            sample = candidate
            enrichment = candidate_enrichment
            full_text_ok = True
            lead_ok = candidate_lead_ok
            tags_count = candidate_tags_count
            break

        if not lead_ok and (candidate_lead_ok or candidate_tags_count):
            sample = candidate
            enrichment = candidate_enrichment
            lead_ok = candidate_lead_ok
            tags_count = candidate_tags_count

    if full_text_ok:
        readiness = "ready"
        message = f"Найдено {len(items)} элементов. Full text у одной из sample-новостей успешно извлечён."
    elif lead_ok or tags_count:
        readiness = "partial"
        message = f"Найдено {len(items)} элементов. Источник частично годится для production-flow, но full text пока слабый."
    else:
        readiness = "feed_only"
        message = (
            f"Найдено {len(items)} элементов, но ни одна из sample-новостей не дала full text enrichment. "
            "Такой источник лучше не переводить в active до доработки extractor."
        )

    return SourceProbeResult(
        True,
        len(items),
        message,
        readiness,
        full_text_ok,
        lead_ok,
        tags_count,
        sample.title,
        sample.url,
    )


def _collect_source_items_with_retry(
    source: SourceItem,
    *,
    timeout: int,
    max_retries: int,
    ai_search_prompt: PromptConfig | None = None,
) -> SourceIngestionResult:
    attempts = 0
    last_error: str | None = None

    while attempts <= max_retries:
        attempts += 1
        try:
            items = _collect_source_items(source, timeout=timeout, ai_search_prompt=ai_search_prompt)
        except SourceFetchError as exc:
            last_error = str(exc)
            if attempts <= max_retries:
                continue
            return SourceIngestionResult(
                source=source,
                items=[],
                fetch_status="error",
                parse_status="idle",
                error=last_error,
                retry_count=attempts - 1,
            )
        except ValueError as exc:
            last_error = str(exc)
            return SourceIngestionResult(
                source=source,
                items=[],
                fetch_status="ok",
                parse_status="error",
                error=last_error,
                retry_count=attempts - 1,
            )

        if items:
            return SourceIngestionResult(
                source=source,
                items=items,
                fetch_status="ok",
                parse_status="ok",
                error=None,
                retry_count=attempts - 1,
            )

        last_error = "Источник не вернул элементов."

    return SourceIngestionResult(
        source=source,
        items=[],
        fetch_status="ok",
        parse_status="empty",
        error=last_error,
        retry_count=max_retries,
    )


def _collect_source_items(
    source: SourceItem,
    timeout: int,
    ai_search_prompt: PromptConfig | None = None,
) -> list[RawItem]:
    if source.source_type == "rss":
        return _parse_feed(source, timeout=timeout)
    if source.source_type == "scraping":
        return _parse_scraping_source(source, timeout=timeout)
    if source.source_type == "ai_research":
        return _parse_ai_research_source(source, timeout=timeout, ai_search_prompt=ai_search_prompt)
    return []


def _parse_feed(source: SourceItem, timeout: int) -> list[RawItem]:
    payload = _fetch_remote_document(source.url, timeout)

    encoded_payload = payload.encode("utf-8", errors="ignore")
    try:
        root = ElementTree.fromstring(encoded_payload)
    except ElementTree.ParseError:
        return []

    if root.tag.endswith("feed"):
        return _parse_atom(root, source, payload)

    return _parse_rss(root, source, payload)


def _parse_scraping_source(source: SourceItem, timeout: int) -> list[RawItem]:
    payload = _fetch_remote_document(source.url, timeout)

    parser = _ScrapingDocumentParser(source.url)
    try:
        parser.feed(payload)
        parser.close()
    except ValueError:
        return []

    fetched_at = datetime.now(timezone.utc)
    items: list[RawItem] = []

    for index, candidate in enumerate(parser.candidates):
        published = candidate.published_at or (fetched_at - timedelta(seconds=index))
        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=candidate.url,
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url,
                published=published,
            )
        )

    if items:
        return items

    fallback_title = parser.og_title or parser.page_title or source.title
    fallback_summary = parser.og_description or parser.meta_description or fallback_title
    canonical_url = parser.canonical_url or source.url
    if not fallback_title:
        return []

    return [
        _build_raw_item(
            source=source,
            payload=payload,
            fetched_at=fetched_at,
            external_id=canonical_url,
            title=fallback_title,
            summary=fallback_summary,
            url=canonical_url,
            published=fetched_at,
        )
    ]


def _parse_ai_research_source(
    source: SourceItem,
    timeout: int,
    ai_search_prompt: PromptConfig | None = None,
) -> list[RawItem]:
    ai_client = OpenAIEditorialClient()
    if not ai_client.enabled:
        raise SourceFetchError("AI search source requires an enabled OpenAI Responses client.")

    discovered = ai_client.discover_source_items(source, limit=12, prompt=ai_search_prompt)
    if not discovered:
        return []

    fetched_at = datetime.now(timezone.utc)
    items: list[RawItem] = []
    payload = ""

    for discovered_item in discovered:
        resolved_url = discovered_item.url
        resolved_published_at = discovered_item.published_at
        resolved_source_title = discovered_item.source_title

        published = _try_parse_datetime(resolved_published_at or "") or fetched_at
        payload = payload or _serialize_ai_discovery_payload(source, discovered)
        full_text: str | None = None
        lead = discovered_item.summary
        tags = discovered_item.tags

        ai_enrichment = _extract_ai_research_article_enrichment(
            ai_client=ai_client,
            url=resolved_url,
            source_title=resolved_source_title or source.title,
            raw_title=discovered_item.title,
            raw_summary=discovered_item.summary,
            timeout=timeout,
        )
        if ai_enrichment is not None:
            full_text = ai_enrichment.full_text
            lead = ai_enrichment.lead or lead
            if ai_enrichment.tags:
                tags = ai_enrichment.tags

        if not _is_usable_full_text(full_text, discovered_item.summary):
            resolved_target = ai_client.resolve_article_target(
                source=source,
                raw_title=discovered_item.title,
                current_url=resolved_url,
            )
            if resolved_target is not None and resolved_target.url != resolved_url:
                resolved_url = resolved_target.url
                resolved_published_at = resolved_target.published_at or resolved_published_at
                resolved_source_title = resolved_target.source_title or resolved_source_title
                published = _try_parse_datetime(resolved_published_at or "") or published
                ai_enrichment = _extract_ai_research_article_enrichment(
                    ai_client=ai_client,
                    url=resolved_url,
                    source_title=resolved_source_title or source.title,
                    raw_title=discovered_item.title,
                    raw_summary=discovered_item.summary,
                    timeout=timeout,
                )
                if ai_enrichment is not None:
                    full_text = ai_enrichment.full_text
                    lead = ai_enrichment.lead or lead
                    if ai_enrichment.tags:
                        tags = ai_enrichment.tags

        if not _is_usable_full_text(full_text, discovered_item.summary):
            continue

        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=resolved_url,
                title=discovered_item.title,
                summary=discovered_item.summary,
                lead=lead,
                full_text=full_text,
                source_title=resolved_source_title,
                source_url=resolved_url,
                url=resolved_url,
                published=published,
                tags=tags,
            )
        )

    items.sort(key=lambda item: (item.published_at, item.importance_score), reverse=True)
    return items


def _extract_ai_research_article_enrichment(
    *,
    ai_client: OpenAIEditorialClient,
    url: str,
    source_title: str,
    raw_title: str,
    raw_summary: str,
    timeout: int,
):
    html = fetch_remote_document(url, timeout=timeout)
    if not html:
        return None
    return ai_client.extract_article_enrichment(
        url=url,
        source_title=source_title,
        raw_title=raw_title,
        raw_summary=raw_summary,
        html=html,
    )


def _discover_ai_research_candidates_from_listing(
    source: SourceItem,
    *,
    timeout: int,
) -> list["SourceDiscoveryItem"]:
    try:
        payload = _fetch_remote_document(source.url, timeout)
    except SourceFetchError:
        return []

    parser = _ScrapingDocumentParser(source.url)
    try:
        parser.feed(payload)
        parser.close()
    except ValueError:
        return []

    from .ai_client import SourceDiscoveryItem

    items: list[SourceDiscoveryItem] = []
    for candidate in parser.candidates[:12]:
        items.append(
            SourceDiscoveryItem(
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url,
                published_at=candidate.published_at.isoformat() if candidate.published_at is not None else None,
                full_text=None,
                source_title=source.title,
                tags=[],
            )
        )

    return items


def extract_article_enrichment(url: str | None, timeout: int = 10) -> ArticleEnrichmentResult | None:
    if not url:
        return None

    try:
        payload = _fetch_remote_document(url, timeout)
    except SourceFetchError:
        return None

    parser = _ArticleDocumentParser(url)
    try:
        parser.feed(payload)
        parser.close()
    except ValueError:
        return None

    paragraphs = [paragraph for paragraph in parser.paragraphs if len(paragraph) >= 40]
    full_text: str | None = None
    if len(paragraphs) >= 2:
        full_text = "\n\n".join(paragraphs)
    elif paragraphs:
        full_text = paragraphs[0]
    else:
        fallback = parser.og_description or parser.meta_description
        if fallback and len(fallback) >= 80:
            full_text = fallback

    lead = parser.og_description or parser.meta_description
    if lead:
        lead = _normalize_whitespace(lead)

    return ArticleEnrichmentResult(
        full_text=full_text,
        lead=lead or None,
        tags=parser.tags,
    )


def _is_usable_full_text(value: str | None, source_summary: str | None = None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if len(normalized) >= 180:
        return True
    if normalized.count("\n\n") >= 1 and len(normalized) >= 120:
        return True
    summary = (source_summary or "").strip()
    if summary and len(normalized) >= max(120, int(len(summary) * 1.35)):
        return True
    return False


def _is_usable_lead(value: str | None) -> bool:
    return bool(value and len(value.strip()) >= 40)


def extract_article_full_text(url: str | None, timeout: int = 10) -> str | None:
    enrichment = extract_article_enrichment(url, timeout=timeout)
    if enrichment is None:
        return None
    return enrichment.full_text


def fetch_remote_document(url: str | None, timeout: int = 10) -> str | None:
    if not url:
        return None
    try:
        return _fetch_remote_document(url, timeout)
    except SourceFetchError:
        return None


def _filter_new_items(
    items: list[RawItem],
    state: SourceSyncState | None,
    source_type: str,
) -> list[RawItem]:
    if state is not None and source_type == "scraping" and state.last_external_id:
        fresh_items: list[RawItem] = []
        for item in items:
            if item.external_id == state.last_external_id:
                break
            fresh_items.append(item)
        if fresh_items:
            return fresh_items

    if state is None or state.last_published_at is None:
        return items

    last_published_at = state.last_published_at
    last_external_id = state.last_external_id
    fresh_items: list[RawItem] = []

    for item in items:
        if item.published_at > last_published_at:
            fresh_items.append(item)
            continue

        if (
            item.published_at == last_published_at
            and last_external_id is not None
            and item.external_id != last_external_id
        ):
            fresh_items.append(item)

    return fresh_items


def _parse_rss(root: ElementTree.Element, source: SourceItem, payload: str) -> list[RawItem]:
    items: list[RawItem] = []
    fetched_at = datetime.now(timezone.utc)

    for node in root.findall("./channel/item"):
        title = _node_text(node.find("title")) or "Без заголовка"
        summary = _strip_html(_node_text(node.find("description")) or "Описание отсутствует.")
        url = _node_text(node.find("link"))
        published = _parse_datetime(_node_text(node.find("pubDate")))
        external_id = url or f"{source.key}:{title}"
        category_nodes = [_normalize_whitespace(_node_text(category)) for category in node.findall("category")]
        tags = [value for value in category_nodes if value]

        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=external_id,
                title=title,
                summary=summary,
                lead=summary,
                url=url,
                published=published,
                tags=tags,
            )
        )

    return items


def _parse_atom(root: ElementTree.Element, source: SourceItem, payload: str) -> list[RawItem]:
    items: list[RawItem] = []
    fetched_at = datetime.now(timezone.utc)
    namespace = {"atom": "http://www.w3.org/2005/Atom"}

    for node in root.findall("atom:entry", namespace):
        title = _node_text(node.find("atom:title", namespace)) or "Без заголовка"
        summary = _strip_html(_node_text(node.find("atom:summary", namespace)) or "Описание отсутствует.")
        link_node = node.find("atom:link", namespace)
        url = link_node.get("href") if link_node is not None else None
        category_nodes = [_normalize_whitespace(node.get("term", "")) for node in node.findall("atom:category", namespace)]
        tags = [value for value in category_nodes if value]
        published = _parse_datetime(
            _node_text(node.find("atom:updated", namespace))
            or _node_text(node.find("atom:published", namespace))
        )
        external_id = url or f"{source.key}:{title}"

        items.append(
            _build_raw_item(
                source=source,
                payload=payload,
                fetched_at=fetched_at,
                external_id=external_id,
                title=title,
                summary=summary,
                lead=summary,
                url=url,
                published=published,
                tags=tags,
            )
        )

    return items


def _build_raw_item(
    *,
    source: SourceItem,
    payload: str,
    fetched_at: datetime,
    external_id: str,
    title: str,
    summary: str,
    lead: str | None = None,
    full_text: str | None = None,
    source_title: str | None = None,
    source_url: str | None = None,
    url: str | None,
    published: datetime,
    tags: list[str] | None = None,
) -> RawItem:
    normalized_category = _classify_category(title, summary, source)
    dedupe_key = _make_dedupe_key(url, title)
    importance_score = _score_importance(title, summary, published, source)
    triage_label = _triage_label(importance_score)

    return RawItem(
        id=f"{source.key}:{external_id}",
        source_key=source.key,
        source_title=source_title or source.title,
        source_url=source_url or source.url,
        category=source.category,
        normalized_category=normalized_category,
        external_id=external_id,
        dedupe_key=dedupe_key,
        title=title,
        summary=summary,
        lead=lead,
        url=url,
        published_at=published,
        fetched_at=fetched_at,
        importance_score=importance_score,
        triage_label=triage_label,
        full_text=full_text,
        tags=tags or [],
        payload=payload,
    )


class _ScrapingCandidate:
    def __init__(
        self,
        url: str,
        title: str,
        summary: str,
        published_at: datetime | None = None,
    ) -> None:
        self.url = url
        self.title = title
        self.summary = summary
        self.published_at = published_at


class _ScrapingDocumentParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.base_host = urlsplit(base_url).netloc.lower()
        self.candidates: list[_ScrapingCandidate] = []
        self._seen_candidate_urls: set[str] = set()
        self._anchor_href: str | None = None
        self._anchor_title: str | None = None
        self._anchor_text_parts: list[str] = []
        self._anchor_context_score = 0
        self._anchor_published_at: datetime | None = None
        self._in_title_tag = False
        self._title_parts: list[str] = []
        self._container_scores: list[int] = [0]
        self._container_time_hints: list[datetime | None] = [None]
        self.page_title: str | None = None
        self.og_title: str | None = None
        self.meta_description: str | None = None
        self.og_description: str | None = None
        self.canonical_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        self._container_scores.append(self._container_scores[-1] + _container_score(tag, attr_map))
        self._container_time_hints.append(_extract_time_hint(attr_map) or self._container_time_hints[-1])

        if tag == "title":
            self._in_title_tag = True
            return

        if tag == "a":
            self._anchor_href = attr_map.get("href") or None
            self._anchor_title = attr_map.get("title") or None
            self._anchor_text_parts = []
            self._anchor_context_score = self._container_scores[-1]
            self._anchor_published_at = self._container_time_hints[-1]
            return

        if tag == "link" and attr_map.get("rel", "").lower() == "canonical":
            href = attr_map.get("href")
            if href:
                self.canonical_url = urljoin(self.base_url, href)
            return

        if tag != "meta":
            return

        name = attr_map.get("name", "").lower()
        prop = attr_map.get("property", "").lower()
        content = _normalize_whitespace(attr_map.get("content", ""))
        if not content:
            return

        if name == "description":
            self.meta_description = content
        elif prop == "og:title":
            self.og_title = content
        elif prop == "og:description":
            self.og_description = content
        elif prop == "og:url":
            self.canonical_url = content

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        try:
            if tag == "title":
                self._in_title_tag = False
                title = _normalize_whitespace(" ".join(self._title_parts))
                if title:
                    self.page_title = title
                self._title_parts = []
                return

            if tag != "a" or self._anchor_href is None:
                return

            href = self._anchor_href
            title = _normalize_whitespace(" ".join(self._anchor_text_parts)) or _normalize_whitespace(
                self._anchor_title or ""
            )
            url = _normalize_candidate_url(self.base_url, href)
            self._anchor_href = None
            self._anchor_title = None
            self._anchor_text_parts = []
            published_at = self._anchor_published_at

            if not url or not title or not _looks_like_story_title(title):
                return
            if self._anchor_context_score < 1:
                return
            if urlsplit(url).netloc.lower() != self.base_host:
                return
            if not _looks_like_news_url(url):
                return
            if url in self._seen_candidate_urls:
                return

            self._seen_candidate_urls.add(url)
            self.candidates.append(
                _ScrapingCandidate(
                    url=url,
                    title=title,
                    summary=title,
                    published_at=published_at,
                )
            )
        finally:
            if self._container_scores:
                self._container_scores.pop()
            if self._container_time_hints:
                self._container_time_hints.pop()

    def handle_data(self, data: str) -> None:
        if self._in_title_tag:
            self._title_parts.append(data)
        if self._anchor_href is not None:
            self._anchor_text_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._container_scores:
            self._container_scores.pop()
        if self._container_time_hints:
            self._container_time_hints.pop()


class _ArticleDocumentParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self._container_scores: list[int] = [0]
        self._skip_depth = 0
        self._text_capture_depth = 0
        self._text_capture_parts: list[str] = []
        self._in_paragraph = False
        self._paragraph_parts: list[str] = []
        self.paragraphs: list[str] = []
        self.meta_description: str | None = None
        self.og_description: str | None = None
        self.tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        self._container_scores.append(self._container_scores[-1] + _article_container_score(tag, attr_map))

        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if (
            self._skip_depth == 0
            and self._text_capture_depth == 0
            and self._container_scores[-1] >= 3
            and _looks_like_article_text_container(attr_map)
        ):
            self._text_capture_depth = 1
            self._text_capture_parts = []
        elif self._text_capture_depth > 0:
            self._text_capture_depth += 1

        if tag == "meta":
            name = attr_map.get("name", "").lower()
            prop = attr_map.get("property", "").lower()
            content = _normalize_whitespace(attr_map.get("content", ""))
            if not content:
                return
            if name == "description":
                self.meta_description = content
            elif prop == "og:description":
                self.og_description = content
            elif name == "keywords":
                self._add_tags(content)
            elif prop in {"article:tag", "og:article:tag"}:
                self._add_tags(content)
            return

        if tag == "p" and self._skip_depth == 0 and self._container_scores[-1] >= 2:
            self._in_paragraph = True
            self._paragraph_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        try:
            if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
                self._skip_depth -= 1
                return

            if tag == "p" and self._in_paragraph:
                text = _normalize_whitespace(" ".join(self._paragraph_parts))
                if text and text not in self.paragraphs:
                    self.paragraphs.append(text)
                self._in_paragraph = False
                self._paragraph_parts = []

            if self._text_capture_depth > 0:
                self._text_capture_depth -= 1
                if self._text_capture_depth == 0:
                    text = _normalize_article_text(" ".join(self._text_capture_parts))
                    for paragraph in _split_article_text(text):
                        if paragraph not in self.paragraphs:
                            self.paragraphs.append(paragraph)
                    self._text_capture_parts = []
        finally:
            if self._container_scores:
                self._container_scores.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_paragraph:
            self._paragraph_parts.append(data)
        if self._text_capture_depth > 0:
            self._text_capture_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._container_scores:
            self._container_scores.pop()

    def _add_tags(self, value: str) -> None:
        for tag in _split_meta_values(value):
            if tag not in self.tags:
                self.tags.append(tag)


def _classify_category(title: str, summary: str, source: SourceItem) -> str:
    haystack = f"{title} {summary} {source.title}".lower()

    for category, keywords in CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return category

    return "general"


def _score_importance(title: str, summary: str, published_at: datetime, source: SourceItem) -> int:
    score = 18
    title_lower = title.lower()
    summary_lower = summary.lower()
    haystack = f"{title_lower} {summary_lower}"

    score += _freshness_bonus(published_at)
    score += _source_reputation_bonus(source)
    score += _category_bonus(source, haystack)

    for term in HIGH_PRIORITY_TERMS:
        if term in title_lower:
            score += 16
        elif term in summary_lower:
            score += 8

    for term in MEDIUM_PRIORITY_TERMS:
        if term in title_lower:
            score += 6
        elif term in summary_lower:
            score += 3

    for term in MAJOR_EVENT_TERMS:
        if term in haystack:
            score += 8

    for term in OFFICIAL_SIGNAL_TERMS:
        if term in haystack:
            score += 6

    if re.search(r"\b\d+\s*[:\-]\s*\d+\b", title_lower):
        score += 4
    if re.search(r"\b\d+\s+(матч|тур|игр|round|game|games)\b", haystack):
        score += 4

    if len(title.strip()) >= 55:
        score += 3
    if len(summary.strip()) >= 140:
        score += 4
    elif len(summary.strip()) < 45:
        score -= 6

    if any(noise in haystack for noise in ("прямой эфир", "live", "видео", "video")):
        score -= 6

    return max(0, min(score, 100))


def _triage_label(score: int) -> str:
    if score >= 78:
        return "high"
    if score >= 48:
        return "medium"
    return "low"


def _freshness_bonus(published_at: datetime) -> int:
    age = datetime.now(timezone.utc) - published_at
    if age <= timedelta(hours=1):
        return 28
    if age <= timedelta(hours=3):
        return 22
    if age <= timedelta(hours=6):
        return 16
    if age <= timedelta(hours=12):
        return 10
    if age <= timedelta(hours=24):
        return 5
    return 0


def _source_reputation_bonus(source: SourceItem) -> int:
    haystack = f"{source.title} {source.url}".lower()
    best_match = 0
    for hint, bonus in SOURCE_REPUTATION_HINTS.items():
        if hint in haystack:
            best_match = max(best_match, bonus)
    return best_match


def _category_bonus(source: SourceItem, haystack: str) -> int:
    category = _classify_category("", haystack, source)
    if category in {"football", "hockey", "basketball", "tennis"}:
        return 6
    if category == "betting":
        return 4
    return 0


def _make_dedupe_key(url: str | None, title: str) -> str:
    if url:
        normalized_url = _normalize_url(url)
        if normalized_url:
            return normalized_url

    normalized_title = " ".join(title.lower().split())
    return normalized_title[:240]


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url.strip().lower()

    cleaned = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
    return cleaned.rstrip("/")


def _normalize_candidate_url(base_url: str, href: str) -> str | None:
    normalized = _normalize_url(urljoin(base_url, href))
    parts = urlsplit(normalized)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return normalized


def _looks_like_story_title(value: str) -> bool:
    lowered = value.strip().lower()
    if len(lowered) < 18:
        return False
    if len(re.findall(r"[a-zа-я0-9]+", lowered, flags=re.IGNORECASE)) < 3:
        return False

    blocked = {
        "читать далее",
        "подробнее",
        "новости",
        "главная",
        "войти",
        "регистрация",
        "все новости",
        "прямой эфир",
        "смотреть",
    }
    if lowered in blocked:
        return False
    blocked_terms = ("канал", "подписк", "кинотеатр", "okko", "аккаунт", "авторизац")
    return not any(term in lowered for term in blocked_terms)


def _normalize_whitespace(value: str) -> str:
    return " ".join(unescape(value).split())


def _split_meta_values(value: str) -> list[str]:
    cleaned = _normalize_whitespace(value)
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"[;,|/]", cleaned) if part.strip()]


def _looks_like_article_text_container(attr_map: dict[str, str]) -> bool:
    haystack = " ".join(
        filter(
            None,
            (
                attr_map.get("class", ""),
                attr_map.get("id", ""),
                attr_map.get("itemprop", ""),
                attr_map.get("data-testid", ""),
            ),
        )
    ).lower()
    if not haystack:
        return False

    positive = (
        "articletext",
        "article-text",
        "article_text",
        "articlebody",
        "article-body",
        "article_body",
        "articlecontent",
        "article-content",
        "article_content",
        "article-card-text",
        "news-text",
        "news_content",
        "storytext",
        "story-text",
        "post-content",
        "entry-content",
        "material-content",
        "contentbody",
        "content-body",
        "bodytext",
        "textcontainer",
        "text-container",
    )
    negative = (
        "card",
        "cards",
        "container",
        "preview",
        "related",
        "recommend",
        "comment",
        "share",
        "tag",
        "author",
        "breadcrumb",
        "pagination",
    )
    return any(term in haystack for term in positive) and not any(term in haystack for term in negative)


def _normalize_article_text(value: str) -> str:
    cleaned = _normalize_whitespace(value)
    cleaned = re.sub(r"\s+(?=[,.;:!?])", "", cleaned)
    return cleaned


def _split_article_text(value: str) -> list[str]:
    if not value:
        return []
    chunks = re.split(r"(?<=[.!?])\s+(?=[А-ЯA-Z«\"0-9])", value)
    paragraphs: list[str] = []
    current: list[str] = []
    current_len = 0
    for chunk in chunks:
        cleaned = chunk.strip()
        if not cleaned:
            continue
        current.append(cleaned)
        current_len += len(cleaned)
        if current_len >= 180:
            paragraphs.append(" ".join(current))
            current = []
            current_len = 0
    if current:
        paragraphs.append(" ".join(current))
    return [paragraph for paragraph in paragraphs if len(paragraph) >= 40]


def _serialize_ai_discovery_payload(source: SourceItem, discovered_items: list[object]) -> str:
    return (
        f'{{"source_type":"ai_research","source_key":{json.dumps(source.key)},'
        f'"source_url":{json.dumps(source.url)},"item_count":{len(discovered_items)}}}'
    )


def _fetch_remote_document(url: str, timeout: int) -> str:
    try:
        with urlopen(url, timeout=timeout) as response:
            if getattr(response, "status", 200) >= 400:
                raise SourceFetchError(f"Fetch failed for {url}: HTTP {response.status}")
            payload = response.read()
    except HTTPError as exc:
        raise SourceFetchError(f"Fetch failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise SourceFetchError(f"Fetch failed for {url}: {exc.reason if hasattr(exc, 'reason') else exc}") from exc

    return payload.decode("utf-8", errors="ignore")


def _extract_time_hint(attr_map: dict[str, str]) -> datetime | None:
    candidate_keys = (
        "datetime",
        "data-datetime",
        "data-date",
        "data-published",
        "data-published-at",
        "data-created-at",
    )
    for key in candidate_keys:
        value = _normalize_whitespace(attr_map.get(key, ""))
        if not value:
            continue
        parsed = _try_parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _container_score(tag: str, attr_map: dict[str, str]) -> int:
    score = 0
    if tag in {"article", "main", "section", "li", "h2", "h3", "h4"}:
        score += 1

    haystack = " ".join(
        filter(
            None,
            (
                attr_map.get("class", ""),
                attr_map.get("id", ""),
                attr_map.get("data-testid", ""),
            ),
        )
    ).lower()

    if any(term in haystack for term in POSITIVE_CONTAINER_TERMS):
        score += 1
    if any(term in haystack for term in NEGATIVE_CONTAINER_TERMS):
        score -= 2

    return score


def _article_container_score(tag: str, attr_map: dict[str, str]) -> int:
    score = 0
    if tag in {"article", "main", "section", "div"}:
        score += 1

    haystack = " ".join(
        filter(
            None,
            (
                attr_map.get("class", ""),
                attr_map.get("id", ""),
                attr_map.get("itemprop", ""),
                attr_map.get("role", ""),
            ),
        )
    ).lower()

    if any(term in haystack for term in ARTICLE_CONTAINER_TERMS):
        score += 2
    if any(term in haystack for term in ARTICLE_NEGATIVE_TERMS):
        score -= 3

    return score


def _looks_like_news_url(url: str) -> bool:
    parts = urlsplit(url)
    path = parts.path.strip("/").lower()
    if not path:
        return False

    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False

    if any(segment in BLOCKED_URL_SEGMENTS for segment in segments):
        return False

    if any(segment in PREFERRED_URL_SEGMENTS for segment in segments):
        return True

    if len(segments) >= 2:
        return True

    return bool(re.search(r"\d", path))


def _try_parse_datetime(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _node_text(node: ElementTree.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return node.text.strip()


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _strip_html(value: str) -> str:
    if "<" not in value:
        return value

    try:
        return " ".join(ElementTree.fromstring(f"<root>{value}</root>").itertext())
    except ElementTree.ParseError:
        return value
