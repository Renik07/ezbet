import { getNews } from "@/lib/news";
import { getForecastApiItems } from "@/lib/forecasts";
import { absoluteUrl, SITE_DESCRIPTION, SITE_NAME } from "@/lib/site";

export const dynamic = "force-dynamic";

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

async function fetchNewsFeedItems(): Promise<FeedItem[]> {
  const feeds = await Promise.all([getNews(undefined, { limit: 100 }), getNews(undefined, { limit: 100, guideOnly: true })]);
  return feeds.flatMap(({ items }) => items).filter((item) => item.articleSlug).map((item) => ({
    id: item.id, title: item.title, description: item.description, category: item.category,
    publishedAt: item.publishedAt, url: absoluteUrl(`/news/${item.articleSlug}`)
  }));
}

async function fetchForecastFeedItems(): Promise<FeedItem[]> {
  return (await getForecastApiItems()).map((item) => ({
    id: `forecast:${item.slug}`, title: `${item.homeTeam} — ${item.awayTeam}: прогноз на матч`,
    description: item.lead || `Прогноз на матч ${item.homeTeam} — ${item.awayTeam}.`, category: "Прогнозы",
    publishedAt: item.updatedAt, url: absoluteUrl(`/match/${item.slug}`)
  }));
}

async function fetchFeedItems(): Promise<FeedItem[]> {
  const results = await Promise.allSettled([fetchNewsFeedItems(), fetchForecastFeedItems()]);
  return results.flatMap((result) => result.status === "fulfilled" ? result.value : [])
    .filter((item) => Number.isFinite(Date.parse(item.publishedAt)))
    .sort((left, right) => Date.parse(right.publishedAt) - Date.parse(left.publishedAt)).slice(0, 100);
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
