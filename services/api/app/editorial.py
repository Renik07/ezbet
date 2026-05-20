from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from .ai_client import OpenAIEditorialClient
from .ingestion import enrich_raw_item_content
from .models import Article, DraftArticle, EditorReview, PromptConfig, RawItem
from .repository import NewsRepository


def default_prompt_configs() -> list[PromptConfig]:
    return [
        PromptConfig(
            id="prompt:writer:v3",
            agent_key="writer",
            name="Writer Editorial v3",
            version=3,
            status="draft",
            system_prompt=(
                "Ты новостной редактор ezbet.ru. Пиши как живой спортивный редактор: "
                "спокойно, точно, без шаблонного AI-тона, без воды и без домыслов. "
                "Не раздувай короткую новость ради объема, но и не сжимай богатый "
                "первоисточник до двух сухих предложений. Сохраняй ключевые факты, "
                "контекст, имена, счёт, исход голосований и другие существенные детали."
            ),
            user_prompt_template=(
                "Собери новостной материал на русском языке по исходным данным.\n"
                "Верни JSON с keys: title, dek, body.\n"
                "Требования:\n"
                "- title: естественный новостной заголовок без кликбейта; обязательно "
                "переформулируй его и не повторяй source title дословно\n"
                "- dek: 1-2 предложения, коротко и по делу\n"
                "- body: пиши столько абзацев, сколько реально нужно по объему фактов; "
                "если новость короткая, достаточно 1-2 коротких абзацев; если есть "
                "содержательный full_text, обычно нужен более полный материал на 2-4 "
                "абзаца с сохранением основных фактов\n"
                "- не добавляй факты, которых нет в source\n"
                "- не используй фразы вроде 'данный материал', 'в рамках', 'следует отметить', "
                "'на текущий момент', если они не нужны\n"
                "- избегай AI-канцелярита и повторов\n"
                "- если есть full_text, опирайся в первую очередь на него и не своди весь "
                "первоисточник к краткому пересказу из 1-2 фраз, если в нём есть несколько "
                "самостоятельных фактов"
            ),
            model="editorial-default-v2",
            provider="internal",
            notes="Recommended default writer prompt tuned for rewritten headlines and fuller fact retention.",
        ),
        PromptConfig(
            id="prompt:editor:v3",
            agent_key="editor",
            name="Editor Editorial v3",
            version=3,
            status="draft",
            system_prompt=(
                "Ты выпускающий редактор ezbet.ru. Проверяй новостной текст как живой редактор: "
                "смотри на точность, естественность, плотность фактов и отсутствие воды. "
                "Не переписывай ради красоты: твоя цель — понять, готов ли текст к публикации."
            ),
            user_prompt_template=(
                "Проверь черновик и верни JSON с keys: summary, notes.\n"
                "Что проверить:\n"
                "- нет ли домыслов сверх source\n"
                "- не слишком ли текст шаблонный или AI-похожий по тону\n"
                "- нет ли воды, повторов и искусственного раздувания\n"
                "- соответствует ли объем количеству фактов\n"
                "- не повторяет ли title источник почти дословно; если повторяет, это минус\n"
                "- если у source есть содержательный full_text, не был ли он слишком сильно сжат\n"
                "- если данных мало, прямо скажи, что лучше оставить материал коротким\n"
                "- если нужен rewrite, в notes коротко объясни почему"
            ),
            model="editorial-default-v2",
            provider="internal",
            notes="Recommended default editor prompt focused on rewritten headlines and preserving source detail.",
        ),
        PromptConfig(
            id="prompt:ai-search:v1",
            agent_key="ai_search",
            name="AI Search Discovery v1",
            version=1,
            status="active",
            system_prompt=(
                "Ты discovery-слой ezbet.ru. Ищи свежие спортивные новости на заданном домене "
                "и возвращай только реальные страницы статей. Не возвращай теги, разделы, видео-хабы, "
                "промо, подписки и служебные страницы."
            ),
            user_prompt_template=(
                "Верни только JSON с key items.\n"
                "Для каждой новости верни: title, summary, url, published_at, source_title, tags.\n"
                "Требования:\n"
                "- url должен быть канонической ссылкой на страницу статьи и открываться\n"
                "- published_at должен быть ISO 8601, если дату можно определить\n"
                "- summary должен быть кратким фактическим описанием на русском\n"
                "- tags должны быть коротким массивом тематических тегов на русском\n"
                "- не выдумывай факты"
            ),
            model="editorial-default-v2",
            provider="internal",
            notes="Default prompt for AI search source discovery.",
        ),
    ]


