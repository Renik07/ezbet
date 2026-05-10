from __future__ import annotations

from datetime import datetime, timezone

from .ai_client import OpenAIEditorialClient, PlannerRerankItem
from .models import ContentPlanItem, RawItem
from .repository import NewsRepository


def run_content_planner(repository: NewsRepository, limit: int = 6) -> list[ContentPlanItem]:
    shortlist_limit = max(limit * 3, limit)
    candidates = repository.list_raw_candidates_for_plan(limit=shortlist_limit)
    planned_items: list[ContentPlanItem] = []
    ai_client = OpenAIEditorialClient()
    reranked_items = select_reranked_candidates(candidates, limit=limit, ai_client=ai_client)

    for raw_item, rerank in reranked_items:
        plan_item = build_plan_item(raw_item, rerank)
        planned_items.append(repository.upsert_content_plan_item(plan_item))

    return planned_items


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
