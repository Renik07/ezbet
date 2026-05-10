import { resolveApiBaseUrl } from "@/lib/api";

export type NewsItem = {
  id: string;
  title: string;
  description: string;
  category: string;
  publishedAt: string;
  source: string;
  link?: string;
  aiReviewed?: boolean;
  articleSlug?: string;
};

export type Article = {
  id: string;
  slug: string;
  newsItemId: string;
  rawItemId: string;
  title: string;
  lead?: string;
  dek: string;
  body: string;
  category: string;
  sourceTitle: string;
  sourceUrl?: string;
  tags: string[];
  publishedAt: string;
  aiReviewed: boolean;
};

export type NewsFeed = {
  items: NewsItem[];
  isLive: boolean;
  apiBaseUrl?: string;
};

const fallbackNews: NewsItem[] = [
  {
    id: "1",
    title: "Клубы РПЛ меняют подготовку к летнему окну, букмекеры пересчитывают линию",
    description:
      "Черновой материал показывает, как MVP будет выглядеть с автоматически собранными новостями и AI-редактурой перед публикацией.",
    category: "Беттинг",
    publishedAt: "2026-04-29T09:15:00.000Z",
    source: "ezbet ingest",
    aiReviewed: true,
    articleSlug: "fallback-rpl-window-1"
  },
  {
    id: "2",
    title: "Турнирная гонка в НБА сдвинула приоритеты редакции на вечерний слот",
    description:
      "Новость попадает в ленту, проходит базовую проверку и затем может быть усилена AI-редактором.",
    category: "Баскетбол",
    publishedAt: "2026-04-29T08:20:00.000Z",
    source: "demo source",
    aiReviewed: false,
    link: "https://example.com/fallback-nba"
  },
  {
    id: "3",
    title: "Лига чемпионов вернула спрос на краткие объясняющие материалы под поисковый трафик",
    description:
      "Главная страница может смешивать свежие новости, служебные KPI и коммерческие точки роста без перегруза интерфейса.",
    category: "Футбол",
    publishedAt: "2026-04-29T07:45:00.000Z",
    source: "demo source",
    aiReviewed: false,
    link: "https://example.com/fallback-ucl"
  }
];

const fallbackArticles: Article[] = [
  {
    id: "article:fallback:1",
    slug: "fallback-rpl-window-1",
    newsItemId: "1",
    rawItemId: "raw:fallback:1",
    title: "Клубы РПЛ меняют подготовку к летнему окну, букмекеры пересчитывают линию",
    lead: "Тестовая article page для MVP показывает, как enrichment и AI-редактура превращаются в полноценный материал для чтения.",
    dek: "Тестовая article page для MVP показывает, как AI-редактура превращается в полноценный материал для чтения.",
    body:
      "На текущем этапе ezbet уже собирает сигналы из внешних источников и превращает их в публикационный поток.\n\nСледующий слой после ленты — полноценная статья, где у пользователя есть не только короткий dek, но и связный body для чтения.\n\nИменно этот формат станет базой для SEO, внутренних переходов и дальнейшей монетизации через редакционные и коммерческие блоки.",
    category: "Беттинг",
    sourceTitle: "ezbet ingest",
    sourceUrl: "https://example.com/fallback-rpl",
    tags: ["РПЛ", "Беттинг", "AI news"],
    publishedAt: "2026-04-29T09:15:00.000Z",
    aiReviewed: true
  }
];

export async function getNews(query?: string, options?: { aiOnly?: boolean }): Promise<NewsFeed> {
  const baseUrl = resolveApiBaseUrl();

  if (!baseUrl) {
    return {
      items: filterNews(fallbackNews, query, options),
      isLive: false
    };
  }

  try {
    const url = new URL("/api/v1/news", baseUrl);
    if (query) {
      url.searchParams.set("query", query);
    }
    if (options?.aiOnly) {
      url.searchParams.set("aiOnly", "true");
    }

    const response = await fetch(url.toString(), {
      next: { revalidate: 30 }
    });

    if (!response.ok) {
      return {
        items: filterNews(fallbackNews, query, options),
        isLive: false
      };
    }

    const payload = (await response.json()) as { items: NewsItem[] };
    return {
      items: filterNews(payload.items, query, options),
      isLive: true,
      apiBaseUrl: baseUrl
    };
  } catch {
    return {
      items: filterNews(fallbackNews, query, options),
      isLive: false
    };
  }
}

export async function getArticle(slug: string): Promise<{ item?: Article; isLive: boolean }> {
  const baseUrl = resolveApiBaseUrl();

  if (!baseUrl) {
    return {
      item: fallbackArticles.find((article) => article.slug === slug),
      isLive: false
    };
  }

  try {
    const response = await fetch(new URL(`/api/v1/articles/${slug}`, baseUrl).toString(), {
      next: { revalidate: 30 }
    });

    if (!response.ok) {
      return {
        item: fallbackArticles.find((article) => article.slug === slug),
        isLive: false
      };
    }

    const payload = (await response.json()) as { item: Article };
    return {
      item: payload.item,
      isLive: true
    };
  } catch {
    return {
      item: fallbackArticles.find((article) => article.slug === slug),
      isLive: false
    };
  }
}

function filterNews(items: NewsItem[], query?: string, options?: { aiOnly?: boolean }) {
  let filtered = items;

  if (options?.aiOnly) {
    filtered = filtered.filter((item) => item.aiReviewed && item.articleSlug);
  }

  if (!query) {
    return filtered;
  }

  const normalized = query.trim().toLowerCase();
  return filtered.filter((item) => {
    return [item.title, item.description, item.category, item.source]
      .join(" ")
      .toLowerCase()
      .includes(normalized);
  });
}
