import { resolveApiBaseUrl } from "@/lib/api";
import { absoluteUrl, SITE_DESCRIPTION, SITE_NAME } from "@/lib/site";

export const dynamic = "force-dynamic";

type NewsFeedItem = {
  id: string;
  title: string;
  description: string;
  category: string;
  publishedAt: string;
  articleSlug?: string;
};

type ForecastFeedItem = {
  slug: string;
  homeTeam: string;
  awayTeam: string;
  lead?: string;
  updatedAt: string;
  generationStatus?: string;
};

type FeedItem = {
  id: string;
  title: string;
  description: string;
  category: string;
  publishedAt: string;
  url: string;
};

function escapeXml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

async function fetchNewsFeedItems(apiBaseUrl: string): Promise<FeedItem[]> {
  const url = new URL("/api/v1/news", apiBaseUrl);
  url.searchParams.set("limit", "100");

  const response = await fetch(url.toString(), { cache: "no-store" });
  if (!response.ok) return [];

  const payload = (await response.json()) as { items?: NewsFeedItem[] };
  return (payload.items ?? [])
    .filter((item) => item.articleSlug)
    .map((item) => ({
      id: item.id,
      title: item.title,
      description: item.description,
      category: item.category,
      publishedAt: item.publishedAt,
      url: absoluteUrl(`/news/${item.articleSlug}`)
    }));
}

async function fetchForecastFeedItems(apiBaseUrl: string): Promise<FeedItem[]> {
  const response = await fetch(new URL("/api/v1/forecasts", apiBaseUrl).toString(), {
    cache: "no-store"
  });
  if (!response.ok) return [];

  const payload = (await response.json()) as { items?: ForecastFeedItem[] };
  return (payload.items ?? [])
    .filter((item) => !item.generationStatus || item.generationStatus === "ready")
    .map((item) => ({
      id: `forecast:${item.slug}`,
      title: `${item.homeTeam} — ${item.awayTeam}: прогноз на матч`,
      description: item.lead || `Прогноз на матч ${item.homeTeam} — ${item.awayTeam}.`,
      category: "Прогнозы",
      publishedAt: item.updatedAt,
      url: absoluteUrl(`/match/${item.slug}`)
    }));
}

async function fetchFeedItems(): Promise<FeedItem[]> {
  const apiBaseUrl = resolveApiBaseUrl();

  if (!apiBaseUrl) {
    return [];
  }

  const results = await Promise.allSettled([
    fetchNewsFeedItems(apiBaseUrl),
    fetchForecastFeedItems(apiBaseUrl)
  ]);

  return results
    .flatMap((result) => (result.status === "fulfilled" ? result.value : []))
    .filter((item) => !Number.isNaN(Date.parse(item.publishedAt)))
    .sort((left, right) => Date.parse(right.publishedAt) - Date.parse(left.publishedAt))
    .slice(0, 100);
}

export async function GET() {
  const items = await fetchFeedItems();
  const buildDate = new Date().toUTCString();
  const lastBuildDate =
    items.length > 0 ? new Date(items[0].publishedAt).toUTCString() : buildDate;

  const itemXml = items
    .map((item) => {
      const pubDate = new Date(item.publishedAt).toUTCString();

      return `
    <item>
      <title>${escapeXml(item.title)}</title>
      <link>${escapeXml(item.url)}</link>
      <guid isPermaLink="true">${escapeXml(item.url)}</guid>
      <description>${escapeXml(item.description)}</description>
      <category>${escapeXml(item.category)}</category>
      <pubDate>${pubDate}</pubDate>
    </item>`;
    })
    .join("");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>${escapeXml(SITE_NAME)}</title>
    <link>${escapeXml(absoluteUrl("/"))}</link>
    <description>${escapeXml(SITE_DESCRIPTION)}</description>
    <language>ru</language>
    <lastBuildDate>${lastBuildDate}</lastBuildDate>
    <ttl>15</ttl>${itemXml}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600"
    }
  });
}
