import Link from "next/link";
import type { Metadata } from "next";
import type { Route } from "next";
import { NewsCard } from "@/components/news-card";
import { SearchForm } from "@/components/search-form";
import { getNews } from "@/lib/news";
import { absoluteUrl, SITE_DESCRIPTION, SITE_NAME, SITE_OG_IMAGE, truncateMeta } from "@/lib/site";

const NEWS_PER_PAGE = 20;

function buildNewsPageHref(page: number, query: string, type: string) {
  const params = new URLSearchParams();
  if (query) {
    params.set("query", query);
  }
  if (type) {
    params.set("type", type);
  }
  if (page > 1) {
    params.set("page", String(page));
  }
  const search = params.toString();
  return search ? `/news?${search}` : "/news";
}

export async function generateMetadata({
  searchParams
}: {
  searchParams?: Promise<{ query?: string; page?: string; type?: string }>;
}): Promise<Metadata> {
  const params = (await searchParams) ?? {};
  const query = params.query?.trim() ?? "";
  const isGuides = params.type === "guides";
  const page = params.page ? Number(params.page) : 1;
  const title = isGuides ? "Полезные статьи" : query ? `Новости по запросу «${query}»` : "Лента спортивных новостей";
  const description = query
    ? truncateMeta(`Свежие спортивные новости ezbet.ru по запросу «${query}»: главные события, лента публикаций и материалы редакции.`)
    : isGuides
      ? "Полезные статьи ezbet.ru о спорте, киберспорте, автоспорте, здоровье, технологиях и деньгах в индустрии."
      : SITE_DESCRIPTION;

  return {
    title,
    description,
    alternates: {
      canonical: buildNewsPageHref(page, query, isGuides ? "guides" : "")
    },
    robots: query
      ? {
          index: false,
          follow: true
        }
      : undefined,
    openGraph: {
      title: `${title} | ${SITE_NAME}`,
      description,
      url: "/news",
      images: [
        {
          url: SITE_OG_IMAGE,
          width: 1200,
          height: 630,
          alt: `${title} | ${SITE_NAME}`
        }
      ]
    },
    twitter: {
      title: `${title} | ${SITE_NAME}`,
      description,
      images: [SITE_OG_IMAGE]
    }
  };
}

