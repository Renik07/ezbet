from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from .models import (
    RawItem,
    SourceItem,
)


SUPPORTED_ACTIVE_SOURCE_TYPES = {"rss", "news_sitemap", "scraping", "ai_research"}


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
    "advertisement",
    "advertising",
    "ads",
    "promo",
    "cookie",
    "cookies",
    "agreement",
    "privacy",
    "policy",
    "policies",
    "terms",
    "legal",
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


LIVE_MATCH_TRACKER_TERMS = (
    "онлайн-трансляц",
    "онлайн трансляц",
    "прямой эфир",
    "текстовая трансляц",
    "live",
    "лайв",
    "matchcenter",
    "match centre",
    "match center",
    "история личных встреч",
    "коэффиц",
)


CHAMPIONAT_ALLOWED_TOP_LEVEL_SECTIONS = {
    "football",
    "hockey",
    "basketball",
    "tennis",
    "boxing",
    "mma",
    "auto",
    "f1",
    "biathlon",
    "skiing",
    "figure-skating",
    "volleyball",
    "handball",
    "athletics",
    "swimming",
    "chess",
    "other",
}


CHAMPIONAT_BLOCKED_TOP_LEVEL_SECTIONS = {
    "lifestyle",
    "health",
    "medicine",
    "food",
    "travel",
    "science",
    "tech",
    "technology",
    "business",
    "auto-world",
    "esports",
    "cybersport",
    "games",
    "game",
    "movies",
    "music",
    "showbiz",
    "culture",
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


ARTICLE_TRAILING_NOISE_MARKERS = (
    "читать дальше",
    "читать также",
    "читайте также",
    "по теме",
    "также по теме",
    "совспорт теперь",
    "заглавное фото",
    "источник:",
)


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
    filter_reasons: dict[str, int] | None = None


class SourceFetchError(RuntimeError):
    pass


@dataclass
class ArticleEnrichmentResult:
    title: str | None
    full_text: str | None
    lead: str | None
    tags: list[str]


@dataclass
class SourceProbeResult:
    ok: bool
    item_count: int
    message: str
    readiness: str
    resolved_source_type: str | None
    resolved_source_url: str | None
    supports_rss: bool
    supports_news_sitemap: bool
    supports_sitemap: bool
    supports_scraping: bool
    full_text_ok: bool
    full_text_method: str | None
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


DEFAULT_INGEST_MAX_ITEM_AGE = timedelta(hours=1)



CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("football", ("футбол", "football", "soccer", "рпл", "лига чемпионов", "апл", "ла лига", "серия а")),
    ("hockey", ("хоккей", "hockey", "кхл", "нхл", "nhl")),
    ("basketball", ("баскетбол", "basketball", "нба", "nba", "евролига", "единая лига втб", "vtb")),
    ("tennis", ("теннис", "tennis", "atp", "wta", "ролан гаррос", "wimbledon", "us open")),
    ("mma", ("mma", "ufc", "bellator", "смешанн", "единоборств", "мма")),
    ("boxing", ("бокс", "boxing", "box", "wbc", "wba", "ibf", "wbo")),
    ("fencing", ("фехтован", "fencing")),
    ("volleyball", ("волейбол", "volleyball")),
    ("handball", ("гандбол", "handball")),
    ("swimming", ("плавани", "swimming")),
    ("athletics", ("лёгкая атлетика", "легкая атлетика", "athletics", "track and field")),
    ("biathlon", ("биатлон", "biathlon")),
    ("skiing", ("лыжи", "лыж", "skiing", "лыжные гонки", "горные лыжи")),
    ("figure_skating", ("фигурное катание", "figure skating")),
    ("gymnastics", ("гимнастик", "gymnastics")),
    ("motorsport", ("формула-1", "формула 1", "formula 1", "f1", "motorsport", "автоспорт", "motogp")),
    ("chess", ("шахмат", "chess")),
    ("esports", ("киберспорт", "esports", "e-sports", "dota", "cs2", "counter-strike", "league of legends")),
    ("betting", ("букмекер", "ставк", "bet", "коэффициент", "линия")),
]


SOURCE_REPUTATION_HINTS: dict[str, int] = {
    "sports.ru": 6,
    "sport-express": 7,
    "спорт-экспресс": 7,
    "championat": 6,
    "чемпионат": 6,
    "sovsport": 5,
    "советский спорт": 5,
}