@dataclass
class QualityGateResult:
    decision: str
    reason: str


def run_editorial_cycle(repository: NewsRepository, limit: int = 2) -> tuple[list[DraftArticle], list[EditorReview]]:
    ai_client = OpenAIEditorialClient()
    writer_prompt = repository.get_active_prompt("writer")
    editor_prompt = repository.get_active_prompt("editor")
    raw_candidates = repository.list_planned_raw_items_for_drafts(limit=limit)
    rewrite_enabled = False

    generated: list[DraftArticle] = []
    reviews: list[EditorReview] = []

    for raw_item in raw_candidates:
        raw_item = enrich_raw_item_if_needed(repository, raw_item)
        draft = generate_draft(raw_item, writer_prompt, ai_client)
        stored_draft = repository.upsert_draft(draft)
        repository.set_content_plan_status(raw_item.id, "drafted")
        similarity_candidates = repository.list_article_similarity_candidates(
            category=stored_draft.category,
            published_at=stored_draft.published_at,
            exclude_news_item_id=raw_item.external_id,
            window_hours=24,
            limit=20,
        )
        review = review_draft(stored_draft, raw_item, editor_prompt, ai_client, similarity_candidates)
        stored_review = repository.upsert_review(review)
        quality_gate = evaluate_quality_gate(stored_draft, raw_item, stored_review, similarity_candidates)

        if quality_gate.decision == "pass":
            repository.set_draft_review_status(
                stored_draft.id,
                review_status="reviewed",
                status="ready_for_publish",
                review_summary=stored_review.summary,
                publish_decision="publish_auto",
                publish_reason=quality_gate.reason,
            )
            repository.set_content_plan_status(raw_item.id, "ready_to_publish")
        elif quality_gate.decision == "rewrite" and rewrite_enabled:
            rewritten_draft = rewrite_draft(stored_draft, raw_item, writer_prompt, ai_client, quality_gate.reason)
            if rewritten_draft is not None:
                stored_draft = repository.upsert_draft(rewritten_draft)
                second_review = review_draft(
                    stored_draft,
                    raw_item,
                    editor_prompt,
                    ai_client,
                    similarity_candidates,
                )
                stored_review = repository.upsert_review(second_review)
                second_gate = evaluate_quality_gate(stored_draft, raw_item, stored_review, similarity_candidates)
                if second_gate.decision == "pass":
                    repository.set_draft_review_status(
                        stored_draft.id,
                        review_status="reviewed",
                        status="ready_for_publish",
                        review_summary=stored_review.summary,
                        publish_decision="publish_auto",
                        publish_reason=second_gate.reason,
                    )
                    repository.set_content_plan_status(raw_item.id, "ready_to_publish")
                else:
                    repository.set_draft_review_status(
                        stored_draft.id,
                        review_status="quality_hold",
                        status="hold",
                        review_summary=second_gate.reason,
                        publish_decision="publish_hold",
                        publish_reason=second_gate.reason,
                    )
                    repository.set_content_plan_status(raw_item.id, "hold")
            else:
                repository.set_draft_review_status(
                    stored_draft.id,
                    review_status="quality_rewrite",
                    status="rewrite_needed",
                    review_summary=quality_gate.reason,
                    publish_decision="publish_hold",
                    publish_reason=quality_gate.reason,
                )
                repository.set_content_plan_status(raw_item.id, "rewrite_needed")
        elif quality_gate.decision == "rewrite":
            repository.set_draft_review_status(
                stored_draft.id,
                review_status="quality_rewrite",
                status="rewrite_needed",
                review_summary=quality_gate.reason,
                publish_decision="publish_hold",
                publish_reason=quality_gate.reason,
            )
            repository.set_content_plan_status(raw_item.id, "rewrite_needed")
        else:
            if stored_draft.generation_mode == "template":
                repository.set_draft_review_status(
                    stored_draft.id,
                    review_status="fallback_only",
                    status="fallback_only",
                    review_summary=quality_gate.reason,
                    publish_decision="publish_skip",
                    publish_reason=quality_gate.reason,
                )
                repository.set_content_plan_status(raw_item.id, "fallback_only")
                generated.append(repository.get_draft(stored_draft.id) or stored_draft)
                reviews.append(stored_review)
                continue
            repository.set_draft_review_status(
                stored_draft.id,
                review_status="quality_hold",
                status="hold",
                review_summary=quality_gate.reason,
                publish_decision="publish_hold",
                publish_reason=quality_gate.reason,
            )
            repository.set_content_plan_status(raw_item.id, "hold")

        generated.append(repository.get_draft(stored_draft.id) or stored_draft)
        reviews.append(stored_review)

    return generated, reviews


