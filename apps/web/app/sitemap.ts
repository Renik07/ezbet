import type { MetadataRoute } from "next";

import { getNews, type NewsItem } from "@/lib/news";
import { absoluteUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

async function sitemapItems(guideOnly = false): Promise<NewsItem[]> {
  const first = await getNews(undefined, { aiOnly: !guideOnly, guideOnly, limit: 100, page: 1 });
  const items = [...first.items];
  const pages = Math.min(500, Math.ceil((first.total ?? items.length) / 100));
  // Bound API concurrency while avoiding a network round trip for every page in series.
  for (let page = 2; page <= pages; page += 4) {
    const batch = await Promise.all(Array.from({ length: Math.min(4, pages - page + 1) }, (_, offset) =>
      getNews(undefined, { aiOnly: !guideOnly, guideOnly, limit: 100, page: page + offset })
    ));
    for (let offset = 0; offset < batch.length; offset++) {
      if (batch[offset].page !== page + offset) return items;
      items.push(...batch[offset].items);
    }
  }
  return items;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [newsItems, guideItems] = await Promise.all([
    sitemapItems(),
    sitemapItems(true)
  ]);
  const modifiedDates = [...newsItems, ...guideItems].map((item) => Date.parse(item.updatedAt ?? item.publishedAt)).filter(Number.isFinite);
  const lastModified = modifiedDates.length ? new Date(Math.max(...modifiedDates)) : undefined;
  const articleUrls = Array.from(new Map([...newsItems, ...guideItems].map((item) => [item.articleSlug, item])).values())
    .filter((item) => item.articleSlug)
    .map((item) => ({
      url: absoluteUrl(`/news/${item.articleSlug}`),
      lastModified: new Date(item.updatedAt ?? item.publishedAt),
      changeFrequency: "daily" as const,
      priority: 0.8
    }));

  return [
    {
      url: absoluteUrl("/"),
      lastModified,
      changeFrequency: "hourly",
      priority: 1
    },
    {
      url: absoluteUrl("/news"),
      lastModified,
      changeFrequency: "hourly",
      priority: 0.9
    },
    ...articleUrls
  ];
}
