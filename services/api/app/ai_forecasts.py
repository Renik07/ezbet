from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from .ai_response_helpers import _loads_llm_json
from .ai_text_helpers import (
    _clean_text,
    _is_public_http_url,
    _replace_yo,
    _source_publisher_tokens,
    _validate_match_research_facts,
)
from .ai_types import (
    LLM_REQUEST_EXCEPTIONS,
    logger,
)


class ForecastsAIClient:
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

