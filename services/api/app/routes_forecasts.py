from __future__ import annotations

from fastapi import Request
from .models import (
    ForecastRefreshResponse,
    ForecastGenerationResponse,
    MatchForecastListResponse,
    MatchForecastResponse,
)
from fastapi import APIRouter
from . import service_forecasts

router = APIRouter()


@router.get("/api/v1/forecasts", response_model=MatchForecastListResponse)
def list_match_forecasts() -> MatchForecastListResponse:
    return service_forecasts.list_match_forecasts()


@router.get("/api/v1/forecasts/{slug}", response_model=MatchForecastResponse)
def get_match_forecast(slug: str) -> MatchForecastResponse:
    return service_forecasts.get_match_forecast(slug=slug)


@router.post("/api/v1/forecasts/run", response_model=ForecastRefreshResponse)
def refresh_match_forecasts(request: Request) -> ForecastRefreshResponse:
    return service_forecasts.refresh_match_forecasts(request=request)


@router.post("/api/v1/forecasts/test-generate", response_model=MatchForecastResponse)
def generate_first_match_forecast_test(request: Request) -> MatchForecastResponse:
    'Temporary cost guard: research and write exactly one, highest-ranked current match.'
    return service_forecasts.generate_first_match_forecast_test(request=request)


@router.post("/api/v1/forecasts/daily-run", response_model=ForecastGenerationResponse)
def run_daily_match_forecasts(request: Request) -> ForecastGenerationResponse:
    'Publish from three to six forecasts, using same-day reserves when generation fails.'
    return service_forecasts.run_daily_match_forecasts(request=request)


