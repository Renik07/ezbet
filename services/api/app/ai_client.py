from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from socket import timeout as SocketTimeout
from time import sleep
from typing import Any
from urllib.parse import urlsplit
from urllib.parse import urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ai_usage import record_ai_usage_event
from .config import OpenAISettings, get_openai_settings
from .models import DraftArticle, GuideTopic, PromptConfig, RawItem, SourceItem


@dataclass
class DraftGenerationResult:
    title: str
    dek: str
    body: str
    model: str
    generation_mode: str


@dataclass
class GuideResearchResult:
    brief: str
    model: str
    generation_mode: str


@dataclass
class ReviewGenerationResult:
    decision: str
    summary: str
    notes: str
    revised_title: str | None
    revised_dek: str | None
    revised_body: str | None
    model: str
    generation_mode: str


@dataclass
class PlannerRerankItem:
    raw_item_id: str
    score: int
    reason: str


@dataclass
class SourceDiscoveryItem:
    title: str
    summary: str
    url: str
    published_at: str | None
    full_text: str | None
    source_title: str | None
    tags: list[str]


@dataclass
class ResolvedArticleTarget:
    url: str
    published_at: str | None
    source_title: str | None


@dataclass
class ArticleExtractionResult:
    full_text: str | None
    lead: str | None
    tags: list[str]
    source_url: str | None
    source_title: str | None
    reference_urls: list[str]
    used_web_search: bool
    model: str
    generation_mode: str


LLM_REQUEST_EXCEPTIONS = (ValueError, HTTPError, URLError, TimeoutError, SocketTimeout, OSError)
LLM_TRANSIENT_EXCEPTIONS = (URLError, TimeoutError, SocketTimeout, OSError)
logger = logging.getLogger("uvicorn.error")