def enrich_raw_item_if_needed(repository: NewsRepository, raw_item: RawItem) -> RawItem:
    return enrich_raw_item_content(repository, raw_item)


def generate_draft(
    raw_item: RawItem,
    prompt: PromptConfig,
    ai_client: OpenAIEditorialClient,
) -> DraftArticle:
    generated = ai_client.generate_draft(raw_item, prompt)
    now = datetime.now(timezone.utc)

    if generated is None:
        title = raw_item.title
        dek = build_dek(raw_item)
        body = build_body(raw_item)
        model = prompt.model
        generation_mode = "template"
    else:
        title = generated.title
        dek = generated.dek
        body = generated.body
        model = generated.model
        generation_mode = generated.generation_mode

    return DraftArticle(
        id=f"draft:{raw_item.id}",
        raw_item_id=raw_item.id,
        title=title,
        dek=dek,
        body=body,
        category=raw_item.normalized_category,
        source_title=raw_item.source_title,
        source_url=raw_item.url,
        published_at=raw_item.published_at,
        status="draft",
        review_status="pending",
        publish_decision="publish_pending",
        publish_reason="Материал еще не прошел editorial quality gate.",
        prompt_config_id=prompt.id,
        prompt_name=prompt.name,
        model=model,
        generation_mode=generation_mode,
        created_at=now,
        updated_at=now,
    )


def rewrite_draft(
    draft: DraftArticle,
    raw_item: RawItem,
    prompt: PromptConfig,
    ai_client: OpenAIEditorialClient,
    reason: str,
) -> DraftArticle | None:
    rewritten = ai_client.rewrite_draft(draft, raw_item, prompt, reason)
    if rewritten is None:
        return None

    now = datetime.now(timezone.utc)
    return DraftArticle(
        id=draft.id,
        raw_item_id=draft.raw_item_id,
        title=rewritten.title,
        dek=rewritten.dek,
        body=rewritten.body,
        category=draft.category,
        source_title=draft.source_title,
        source_url=draft.source_url,
        published_at=draft.published_at,
        status="draft",
        review_status="pending",
        review_summary=None,
        publish_decision="publish_pending",
        publish_reason=reason,
        prompt_config_id=prompt.id,
        prompt_name=prompt.name,
        model=rewritten.model,
        generation_mode=rewritten.generation_mode,
        created_at=draft.created_at,
        updated_at=now,
    )


def review_draft(
    draft: DraftArticle,
    raw_item: RawItem,
    prompt: PromptConfig,
    ai_client: OpenAIEditorialClient,
    similarity_candidates: list[Article],
) -> EditorReview:
    notes: list[str] = [
        "Структура черновика адаптируется под плотность фактов: короткая новость может остаться короткой, богатый source требует более полного body.",
        "Фактура опирается на доступные данные raw-item: title, summary и при наличии full_text страницы-источника.",
    ]

    if raw_item.triage_label == "high":
        notes.append("Инфоповод помечен как high priority и подходит для быстрого слота публикации.")
    if len(raw_item.summary.strip()) < 120:
        notes.append("У исходного summary мало деталей, перед автопубликацией стоит проверить первоисточник.")
    if similarity_candidates:
        notes.append(
            f"Для будущего similarity-check найдено {len(similarity_candidates)} недавних материалов той же категории за последние 24 часа."
        )
    else:
        notes.append("За последние 24 часа в этой категории не найдено близких опубликованных материалов-кандидатов.")

    fallback_summary = "Черновик выровнен по тону, структура читается, явных фактических расширений не добавлено."
    generated = ai_client.review_draft(draft, raw_item, prompt)
    if generated is None:
        summary = fallback_summary
        joined_notes = " ".join(notes)
        model = prompt.model
    else:
        summary = generated.summary
        joined_notes = generated.notes
        model = generated.model

    return EditorReview(
        id=f"review:{draft.id}",
        draft_id=draft.id,
        status="reviewed",
        summary=summary,
        notes=joined_notes,
        prompt_config_id=prompt.id,
        prompt_name=prompt.name,
        model=model,
        created_at=datetime.now(timezone.utc),
    )


