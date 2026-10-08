from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.parse import urlsplit
from .ingestion_text import (
    _article_container_score,
    _is_sovsport_preferred_article_container,
    _looks_like_article_text_container,
    _normalize_article_text,
    _normalize_whitespace,
    _split_article_text,
    _split_meta_values,
)


class _ArticleDocumentParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.base_host = urlsplit(base_url).netloc.lower()
        self._container_scores: list[int] = [0]
        self._skip_depth = 0
        self._text_capture_depth = 0
        self._text_capture_parts: list[str] = []
        self._preferred_container_depth = 0
        self._preferred_text_capture_depth = 0
        self._preferred_text_capture_parts: list[str] = []
        self._in_paragraph = False
        self._paragraph_parts: list[str] = []
        self._in_title_tag = False
        self._title_parts: list[str] = []
        self._in_h1_tag = False
        self._h1_parts: list[str] = []
        self._in_json_ld_script = False
        self._json_ld_parts: list[str] = []
        self.paragraphs: list[str] = []
        self.preferred_paragraphs: list[str] = []
        self.preferred_container_paragraphs: list[str] = []
        self.preferred_container_text: str | None = None
        self.page_title: str | None = None
        self.og_title: str | None = None
        self.heading_title: str | None = None
        self.meta_description: str | None = None
        self.og_description: str | None = None
        self.tags: list[str] = []
        self.json_ld_title: str | None = None
        self.json_ld_description: str | None = None
        self.json_ld_article_body: str | None = None
        self.json_ld_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        self._container_scores.append(self._container_scores[-1] + _article_container_score(tag, attr_map))
        if self._preferred_container_depth > 0:
            self._preferred_container_depth += 1
            if self._preferred_text_capture_depth > 0:
                self._preferred_text_capture_depth += 1
        elif _is_sovsport_preferred_article_container(self.base_host, attr_map):
            self._preferred_container_depth = 1
            self._preferred_text_capture_depth = 1
            self._preferred_text_capture_parts = []

        if tag == "title":
            self._in_title_tag = True
            return
        if tag == "h1":
            self._in_h1_tag = True
            self._h1_parts = []

        if tag == "script" and attr_map.get("type", "").lower() == "application/ld+json":
            self._in_json_ld_script = True
            self._json_ld_parts = []
            return

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
            elif prop == "og:title":
                self.og_title = content
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
            if tag == "title":
                self._in_title_tag = False
                title = _normalize_whitespace(" ".join(self._title_parts))
                if title:
                    self.page_title = title
                self._title_parts = []
                return
            if tag == "h1" and self._in_h1_tag:
                self._in_h1_tag = False
                heading = _normalize_whitespace(" ".join(self._h1_parts))
                if heading and not self.heading_title:
                    self.heading_title = heading
                self._h1_parts = []

            if tag == "script" and self._in_json_ld_script:
                self._in_json_ld_script = False
                self._consume_json_ld_script("".join(self._json_ld_parts))
                self._json_ld_parts = []
                return

            if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
                self._skip_depth -= 1
                return

            if tag == "p" and self._in_paragraph:
                text = _normalize_whitespace(" ".join(self._paragraph_parts))
                if text and text not in self.paragraphs:
                    self.paragraphs.append(text)
                if (
                    text
                    and self._preferred_container_depth > 0
                    and text not in self.preferred_paragraphs
                ):
                    self.preferred_paragraphs.append(text)
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
            if self._preferred_text_capture_depth > 0:
                self._preferred_text_capture_depth -= 1
                if self._preferred_text_capture_depth == 0:
                    text = _normalize_article_text(" ".join(self._preferred_text_capture_parts))
                    if text and not self.preferred_container_text:
                        self.preferred_container_text = text
                    for paragraph in _split_article_text(text):
                        if paragraph not in self.preferred_container_paragraphs:
                            self.preferred_container_paragraphs.append(paragraph)
                    self._preferred_text_capture_parts = []
        finally:
            if self._preferred_container_depth > 0:
                self._preferred_container_depth -= 1
            if self._container_scores:
                self._container_scores.pop()

    def handle_data(self, data: str) -> None:
        if self._in_title_tag:
            self._title_parts.append(data)
        if self._in_h1_tag:
            self._h1_parts.append(data)
        if self._in_json_ld_script:
            self._json_ld_parts.append(data)
            return
        if self._skip_depth > 0:
            return
        if self._in_paragraph:
            self._paragraph_parts.append(data)
        if self._text_capture_depth > 0:
            self._text_capture_parts.append(data)
        if self._preferred_text_capture_depth > 0:
            self._preferred_text_capture_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._container_scores:
            self._container_scores.pop()

    def _add_tags(self, value: str) -> None:
        for tag in _split_meta_values(value):
            if tag not in self.tags:
                self.tags.append(tag)

    def _consume_json_ld_script(self, payload: str) -> None:
        cleaned = payload.strip()
        if not cleaned:
            return
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return
        _merge_json_ld_article_metadata(self, data)


def _merge_json_ld_article_metadata(parser: _ArticleDocumentParser, payload: object) -> None:
    if isinstance(payload, list):
        for item in payload:
            _merge_json_ld_article_metadata(parser, item)
        return

    if not isinstance(payload, dict):
        return

    if "@graph" in payload:
        _merge_json_ld_article_metadata(parser, payload.get("@graph"))

    article_type = str(payload.get("@type") or "").lower()
    if article_type and article_type not in {
        "newsarticle",
        "article",
        "blogposting",
        "report",
        "liveblogposting",
    }:
        return

    headline = _normalize_whitespace(str(payload.get("headline") or ""))
    description = _normalize_whitespace(str(payload.get("description") or ""))
    article_body = _normalize_whitespace(str(payload.get("articleBody") or payload.get("articlebody") or ""))
    keywords = payload.get("keywords")

    if headline and not parser.json_ld_title:
        parser.json_ld_title = headline
    if description and not parser.json_ld_description:
        parser.json_ld_description = description
    if article_body and (not parser.json_ld_article_body or len(article_body) > len(parser.json_ld_article_body)):
        parser.json_ld_article_body = article_body

    if isinstance(keywords, str):
        for tag in _split_meta_values(keywords):
            if tag not in parser.json_ld_tags:
                parser.json_ld_tags.append(tag)
    elif isinstance(keywords, list):
        for keyword in keywords:
            tag = _normalize_whitespace(str(keyword or ""))
            if tag and tag not in parser.json_ld_tags:
                parser.json_ld_tags.append(tag)

