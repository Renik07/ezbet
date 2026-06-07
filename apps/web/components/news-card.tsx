import Link from "next/link";
import { formatCategoryLabel } from "@/lib/category";
import type { NewsItem } from "@/lib/news";

type NewsCardProps = {
  item: NewsItem;
};

export function NewsCard({ item }: NewsCardProps) {
  const content = (
    <article className="news-card">
      <div className="badge-row">
        <span>{formatCategoryLabel(item.category)}</span>
        {item.aiReviewed ? <span className="ai-badge">Проверено AI</span> : null}
      </div>
      <h3>{item.title}</h3>
      <p>{item.description}</p>
      <div className="section-head" style={{ margin: "16px 0 0" }}>
        <time dateTime={item.publishedAt}>
          {new Date(item.publishedAt).toLocaleString("ru-RU", {
            dateStyle: "medium",
            timeStyle: "short"
          })}
        </time>
        <span>{item.source}</span>
      </div>
    </article>
  );

  if (item.articleSlug) {
    return <Link href={`/news/${item.articleSlug}`}>{content}</Link>;
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