def evaluate_quality_gate(
    draft: DraftArticle,
    raw_item: RawItem,
    review: EditorReview,
    similarity_candidates: list[Article],
) -> QualityGateResult:
    title = draft.title.strip()
    dek = draft.dek.strip()
    body = draft.body.strip()
    summary = raw_item.summary.strip()
    source_title = raw_item.title.strip()
    source_full_text_paragraphs = unique_paragraphs(raw_item.full_text or "")
    source_full_text = " ".join(source_full_text_paragraphs)

    if not title or not dek or not body:
        return QualityGateResult("hold", "Quality gate: отсутствует обязательная часть материала.")

    if draft.generation_mode == "template":
        return QualityGateResult("hold", "Quality gate: template fallback не должен публиковаться автоматически.")

    # Internal MVP filler text should never leak into published content.
    blocked_markers = (
        "На MVP",
        "Следующий шаг для прод-версии",
        "системой ezbet",
    )
    if any(marker in body for marker in blocked_markers):
        return QualityGateResult("hold", "Quality gate: обнаружен служебный или шаблонный текст MVP.")

    paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]

    if title == raw_item.title and dek == raw_item.summary and draft.generation_mode == "template":
        return QualityGateResult("rewrite", "Quality gate: материал слишком близок к сырому RSS и требует rewrite pass.")

    repeated_paragraphs = len(set(paragraphs)) != len(paragraphs)
    if repeated_paragraphs:
        return QualityGateResult("rewrite", "Quality gate: в тексте обнаружены повторяющиеся абзацы.")

    source_similarity = compute_similarity(f"{draft.title} {draft.dek} {body}", f"{raw_item.title} {raw_item.summary}")
    if source_similarity >= 0.82:
        return QualityGateResult("rewrite", "Quality gate: итоговый текст слишком близок к исходному source summary.")

    candidate_similarities = [
        compute_similarity(f"{draft.title} {draft.dek} {body}", f"{candidate.title} {candidate.dek} {candidate.body}")
        for candidate in similarity_candidates
    ]
    max_similarity = max(candidate_similarities, default=0.0)
    if max_similarity >= 0.9:
        return QualityGateResult("hold", "Quality gate: материал слишком похож на уже опубликованную статью.")
    if max_similarity >= 0.78:
        return QualityGateResult("rewrite", "Quality gate: материал слишком близок к недавней статье той же категории.")

    return QualityGateResult("pass", "Quality gate: материал можно публиковать.")


def normalize_gate_text(value: str) -> str:
    return " ".join(tokenize_text(value))


def compute_similarity(left: str, right: str) -> float:
    left_tokens = set(tokenize_text(left))
    right_tokens = set(tokenize_text(right))

    if not left_tokens or not right_tokens:
        return 0.0

    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if union == 0:
        return 0.0
    return intersection / union


def tokenize_text(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Zа-яА-Я0-9]+", value.lower()) if len(token) > 2]


def unique_paragraphs(value: str) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []

    for raw_paragraph in value.split("\n\n"):
        paragraph = " ".join(raw_paragraph.split()).strip()
        if not paragraph:
            continue
        normalized = normalize_gate_text(paragraph)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(paragraph)

    return unique


def build_dek(raw_item: RawItem) -> str:
    source_text = " ".join((raw_item.full_text or raw_item.summary).split())
    summary = source_text or " ".join(raw_item.summary.split())
    if len(summary) <= 180:
        return summary
    return f"{summary[:177].rstrip()}..."


def build_body(raw_item: RawItem) -> str:
    published = raw_item.published_at.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    intro = f'{raw_item.source_title} опубликовал новость "{raw_item.title}". Публикация была зафиксирована системой ezbet {published}.'

    if raw_item.full_text:
        paragraphs = [paragraph.strip() for paragraph in raw_item.full_text.split("\n\n") if paragraph.strip()]
        selected = paragraphs[:3] if paragraphs else [raw_item.full_text.strip()]
        body_parts = [intro, *selected]
        return "\n\n".join(part for part in body_parts if part)

    context = (
        f"Сырой summary после нормализации выглядит так: {raw_item.summary} "
        "На MVP это становится опорой для быстрого черновика без добавления новых фактов."
    )
    editorial = (
        f"Материал отнесен к категории {raw_item.normalized_category} и получил "
        f"приоритет {raw_item.triage_label} ({raw_item.importance_score}/100). "
        "Следующий шаг для прод-версии - подключить живой LLM-провайдер вместо шаблонного editorial pass."
    )
    return "\n\n".join((intro, context, editorial))
