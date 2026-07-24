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
export const fallbackForecasts: MatchForecast[] = [
  {
    slug: "22-07-2026-egnatia-rogozina-cele",
    homeTeam: "Эгнатиа Рогожина",
    awayTeam: "Целе",
    homeLogo: "https://leon.ru/blog/uploads/logotypes/soccer/egnatia-rogozina__thumb_60x60.png",
    awayLogo: "https://leon.ru/blog/uploads/logotypes/soccer/cele__thumb_60x60.png",
    league: "Лига чемпионов УЕФА",
    kickoff: "22 июля, 22:00",
    odds: { home: "3.51", draw: "3.43", away: "1.98" },
    pick: "Целе не проиграет",
    lead: "Гости идут фаворитами по линии, но домашний матч Эгнатии добавляет сценарию осторожности.",
    homeForm: "Эгнатиа будет делать ставку на организованную игру дома и быстрые атаки после отбора.",
    awayForm: "Целе выглядит предпочтительнее по котировкам и постарается контролировать ход встречи.",
    factors: ["статус гостей как фаворита по линии", "домашнее поле Эгнатии", "осторожный характер первого матча"],
  },
  {
    slug: "22-07-2026-vardar-riga",
    homeTeam: "Вардар",
    awayTeam: "Рига",
    homeLogo: "https://leon.ru/blog/uploads/logotypes/soccer/vardar__thumb_60x60.png",
    awayLogo: "https://leon.ru/blog/uploads/logotypes/soccer/riga__thumb_60x60.png",
    league: "Лига конференций УЕФА",
    kickoff: "22 июля, 21:00",
    odds: { home: "3.30", draw: "3.42", away: "2.07" },
    pick: "Рига не проиграет",
    lead: "Рига имеет небольшое преимущество в линии, однако разрыв между командами не выглядит большим.",
    homeForm: "Вардар на своём поле постарается сыграть компактно и не дать сопернику свободно развивать атаки.",
    awayForm: "Риге важно подтвердить статус фаворита контролем мяча и аккуратной игрой без лишнего риска.",
    factors: ["умеренное преимущество гостей в коэффициентах", "фактор домашнего поля", "вероятность равного начала матча"],
  },
  {
    slug: "22-07-2026-levski-sofiia-kraiova",
    homeTeam: "Левски София",
    awayTeam: "Крайова",
    homeLogo: "https://leon.ru/blog/uploads/logotypes/soccer/levski-sofiia__thumb_60x60.png",
    awayLogo: "https://leon.ru/blog/uploads/logotypes/soccer/kraiova__thumb_60x60.png",
    league: "Лига чемпионов УЕФА",
    kickoff: "22 июля, 20:30",
    odds: { home: "2.11", draw: "3.12", away: "3.49" },
    pick: "Левски София с форой 0",
    lead: "Домашняя команда получила небольшое преимущество в линии — матч обещает быть конкурентным.",
    homeForm: "Левски может использовать поддержку трибун и активнее начать встречу.",
    awayForm: "Крайова наверняка сделает ставку на дисциплину без мяча и свои шансы в быстрых атаках.",
    factors: ["близкие коэффициенты на исход", "небольшой перевес хозяев", "важность первого шага в противостоянии"],
  },
  {
    slug: "22-07-2026-omoniia-nikosiia-kairat",
    homeTeam: "Омония Никосия",
    awayTeam: "Кайрат",
    homeLogo: "https://leon.ru/blog/uploads/logotypes/soccer/omoniia-nikosiia__thumb_60x60.png",
    awayLogo: "https://leon.ru/blog/uploads/logotypes/soccer/kairat__thumb_60x60.png",
    league: "Лига чемпионов УЕФА",
    kickoff: "22 июля, 20:00",
    odds: { home: "1.63", draw: "3.75", away: "5.00" },
    pick: "Победа Омонии Никосии",
    lead: "Омония заметно выше в линии и получает преимущество домашнего поля.",
    homeForm: "Хозяева могут спокойно вести матч первым номером и искать моменты через позиционные атаки.",
    awayForm: "Кайрату важно сохранять плотность в обороне и использовать редкие быстрые выпады.",
    factors: ["явное преимущество хозяев в коэффициентах", "матч на своём поле", "разный статус команд перед игрой"],
  },
  {
    slug: "22-07-2026-neftci-dinamo-minsk",
    homeTeam: "Нефтчи",
    awayTeam: "Динамо Минск",
    homeLogo: "https://leon.ru/blog/uploads/logotypes/soccer/neftci__thumb_60x60.png",
    awayLogo: "https://leon.ru/blog/uploads/logotypes/soccer/dinamo-minsk__thumb_60x60.png",
    league: "Лига конференций УЕФА",
    kickoff: "22 июля, 19:00",
    odds: { home: "1.99", draw: "3.22", away: "3.75" },
    pick: "Нефтчи не проиграет",
    lead: "Нефтчи — небольшой фаворит, но коэффициенты оставляют Динамо реальные шансы на борьбу.",
    homeForm: "Нефтчи постарается использовать преимущество своего поля и не раскрывать игру раньше времени.",
    awayForm: "Динамо Минск может рассчитывать на организованную оборону и контратаки.",
    factors: ["небольшой перевес хозяев в линии", "равный по ожиданиям сценарий", "ценность первого результата в паре"],
  },
];

export function getForecast(slug: string) {
  return fallbackForecasts.find((forecast) => forecast.slug === slug);
}

type ForecastApiItem = {
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
};

export async function getTodayForecasts(): Promise<MatchForecast[]> {
  const baseUrl = process.env.EZBET_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || (process.env.NODE_ENV === "development" ? "http://localhost:8000" : undefined);
  if (!baseUrl) return fallbackForecasts;

  try {
    const response = await fetch(new URL("/api/v1/forecasts", baseUrl).toString(), { cache: "no-store" });
    if (!response.ok) return fallbackForecasts;
    const payload = (await response.json()) as { items: ForecastApiItem[] };
    return payload.items.length ? payload.items.map(toDisplayForecast) : fallbackForecasts;
  } catch {
    return fallbackForecasts;
  }
}

export async function getLiveForecast(slug: string): Promise<MatchForecast | undefined> {
  const forecasts = await getTodayForecasts();
  return forecasts.find((forecast) => forecast.slug === slug);
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
