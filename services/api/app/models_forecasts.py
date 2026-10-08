from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class MatchForecast(BaseModel):
    slug: str
    home_team: str = Field(serialization_alias="homeTeam")
    away_team: str = Field(serialization_alias="awayTeam")
    home_logo: str | None = Field(default=None, serialization_alias="homeLogo")
    away_logo: str | None = Field(default=None, serialization_alias="awayLogo")
    league: str
    kickoff: datetime
    odds_home: float = Field(serialization_alias="oddsHome")
    odds_draw: float = Field(serialization_alias="oddsDraw")
    odds_away: float = Field(serialization_alias="oddsAway")
    selection_score: int = Field(serialization_alias="selectionScore")
    research_brief: str | None = Field(default=None, serialization_alias="researchBrief")
    source_urls: list[str] = Field(default_factory=list, serialization_alias="sourceUrls")
    lead: str | None = None
    home_form: str | None = Field(default=None, serialization_alias="homeForm")
    away_form: str | None = Field(default=None, serialization_alias="awayForm")
    factors: list[str] = Field(default_factory=list)
    pick: str | None = None
    generation_status: str = Field(default="pending", serialization_alias="generationStatus")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class MatchForecastListResponse(BaseModel):
    items: list[MatchForecast]


class MatchForecastResponse(BaseModel):
    item: MatchForecast


class ForecastRefreshResponse(BaseModel):
    fetched_count: int = Field(serialization_alias="fetchedCount")
    selected_count: int = Field(serialization_alias="selectedCount")
    items: list[MatchForecast]


class ForecastGenerationResponse(BaseModel):
    fetched_count: int = Field(serialization_alias="fetchedCount")
    selected_count: int = Field(serialization_alias="selectedCount")
    attempted_count: int = Field(serialization_alias="attemptedCount")
    generated_count: int = Field(serialization_alias="generatedCount")
    failed_slugs: list[str] = Field(serialization_alias="failedSlugs")
    items: list[MatchForecast]