class OpenAIEditorialClient:
    def __init__(self, settings: OpenAISettings | None = None) -> None:
        self.settings = settings or get_openai_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

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

    def generate_match_forecast(
        self,
        forecast: Any,
        *,
        search_context_size: str = "medium",
    ) -> dict[str, object] | None:
        """One-match test flow: factual web research first, polished Russian copy second."""
        if not self.enabled or not self._should_enable_web_search_for_request():
            return None
        cutoff_date = forecast.kickoff.date().isoformat()
        research_input = (
            f"match: {forecast.home_team} vs {forecast.away_team}\nleague: {forecast.league}\n"
            f"kickoff: {forecast.kickoff.isoformat()}\nodds: 1={forecast.odds_home}, X={forecast.odds_draw}, 2={forecast.odds_away}\n"
            f"Cutoff date: {cutoff_date}. Do not use events or news after this date.\n"
            "Find at least one recent completed match for EACH team (two result facts total). "
            "Optionally add one head-to-head result and one squad/injury fact only when confidently identified. "
            "Do not return the upcoming fixture itself as a fact. "
            "Every fact must contain one direct public source URL. Include the event or publication date in YYYY-MM-DD "
            "when it is available; otherwise return an empty event_date. "
            "Prefer official league/club pages and established sports media. Search snippets, prediction/odds sites, "
            "aggregators and unsourced statistics are not sufficient evidence. Preserve team names exactly as provided. "
            "Write every statement and source title in Russian. "
            "Do not infer form, trends, injuries, transfers or lineup changes beyond what the cited source explicitly says. "
            "If a fact cannot be verified, omit it."
        )
        cited_urls: list[str] = []
        try:
            research_payload = self._create_response(
                instructions="Ты фактчекер спортивной редакции. Найди свежие проверяемые факты, не пиши прогноз и не добавляй домыслы.",
                input_text=research_input,
                model=self.settings.search_model,
                tools=[{"type": "web_search", "search_context_size": search_context_size}],
                include=["web_search_call.action.sources"],
                max_output_tokens=4000,
                reasoning_effort="low",
                citation_urls=cited_urls,
                text_format={
                    "type": "json_schema",
                    "name": "match_research",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "facts": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "statement": {"type": "string"},
                                        "source_url": {"type": "string"},
                                        "source_title": {"type": "string"},
                                        "event_date": {"type": "string"},
                                        "kind": {
                                            "type": "string",
                                            "enum": ["home_result", "away_result", "head_to_head", "squad_news"],
                                        },
                                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                    },
                                    "required": [
                                        "statement",
                                        "source_url",
                                        "source_title",
                                        "event_date",
                                        "kind",
                                        "confidence",
                                    ],
                                    "additionalProperties": False,
                                },
                                "minItems": 2,
                                "maxItems": 8,
                            },
                        },
                        "required": ["facts"],
                        "additionalProperties": False,
                    },
                },
                operation="match_forecast_test_research",
                related_id=f"match:{forecast.slug}",
            )
            research_data = _loads_llm_json(research_payload)
        except json.JSONDecodeError as exc:
            logger.error(
                "Match research returned invalid JSON: %s payload_preview=%s",
                exc,
                research_payload[:1200],
            )
            return None
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")[:2000]
            logger.error("Match research OpenAI HTTP error: status=%s body=%s", exc.code, error_body)
            return None
        except LLM_REQUEST_EXCEPTIONS as exc:
            logger.error("Match research OpenAI request failed: %s: %s", type(exc).__name__, exc)
            return None
        raw_facts = research_data.get("facts") if isinstance(research_data, dict) else None
        facts = _validate_match_research_facts(
            raw_facts,
            cutoff_date=forecast.kickoff.date(),
            cited_urls=cited_urls,
        )
        home_result_dates = {fact["event_date"] for fact in facts if fact["kind"] == "home_result"}
        away_result_dates = {fact["event_date"] for fact in facts if fact["kind"] == "away_result"}
        if len(facts) < 2 or not home_result_dates or not away_result_dates:
            logger.error("Match research validation failed: payload_preview=%s", research_payload[:1000])
            return None

        research_brief = "\n".join(
            f"- {fact['statement']} ({fact['event_date']}; {fact['source_title']})"
            for fact in facts
        )
        cited_publishers = {
            publisher
            for url in cited_urls
            if _is_public_http_url(url)
            for publisher in _source_publisher_tokens(url)
        }
        source_urls = list(
            dict.fromkeys(
                fact["source_url"]
                for fact in facts
                if _source_publisher_tokens(fact["source_url"]) & cited_publishers
            )
        )[:8]
        if not source_urls:
            logger.error("Match research source matching failed: cited_publishers=%s", sorted(cited_publishers))
            return None
        writing_input = (
            f"Команды: {forecast.home_team} — {forecast.away_team}\nЛига: {forecast.league}\n"
            f"Коэффициенты: П1 {forecast.odds_home}, X {forecast.odds_draw}, П2 {forecast.odds_away}\n"
            f"Проверенные факты:\n{research_brief}\n"
            "Напиши короткий прогноз для страницы матча. Используй исходные русские названия команд и не переводи их "
            "на другой язык. Допустимы естественные сокращения и склонение названий в русском тексте. "
            "Только грамотный русский язык, без ссылок, названий источников, канцелярита и сведений сверх списка фактов. "
            "Используй естественные футбольные формулировки, без буквальных переводов, смешения языков и несуществующих слов. "
            "Если подтвержденные матчи состоялись давно, называй их доступными результатами, а не последними турами. "
            "Не обсуждай отсутствие данных. lead — 1-2 предложения. home_form и away_form — по 2 предложения. "
            "factors — три коротких тезиса. pick — один исход из П1, 1X, X, X2, П2, обе забьют, тотал больше/меньше "
            "и одно короткое объяснение. Каждый элемент factors и значение pick возвращай без точки, точки с запятой "
            "или другого завершающего знака. Не предлагай альтернатив и не гарантируй результат."
        )
        output_schema = {
            "type": "json_schema",
            "name": "match_forecast",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "lead": {"type": "string"},
                    "home_form": {"type": "string"},
                    "away_form": {"type": "string"},
                    "factors": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                    "pick": {"type": "string"},
                },
                "required": ["lead", "home_form", "away_form", "factors", "pick"],
                "additionalProperties": False,
            },
        }
        try:
            writing_payload = self._create_response(
                instructions="Ты выпускающий редактор ezbet.ru. Преврати проверенные факты в ясный и аккуратный прогноз на русском языке.",
                input_text=writing_input,
                model=self.settings.editorial_model,
                max_output_tokens=2400,
                reasoning_effort="low",
                text_format=output_schema,
                operation="match_forecast_test_writer",
                related_id=f"match:{forecast.slug}",
            )
            data = _loads_llm_json(writing_payload)
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")[:2000]
            logger.error("Match writer OpenAI HTTP error: status=%s body=%s", exc.code, error_body)
            return None
        except LLM_REQUEST_EXCEPTIONS as exc:
            logger.error("Match writer OpenAI request failed: %s: %s", type(exc).__name__, exc)
            return None

        factors = data.get("factors") if isinstance(data, dict) else None
        required = ("lead", "home_form", "away_form", "pick")
        if not isinstance(data, dict) or not all(_clean_text(data.get(key)) for key in required) or not isinstance(factors, list):
            logger.error("Match writer validation failed: payload_preview=%s", writing_payload[:1000])
            return None
        return {
            "research_brief": _replace_yo(research_brief),
            "source_urls": source_urls,
            "lead": _replace_yo(_clean_text(data["lead"])),
            "home_form": _replace_yo(_clean_text(data["home_form"])),
            "away_form": _replace_yo(_clean_text(data["away_form"])),
            "factors": [_replace_yo(_clean_text(value)) for value in factors if _clean_text(value)][:3],
            "pick": _replace_yo(_clean_text(data["pick"])),
        }

    def generate_guide_article(
        self,
        topic: GuideTopic,
        prompt: PromptConfig,
        editor_prompt: PromptConfig | None = None,
    ) -> DraftGenerationResult | None:
        if not self.enabled:
            return None

        use_web_search = topic.requires_web_search and self._should_enable_web_search_for_request()
        research = self.research_guide_topic(topic) if use_web_search else None
        if use_web_search and research is None:
            sleep(1)
            research = self.research_guide_topic(topic)
        if use_web_search and research is None:
            return None

        generated = self._write_guide_article(topic, prompt, research=research)
        if generated is None:
            return None

        if use_web_search and editor_prompt is not None:
            edited = self.edit_guide_article(topic, editor_prompt, generated, research=research)
            if edited is not None:
                return edited

        return generated

    def research_guide_topic(self, topic: GuideTopic) -> GuideResearchResult | None:
        if not self.enabled or not self._should_enable_web_search_for_request():
            return None

        input_text = (
            "Return only valid JSON with key research_brief.\n"
            f"topic: {topic.title}\n"
            f"section: {topic.section}\n"
            f"category: {topic.category}\n"
            "Task: collect concrete factual material for a Russian longform sports article.\n"
            "The research_brief must be in Russian and contain 6-10 compact bullet lines.\n"
            "Each bullet must include at least one concrete number, amount, date, country, organization, person, event, or named program.\n"
            "Prefer official sources, federations, Olympic committees, major sports media, financial reports, and reputable business media.\n"
            "Do not write generic advice. Do not include markdown links, source URLs, citation markers, or bibliography in research_brief.\n"
            "If sources disagree, mention the range or uncertainty in the bullet itself."
        )

        try:
            payload = self._create_response(
                instructions=(
                    "Ты research-редактор ezbet.ru. Твоя задача — найти конкретные проверяемые факты, цифры, "
                    "суммы, имена, страны и даты для будущей статьи. Не пиши статью. Не добавляй ссылки в текст."
                ),
                input_text=input_text,
                model=self.settings.editorial_model,
                tools=self._build_guide_web_search_tools(topic.search_context_size),
                operation="guide_research_web_search",
                related_id=f"guide-topic:{topic.topic_number}",
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        research_value: Any = data
        if isinstance(data, dict):
            research_value = data.get("research_brief") or data.get("facts") or data.get("items") or data
        brief = _strip_markdown_links(_replace_yo(_coerce_research_brief(research_value)))
        if len(brief) < 200:
            return None

        return GuideResearchResult(
            brief=brief,
            model=self.settings.editorial_model,
            generation_mode=f"llm_{self.settings.api_style}_guide_research_web_search",
        )

    def _write_guide_article(
        self,
        topic: GuideTopic,
        prompt: PromptConfig,
        *,
        research: GuideResearchResult | None = None,
    ) -> DraftGenerationResult | None:
        fact_mode_block = (
            "Research brief is provided below. Use it as the factual backbone of the article.\n"
            "Requirements for this fact-based article:\n"
            "- use at least 7 concrete facts from research_brief;\n"
            "- include numbers, amounts, dates, countries, organizations, names or named programs where relevant;\n"
            "- explain what the numbers mean for the reader;\n"
            "- do not include markdown links, URLs, citation markers, source lists, or bibliography in title, dek or body;\n"
            "- do not write generic filler if a concrete figure is available.\n"
            f"research_brief:\n{research.brief}\n"
            if research is not None
            else "Fresh facts mode: web search is disabled for this topic; avoid precise current facts unless they are stable and widely known.\n"
        )
        input_text = (
            "Return only valid JSON with keys title, dek, body.\n"
            f"topic: {topic.title}\n"
            f"section: {topic.section}\n"
            f"category: {topic.category}\n"
            f"{fact_mode_block}"
            "Audience: Russian sports media readers. The article should be evergreen, useful for search traffic, "
            "and readable as a standalone longform piece on ezbet.ru.\n"
            "Constraints: write in Russian, do not invent precise current facts, avoid betting calls to action, "
            "proofread grammar carefully, do not duplicate dek in the first paragraph, do not write standalone section headings, "
            "make every paragraph complete prose, and separate body paragraphs with two newline characters."
        )
        instructions = f"{prompt.system_prompt}\n\n{prompt.user_prompt_template}"

        try:
            payload = self._create_response(
                instructions=instructions,
                input_text=input_text,
                operation="guide_writer_from_research" if research is not None else "guide_writer",
                related_id=f"guide-topic:{topic.topic_number}",
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        title = _replace_yo(_clean_text(data.get("title")) or topic.title)
        dek = _replace_yo(_clean_text(data.get("dek")))
        body = _normalize_guide_body(_replace_yo(_clean_text(data.get("body"))))
        if not dek or not body:
            return None

        return DraftGenerationResult(
            title=title,
            dek=dek,
            body=body,
            model=self.settings.editorial_model,
            generation_mode=(
                f"llm_{self.settings.api_style}_guide_from_research"
                if research is not None
                else f"llm_{self.settings.api_style}_guide"
            ),
        )

    def edit_guide_article(
        self,
        topic: GuideTopic,
        prompt: PromptConfig,
        draft: DraftGenerationResult,
        *,
        research: GuideResearchResult | None = None,
    ) -> DraftGenerationResult | None:
        if not self.enabled:
            return None

        research_block = f"research_brief:\n{research.brief}\n" if research is not None else ""
        input_text = (
            "Return only valid JSON with keys title, dek, body.\n"
            f"topic: {topic.title}\n"
            f"section: {topic.section}\n"
            f"category: {topic.category}\n"
            f"{research_block}"
            "draft_title:\n"
            f"{draft.title}\n"
            "draft_dek:\n"
            f"{draft.dek}\n"
            "draft_body:\n"
            f"{draft.body}\n"
            "Edit the draft for publication. Preserve concrete facts, numbers, amounts, dates and named entities from the research. "
            "Remove generic filler, grammar mistakes, markdown links, URLs, citation markers and source lists. "
            "Make the prose lively but calm, with complete paragraphs separated by two newline characters."
        )

        try:
            payload = self._create_response(
                instructions=f"{prompt.system_prompt}\n\n{prompt.user_prompt_template}",
                input_text=input_text,
                operation="guide_editor",
                related_id=f"guide-topic:{topic.topic_number}",
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        title = _replace_yo(_clean_text(data.get("title")) or draft.title)
        dek = _replace_yo(_clean_text(data.get("dek")) or draft.dek)
        body = _normalize_guide_body(_replace_yo(_clean_text(data.get("body")) or draft.body))
        if not dek or not body:
            return None

        return DraftGenerationResult(
            title=_strip_markdown_links(title),
            dek=_strip_markdown_links(dek),
            body=_strip_markdown_links(body),
            model=self.settings.editorial_model,
            generation_mode=f"{draft.generation_mode}_edited",
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

    def discover_source_items(
        self,
        source: SourceItem,
        *,
        limit: int,
        prompt: PromptConfig | None = None,
    ) -> list[SourceDiscoveryItem] | None:
        if not self.enabled or not self._should_enable_web_search_for_request():
            return None

        discovery_url = _normalize_source_discovery_url(source.url)
        host = urlsplit(discovery_url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        notes_block = f"source_specific_ai_search_instructions: {source.notes}\n" if source.notes.strip() else ""
        input_text = (
            "Return only valid JSON with key items.\n"
            f"Need up to {limit} latest relevant news items from this source.\n"
            f"source_title: {source.title}\n"
            f"source_url: {discovery_url}\n"
            f"source_category: {source.category}\n"
            f"{notes_block}"
            "For each item return: title, summary, url, published_at, source_title, tags.\n"
            "Rules:\n"
            "- search only this source/domain\n"
            "- prefer fresh sports news items, not promos, nav pages, tag pages, video hubs or subscriptions\n"
            "- summary should be concise and factual in Russian\n"
            "- source_title should be the publication/site name if visible, otherwise use the given source title\n"
            "- url must point to the article page\n"
            "- published_at should be ISO 8601 if you can infer it, otherwise null\n"
            "- tags should be a short topical array in Russian\n"
            "- do not invent facts\n"
        )
        instructions = (
            f"{prompt.system_prompt}\n\n{prompt.user_prompt_template}"
            if prompt is not None
            else (
                "Ты discovery-слой ezbet.ru. Найди на указанном домене свежие новостные материалы и верни "
                "строго JSON без пояснений."
            )
        )

        try:
            payload = self._create_response(
                instructions=instructions,
                input_text=input_text,
                tools=self._build_web_search_tools(discovery_url),
                model=self.settings.search_model,
                operation="source_discovery",
                related_id=source.key,
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        items = data.get("items")
        if not isinstance(items, list):
            return None

        discovered: list[SourceDiscoveryItem] = []
        seen_urls: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("title"))
            summary = _clean_text(item.get("summary"))
            url = _clean_text(item.get("url"))
            published_at = _clean_text(item.get("published_at")) or None
            source_title = _clean_text(item.get("source_title")) or source.title
            tags_value = item.get("tags")
            tags: list[str] = []
            if isinstance(tags_value, list):
                tags = [tag for tag in (_clean_text(tag) for tag in tags_value) if tag]

            if not title or not url or url in seen_urls:
                continue
            if host and host not in url.lower():
                continue
            if not summary:
                summary = title

            seen_urls.add(url)
            discovered.append(
                SourceDiscoveryItem(
                    title=title,
                    summary=summary,
                    url=url,
                    published_at=published_at,
                    full_text=None,
                    source_title=source_title,
                    tags=tags,
                )
            )

        return discovered[:limit] or None

    def resolve_article_target(
        self,
        *,
        source: SourceItem,
        raw_title: str,
        current_url: str,
    ) -> ResolvedArticleTarget | None:
        if not self.enabled or not self._should_enable_web_search_for_request():
            return None

        host = urlsplit(source.url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        input_text = (
            "Return only valid JSON with keys url, published_at, source_title.\n"
            f"source_title: {source.title}\n"
            f"source_url: {source.url}\n"
            f"candidate_title: {raw_title}\n"
            f"current_url: {current_url}\n"
            "Find the exact canonical article URL on this domain for the given title.\n"
            "Rules:\n"
            "- search only this source/domain\n"
            "- prefer the exact article page, not tag pages or mirrors\n"
            "- if current_url is wrong or normalized incorrectly, return the better canonical URL\n"
            "- if you cannot improve the URL, return the current_url\n"
            "- published_at should be ISO 8601 if visible, otherwise null\n"
            "- do not invent facts\n"
        )
        instructions = (
            "Ты resolve-слой ezbet.ru. Найди точную canonical article URL по заголовку и домену. "
            "Отвечай только JSON."
        )

        try:
            payload = self._create_response(
                instructions=instructions,
                input_text=input_text,
                tools=self._build_web_search_tools(source.url),
                model=self.settings.search_model,
                operation="source_resolve_url",
                related_id=source.key,
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        url = _clean_text(data.get("url"))
        if not url:
            return None
        if host and host not in url.lower():
            return None

        published_at = _clean_text(data.get("published_at")) or None
        source_title = _clean_text(data.get("source_title")) or source.title
        return ResolvedArticleTarget(
            url=url,
            published_at=published_at,
            source_title=source_title,
        )

    def extract_article_enrichment(
        self,
        *,
        url: str,
        source_title: str,
        raw_title: str,
        raw_summary: str,
        html: str,
        allow_web_search: bool = False,
    ) -> ArticleExtractionResult | None:
        if not self.enabled:
            return None

        prepared_html = _prepare_html_for_article_extraction(
            html=html,
            raw_title=raw_title,
            raw_summary=raw_summary,
            limit=28000,
        )
        input_text = (
            "Return only valid JSON with keys full_text, lead, tags, source_url, source_title, source_urls, used_web_search.\n"
            f"url: {url}\n"
            f"source_title: {source_title}\n"
            f"raw_title: {raw_title}\n"
            f"raw_summary: {raw_summary}\n"
            "Rules:\n"
            "- if you can reliably use the provided HTML alone, full_text must be the main article text only, not a rewrite\n"
            "- if HTML is weak and you use web search, full_text must instead be a concise Russian news brief in 2-4 paragraphs based on the found sources\n"
            "- lead: extract a short intro or lead if it is clearly present\n"
            "- tags: return a short array of topical tags in Russian\n"
            "- source_url: return the URL of the page whose article text you actually used\n"
            "- source_title: return the publication/site title whose article text you actually used\n"
            "- source_urls: return a short array of 1-5 source URLs you actually used when web search was needed; otherwise []\n"
            "- used_web_search: true only if HTML alone was insufficient and you used web search\n"
            "- ignore menus, promos, related blocks, comments and footer text\n"
            "- if the article text is inside JSON/script data, extract only the article text\n"
            f"- {'if provided HTML is weak or incomplete, you may use web search results to find the same news and extract it' if allow_web_search else 'do not use web search; work only with the provided HTML'}\n"
            "- if you used only HTML, preserve the original wording of the article as much as possible; normalize whitespace only\n"
            "- if you used web search, do not copy a third-party article verbatim; produce a factual Russian brief instead\n"
            "- do not invent facts\n\n"
            f"HTML:\n{prepared_html}"
        )
        instructions = (
            "Ты extraction-слой ezbet.ru. Из HTML нужно дословно достать основной текст новости и базовые метаданные. "
            "Отвечай только JSON."
        )

        try:
            payload = self._create_response(
                instructions=instructions,
                input_text=input_text,
                tools=self._build_web_search_tools(url, restrict_to_source_domain=False) if allow_web_search else None,
                model=self.settings.search_model,
                include=["web_search_call.action.sources"] if allow_web_search and self._should_enable_web_search_for_request() else None,
                operation="enrichment_web_extract" if allow_web_search else "enrichment_html_extract",
                related_id=url,
            )
            data = _loads_llm_json(payload)
        except LLM_REQUEST_EXCEPTIONS:
            return None

        full_text = _clean_article_text(data.get("full_text"))
        lead = _clean_lead_text(data.get("lead"))
        source_url = _clean_text(data.get("source_url")) or url
        source_title_value = _clean_text(data.get("source_title")) or source_title
        reference_urls = _clean_url_list(data.get("source_urls"))
        used_web_search = bool(data.get("used_web_search")) if allow_web_search else False
        if used_web_search and full_text is not None and not _is_mostly_russian_text(full_text):
            full_text = None
        if lead is not None and not _is_mostly_russian_text(lead):
            lead = None
        tags_value = data.get("tags")
        tags: list[str] = []
        if isinstance(tags_value, list):
            tags = [tag for tag in (_clean_text(item) for item in tags_value) if tag]

        if full_text is None and lead is None and not tags:
            return None

        if used_web_search and not reference_urls and source_url:
            reference_urls = [source_url]

        return ArticleExtractionResult(
            full_text=full_text,
            lead=lead,
            tags=tags,
            source_url=source_url,
            source_title=source_title_value,
            reference_urls=reference_urls,
            used_web_search=used_web_search,
            model=self.settings.search_model,
            generation_mode=(
                f"llm_{self.settings.api_style}_web_search_brief"
                if used_web_search
                else f"llm_{self.settings.api_style}_html_extraction"
            ),
        )

    def extract_article_enrichment_via_search(
        self,
        *,
        url: str,
        source_title: str,
        raw_title: str,
        raw_summary: str,
    ) -> ArticleExtractionResult | None:
        if not self.enabled or not self._should_enable_web_search_for_request():
            return None

        search_profiles = _build_article_search_profiles(
            url=url,
            source_title=source_title,
            raw_title=raw_title,
            raw_summary=raw_summary,
        )

        instructions = (
            "Ты extraction-слой ezbet.ru. Если HTML исходной страницы недоступен, найди ту же новость через web search "
            "и достань основной текст статьи и базовые метаданные. Отвечай только JSON."
        )

        best_partial: ArticleExtractionResult | None = None
        best_partial_score = -1

        for profile in search_profiles:
            input_text = (
                "Return only valid JSON with keys full_text, lead, tags, source_url, source_title, source_urls, used_web_search.\n"
                f"url: {url}\n"
                f"source_title: {source_title}\n"
                f"raw_title: {raw_title}\n"
                f"raw_summary: {raw_summary}\n"
                f"search_strategy: {profile['name']}\n"
                f"query_hint: {profile['query_hint']}\n"
                "Rules:\n"
                "- use web search to find the same news story when direct page HTML is unavailable or unusable\n"
                "- full_text: write a concise Russian news brief in 2-4 short paragraphs based on the sources you found\n"
                "- lead: extract a short intro or lead if it is clearly present\n"
                "- tags: return a short array of topical tags in Russian\n"
                "- source_url: return the main URL you relied on most\n"
                "- source_title: return the publication/site title you relied on most\n"
                "- source_urls: return a short array of 1-5 source URLs you actually used\n"
                "- used_web_search: always true\n"
                "- prioritize exact title match and the same factual event\n"
                "- prefer the same domain first when possible, but if unavailable use another trustworthy source with the same news story\n"
                "- do not reproduce a third-party article verbatim; synthesize a factual brief in Russian\n"
                "- keep all essential facts that help later editorial rewriting\n"
                "- do not invent facts"
            )

            try:
                payload = self._create_response(
                    instructions=instructions,
                    input_text=input_text,
                    tools=self._build_web_search_tools(
                        url,
                        restrict_to_source_domain=bool(profile["restrict_to_source_domain"]),
                    ),
                    model=self.settings.search_model,
                    include=["web_search_call.action.sources"],
                    operation="enrichment_search_extract",
                    related_id=url,
                )
                data = _loads_llm_json(payload)
            except LLM_REQUEST_EXCEPTIONS:
                continue

            full_text = _clean_article_text(data.get("full_text"))
            lead = _clean_lead_text(data.get("lead"))
            source_url = _clean_text(data.get("source_url")) or url
            source_title_value = _clean_text(data.get("source_title")) or source_title
            reference_urls = _clean_url_list(data.get("source_urls"))
            if full_text is not None and not _is_mostly_russian_text(full_text):
                full_text = None
            if lead is not None and not _is_mostly_russian_text(lead):
                lead = None
            tags_value = data.get("tags")
            tags: list[str] = []
            if isinstance(tags_value, list):
                tags = [tag for tag in (_clean_text(item) for item in tags_value) if tag]

            if full_text is None and lead is None and not tags:
                continue

            if not reference_urls and source_url:
                reference_urls = [source_url]

            candidate = ArticleExtractionResult(
                full_text=full_text,
                lead=lead,
                tags=tags,
                source_url=source_url,
                source_title=source_title_value,
                reference_urls=reference_urls,
                used_web_search=True,
                model=self.settings.search_model,
                generation_mode=f"llm_{self.settings.api_style}_web_search_brief",
            )

            if full_text is not None:
                return candidate

            partial_score = _score_partial_search_candidate(lead=lead, tags=tags, reference_urls=reference_urls)
            if partial_score > best_partial_score and (lead is not None or tags):
                best_partial = candidate
                best_partial_score = partial_score

        return best_partial

    def _create_response(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        include: list[str] | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        text_format: dict[str, Any] | None = None,
        citation_urls: list[str] | None = None,
        operation: str = "unknown",
        related_id: str | None = None,
    ) -> str:
        if self.settings.api_style == "chat_completions":
            return self._create_chat_completion(
                instructions=instructions,
                input_text=input_text,
                model=model or self.settings.editorial_model,
                operation=operation,
                related_id=related_id,
            )
        return self._create_responses_completion(
            instructions=instructions,
            input_text=input_text,
            model=model or self.settings.editorial_model,
            tools=tools,
            include=include,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            text_format=text_format,
            citation_urls=citation_urls,
            operation=operation,
            related_id=related_id,
        )

    def _create_responses_completion(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        include: list[str] | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        text_format: dict[str, Any] | None = None,
        citation_urls: list[str] | None = None,
        operation: str,
        related_id: str | None = None,
    ) -> str:
        payload_body: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input_text,
        }
        if tools:
            payload_body["tools"] = tools
            payload_body["tool_choice"] = "auto"
        if include:
            payload_body["include"] = include
        if max_output_tokens is not None:
            payload_body["max_output_tokens"] = max_output_tokens
        if reasoning_effort is not None:
            payload_body["reasoning"] = {"effort": reasoning_effort}
        if text_format is not None:
            payload_body["text"] = {"format": text_format}

        request_body = json.dumps(payload_body).encode("utf-8")
        request = Request(
            url=f"{self.settings.base_url.rstrip('/')}/responses",
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.api_key}",
            },
            method="POST",
        )

        for attempt in range(2):
            try:
                with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except LLM_TRANSIENT_EXCEPTIONS:
                if attempt >= 1:
                    raise
                sleep(1)

        record_ai_usage_event(
            operation=operation,
            model=model,
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
            related_id=related_id,
            web_search_calls=_count_web_search_calls(payload),
        )
        if citation_urls is not None:
            citation_urls.extend(_extract_response_citation_urls(payload))
        return _extract_output_text(payload)

    def _should_enable_web_search_for_request(self) -> bool:
        return (
            self.settings.web_search_enabled
            and self.settings.api_style == "responses"
            and "openai.com" in self.settings.base_url
        )

    def _build_web_search_tools(self, url: str, restrict_to_source_domain: bool = True) -> list[dict[str, Any]] | None:
        if not self._should_enable_web_search_for_request():
            return None

        host = urlsplit(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        tool: dict[str, Any] = {
            "type": "web_search",
            "external_web_access": self.settings.web_search_live,
            "search_context_size": self.settings.web_search_context_size,
        }
        if restrict_to_source_domain and host:
            tool["filters"] = {
                "allowed_domains": [host],
            }
        return [tool]

    def _build_guide_web_search_tools(self, context_size: str = "low") -> list[dict[str, Any]] | None:
        if not self._should_enable_web_search_for_request():
            return None

        safe_context_size = context_size if context_size in {"low", "medium", "high"} else "low"
        return [
            {
                "type": "web_search",
                "external_web_access": self.settings.web_search_live,
                "search_context_size": safe_context_size,
            }
        ]

    def _create_chat_completion(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str,
        operation: str,
        related_id: str | None = None,
    ) -> str:
        request_body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": input_text},
                ],
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = Request(
            url=f"{self.settings.base_url.rstrip('/')}/chat/completions",
            data=request_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.api_key}",
            },
            method="POST",
        )

        with urlopen(request, timeout=self.settings.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        record_ai_usage_event(
            operation=operation,
            model=model,
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
            related_id=related_id,
            used_web_search=False,
        )
        return _extract_chat_completion_text(payload)


def _extract_output_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())

    return "\n".join(chunks).strip()


def _loads_llm_json(payload: str) -> Any:
    cleaned = payload.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1], strict=False)
        raise


