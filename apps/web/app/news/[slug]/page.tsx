import Link from "next/link";
import { notFound } from "next/navigation";

import { formatCategoryLabel } from "@/lib/category";
import { getArticle, getNews } from "@/lib/news";

function formatArticleDate(date: string) {
  return new Date(date).toLocaleString("ru-RU", {
    dateStyle: "long",
    timeStyle: "short"
  });
}

export default async function ArticlePage({
  params
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { item } = await getArticle(slug);

  if (!item) {
    notFound();
  }

  const relatedNews = (await getNews(formatCategoryLabel(item.category), { aiOnly: true })).items
    .filter((newsItem) => newsItem.articleSlug !== item.slug)
    .slice(0, 4);
  const paragraphs = item.body.split("\n\n").filter(Boolean);
  const publicTags = item.tags.filter((tag) => !tag.toLowerCase().includes("ai"));

  return (
    <main className="article-page">
      <section className="article-header container-wide">
        <Link className="article-back-link" href="/news">
          Назад к ленте
        </Link>
        <div className="article-kicker-row">
          <span className="cat-pill cat-pill--football">{formatCategoryLabel(item.category)}</span>
          <time dateTime={item.publishedAt}>{formatArticleDate(item.publishedAt)}</time>
        </div>
        <h1>{item.title}</h1>
        <p>{item.dek}</p>
      </section>

      <div className="article-layout container-wide">
        <article className="article-reading">
          {item.lead ? <p className="article-lead">{item.lead}</p> : null}
          <div className="article-body">
            {paragraphs.map((paragraph, index) => (
              <p key={`${item.id}-${index}`}>{paragraph}</p>
            ))}
          </div>
        </article>

        <aside className="article-aside">
          <div className="sidebar-block article-info-card">
            <h3 className="sidebar-block-title">Коротко</h3>
            <dl className="article-facts">
              <div>
                <dt>Источник</dt>
                <dd>{item.sourceTitle}</dd>
              </div>
              <div>
                <dt>Рубрика</dt>
                <dd>{formatCategoryLabel(item.category)}</dd>
              </div>
              <div>
                <dt>Опубликовано</dt>
                <dd>{formatArticleDate(item.publishedAt)}</dd>
              </div>
            </dl>
          </div>

          {publicTags.length ? (
            <div className="sidebar-block">
              <h3 className="sidebar-block-title">Темы</h3>
              <div className="topic-cloud">
                {publicTags.map((tag) => (
                  <Link key={`${item.id}-${tag}`} href={`/news?query=${encodeURIComponent(tag)}`} className="topic-chip">
                    {tag}
                  </Link>
                ))}
              </div>
            </div>
          ) : null}

          {relatedNews.length ? (
            <div className="sidebar-block">
              <h3 className="sidebar-block-title">Еще по теме</h3>
              <ol className="popular-list" role="list">
                {relatedNews.map((newsItem, index) => (
                  <li className="popular-item" key={newsItem.id}>
                    <span className="popular-num">{index + 1}</span>
                    <a className="popular-link" href={newsItem.articleSlug ? `/news/${newsItem.articleSlug}` : newsItem.link ?? "/news"}>
                      {newsItem.title}
                    </a>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </aside>
      </div>
    </main>
  );
}
