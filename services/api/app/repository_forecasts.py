from __future__ import annotations

from .models import MatchForecast

class ForecastsRepository:
    def replace_current_match_forecasts(self, forecasts: list[MatchForecast]) -> list[MatchForecast]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE match_forecasts SET is_current = FALSE WHERE is_current = TRUE")
                for forecast in forecasts:
                    cursor.execute(
                        """
                        INSERT INTO match_forecasts (
                            slug, home_team, away_team, home_logo, away_logo, league, kickoff,
                            odds_home, odds_draw, odds_away, selection_score, source_order, is_current, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW())
                        ON CONFLICT (slug) DO UPDATE SET
                            home_team = EXCLUDED.home_team,
                            away_team = EXCLUDED.away_team,
                            home_logo = EXCLUDED.home_logo,
                            away_logo = EXCLUDED.away_logo,
                            league = EXCLUDED.league,
                            kickoff = EXCLUDED.kickoff,
                            odds_home = EXCLUDED.odds_home,
                            odds_draw = EXCLUDED.odds_draw,
                            odds_away = EXCLUDED.odds_away,
                            selection_score = EXCLUDED.selection_score,
                            source_order = EXCLUDED.source_order,
                            is_current = TRUE,
                            updated_at = NOW()
                        """,
                        (
                            forecast.slug, forecast.home_team, forecast.away_team, forecast.home_logo, forecast.away_logo,
                            forecast.league, forecast.kickoff, forecast.odds_home, forecast.odds_draw, forecast.odds_away,
                            forecast.selection_score, 0,
                        ),
                    )
            connection.commit()
        return self.list_match_forecasts()

    def list_match_forecasts(self) -> list[MatchForecast]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT slug, home_team, away_team, home_logo, away_logo, league, kickoff,
                           odds_home, odds_draw, odds_away, selection_score, research_brief, lead,
                           home_form, away_form, factors, pick, generation_status, updated_at, source_urls
                    FROM match_forecasts
                    WHERE is_current = TRUE
                    ORDER BY selection_score DESC, kickoff ASC
                    """
                )
                return [self._map_match_forecast_row(row) for row in cursor.fetchall()]

    def get_match_forecast(self, slug: str) -> MatchForecast | None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT slug, home_team, away_team, home_logo, away_logo, league, kickoff,
                           odds_home, odds_draw, odds_away, selection_score, research_brief, lead,
                           home_form, away_form, factors, pick, generation_status, updated_at, source_urls
                    FROM match_forecasts WHERE slug = %s AND is_current = TRUE
                    """,
                    (slug,),
                )
                row = cursor.fetchone()
        return self._map_match_forecast_row(row) if row else None

    def save_match_forecast_content(self, slug: str, content: dict[str, object]) -> MatchForecast | None:
        def clean_text(key: str) -> str:
            return str(content[key]).replace("\x00", "")

        def clean_text_list(key: str) -> list[str]:
            value = content[key]
            if not isinstance(value, list):
                return []
            return [str(item).replace("\x00", "") for item in value]

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE match_forecasts
                    SET research_brief = %s, lead = %s, home_form = %s, away_form = %s,
                        factors = %s, pick = %s, source_urls = %s,
                        generation_status = 'ready', updated_at = NOW()
                    WHERE slug = %s AND is_current = TRUE
                    """,
                    (
                        clean_text("research_brief"),
                        clean_text("lead"),
                        clean_text("home_form"),
                        clean_text("away_form"),
                        clean_text_list("factors"),
                        clean_text("pick"),
                        clean_text_list("source_urls"),
                        slug,
                    ),
                )
            connection.commit()
        return self.get_match_forecast(slug)

    def set_match_forecast_generation_status(self, slug: str, status: str) -> None:
        if status not in {"pending", "generating", "ready", "failed"}:
            raise ValueError(f"Unsupported match forecast generation status: {status}")
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE match_forecasts
                    SET generation_status = %s, updated_at = NOW()
                    WHERE slug = %s AND is_current = TRUE
                    """,
                    (status, slug),
                )
            connection.commit()

