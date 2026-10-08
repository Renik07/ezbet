import { resolveApiBaseUrl } from "./api";
import { publicDataCache, PublicApiError } from "./public-data-cache";

export type MatchForecast = {
  slug: string;
  homeTeam: string;
  awayTeam: string;
  homeLogo: string;
  awayLogo: string;
  league: string;
  kickoff: string;
  odds: {
    home: string;
    draw: string;
    away: string;
  };
  pick: string;
  lead: string;
  homeForm: string;
  awayForm: string;
  factors: string[];
};

// Временный источник для первого визуального релиза. Следующий этап заменит
// этот список результатом ежедневного сценария Leon API → веб-поиск → AI-текст.
export type ForecastApiItem = {
  slug: string;
  homeTeam: string;
  awayTeam: string;
  homeLogo?: string;
  awayLogo?: string;
  league: string;
  kickoff: string;
  oddsHome: number;
  oddsDraw: number;
  oddsAway: number;
  lead?: string;
  homeForm?: string;
  awayForm?: string;
  factors?: string[];
  pick?: string;
  generationStatus?: string;
  updatedAt: string;
};

function forecastPayload(value: unknown): { items: ForecastApiItem[] } {
  const payload = value as { items?: ForecastApiItem[] };
  if (!payload || !Array.isArray(payload.items)) throw new PublicApiError("Invalid forecast feed.");
  for (const item of payload.items) {
    if (!item || typeof item.slug !== "string" || typeof item.homeTeam !== "string" || typeof item.awayTeam !== "string" ||
        typeof item.league !== "string" || !Number.isFinite(Date.parse(item.kickoff)) ||
        ![item.oddsHome, item.oddsDraw, item.oddsAway].every((odd) => typeof odd === "number" && Number.isFinite(odd))) {
      throw new PublicApiError("Invalid forecast.");
    }
  }
  return { items: payload.items };
}

export async function getForecastApiItems(): Promise<ForecastApiItem[]> {
  const baseUrl = resolveApiBaseUrl();
  if (!baseUrl) throw new PublicApiError("Public API is not configured.");
  const result = await publicDataCache.get(new URL("/api/v1/forecasts", baseUrl).toString(), forecastPayload,
    { freshMs: 60_000, staleMs: 5 * 60_000, timeoutMs: 5000 });
  const date = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Moscow" });
  const today = date.format(new Date());
  return result.data.items.filter((item) => item.generationStatus === "ready" && date.format(new Date(item.kickoff)) === today);
}

export async function getTodayForecasts(): Promise<MatchForecast[]> {
  try { return (await getForecastApiItems()).map(toDisplayForecast); }
  catch { return []; }
}

export async function getLiveForecast(slug: string): Promise<MatchForecast | undefined> {
  // An outage is an error; only an actual missing item becomes a 404 page.
  const item = (await getForecastApiItems()).find((forecast) => forecast.slug === slug);
  return item ? toDisplayForecast(item) : undefined;
}

function toDisplayForecast(item: ForecastApiItem): MatchForecast {
  const homeIsFavourite = item.oddsHome <= item.oddsAway;
  const favourite = homeIsFavourite ? item.homeTeam : item.awayTeam;
  return {
    slug: item.slug,
    homeTeam: item.homeTeam,
    awayTeam: item.awayTeam,
    homeLogo: item.homeLogo || "",
    awayLogo: item.awayLogo || "",
    league: item.league,
    kickoff: new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow" }).format(new Date(item.kickoff)).replace(" в ", ", "),
    odds: { home: item.oddsHome.toFixed(2), draw: item.oddsDraw.toFixed(2), away: item.oddsAway.toFixed(2) },
    pick: item.pick || "Прогноз редакции готовится",
    lead: item.lead || `Матч отобран по значимости турнира, времени начала и линии. Небольшим фаворитом рынка считается ${favourite}.`,
    homeForm: item.homeForm || "Детальный разбор формы будет добавлен после ежедневного веб-исследования команд.",
    awayForm: item.awayForm || "Детальный разбор формы будет добавлен после ежедневного веб-исследования команд.",
    factors: item.factors?.length ? item.factors : ["значимость турнира", "время матча", "текущая линия на основные исходы"],
  };
}

export function teamInitials(team: string) {
  return team
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}
