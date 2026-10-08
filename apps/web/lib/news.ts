import { resolveApiBaseUrl } from "./api";
import { PublicApiError, publicDataCache } from "./public-data-cache";

export type NewsItem = {
  id: string;
  title: string;
  description: string;
  category: string;
  publishedAt: string;
  updatedAt?: string;
  source: string;
  link?: string;
  visibility?: string;
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
  updatedAt?: string;
  aiReviewed: boolean;
};

export type NewsFeed = {
  items: NewsItem[];
  total?: number;
  page?: number;
  isLive: boolean;
  apiBaseUrl?: string;
  cacheStatus: "api" | "cache" | "stale" | "unavailable";
};

export type NewsOptions = { aiOnly?: boolean; fallbackToAll?: boolean; guideOnly?: boolean; limit?: number; page?: number };

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") throw new PublicApiError("Invalid public API payload.");
  return value as Record<string, unknown>;
}

function validNews(value: unknown): NewsItem {
  const item = record(value);
  for (const key of ["id", "title", "description", "category", "source", "publishedAt"]) {
    if (typeof item[key] !== "string") throw new PublicApiError("Invalid news item.");
  }
  if (!Number.isFinite(Date.parse(item.publishedAt as string))) throw new PublicApiError("Invalid publication date.");
  if (item.visibility === "hidden") throw new PublicApiError("Hidden news cannot enter the public cache.");
  return item as NewsItem;
}

function newsPayload(value: unknown): { items: NewsItem[]; total?: number; page?: number } {
  const payload = record(value);
  if (!Array.isArray(payload.items)) throw new PublicApiError("Invalid news feed.");
  return { items: payload.items.map(validNews), total: typeof payload.total === "number" ? payload.total : undefined,
    page: typeof payload.page === "number" ? payload.page : undefined };
}

function articlePayload(value: unknown): { item: Article } {
  const item = record(record(value).item);
  for (const key of ["id", "slug", "newsItemId", "title", "dek", "body", "category", "sourceTitle", "publishedAt"]) {
    if (typeof item[key] !== "string") throw new PublicApiError("Invalid article.");
  }
  if (!Array.isArray(item.tags) || !item.tags.every((tag) => typeof tag === "string") ||
      !Number.isFinite(Date.parse(item.publishedAt as string))) throw new PublicApiError("Invalid article metadata.");
  return { item: item as Article };
}

export async function getNews(query?: string, options?: NewsOptions): Promise<NewsFeed> {
  const baseUrl = resolveApiBaseUrl();
  if (!baseUrl) return { items: [], isLive: false, cacheStatus: "unavailable" };
  const url = new URL("/api/v1/news", baseUrl);
  url.searchParams.set("limit", String(options?.limit ?? 100));
  url.searchParams.set("page", String(options?.page ?? 1));
  if (query) url.searchParams.set("query", query);
  if (options?.aiOnly) url.searchParams.set("aiOnly", "true");
  if (options?.guideOnly) url.searchParams.set("guideOnly", "true");
  try {
    const result = await publicDataCache.get(url.toString(), newsPayload, { freshMs: 60_000, staleMs: 15 * 60_000 });
    const items = filterNews(result.data.items, query, options);
    if (options?.aiOnly && options.fallbackToAll && !items.length) {
      return getNews(query, { ...options, aiOnly: false, fallbackToAll: false });
    }
    return { ...result.data, items, isLive: result.source !== "stale", cacheStatus: result.source, apiBaseUrl: baseUrl };
  } catch {
    return { items: [], isLive: false, cacheStatus: "unavailable" };
  }
}

export async function getArticle(slug: string): Promise<{ item?: Article; isLive: boolean }> {
  const baseUrl = resolveApiBaseUrl();
  if (!baseUrl) throw new PublicApiError("Public API is not configured.");
  try {
    const result = await publicDataCache.get(new URL(`/api/v1/articles/${encodeURIComponent(slug)}`, baseUrl).toString(),
      articlePayload, { freshMs: 60_000, staleMs: 60 * 60_000 });
    return { item: result.data.item, isLive: result.source !== "stale" };
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) return { isLive: true };
    throw error;
  }
}

function filterNews(items: NewsItem[], query?: string, options?: NewsOptions) {
  let filtered = items;
  if (options?.guideOnly) filtered = filtered.filter((item) => item.id.startsWith("guide:") && item.articleSlug);
  else filtered = filtered.filter((item) => !item.id.startsWith("guide:") && item.articleSlug);
  if (options?.aiOnly) filtered = filtered.filter((item) => item.aiReviewed && item.articleSlug);
  if (!query) return filtered;
  const normalized = query.trim().toLowerCase();
  return filtered.filter((item) => [item.title, item.description, item.category, item.source].join(" ").toLowerCase().includes(normalized));
}
