from __future__ import annotations

from .models import (
    DraftArticle,
    PromptConfig,
    RawItem,
)
from .ai_response_helpers import _loads_llm_json
from .ai_text_helpers import (
    _clean_text,
    _normalize_editor_decision,
    _replace_yo,
)
from .ai_types import (
    DraftGenerationResult,
    LLM_REQUEST_EXCEPTIONS,
    PlannerRerankItem,
    ReviewGenerationResult,
)


class EditorialAIClient:
    def generate_draft(self, raw_item: RawItem, prompt: PromptConfig) -> DraftGenerationResult | None:
        if not self.enabled:
            return None

        source_body = (raw_item.full_text or "").strip()
        source_body_block = f"full_text: {source_body}\n" if source_body else ""
        lead_block = f"lead: {raw_item.lead}\n" if raw_item.lead else ""
        tags_block = f"tags: {', '.join(raw_item.tags)}\n" if raw_item.tags else ""
        input_text = (
            "Return only valid JSON with keys title, dek, body.\n"
            f"source_title: {raw_item.source_title}\n"
            f"ЗАГОЛОВОК ОРИГИНАЛА: {raw_item.title}\n"
            f"ИСТОЧНИК: {raw_item.source_title}\n"
            f"summary: {raw_item.summary}\n"
            f"{lead_block}"
            f"{tags_block}"
            f"{source_body_block}"
            f"category: {raw_item.normalized_category}\n"
            f"priority: {raw_item.triage_label} ({raw_item.importance_score}/100)\n"
            "Constraints: do not invent facts, keep the tone concise, write in Russian, "
            "and separate body paragraphs with two newline characters."
        )
        instructions = f"{prompt.system_prompt}\n\n{prompt.user_prompt_template}"

        try:
            payload = self._create_response(
                instructions=instructions,
                input_text=input_text,
                operation="news_writer",
                related_id=raw_item.id,
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        title = _replace_yo(_clean_text(data.get("title")) or raw_item.title)
        dek = _replace_yo(_clean_text(data.get("dek")) or raw_item.summary)
        body = _replace_yo(_clean_text(data.get("body")))
        if not body:
            return None

        return DraftGenerationResult(
            title=title,
            dek=dek,
            body=body,
            model=self.settings.editorial_model,
            generation_mode=f"llm_{self.settings.api_style}",
        )

    def review_draft(
        self,
        draft: DraftArticle,
        raw_item: RawItem,
        prompt: PromptConfig,
    ) -> ReviewGenerationResult | None:
        if not self.enabled:
            return None

        source_body = (raw_item.full_text or "").strip()
        source_body_block = f"source_full_text: {source_body}\n" if source_body else ""
        lead_block = f"source_lead: {raw_item.lead}\n" if raw_item.lead else ""
        tags_block = f"source_tags: {', '.join(raw_item.tags)}\n" if raw_item.tags else ""
        input_text = (
            "Return only valid JSON with keys decision, summary, notes, revised_title, revised_dek, revised_body.\n"
            "ОРИГИНАЛЬНАЯ НОВОСТЬ\n"
            f"ЗАГОЛОВОК: {raw_item.title}\n"
            f"ИСТОЧНИК: {raw_item.source_title}\n"
            f"source_summary: {raw_item.summary}\n"
            f"{lead_block}"
            f"{tags_block}"
            f"{source_body_block}"
            "\nТЕКСТ ОТ WRITER AGENT\n"
            f"draft_title: {draft.title}\n"
            f"draft_dek: {draft.dek}\n"
            f"draft_body: {draft.body}\n"
            "Rules:\n"
            "- decision must be one of: approve, light_edit, rewrite\n"
            "- approve: the draft is already good enough; revised_* must be null or omitted\n"
            "- light_edit: choose only for a concrete public-facing issue; return full revised_title, revised_dek, revised_body\n"
            "- rewrite: choose only for factual errors, unsafe invention, strong plagiarism, or unusable news tone; return full revised_title, revised_dek, revised_body\n"
            "- review in Russian\n"
            "- summary and notes must be short, one sentence each\n"
            "- if the draft is acceptable, approve it instead of rewriting for style\n"
            "- do not invent facts beyond the source"
        )
        instructions = (
            f"{prompt.system_prompt}\n\n"
            f"{prompt.user_prompt_template}\n\n"
            "Сначала оцени качество текста как редактор. Если правки не нужны, выбери approve. "
            "Approve должен быть выбором по умолчанию, если текст фактически точный, читаемый и любые правки были бы лишь вкусовой микрополировкой. "
            "Не переписывай материал только ради легкой стилистической шлифовки. "
            "Не считай проблемой само по себе то, что dek частично перекликается с первым абзацем, если body дальше добавляет факты и не топчется на месте. "
            "Если нужны точечные правки из-за реальной публичной проблемы, выбери light_edit и верни полную исправленную версию. "
            "Если текст нужно заметно переписать из-за фактической ошибки, домысла, сильного плагиата или verification-тона, выбери rewrite. "
            "Во всех остальных случаях выбери approve и не возвращай revised_body."
        )

        try:
            payload = self._create_response(
                instructions=instructions,
                input_text=input_text,
                operation="news_editor",
                related_id=draft.raw_item_id,
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        decision = _clean_text(data.get("decision"))
        summary = _clean_text(data.get("summary"))
        notes = _clean_text(data.get("notes"))
        revised_title = _replace_yo(_clean_text(data.get("revised_title"))) or None
        revised_dek = _replace_yo(_clean_text(data.get("revised_dek"))) or None
        revised_body = _replace_yo(_clean_text(data.get("revised_body"))) or None
        normalized_decision = _normalize_editor_decision(decision, revised_title, revised_dek, revised_body)
        if not summary or not notes:
            return None
        if normalized_decision in {"light_edit", "rewrite"} and not (revised_title and revised_dek and revised_body):
            return None

        return ReviewGenerationResult(
            decision=normalized_decision,
            summary=summary,
            notes=notes,
            revised_title=revised_title,
            revised_dek=revised_dek,
            revised_body=revised_body,
            model=self.settings.editorial_model,
            generation_mode=f"llm_{self.settings.api_style}",
        )

    def rewrite_draft(
        self,
        draft: DraftArticle,
        raw_item: RawItem,
        prompt: PromptConfig,
        reason: str,
    ) -> DraftGenerationResult | None:
        if not self.enabled:
            return None

        source_body = (raw_item.full_text or "").strip()
        source_body_block = f"source_full_text: {source_body}\n" if source_body else ""
        lead_block = f"source_lead: {raw_item.lead}\n" if raw_item.lead else ""
        tags_block = f"source_tags: {', '.join(raw_item.tags)}\n" if raw_item.tags else ""
        input_text = (
            "Return only valid JSON with keys title, dek, body.\n"
            f"rewrite_reason: {reason}\n"
            f"source_title: {raw_item.source_title}\n"
            f"source_summary: {raw_item.summary}\n"
            f"{lead_block}"
            f"{tags_block}"
            f"{source_body_block}"
            f"current_title: {draft.title}\n"
            f"current_dek: {draft.dek}\n"
            f"current_body: {draft.body}\n"
            "Constraints: keep only facts that are supported by the source summary, write in Russian, "
            "reduce repetition, avoid boilerplate phrasing, and keep the article concise but readable."
        )
        instructions = (
            f"{prompt.system_prompt}\n\n"
            f"{prompt.user_prompt_template}\n\n"
            "Это rewrite pass. Перепиши материал лучше, чем текущая версия, не добавляя новых фактов."
        )

        try:
            payload = self._create_response(
                instructions=instructions,
                input_text=input_text,
                operation="news_rewrite",
                related_id=draft.raw_item_id,
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        title = _replace_yo(_clean_text(data.get("title")) or draft.title)
        dek = _replace_yo(_clean_text(data.get("dek")) or draft.dek)
        body = _replace_yo(_clean_text(data.get("body")))
        if not body:
            return None

        return DraftGenerationResult(
            title=title,
            dek=dek,
            body=body,
            model=self.settings.editorial_model,
            generation_mode=f"llm_{self.settings.api_style}_rewrite",
        )

    def rerank_plan_candidates(
        self,
        raw_items: list[RawItem],
        *,
        limit: int,
    ) -> list[PlannerRerankItem] | None:
        if not self.enabled or not raw_items:
            return None

        candidate_lines: list[str] = []
        for item in raw_items:
            candidate_lines.append(
                "\n".join(
                    (
                        f"id: {item.id}",
                        f"source: {item.source_title}",
                        f"title: {item.title}",
                        f"summary: {item.summary}",
                        f"category: {item.normalized_category}",
                        f"importance_score: {item.importance_score}",
                        f"triage_label: {item.triage_label}",
                        f"published_at: {item.published_at.isoformat()}",
                    )
                )
            )

        input_text = (
            "Return only valid JSON with key items.\n"
            f"Need top_limit: {limit}\n"
            "For each selected item return: id, score, reason.\n"
            "Score must be integer 0..100.\n"
            "Select only the strongest candidates for a sports news homepage and editorial queue.\n"
            "Prefer: freshness, importance of event, officiality, exclusivity, tournament weight, "
            "clear factual news value.\n"
            "Avoid over-prioritizing weak promo/video/live items.\n\n"
            "Candidates:\n"
            + "\n\n".join(candidate_lines)
        )
        instructions = (
            "Ты редактор планирования ezbet.ru. Твоя задача — быстро переоценить короткий shortlist "
            "новостей и выбрать верхние кандидаты для публикации. Отвечай только JSON без пояснений."
        )

        try:
            payload = self._create_response(
                instructions=instructions,
                input_text=input_text,
                operation="content_plan_rerank",
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        items = data.get("items")
        if not isinstance(items, list):
            return None

        known_ids = {item.id for item in raw_items}
        reranked: list[PlannerRerankItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_item_id = _clean_text(item.get("id"))
            if not raw_item_id or raw_item_id not in known_ids:
                continue
            try:
                score = int(item.get("score"))
            except (TypeError, ValueError):
                continue
            reason = _clean_text(item.get("reason")) or "AI rerank selected this candidate for the shortlist."
            reranked.append(
                PlannerRerankItem(
                    raw_item_id=raw_item_id,
                    score=max(0, min(score, 100)),
                    reason=reason,
                )
            )

        if not reranked:
            return None

        return reranked[:limit]

