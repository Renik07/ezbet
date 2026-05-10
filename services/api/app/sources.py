from __future__ import annotations

import json
from pathlib import Path

from .models import SourceItem

DEFAULT_SOURCE_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "sources.json"
)

FALLBACK_SOURCES: list[SourceItem] = [
    SourceItem(
        key="sports-ru-topnews",
        title="Sports.ru",
        url="https://www.sports.ru/rss/topnews.xml",
        category="Спорт",
    ),
    SourceItem(
        key="sport-express-news",
        title="Спорт-Экспресс",
        url="https://www.sport-express.ru/services/materials/news/se/",
        category="Спорт",
    ),
]


def load_sources(path: Path = DEFAULT_SOURCE_CONFIG_PATH) -> list[SourceItem]:
    if not path.exists():
        return FALLBACK_SOURCES

    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("items", [])
    return [SourceItem(**item) for item in items] or FALLBACK_SOURCES