export default async function NewsPage({
  searchParams
}: {
  searchParams?: Promise<{ query?: string; page?: string; type?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const query = params.query ?? "";
  const type = params.type === "guides" ? "guides" : "";
  const isGuides = type === "guides";
  const requestedPage = Number(params.page ?? "1");
  const safeRequestedPage = Number.isFinite(requestedPage) && requestedPage > 0 ? Math.floor(requestedPage) : 1;
  const { items, isLive } = await getNews(query, isGuides ? { guideOnly: true } : undefined);
  const totalPages = Math.max(1, Math.ceil(items.length / NEWS_PER_PAGE));
  const currentPage = Math.min(safeRequestedPage, totalPages);
  const startIndex = (currentPage - 1) * NEWS_PER_PAGE;
  const pagedItems = items.slice(startIndex, startIndex + NEWS_PER_PAGE);
  const fromItem = items.length ? startIndex + 1 : 0;
  const toItem = Math.min(startIndex + NEWS_PER_PAGE, items.length);
  const popularItems = items.slice(0, 5);
  const collectionJsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: isGuides ? "Полезные статьи" : query ? `Новости по запросу ${query}` : "Лента спортивных новостей",
    url: absoluteUrl(buildNewsPageHref(currentPage, query, type)),
    description: query
      ? `Свежие спортивные новости по запросу ${query}.`
      : isGuides
        ? "Полезные статьи ezbet.ru о спорте, киберспорте, автоспорте, здоровье, деньгах и технологиях."
        : SITE_DESCRIPTION,
    inLanguage: "ru-RU",
    isPartOf: {
      "@type": "WebSite",
      name: SITE_NAME,
      url: absoluteUrl("/")
    },
    mainEntity: {
      "@type": "ItemList",
      itemListElement: pagedItems.map((item, index) => ({
        "@type": "ListItem",
        position: startIndex + index + 1,
        url: item.articleSlug ? absoluteUrl(`/news/${item.articleSlug}`) : item.link,
        name: item.title
      }))
    }
  };

  return (
    <main className="news-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(collectionJsonLd)
        }}
      />
      <section className="news-page-hero container-wide">
        <div className="news-kicker">{isLive ? "Живая лента" : "Резервная лента"}</div>
        <h1>{isGuides ? "Полезные статьи" : "Лента новостей"}</h1>
        <p>
          {isGuides
            ? "Большие материалы о спорте, киберспорте, автоспорте, здоровье, деньгах и технологиях."
            : isLive
            ? "Свежие публикации с поиском по темам, командам, турнирам и источникам."
            : "API временно недоступен, поэтому здесь показаны резервные публикации."}
        </p>
        <SearchForm initialQuery={query} type={type} />
      </section>

      <div className="content-layout container-wide">
        <section className="news-feed" aria-label="Все новости">
          <div className="section-header">
            <h2 className="section-title">
              {isGuides ? "Все полезные статьи" : query ? `Результаты: ${query}` : "Все новости"}
            </h2>
            <span className="section-count">
              {items.length ? `${fromItem}-${toItem} из ${items.length}` : "Ничего не найдено"}
            </span>
          </div>
          <div className="news-list">
            {pagedItems.length ? (
              pagedItems.map((item) => <NewsCard key={item.id} item={item} />)
            ) : (
              <article className="news-item">
                <div className="ni-meta">
                  <span className="ni-time">Поиск</span>
                  <span className="cat-pill cat-pill--football">ezbet</span>
                </div>
                <h3 className="ni-title">По этому запросу пока ничего не найдено</h3>
                <p className="ni-desc">Попробуйте изменить формулировку или открыть всю ленту без фильтра.</p>
              </article>
            )}
          </div>

          {totalPages > 1 ? (
            <nav className="pagination-row" aria-label="Навигация по страницам">
              {currentPage > 1 ? (
                <a className="button-secondary" href={buildNewsPageHref(currentPage - 1, query, type)}>
                  Назад
                </a>
              ) : (
                <span className="button-secondary is-disabled" aria-disabled="true">
                  Назад
                </span>
              )}
              <span className="pagination-label">
                Страница {currentPage} из {totalPages}
              </span>
              {currentPage < totalPages ? (
                <a className="button-secondary" href={buildNewsPageHref(currentPage + 1, query, type)}>
                  Вперед
                </a>
              ) : (
                <span className="button-secondary is-disabled" aria-disabled="true">
                  Вперед
                </span>
              )}
            </nav>
          ) : null}
        </section>

        <aside className="sidebar">
          <div className="sidebar-block">
            <h3 className="sidebar-block-title">Быстрый поиск</h3>
            <div className="topic-cloud">
              {["Футбол", "Хоккей", "Баскетбол", "Теннис", "Беттинг", "Киберспорт"].map((topic) => (
                <Link key={topic} href={buildNewsPageHref(1, topic, type) as Route} className="topic-chip">
                  {topic}
                </Link>
              ))}
            </div>
          </div>

          <div className="sidebar-block">
            <h3 className="sidebar-block-title">В фокусе</h3>
            <ol className="popular-list" role="list">
              {popularItems.map((item, index) => (
                <li className="popular-item" key={item.id}>
                  <span className="popular-num">{index + 1}</span>
                  <a className="popular-link" href={item.articleSlug ? `/news/${item.articleSlug}` : item.link ?? "/news"}>
                    {item.title}
                  </a>
                </li>
              ))}
            </ol>
          </div>

        </aside>
      </div>
    </main>
  );
}
