import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { getArticleAuthor } from "@/lib/authors";
import { formatCategoryLabel } from "@/lib/category";
import { formatMoscowDate, formatMoscowDateTime } from "@/lib/dates";
import { getArticle, getNews } from "@/lib/news";
import { absoluteUrl, SITE_NAME, truncateMeta } from "@/lib/site";

function isGuideArticle(newsItemId: string) {
  return newsItemId.startsWith("guide:");
}

function formatArticleDate(date: string, guideArticle: boolean) {
  return guideArticle ? formatMoscowDate(date, "long") : formatMoscowDateTime(date);
}

export async function generateMetadata({
  params
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const { item } = await getArticle(slug);

  if (!item) {
    return {
      title: "Материал не найден",
      robots: {
        index: false,
        follow: false
      }
    };
  }

  const description = truncateMeta(item.dek || item.lead || item.body);
  const canonical = `/news/${item.slug}`;
  const guideArticle = isGuideArticle(item.newsItemId);
  const articleAuthor = guideArticle ? getArticleAuthor(item.category) : undefined;

  return {
    title: item.title,
    description,
    alternates: {
      canonical
    },
    keywords: [
      formatCategoryLabel(item.category),
      item.sourceTitle,
      ...item.tags.filter((tag) => !tag.toLowerCase().includes("ai"))
    ],
    openGraph: {
      type: "article",
      title: item.title,
      description,
      url: canonical,
      siteName: SITE_NAME,
      publishedTime: item.publishedAt,
      ...(articleAuthor ? { authors: [articleAuthor] } : {}),
      tags: item.tags.filter((tag) => !tag.toLowerCase().includes("ai"))
    },
    twitter: {
      card: "summary_large_image",
      title: item.title,
      description
    }
  };
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
  const articleUrl = absoluteUrl(`/news/${item.slug}`);
  const guideArticle = isGuideArticle(item.newsItemId);
  const articleAuthor = guideArticle ? getArticleAuthor(item.category) : undefined;
  const displayDate = formatArticleDate(item.publishedAt, guideArticle);
  const articleJsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "NewsArticle",
        headline: item.title,
        description: truncateMeta(item.dek || item.lead || item.body),
        articleBody: item.body,
        datePublished: item.publishedAt,
        dateModified: item.publishedAt,
        mainEntityOfPage: articleUrl,
        url: articleUrl,
        inLanguage: "ru-RU",
        articleSection: formatCategoryLabel(item.category),
        keywords: publicTags.join(", "),
        ...(articleAuthor
          ? {
              author: {
                "@type": "Person",
                name: articleAuthor,
                url: absoluteUrl("/")
              }
            }
          : {}),
        publisher: {
          "@type": "Organization",
          name: SITE_NAME,
          url: absoluteUrl("/")
        },
        isBasedOn: item.sourceUrl
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          {
            "@type": "ListItem",
            position: 1,
            name: "Главная",
            item: absoluteUrl("/")
          },
          {
            "@type": "ListItem",
            position: 2,
            name: "Новости",
            item: absoluteUrl("/news")
          },
          {
            "@type": "ListItem",
            position: 3,
            name: item.title,
            item: articleUrl
          }
        ]
      }
    ]
  };

  return (
    <main className="article-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(articleJsonLd)
        }}
      />
      <section className="article-header container-wide">
        <Link className="article-back-link" href="/news">
          Назад к ленте
        </Link>
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
                <dt>Рубрика</dt>
                <dd>{formatCategoryLabel(item.category)}</dd>
              </div>
              <div>
                <dt>Опубликовано</dt>
                <dd>{displayDate}</dd>
              </div>
              {articleAuthor ? (
                <div>
                  <dt>Автор</dt>
                  <dd>{articleAuthor}</dd>
                </div>
              ) : null}
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
