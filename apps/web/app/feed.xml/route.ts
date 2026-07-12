import { resolveApiBaseUrl } from "@/lib/api";
import { absoluteUrl, SITE_DESCRIPTION, SITE_NAME } from "@/lib/site";

export const dynamic = "force-dynamic";

type FeedItem = {
  id: string;
  title: string;
  description: string;
  category: string;
  publishedAt: string;
  source: string;
  articleSlug?: string;
};

function escapeXml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function cdata(value: string) {
  return `<![CDATA[${value.replaceAll("]]>", "]]]]><![CDATA[>")}]]>`;
}

async function fetchFeedItems() {
  const apiBaseUrl = resolveApiBaseUrl();

  if (!apiBaseUrl) {
    return [];
  }

  const url = new URL("/api/v1/news", apiBaseUrl);
  url.searchParams.set("limit", "100");

  const response = await fetch(url.toString(), {
    cache: "no-store"
  });

  if (!response.ok) {
    return [];
  }

  const payload = (await response.json()) as { items?: FeedItem[] };
  return (payload.items ?? []).filter((item) => item.articleSlug);
}

export async function GET() {
  const items = await fetchFeedItems();
  const buildDate = new Date().toUTCString();
  const lastBuildDate =
    items.length > 0 ? new Date(items[0].publishedAt).toUTCString() : buildDate;

  const itemXml = items
    .map((item) => {
      const itemUrl = absoluteUrl(`/news/${item.articleSlug}`);
      const pubDate = new Date(item.publishedAt).toUTCString();
      const guid = item.id || itemUrl;

      return `
    <item>
      <title>${cdata(item.title)}</title>
      <link>${escapeXml(itemUrl)}</link>
      <guid isPermaLink="false">${escapeXml(guid)}</guid>
      <description>${cdata(item.description)}</description>
      <category>${cdata(item.category)}</category>
      <source url="${escapeXml(absoluteUrl("/"))}">${cdata(item.source || SITE_NAME)}</source>
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
