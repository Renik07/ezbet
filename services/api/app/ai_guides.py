from __future__ import annotations

from time import sleep
from typing import Any
from .models import (
    GuideTopic,
    PromptConfig,
)
from .ai_response_helpers import _loads_llm_json
from .ai_text_helpers import (
    _clean_text,
    _coerce_research_brief,
    _normalize_guide_body,
    _replace_yo,
    _strip_markdown_links,
)
from .ai_types import (
    DraftGenerationResult,
    GuideResearchResult,
    LLM_REQUEST_EXCEPTIONS,
)


class GuidesAIClient:
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

