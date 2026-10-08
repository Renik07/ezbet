from __future__ import annotations

from .ingestion_article_parser import _ArticleDocumentParser
from .ingestion_network import _fetch_remote_document
from .ingestion_text import (
    _dedupe_article_paragraphs,
    _looks_like_listing_text,
    _merge_tags,
    _normalize_jsonld_article_body,
    _normalize_whitespace,
    _score_article_text_candidate,
    _trim_article_trailing_noise,
    _trim_article_trailing_noise_text,
)
from .ingestion_types import (
    ArticleEnrichmentResult,
    SourceFetchError,
)
from .ingestion_urls import _is_sovsport_host


def extract_article_enrichment(url: str | None, timeout: int = 10) -> ArticleEnrichmentResult | None:
    if not url:
        return None

    try:
        payload = _fetch_remote_document(url, timeout)
    except SourceFetchError:
        return None

    return _extract_article_enrichment_from_html(url, payload)


def _extract_article_enrichment_from_html(url: str, payload: str | None) -> ArticleEnrichmentResult | None:
    if not payload:
        return None

    parser = _ArticleDocumentParser(url)
    try:
        parser.feed(payload)
        parser.close()
    except ValueError:
        return None

    resolved_title = parser.og_title or parser.json_ld_title or parser.heading_title or parser.page_title
    if resolved_title:
        resolved_title = _normalize_whitespace(resolved_title)

    lead = parser.og_description or parser.json_ld_description or parser.meta_description
    if lead:
        lead = _normalize_whitespace(lead)

    html_full_text: str | None = None
    if _is_sovsport_host(url) and parser.preferred_container_text:
        html_full_text = parser.preferred_container_text
    else:
        if _is_sovsport_host(url):
            paragraph_source = (
                parser.preferred_paragraphs
                or parser.preferred_container_paragraphs
                or parser.paragraphs
            )
        else:
            paragraph_source = parser.preferred_paragraphs if parser.preferred_paragraphs else parser.paragraphs
        paragraphs = _trim_article_trailing_noise(
            _dedupe_article_paragraphs(
                [paragraph for paragraph in paragraph_source if len(paragraph) >= 40]
            )
        )
        if len(paragraphs) >= 2:
            html_full_text = "\n\n".join(paragraphs)
        elif paragraphs:
            html_full_text = paragraphs[0]
        else:
            fallback = parser.og_description or parser.meta_description
            if fallback and len(fallback) >= 80:
                html_full_text = fallback

    html_full_text = _trim_article_trailing_noise_text(html_full_text)
    jsonld_full_text = _normalize_jsonld_article_body(parser.json_ld_article_body)
    full_text = _choose_best_article_full_text(
        url,
        html_full_text=html_full_text,
        jsonld_full_text=jsonld_full_text,
        title=resolved_title,
        lead=lead,
    )

    if _looks_like_listing_text(full_text):
        full_text = None

    return ArticleEnrichmentResult(
        title=resolved_title or None,
        full_text=full_text,
        lead=lead or None,
        tags=_merge_tags(parser.tags, parser.json_ld_tags),
    )


def _choose_best_article_full_text(
    url: str,
    *,
    html_full_text: str | None,
    jsonld_full_text: str | None,
    title: str | None,
    lead: str | None,
) -> str | None:
    candidates = [
        candidate
        for candidate in (html_full_text, jsonld_full_text)
        if candidate
    ]
    if not candidates:
        return None

    return max(
        candidates,
        key=lambda candidate: (
            _score_article_text_candidate(candidate, title=title, lead=lead),
            len(candidate),
        ),
    )


def extract_article_full_text(url: str | None, timeout: int = 10) -> str | None:
    enrichment = extract_article_enrichment(url, timeout=timeout)
    if enrichment is None:
        return None
    return enrichment.full_text

