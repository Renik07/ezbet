import Link from "next/link";
import { notFound } from "next/navigation";

import { getArticle } from "@/lib/news";

export default async function ArticlePage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { item, isLive } = await getArticle(slug);

  if (!item) {
    notFound();
  }

  return (
    <main className="page-shell">
      <section className="hero article-hero">
        <div className="eyebrow">
          <span>{item.category}</span>
          {item.aiReviewed ? <span>AI edited</span> : null}
        </div>
        <h1 style={{ fontSize: "clamp(2.2rem, 5vw, 4rem)" }}>{item.title}</h1>
        <p>{item.dek}</p>
        <div className="hero-actions">
          <Link className="button-secondary" href="/news">
            Назад к ленте
          </Link>
          {item.sourceUrl ? (
            <a className="button-secondary" href={item.sourceUrl} target="_blank" rel="noreferrer">
              Первоисточник
            </a>
          ) : null}
        </div>
      </section>

      <section>
        <div className="article-meta">
          <span>{item.sourceTitle}</span>
          <time dateTime={item.publishedAt}>
            {new Date(item.publishedAt).toLocaleString("ru-RU", {
              dateStyle: "medium",
              timeStyle: "short"
            })}
          </time>
        </div>
        {item.tags.length ? (
          <div className="article-tags">
            {item.tags.map((tag) => (
              <span key={`${item.id}-${tag}`}>{tag}</span>
            ))}
          </div>
        ) : null}
        {item.lead ? <p className="article-lead">{item.lead}</p> : null}
        <article className="section-card article-body">
          {item.body.split("\n\n").map((paragraph, index) => (
            <p key={`${item.id}-${index}`}>{paragraph}</p>
          ))}
        </article>
      </section>

      <p className="footer-note">
        {isLive
          ? "Материал загружен из живого publication API и уже хранится как полноценная статья."
          : "Показан fallback-материал для локальной разработки, потому что API статьи сейчас недоступен."}
      </p>
    </main>
  );
}
