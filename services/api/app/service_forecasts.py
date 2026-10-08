from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
from datetime import (
    datetime,
    timezone,
)
from fastapi import (
    HTTPException,
    Request,
)
from .ai_client import OpenAIEditorialClient
from .auth import require_admin_api_token as _require_admin_api_token
from .forecasts import (
    fetch_leon_football_events,
    is_current_moscow_date,
    select_top_forecasts,
)
from .models import (
    ForecastRefreshResponse,
    ForecastGenerationResponse,
    MatchForecast,
    MatchForecastListResponse,
    MatchForecastResponse,
)
from . import runtime
from .runtime import (
    FORECAST_CANDIDATE_LIMIT,
    FORECAST_MIN_READY,
    FORECAST_PUBLISH_LIMIT,
    logger,
)


def list_match_forecasts() -> MatchForecastListResponse:
    ready = [
        forecast
        for forecast in runtime.repository.list_match_forecasts()
        if forecast.generation_status == "ready" and is_current_moscow_date(forecast.kickoff)
    ]
    if len(ready) < FORECAST_MIN_READY:
        return MatchForecastListResponse(items=[])
    return MatchForecastListResponse(items=ready[:FORECAST_PUBLISH_LIMIT])


def get_match_forecast(slug: str) -> MatchForecastResponse:
    forecast = runtime.repository.get_match_forecast(slug)
    if (
        forecast is None
        or forecast.generation_status != "ready"
        or not is_current_moscow_date(forecast.kickoff)
    ):
        raise HTTPException(status_code=404, detail="Match forecast not found")
    return MatchForecastResponse(item=forecast)


def refresh_match_forecasts(request: Request) -> ForecastRefreshResponse:
    _require_admin_api_token(request)
    events = fetch_leon_football_events()
    selected = select_top_forecasts(events)
    now = datetime.now(timezone.utc)
    forecasts = [
        MatchForecast(
            slug=item.slug,
            home_team=item.home_team,
            away_team=item.away_team,
            home_logo=item.home_logo,
            away_logo=item.away_logo,
            league=item.league,
            kickoff=item.kickoff,
            odds_home=item.odds_home,
            odds_draw=item.odds_draw,
            odds_away=item.odds_away,
            selection_score=item.selection_score,
            updated_at=now,
        )
        for item in selected
    ]
    items = runtime.repository.replace_current_match_forecasts(forecasts)
    return ForecastRefreshResponse(fetched_count=len(events), selected_count=len(items), items=items)


def generate_first_match_forecast_test(request: Request) -> MatchForecastResponse:
    """Temporary cost guard: research and write exactly one, highest-ranked current match."""
    _require_admin_api_token(request)
    forecasts = runtime.repository.list_match_forecasts()
    if not forecasts:
        raise HTTPException(status_code=409, detail="Run forecast selection before the test generation.")
    forecast = forecasts[0]
    generated = OpenAIEditorialClient().generate_match_forecast(forecast)
    if generated is None:
        raise HTTPException(status_code=503, detail="Match research or AI generation is unavailable.")
    saved = runtime.repository.save_match_forecast_content(forecast.slug, generated)
    if saved is None:
        raise HTTPException(status_code=404, detail="Selected match forecast disappeared during generation.")
    return MatchForecastResponse(item=saved)


def run_daily_match_forecasts(request: Request) -> ForecastGenerationResponse:
    """Publish from three to six forecasts, using same-day reserves when generation fails."""
    _require_admin_api_token(request)
    events = fetch_leon_football_events()
    selected = select_top_forecasts(events, limit=FORECAST_CANDIDATE_LIMIT)
    now = datetime.now(timezone.utc)
    forecasts = [
        MatchForecast(
            slug=item.slug,
            home_team=item.home_team,
            away_team=item.away_team,
            home_logo=item.home_logo,
            away_logo=item.away_logo,
            league=item.league,
            kickoff=item.kickoff,
            odds_home=item.odds_home,
            odds_draw=item.odds_draw,
            odds_away=item.odds_away,
            selection_score=item.selection_score,
            updated_at=now,
        )
        for item in selected
    ]
    current = runtime.repository.replace_current_match_forecasts(forecasts)
    failed_slugs: list[str] = []
    attempted_count = 0

    def generate(forecast: MatchForecast) -> str | None:
        runtime.repository.set_match_forecast_generation_status(forecast.slug, "generating")
        client = OpenAIEditorialClient()
        for search_context_size in ("medium", "high"):
            generated = client.generate_match_forecast(
                forecast,
                search_context_size=search_context_size,
            )
            if generated is not None and runtime.repository.save_match_forecast_content(forecast.slug, generated) is not None:
                return None
        runtime.repository.set_match_forecast_generation_status(forecast.slug, "failed")
        return forecast.slug

    primary = current[:FORECAST_PUBLISH_LIMIT]
    primary_pending = [forecast for forecast in primary if forecast.generation_status != "ready"]
    attempted_count += len(primary_pending)
    if primary_pending:
        with ThreadPoolExecutor(max_workers=min(2, len(primary_pending))) as executor:
            futures = {executor.submit(generate, forecast): forecast.slug for forecast in primary_pending}
            for future in as_completed(futures):
                slug = futures[future]
                try:
                    failed_slug = future.result()
                except Exception:
                    logger.exception("Daily match forecast generation failed: slug=%s", slug)
                    runtime.repository.set_match_forecast_generation_status(slug, "failed")
                    failed_slug = slug
                if failed_slug:
                    failed_slugs.append(failed_slug)

    ready_count = sum(
        forecast.generation_status == "ready"
        for forecast in runtime.repository.list_match_forecasts()
    )
    for reserve in current[FORECAST_PUBLISH_LIMIT:]:
        if ready_count >= FORECAST_MIN_READY:
            break
        if reserve.generation_status == "ready":
            ready_count += 1
            continue
        attempted_count += 1
        try:
            failed_slug = generate(reserve)
        except Exception:
            logger.exception("Reserve match forecast generation failed: slug=%s", reserve.slug)
            runtime.repository.set_match_forecast_generation_status(reserve.slug, "failed")
            failed_slug = reserve.slug
        if failed_slug:
            failed_slugs.append(failed_slug)
        else:
            ready_count += 1

    items = runtime.repository.list_match_forecasts()
    ready_items = [item for item in items if item.generation_status == "ready"]
    return ForecastGenerationResponse(
        fetched_count=len(events),
        selected_count=len(current),
        attempted_count=attempted_count,
        generated_count=len(ready_items),
        failed_slugs=failed_slugs,
        items=items,
    )

