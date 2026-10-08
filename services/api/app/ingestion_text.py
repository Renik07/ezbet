from __future__ import annotations

import json
import re
from datetime import (
    datetime,
    timezone,
)
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree
from .content_filters import detect_promotional_giveaway
from .models import (
    RawItem,
    SourceItem,
)
from .ingestion_types import (
    ARTICLE_CONTAINER_TERMS,
    ARTICLE_NEGATIVE_TERMS,
    ARTICLE_TRAILING_NOISE_MARKERS,
    LIVE_MATCH_TRACKER_TERMS,
    NEGATIVE_CONTAINER_TERMS,
    POSITIVE_CONTAINER_TERMS,
)






def _merge_tags(*tag_groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in tag_groups:
        for tag in group:
            normalized = _normalize_whitespace(tag)
            lowered = normalized.lower()
            if not normalized or lowered in seen:
                continue
            seen.add(lowered)
            merged.append(normalized)
    return merged


def _is_usable_full_text(value: str | None, *context_parts: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if _contains_article_noise_marker(normalized):
        return False
    if _looks_like_listing_text(normalized):
        return False
    if len(normalized) >= 160 and _article_context_overlap(normalized, *context_parts) < 0.08:
        return False
    if len(normalized) >= 180:
        return True
    if normalized.count("\n\n") >= 1 and len(normalized) >= 120:
        return True
    primary_context = next((part.strip() for part in context_parts if part and part.strip()), "")
    if primary_context and len(normalized) >= max(120, int(len(primary_context) * 1.35)):
        return True
    return False


def _is_probe_usable_full_text(value: str | None, *context_parts: str | None) -> bool:
    if _is_usable_full_text(value, *context_parts):
        return True
    if not value:
        return False

    normalized = value.strip()
    if _contains_article_noise_marker(normalized):
        return False
    if _looks_like_listing_text(normalized):
        return False
    if _article_context_overlap(normalized, *context_parts) < 0.08:
        return False

    if len(normalized) >= 100:
        return True
    if len(normalized) >= 80 and any(part and part.strip() for part in context_parts):
        return True
    return False


def _is_usable_lead(value: str | None) -> bool:
    return bool(value and len(value.strip()) >= 40)


def _looks_like_live_match_tracker(title: str, summary: str) -> bool:
    title_lower = title.strip().lower()
    summary_lower = summary.strip().lower()
    haystack = f"{title_lower} {summary_lower}"

    if any(term in haystack for term in LIVE_MATCH_TRACKER_TERMS):
        return True

    if re.search(r"^\s*.+\s+[–:-]\s+[–:-]\s+.+\s*$", title_lower):
        return True

    if re.search(r"^\s*.+\s+[–-]\s+\d+\s*:\s*\d+\s+.+\s*$", title_lower):
        return True

    return False


def _should_drop_raw_item_as_service_page(raw_item: RawItem) -> bool:
    if _looks_like_live_match_tracker(raw_item.title, raw_item.summary or ""):
        return True

    if detect_promotional_giveaway(
        raw_item.title,
        raw_item.summary,
        raw_item.lead,
        raw_item.full_text,
    ) is not None:
        return True

    lead = (raw_item.lead or "").strip()
    full_text = (raw_item.full_text or "").strip()
    service_haystack = " ".join(
        part.strip().lower()
        for part in (raw_item.title, raw_item.summary or "", lead, full_text)
        if part
    )

    if "онлайн-трансляц" in service_haystack or "прямой эфир" in service_haystack:
        return True

    return False


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
    if any(term in lowered for term in blocked_terms):
        return False
    return not _looks_like_category_label(lowered)


def _looks_like_listing_title(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    patterns = (
        "новости ",
        "последние новости",
        "актуальные события",
        "самые свежие",
        "все новости",
    )
    return any(pattern in lowered for pattern in patterns)


def _looks_like_category_label(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False

    words = re.findall(r"[a-zа-я0-9]+", lowered, flags=re.IGNORECASE)
    if 1 <= len(words) <= 4 and lowered.count("/") >= 1 and not re.search(r"\d", lowered):
        return True

    generic_labels = {
        "футбол",
        "хоккей",
        "теннис",
        "баскетбол",
        "биатлон",
        "бобслей",
        "скелетон",
        "санный спорт",
        "фигурное катание",
        "мма",
        "бокс",
        "авто",
        "формула 1",
        "кхл",
        "нхл",
        "рпл",
        "апл",
        "ла лига",
        "серия а",
        "лига 1",
        "бундеслига",
    }
    return lowered in generic_labels


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
        "text-editor",
        "text_editor",
        "content-controller_text-editor",
        "content-controller__text-editor",
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


def _is_sovsport_preferred_article_container(base_host: str, attr_map: dict[str, str]) -> bool:
    if "sovsport.ru" not in base_host:
        return False
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
    return "content-controller_text-editor" in haystack or "text-editor" in haystack


def _contains_article_noise_marker(value: str | None) -> bool:
    if not value:
        return False
    normalized = _normalize_dedupe_text(value)
    if not normalized:
        return False
    for marker in ARTICLE_TRAILING_NOISE_MARKERS:
        if _normalize_dedupe_text(marker) in normalized:
            return True
    return False


def _article_context_overlap(value: str | None, *context_parts: str | None) -> float:
    if not value:
        return 1.0
    context_tokens: set[str] = set()
    for part in context_parts:
        if not part:
            continue
        context_tokens.update(
            token
            for token in _normalize_dedupe_text(part).split()
            if len(token) >= 4
        )
    if not context_tokens:
        return 1.0

    text_tokens = {
        token
        for token in _normalize_dedupe_text(value).split()
        if len(token) >= 4
    }
    if not text_tokens:
        return 0.0
    return len(text_tokens & context_tokens) / len(context_tokens)


def _score_article_text_candidate(
    value: str,
    *,
    title: str | None,
    lead: str | None,
) -> tuple[int, int]:
    score = 0
    overlap = _article_context_overlap(value, title, lead)

    if overlap >= 0.2:
        score += 4
    elif overlap >= 0.12:
        score += 3
    elif overlap >= 0.08:
        score += 2
    elif overlap >= 0.04:
        score += 1

    if _contains_article_noise_marker(value):
        score -= 4
    if _looks_like_listing_text(value):
        score -= 5
    if len(value) >= 180:
        score += 1

    return score, int(overlap * 1000)


def _normalize_jsonld_article_body(value: str | None) -> str | None:
    if not value:
        return None
    normalized = _trim_article_trailing_noise_text(_normalize_whitespace(value))
    if not normalized:
        return None
    paragraphs = _split_article_text(normalized)
    if len(paragraphs) >= 2:
        return "\n\n".join(paragraphs)
    if paragraphs:
        return paragraphs[0]
    return normalized if len(normalized) >= 80 else None


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


def _dedupe_article_paragraphs(paragraphs: list[str]) -> list[str]:
    unique: list[str] = []
    normalized_seen: list[str] = []

    for paragraph in paragraphs:
        normalized = _normalize_dedupe_text(paragraph)
        if not normalized:
            continue

        is_duplicate = False
        for seen in normalized_seen:
            if normalized == seen:
                is_duplicate = True
                break
            if normalized in seen and len(normalized) >= int(len(seen) * 0.7):
                is_duplicate = True
                break
            if seen in normalized and len(seen) >= int(len(normalized) * 0.7):
                is_duplicate = True
                break
            if _text_overlap_ratio(normalized, seen) >= 0.9:
                is_duplicate = True
                break

        if is_duplicate:
            continue

        unique.append(paragraph)
        normalized_seen.append(normalized)

    return unique


def _trim_article_trailing_noise(paragraphs: list[str]) -> list[str]:
    trimmed: list[str] = []

    for paragraph in paragraphs:
        normalized = _normalize_dedupe_text(paragraph)
        if any(marker in normalized for marker in ARTICLE_TRAILING_NOISE_MARKERS):
            break
        cropped = _trim_article_trailing_noise_text(paragraph)
        if cropped:
          trimmed.append(cropped)
          if cropped != paragraph:
              break

    return trimmed or paragraphs


def _trim_article_trailing_noise_text(value: str | None) -> str | None:
    if not value:
        return value

    original = value.strip()
    lowered = original.lower()
    cut_index: int | None = None

    for marker in ARTICLE_TRAILING_NOISE_MARKERS:
        index = lowered.find(marker)
        if index == -1:
            continue
        if cut_index is None or index < cut_index:
            cut_index = index

    if cut_index is None:
        return original

    trimmed = original[:cut_index].rstrip(" \n\r\t:;,.!-")
    return trimmed or None


def _normalize_dedupe_text(value: str) -> str:
    cleaned = _normalize_whitespace(value).lower()
    cleaned = cleaned.replace("ё", "е")
    cleaned = re.sub(r"[^\w\sа-яa-z0-9]", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _text_overlap_ratio(left: str, right: str) -> float:
    left_tokens = {token for token in left.split() if len(token) > 2}
    right_tokens = {token for token in right.split() if len(token) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    baseline = min(len(left_tokens), len(right_tokens))
    if baseline == 0:
        return 0.0
    return intersection / baseline


def _serialize_sitemap_payload(source: SourceItem, source_type: str, item_count: int) -> str:
    return (
        "{"
        f'"source_type":{json.dumps(source_type)},'
        f'"source_key":{json.dumps(source.key)},'
        f'"source_url":{json.dumps(source.url)},'
        f'"item_count":{item_count}'
        "}"
    )


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find_child(node: ElementTree.Element | None, names: set[str]) -> ElementTree.Element | None:
    if node is None:
        return None
    wanted = {name.lower() for name in names}
    for child in node:
        if _xml_local_name(child.tag) in wanted:
            return child
    return None


def _find_child_text(node: ElementTree.Element | None, names: set[str]) -> str | None:
    child = _find_child(node, names)
    return _node_text(child)


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


def _looks_like_listing_text(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False

    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if len(lines) >= 4:
        list_like_lines = sum(
            1
            for line in lines
            if re.match(r"^\d{1,2}:\d{2}\s+", line) and "|" in line
        )
        if list_like_lines >= 3:
            return True

    compact = " ".join(normalized.split())
    matches = re.findall(r"\b\d{1,2}:\d{2}\b.*?\|\s*\d+", compact)
    return len(matches) >= 3


def _looks_like_translit_slug_title(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    if re.search(r"[А-Яа-я]", normalized):
        return False
    words = re.findall(r"[a-z0-9]+", normalized.lower())
    if len(words) < 4:
        return False
    translit_patterns = (
        "zh",
        "shh",
        "sh",
        "kh",
        "ts",
        "ch",
        "ya",
        "yu",
        "yo",
        "cz",
    )
    translit_word_count = sum(
        1 for word in words if any(pattern in word for pattern in translit_patterns)
    )
    if translit_word_count >= 2:
        return True

    translit_markers = {
        "povyol",
        "kubka",
        "stenli",
        "zabili",
        "golu",
        "vyshel",
        "chempionov",
        "rossiya",
        "futbol",
        "khokkey",
        "rolan",
        "garros",
        "ukrainskih",
        "diskvalificzirovala",
        "korrupcziyu",
        "tennisisty",
        "ogranichat",
        "obshhenie",
    }
    return any(marker in words for marker in translit_markers)


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

