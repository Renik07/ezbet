from __future__ import annotations

from urllib.parse import urlsplit
from .models import (
    PromptConfig,
    SourceItem,
)
from .ai_response_helpers import _loads_llm_json
from .ai_search_helpers import (
    _build_article_search_profiles,
    _normalize_source_discovery_url,
    _prepare_html_for_article_extraction,
    _score_partial_search_candidate,
)
from .ai_text_helpers import (
    _clean_article_text,
    _clean_lead_text,
    _clean_text,
    _clean_url_list,
    _is_mostly_russian_text,
)
from .ai_types import (
    ArticleExtractionResult,
    LLM_REQUEST_EXCEPTIONS,
    ResolvedArticleTarget,
    SourceDiscoveryItem,
)


class SourcesAIClient:
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

