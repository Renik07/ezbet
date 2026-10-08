from __future__ import annotations

import unicodedata
import zlib
from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)
import psycopg
from .models import RawItem

_CYRILLIC_TO_LATIN = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)

@dataclass
class InsertRawItemsResult:
    inserted_count: int
    skipped_items: list[dict[str, str]]

@dataclass
class PrefilterRawItemsResult:
    fresh_items: list[RawItem]
    skipped_items: list[dict[str, str]]

def _reset_pooled_connection(connection: psycopg.Connection) -> None:
    # Session advisory locks must not leak to the next borrower after an error.
    connection.execute("SELECT pg_advisory_unlock_all()")
    connection.commit()

def _build_article_slug(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title.lower()).translate(_CYRILLIC_TO_LATIN)
    normalized = "".join(char if char.isascii() and char.isalnum() else "-" for char in normalized)
    slug = "-".join(part for part in normalized.split("-") if part).strip("-")
    if not slug:
        slug = "article"

    return slug[:80].rstrip("-")

def _deduplicate_article_slug(base_slug: str, used_slugs: set[str]) -> str:
    if base_slug not in used_slugs:
        return base_slug

    number = 2
    while True:
        suffix = f"-{number}"
        candidate = f"{base_slug[:80 - len(suffix)].rstrip('-')}{suffix}"
        if candidate not in used_slugs:
            return candidate
        number += 1

def _available_article_slug(cursor: psycopg.Cursor, base_slug: str, article_id: str) -> str:
    cursor.execute("SELECT slug FROM articles WHERE id = %s", (article_id,))
    existing = cursor.fetchone()
    if existing is not None:
        # Published URLs are immutable: title edits and repeated upserts must
        # never replace a URL that may already be indexed or shared.
        return str(existing[0])

    cursor.execute(
        "SELECT slug FROM articles WHERE slug = %s OR slug LIKE %s",
        (base_slug, f"{base_slug}-%"),
    )
    used_slugs = {str(row[0]) for row in cursor.fetchall()}
    return _deduplicate_article_slug(base_slug, used_slugs)

def _build_public_published_at(raw_item: RawItem) -> datetime:
    return _build_public_published_at_from_values(
        source_key=raw_item.source_key,
        external_id=raw_item.external_id,
        title=raw_item.title,
        fetched_at=raw_item.fetched_at,
    )

def _build_public_published_at_from_values(
    *,
    source_key: str,
    external_id: str,
    title: str,
    fetched_at: datetime,
) -> datetime:
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    else:
        fetched_at = fetched_at.astimezone(timezone.utc)

    seed = f"{source_key}:{external_id}:{title}".encode("utf-8", errors="ignore")
    hash_value = zlib.crc32(seed)
    offset_seconds = 120 + (hash_value % (54 * 60))
    return fetched_at - timedelta(hours=1) + timedelta(seconds=offset_seconds)

