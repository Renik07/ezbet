import type { MetadataRoute } from "next";

import { getNews } from "@/lib/news";
import { absoluteUrl } from "@/lib/site";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const [{ items: newsItems }, { items: guideItems }] = await Promise.all([
    getNews(undefined, { aiOnly: true }),
    getNews(undefined, { guideOnly: true })
  ]);
  const articleUrls = [...newsItems, ...guideItems]
    .filter((item) => item.articleSlug)
    .map((item) => ({
      url: absoluteUrl(`/news/${item.articleSlug}`),
      lastModified: new Date(item.publishedAt),
      changeFrequency: "daily" as const,
      priority: 0.8
    }));

  return [
    {
      url: absoluteUrl("/"),
      lastModified: now,
      changeFrequency: "hourly",
      priority: 1
    },
    {
      url: absoluteUrl("/news"),
      lastModified: now,
      changeFrequency: "hourly",
      priority: 0.9
    },
    ...articleUrls
  ];
}