def _validate_match_research_facts(
    value: Any,
    *,
    cutoff_date: date,
    cited_urls: list[str],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    if not any(_is_public_http_url(url) for url in cited_urls):
        return []
    accepted: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    allowed_kinds = {"home_result", "away_result", "head_to_head", "squad_news"}
    for item in value:
        if not isinstance(item, dict) or item.get("confidence") not in {"high", "medium"}:
            continue
        statement = _clean_text(item.get("statement"))
        source_url = _clean_text(item.get("source_url"))
        source_title = _clean_text(item.get("source_title"))
        event_date_text = _clean_text(item.get("event_date"))
        kind = _clean_text(item.get("kind"))
        if not all((statement, source_url, source_title)) or kind not in allowed_kinds:
            continue
        if len(statement) < 30 or _is_internal_citation_text(statement):
            continue
        if not _is_public_http_url(source_url):
            continue
        if event_date_text:
            try:
                event_date = date.fromisoformat(event_date_text)
            except ValueError:
                continue
            if event_date > cutoff_date:
                continue
        key = (statement.casefold(), source_url)
        if key in seen:
            continue
        seen.add(key)
        accepted.append(
            {
                "statement": statement,
                "source_url": source_url,
                "source_title": source_title,
                "event_date": event_date_text or "дата не указана",
                "kind": kind,
            }
        )
    return accepted


def _is_public_http_url(value: str) -> bool:
    if _is_internal_citation_text(value):
        return False
    parts = urlsplit(value)
    host = parts.netloc.casefold().removeprefix("www.")
    denied_hosts = {
        "flashscore.com",
        "flashscore.com.ar",
        "predictz.com",
        "sofascore.com",
        "bet365.com",
        "oddsportal.com",
    }
    return (
        parts.scheme in {"http", "https"}
        and bool(host)
        and "." in host
        and host not in denied_hosts
        and not any(host.endswith(f".{denied}") for denied in denied_hosts)
        and len(parts.path.strip("/")) >= 4
        and not parts.path.rstrip("/").endswith("/gameId")
    )


def _is_internal_citation_text(value: str) -> bool:
    return bool(re.search(r"\bturn\d+(?:search|fetch|view)\d+\b", value.casefold()))


def _source_publisher_tokens(value: str) -> set[str]:
    generic_labels = {"www", "com", "org", "net", "gob", "gov", "ar", "mx", "cl", "co", "uk"}
    host = urlsplit(value).netloc.casefold()
    return {label for label in host.split(".") if len(label) >= 4 and label not in generic_labels}


def _extract_response_citation_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if isinstance(action, dict):
            for source in action.get("sources", []):
                if not isinstance(source, dict):
                    continue
                url = source.get("url")
                if isinstance(url, str) and _is_public_http_url(url):
                    urls.append(url)
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            for annotation in content.get("annotations", []):
                if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                    continue
                url = annotation.get("url")
                if isinstance(url, str) and _is_public_http_url(url):
                    urls.append(url)
    return list(dict.fromkeys(urls))


def _count_web_search_calls(payload: dict[str, Any]) -> int:
    count = 0
    for item in payload.get("output", []):
        if isinstance(item, dict) and item.get("type") == "web_search_call":
            count += 1
    return count


def _normalize_source_discovery_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip()


def _clean_article_text(value: Any) -> str | None:
    cleaned = _clean_text(value) or None
    if cleaned is None:
        return None

    normalized = cleaned.lower()
    refusal_markers = (
        "не удалось получить html",
        "не найдено копий этой новости",
        "не могу предоставить текст статьи",
        "я ограничен результатами",
        "html исходной страницы недоступен",
        "не найдено подтверждений",
        "не нашли подтверждений",
        "проверка сайта не выявила публикации",
        "проверка сайта не выявила",
        "рекомендуется уточнить заголовок",
        "расширить поиск на внешние источники",
        "прислать ссылку на первоисточник",
        "i can't provide the article text",
        "could not retrieve html",
    )
    if any(marker in normalized for marker in refusal_markers):
        return None
    return cleaned


def _clean_lead_text(value: Any) -> str | None:
    cleaned = _clean_text(value) or None
    if cleaned is None:
        return None

    normalized = cleaned.lower()
    refusal_markers = (
        "извините",
        "не могу предоставить",
        "не удалось получить",
        "не найдено копий",
        "краткое содержание",
        "summary:",
        "i can't provide",
        "sorry",
    )
    if any(marker in normalized for marker in refusal_markers):
        return None
    return cleaned


def _clean_url_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        url = _clean_text(item)
        if not url or not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned[:5]


def _is_mostly_russian_text(value: str) -> bool:
    cyrillic_count = len(re.findall(r"[А-Яа-яЁё]", value))
    latin_count = len(re.findall(r"[A-Za-z]", value))
    if cyrillic_count == 0:
        return False
    if latin_count == 0:
        return True
    return cyrillic_count >= latin_count * 1.5

    path = parts.path or "/"

    # If a user pastes an article-like URL into ai search, step back to the
    # parent listing path so discovery searches the section/domain, not one page.
    article_like = (
        path.endswith(".html")
        or path.endswith(".htm")
        or "/news/" in path
        or path.rstrip("/").split("/")[-1].isdigit()
    )

    if article_like:
        normalized_path = path
        if normalized_path.endswith(".html") or normalized_path.endswith(".htm"):
            normalized_path = normalized_path.rsplit("/", 1)[0] + "/"
        elif not normalized_path.endswith("/"):
            normalized_path = normalized_path.rsplit("/", 1)[0] + "/"
        if not normalized_path:
            normalized_path = "/"
        return urlunsplit((parts.scheme, parts.netloc, normalized_path, "", ""))

    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalize_guide_body(value: str) -> str:
    replacements = {
        "групповго": "группового",
        "чемпионом победа": "чемпиона победа",
        "выгодu": "выгоду",
        "тп.": "т. п.",
        " тп": " т. п.",
        "из за": "из-за",
    }
    normalized = value
    for raw, replacement in replacements.items():
        normalized = re.sub(re.escape(raw), replacement, normalized, flags=re.IGNORECASE)
    return _strip_markdown_links(normalized).strip()


def _strip_markdown_links(value: str) -> str:
    cleaned = re.sub(r"\s*\(\[[^\]]+\]\([^)]+\)\)", "", value)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip()


def _coerce_research_brief(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, str):
                lines.append(item.strip())
            elif isinstance(item, dict):
                parts = [_clean_text(part) for part in item.values()]
                lines.append("; ".join(part for part in parts if part))
        return "\n".join(line for line in lines if line)

    if isinstance(value, dict):
        for key in ("research_brief", "facts", "items", "bullets"):
            if key in value:
                return _coerce_research_brief(value[key])
        parts = [_clean_text(part) for part in value.values()]
        return "\n".join(part for part in parts if part)

    return ""


def _replace_yo(value: str) -> str:
    return value.replace("ё", "е").replace("Ё", "Е")


def _normalize_editor_decision(
    decision: str,
    revised_title: str | None,
    revised_dek: str | None,
    revised_body: str | None,
) -> str:
    normalized = decision.strip().lower()
    if normalized in {"approve", "light_edit", "rewrite"}:
        return normalized
    if revised_title and revised_dek and revised_body:
        return "light_edit"
    return "approve"


def _build_article_search_profiles(
    *,
    url: str,
    source_title: str,
    raw_title: str,
    raw_summary: str,
) -> list[dict[str, Any]]:
    compact_title = _compress_search_text(raw_title, limit=180)
    compact_summary = _compress_search_text(raw_summary, limit=260)
    fact_keywords = _extract_fact_keywords(raw_title, raw_summary, limit=8)
    fact_hint = ", ".join(fact_keywords)
    host = urlsplit(url).netloc.lower()

    profiles: list[dict[str, Any]] = [
        {
            "name": "same_domain_title_first",
            "query_hint": (
                f'Find the same news on the original source first. Domain: {host or source_title}. '
                f'Use this title: "{compact_title}".'
            ),
            "restrict_to_source_domain": True,
        },
        {
            "name": "title_plus_summary",
            "query_hint": (
                f'Find the same news story by title and facts. Title: "{compact_title}". '
                f"Summary facts: {compact_summary}"
            ),
            "restrict_to_source_domain": False,
        },
    ]

    if fact_hint:
        profiles.append(
            {
                "name": "fact_keywords",
                "query_hint": (
                    "Find the same sports news story by factual keywords and entities, even if the original title "
                    f"is noisy or transliterated. Keywords: {fact_hint}"
                ),
                "restrict_to_source_domain": False,
            }
        )

    return profiles


def _compress_search_text(value: str, *, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip(" ,.;:!?")


def _extract_fact_keywords(raw_title: str, raw_summary: str, *, limit: int) -> list[str]:
    text = f"{raw_title} {raw_summary}"
    candidates = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9'’.-]{2,}", text)
    keywords: list[str] = []
    seen: set[str] = set()
    stopwords = {
        "что",
        "это",
        "как",
        "для",
        "при",
        "или",
        "его",
        "еще",
        "after",
        "with",
        "from",
        "this",
        "that",
        "have",
        "will",
        "been",
        "news",
        "sport",
    }

    for candidate in candidates:
        lowered = candidate.lower()
        if lowered in seen or lowered in stopwords:
            continue
        if len(lowered) <= 2:
            continue
        seen.add(lowered)
        keywords.append(candidate)
        if len(keywords) >= limit:
            break

    return keywords


def _score_partial_search_candidate(
    *,
    lead: str | None,
    tags: list[str],
    reference_urls: list[str],
) -> int:
    score = 0
    if lead:
        score += 3
        if len(lead) >= 80:
            score += 2
    if tags:
        score += min(len(tags), 4)
    if reference_urls:
        score += min(len(reference_urls), 3)
    return score


def _truncate_for_llm(value: str, limit: int) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit]


def _prepare_html_for_article_extraction(
    *,
    html: str,
    raw_title: str,
    raw_summary: str,
    limit: int,
) -> str:
    cleaned = html.strip()
    if len(cleaned) <= limit:
        return cleaned

    snippets: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add_snippet(label: str, snippet: str | None) -> None:
        if not snippet:
            return
        compact = snippet.strip()
        if not compact or compact in seen:
            return
        seen.add(compact)
        snippets.append((label, compact))

    add_snippet("HEAD", cleaned[:5000])
    add_snippet("TAIL", cleaned[-3000:])

    focus_terms = [raw_title, raw_summary]
    focus_terms.extend(
        term
        for term in (
            "<article",
            "<main",
            "articlebody",
            "article-body",
            "story-body",
            "news__content",
            "articlecontent",
            "\"article\"",
            "\"content\"",
        )
    )

    lowered = cleaned.lower()
    for term in focus_terms:
        normalized_term = (term or "").strip()
        if not normalized_term:
            continue
        lookup = normalized_term.lower()
        index = lowered.find(lookup)
        if index == -1 and len(lookup) > 80:
            lookup = lookup[:80]
            index = lowered.find(lookup)
        if index == -1:
            continue
        start = max(0, index - 5000)
        end = min(len(cleaned), index + 18000)
        add_snippet(f"FOCUS:{normalized_term[:48]}", cleaned[start:end])
        if sum(len(text) for _, text in snippets) >= limit:
            break

    if not snippets:
        return _truncate_for_llm(cleaned, limit)

    parts: list[str] = []
    total = 0
    for label, snippet in snippets:
        block = f"<!-- {label} -->\n{snippet}"
        remaining = limit - total
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining]
        parts.append(block)
        total += len(block)

    prepared = "\n\n".join(parts).strip()
    return prepared or _truncate_for_llm(cleaned, limit)


def _extract_chat_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return ""

    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    return ""
