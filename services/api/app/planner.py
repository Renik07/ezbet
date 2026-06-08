from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from .ai_client import OpenAIEditorialClient, PlannerRerankItem
from .models import ContentPlanItem, RawItem
from .repository import NewsRepository

STRICT_SHORTLIST_POOL_MULTIPLIER = 3
STRICT_SHORTLIST_LOW_FALLBACK_CAP = 2
STRICT_SHORTLIST_LOW_SCORE_FLOOR = 36
STRICT_SHORTLIST_LOW_MAX_AGE = timedelta(hours=24)
STRICT_SHORTLIST_LOW_FULL_TEXT_MIN_LEN = 280
STRICT_SHORTLIST_LOW_SUMMARY_MIN_LEN = 110
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


def run_content_planner(
    repository: NewsRepository,
    limit: int = 6,
    since: datetime | None = None,
) -> list[ContentPlanItem]:
    shortlist_limit = max(limit * STRICT_SHORTLIST_POOL_MULTIPLIER, limit)
    pool_limit = max(shortlist_limit * STRICT_SHORTLIST_POOL_MULTIPLIER, limit)
    candidate_pool = repository.list_raw_candidates_for_plan(limit=pool_limit, since=since)
    candidates = build_editorial_shortlist(candidate_pool, shortlist_limit=shortlist_limit, batch_limit=limit)
    planned_items: list[ContentPlanItem] = []
    ai_client = OpenAIEditorialClient()
    reranked_items = select_reranked_candidates(candidates, limit=limit, ai_client=ai_client)

    for raw_item, rerank in reranked_items:
        plan_item = build_plan_item(raw_item, rerank)
        planned_items.append(repository.upsert_content_plan_item(plan_item))

    return planned_items


def build_editorial_shortlist(
    candidates: list[RawItem],
    *,
    shortlist_limit: int,
    batch_limit: int,
) -> list[RawItem]:
    if not candidates:
        return []

    preferred_candidates = [
        item for item in candidates if item.triage_label in {"high", "medium"} and not is_live_match_tracker_candidate(item)
    ]
    shortlisted: list[RawItem] = preferred_candidates[:shortlist_limit]
    if len(shortlisted) >= shortlist_limit:
        return shortlisted

    low_candidates = [
        item
        for item in candidates
        if item.triage_label == "low"
        and not is_live_match_tracker_candidate(item)
        and is_viable_low_priority_candidate(item)
    ]
    remaining_slots = shortlist_limit - len(shortlisted)
    low_cap = low_priority_fallback_cap(batch_limit=batch_limit, preferred_count=len(shortlisted))
    if remaining_slots <= 0 or low_cap <= 0:
        return shortlisted

    shortlisted.extend(low_candidates[: min(remaining_slots, low_cap)])
    return shortlisted


def low_priority_fallback_cap(*, batch_limit: int, preferred_count: int) -> int:
    if batch_limit <= 0:
        return 0
    if preferred_count > 0:
        return max(1, min(STRICT_SHORTLIST_LOW_FALLBACK_CAP, batch_limit // 3 or 1))
    return max(1, min(STRICT_SHORTLIST_LOW_FALLBACK_CAP, batch_limit // 2 or 1))


def is_viable_low_priority_candidate(raw_item: RawItem) -> bool:
    if raw_item.importance_score < STRICT_SHORTLIST_LOW_SCORE_FLOOR:
        return False

    reference_time = raw_item.published_at or raw_item.fetched_at
    if reference_time is None:
        return False
    if datetime.now(timezone.utc) - reference_time > STRICT_SHORTLIST_LOW_MAX_AGE:
        return False

    full_text = (raw_item.full_text or "").strip()
    summary = (raw_item.summary or "").strip()
    lead = (raw_item.lead or "").strip()

    if len(full_text) >= STRICT_SHORTLIST_LOW_FULL_TEXT_MIN_LEN:
        return True
    if len(summary) >= STRICT_SHORTLIST_LOW_SUMMARY_MIN_LEN and len(lead) >= 60:
        return True
    return False


def is_live_match_tracker_candidate(raw_item: RawItem) -> bool:
    haystack = " ".join(
        part.strip().lower()
        for part in (raw_item.title, raw_item.summary or "", raw_item.lead or "", raw_item.full_text or "")
        if part
    )
    if any(term in haystack for term in LIVE_MATCH_TRACKER_TERMS):
        return True
    if re.search(r"^\s*.+\s+[–:-]\s+[–:-]\s+.+\s*$", raw_item.title.strip().lower()):
        return True
    if re.search(r"^\s*.+\s+[–-]\s+\d+\s*:\s*\d+\s+.+\s*$", raw_item.title.strip().lower()):
        return True
    return False


def select_reranked_candidates(
    candidates: list[RawItem],
    *,
    limit: int,
    ai_client: OpenAIEditorialClient,
) -> list[tuple[RawItem, PlannerRerankItem | None]]:
    if not candidates:
        return []

    reranked = ai_client.rerank_plan_candidates(candidates, limit=limit)
    if not reranked:
        return [(raw_item, None) for raw_item in candidates[:limit]]

    candidate_map = {item.id: item for item in candidates}
    selected: list[tuple[RawItem, PlannerRerankItem | None]] = []
    used_ids: set[str] = set()

    for rerank_item in reranked:
        raw_item = candidate_map.get(rerank_item.raw_item_id)
        if raw_item is None or raw_item.id in used_ids:
            continue
        selected.append((raw_item, rerank_item))
        used_ids.add(raw_item.id)

    for raw_item in candidates:
        if len(selected) >= limit:
            break
        if raw_item.id in used_ids:
            continue
        selected.append((raw_item, None))
        used_ids.add(raw_item.id)

    return selected


def build_plan_item(raw_item: RawItem, rerank: PlannerRerankItem | None = None) -> ContentPlanItem:
    priority_score = rerank.score if rerank is not None else raw_item.importance_score
    priority_label = priority_label_for_score(priority_score)
    planned_format = select_format(raw_item, priority_label)
    reason = build_reason(raw_item, planned_format, rerank)
    now = datetime.now(timezone.utc)

    return ContentPlanItem(
        id=f"plan:{raw_item.id}",
        raw_item_id=raw_item.id,
        title=raw_item.title,
        source_title=raw_item.source_title,
        category=raw_item.normalized_category,
        priority_score=priority_score,
        priority_label=priority_label,
        planned_format=planned_format,
        status="planned",
        reason=reason,
        created_at=now,
        updated_at=now,
    )


def select_format(raw_item: RawItem, priority_label: str) -> str:
    if priority_label == "high":
        return "breaking_news"
    if raw_item.normalized_category in {"football", "hockey", "basketball", "tennis"}:
        return "news_update"
    return "brief"


def build_reason(raw_item: RawItem, planned_format: str, rerank: PlannerRerankItem | None = None) -> str:
    if rerank is not None:
        return (
            f"AI rerank поднял материал от {raw_item.source_title} до {rerank.score}/100. "
            f"Причина: {rerank.reason} Planner выбрал формат {planned_format}."
        )
    return (
        f"Материал от {raw_item.source_title} получил {raw_item.importance_score}/100 "
        f"и triage {raw_item.triage_label}. Planner выбрал формат {planned_format} "
        "как подходящий для MVP-редакции."
    )


def priority_label_for_score(score: int) -> str:
    if score >= 78:
        return "high"
    if score >= 48:
        return "medium"
    return "low"
