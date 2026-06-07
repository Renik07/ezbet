import Link from "next/link";
import type { Route } from "next";

import { formatCategoryLabel } from "@/lib/category";
import type { NewsItem } from "@/lib/news";

type NewsCardProps = {
  item: NewsItem;
};

function categoryTone(category?: string) {
  const normalized = category?.toLowerCase();
  if (normalized === "football" || normalized === "футбол") return "football";
  if (normalized === "hockey" || normalized === "хоккей") return "hockey";
  if (normalized === "basketball" || normalized === "баскетбол") return "basketball";
  if (normalized === "tennis" || normalized === "теннис") return "tennis";
  if (normalized === "mma" || normalized === "мма" || normalized === "boxing" || normalized === "бокс") return "mma";
  if (normalized === "esports" || normalized === "киберспорт") return "cyber";
  return "football";
}

export function NewsCard({ item }: NewsCardProps) {
  const label = formatCategoryLabel(item.category);
  const href = item.articleSlug ? (`/news/${item.articleSlug}` as Route) : item.link;
  const publishedAt = new Date(item.publishedAt).toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short"
  });

  const content = (
    <article className="news-item">
      <div className="ni-meta">
        <time className="ni-time" dateTime={item.publishedAt}>
          {publishedAt}
        </time>
        <span className={`cat-pill cat-pill--${categoryTone(item.category)}`}>{label}</span>
      </div>
      <h3 className="ni-title">{href ? <span>{item.title}</span> : item.title}</h3>
      <p className="ni-desc">{item.description}</p>
      <span className="ni-source">{item.source}</span>
    </article>
  );

  if (item.articleSlug) {
    return <Link href={href as Route}>{content}</Link>;
  }

  if (item.link) {
    return (
      <a href={item.link} target="_blank" rel="noreferrer">
        {content}
      </a>
    );
  }

  return content;
}
