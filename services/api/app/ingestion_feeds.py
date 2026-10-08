from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from xml.etree import ElementTree
from .models import (
    RawItem,
    SourceItem,
)
from .ingestion_network import _fetch_remote_document
from .ingestion_scoring import _build_raw_item
from .ingestion_text import (
    _node_text,
    _normalize_whitespace,
    _parse_datetime,
    _strip_html,
)


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

