from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from urllib.request import Request, urlopen


LEON_TOP_EVENTS_URL = "https://leon.ru/blog/api/top-events?limit=100&sport_id=1"
MOSCOW_TZ = timezone(timedelta(hours=3))
MAX_FORECASTS = 6
MAX_PER_LEAGUE = 2

HIGH_PRIORITY_LEAGUES = (
    "лига чемпионов",
    "лига европы",
    "лига конференций",
    "чемпионат мира",
    "чемпионат европы",
    "премьер-лига",
    "бундеслига",
    "серия a",
    "ла лига",
    "лига 1",
)


@dataclass(frozen=True)
class SelectedForecast:
    slug: str
    home_team: str
    away_team: str
    home_logo: str | None
    away_logo: str | None
    league: str
    kickoff: datetime
    odds_home: float
    odds_draw: float
    odds_away: float
    selection_score: int
    source_order: int


def fetch_leon_football_events(timeout_seconds: int = 20) -> list[dict[str, Any]]:
    request = Request(LEON_TOP_EVENTS_URL, headers={"User-Agent": "ezbet forecast bot/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310: fixed public endpoint
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Leon top-events response must be a list")
    return [item for item in payload if isinstance(item, dict)]


def select_top_forecasts(
    events: list[dict[str, Any]],
    now: datetime | None = None,
    limit: int = MAX_FORECASTS,
) -> list[SelectedForecast]:
    current_time = (now or datetime.now(MOSCOW_TZ)).astimezone(MOSCOW_TZ)
    day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    candidates: list[SelectedForecast] = []

    for source_order, event in enumerate(events):
        if event.get("sport_id") != 1 or not event.get("is_active") or event.get("is_finished") or event.get("is_live"):
            continue
        kickoff = _parse_kickoff(event.get("kickoff"))
        # Утренний прогон формирует только подборку «на сегодня» по Москве.
        # Если крупных матчей мало, сортировка сама доберёт менее приоритетные
        # события этого же календарного дня, но никогда не перейдёт на завтра.
        if kickoff is None or not current_time < kickoff < day_end:
            continue
        odds = _extract_odds(event)
        if odds is None:
            continue
        # Матчи с почти гарантированным фаворитом не дают содержательного первого прогноза.
        if min(odds) < 1.12:
            continue
        slug = _text(event.get("slug"))
        home_team = _text(event.get("t1_name"))
        away_team = _text(event.get("t2_name"))
        league = _text(event.get("league_name"))
        if not all((slug, home_team, away_team, league)):
            continue
        candidates.append(
            SelectedForecast(
                slug=slug,
                home_team=home_team,
                away_team=away_team,
                home_logo=_optional_text(event.get("t1_logo")),
                away_logo=_optional_text(event.get("t2_logo")),
                league=league,
                kickoff=kickoff,
                odds_home=odds[0],
                odds_draw=odds[1],
                odds_away=odds[2],
                selection_score=_league_priority(league) * 1000 - source_order,
                source_order=source_order,
            )
        )

    selected: list[SelectedForecast] = []
    league_counts: dict[str, int] = {}
    for candidate in sorted(candidates, key=lambda item: (-item.selection_score, item.kickoff, item.source_order)):
        league_key = candidate.league.casefold()
        if league_counts.get(league_key, 0) >= MAX_PER_LEAGUE:
            continue
        selected.append(candidate)
        league_counts[league_key] = league_counts.get(league_key, 0) + 1
        if len(selected) == limit:
            break
    return selected


def _league_priority(league: str) -> int:
    normalized = league.casefold()
    if "женщ" in normalized:
        return 0
    if any(name in normalized for name in HIGH_PRIORITY_LEAGUES):
        return 3
    return 1


def _extract_odds(event: dict[str, Any]) -> tuple[float, float, float] | None:
    runner = event.get("rates", {}).get("isxod-1x2-osnovnoe-vremia", {}).get("runner", {})
    try:
        values = (float(runner["1"]), float(runner["X"]), float(runner["2"]))
    except (KeyError, TypeError, ValueError):
        return None
    return values if all(value > 1 for value in values) else None


def _parse_kickoff(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=MOSCOW_TZ)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None
