import Link from "next/link";
import type { Route } from "next";
import type { Metadata } from "next";
import { NewsCard } from "@/components/news-card";
import { formatCategoryLabel } from "@/lib/category";
import { formatMoscowDate } from "@/lib/dates";
import { getNews } from "@/lib/news";
import { absoluteUrl, SITE_DESCRIPTION, SITE_NAME, SITE_TITLE } from "@/lib/site";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  alternates: {
    canonical: "/"
  },
  openGraph: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: "/"
  },
  twitter: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION
  }
};

function formatRelativeTime(date: string) {
  const diffMs = Date.now() - new Date(date).getTime();
  const diffMinutes = Math.max(1, Math.round(diffMs / 60000));

  if (diffMinutes < 60) {
    return `${diffMinutes} мин`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours} ч`;
  }

  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 8) {
    return `${diffDays} д`;
  }

  return formatMoscowDate(date);
}

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

function newsHref(articleSlug?: string) {
  return articleSlug ? (`/news/${articleSlug}` as Route) : ("/news" as Route);
}

const guideItems: Array<{
  label: string;
  tone: "football" | "hockey" | "tennis" | "cyber";
  title: string;
  description: string;
  readTime: string;
  href: Route;
  featured?: boolean;
}> = [
  {
    label: "Аналитика",
    tone: "football",
    title: "Ценность ставок в российских лигах: где искать нестандартные рынки",
    description:
      "Разбираем, почему букмекеры иногда недооценивают хозяев на кубковых матчах и какие данные полезно держать под рукой перед линией.",
    readTime: "8 мин чтения",
    href: "/news?query=Аналитика",
    featured: true
  },
  {
    label: "Гайд",
    tone: "cyber",
    title: "Ставки на CS2: как читать карту и состав команды",
    description: "Базовые метрики для анализа матчей: карты, форма игроков, роли и стабильность состава.",
    readTime: "5 мин чтения",
    href: "/news?query=Киберспорт"
  },
  {
    label: "Гайд",
    tone: "hockey",
    title: "Ставки на тоталы в хоккее: методология и статистика КХЛ",
    description: "На что смотреть в темпе команд, большинстве, вратарской форме и календарной нагрузке.",
    readTime: "6 мин чтения",
    href: "/news?query=Хоккей"
  },
  {
    label: "Гайд",
    tone: "tennis",
    title: "Теннис на грунте: ключевые показатели для прогнозов",
    description: "Подача, прием, длина розыгрышей и профиль покрытия как быстрый фильтр перед матчем.",
    readTime: "4 мин чтения",
    href: "/news?query=Теннис"
  }
];

export default async function HomePage() {
  const { items: news, isLive } = await getNews(undefined, { aiOnly: true, fallbackToAll: true });
  const guideNews = news.filter((item) => item.id.startsWith("guide:") && item.articleSlug).slice(0, 4);
  const editorialNews = news.filter((item) => !item.id.startsWith("guide:"));
  const heroItem = editorialNews[0];
  const tickerNews = editorialNews.slice(1, 9);
  const featuredNews = editorialNews.slice(1, 9);
  const popularNews = editorialNews.slice(0, 5);
  const homeJsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        name: SITE_NAME,
        url: absoluteUrl("/")
      },
      {
        "@type": "WebSite",
        name: SITE_NAME,
        url: absoluteUrl("/"),
        description: SITE_DESCRIPTION,
        inLanguage: "ru-RU",
        potentialAction: {
          "@type": "SearchAction",
          target: `${absoluteUrl("/news")}?query={search_term_string}`,
          "query-input": "required name=search_term_string"
        }
      }
    ]
  };

  return (
    <main>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(homeJsonLd)
        }}
      />
      <section className="home-hero container-wide">
        {heroItem ? (
          <article className="hero-article">
            <div className="hero-category">
              <span className={`category-dot category-dot--${categoryTone(heroItem.category)}`} />
              <span className="category-label">{formatCategoryLabel(heroItem.category)}</span>
              <span className="hero-time">{formatRelativeTime(heroItem.publishedAt)}</span>
            </div>
            <h1 className="hero-title">{heroItem.title}</h1>
            <p className="hero-desc">{heroItem.description}</p>
            <div className="hero-meta">
              <span className="meta-author">{heroItem.source}</span>
              <Link className="hero-read-btn" href={newsHref(heroItem.articleSlug)}>
                Читать полностью
              </Link>
            </div>
          </article>
        ) : (
          <article className="hero-article">
            <div className="hero-category">
              <span className="category-dot category-dot--football" />
              <span className="category-label">ezbet.ru</span>
              <span className="hero-time">лента обновляется</span>
            </div>
            <h1 className="hero-title">Спортивные новости и беттинг-сигналы в одной ленте</h1>
            <p className="hero-desc">
              Когда API снова отдаст публикации, главная автоматически покажет ведущую новость, live-ленту и свежий выпуск.
            </p>
            <div className="hero-meta">
              <span className="meta-author">Редакция ezbet.ru</span>
              <Link className="hero-read-btn" href="/news">
                Открыть ленту
              </Link>
            </div>
          </article>
        )}

        <aside className="live-ticker">
          <div className="ticker-header">
            <span className={`live-badge${isLive ? "" : " live-badge--muted"}`}>
              <span className="live-dot" />
              {isLive ? "LIVE" : "DEMO"}
            </span>
            <span className="ticker-title">Лента событий</span>
          </div>
          <ul className="ticker-list" role="list">
            {tickerNews.length ? (
              tickerNews.map((item) => (
                <li className="ticker-item" key={item.id}>
                  <span className="ti-time">{formatRelativeTime(item.publishedAt)}</span>
                  <span className={`ti-cat cat--${categoryTone(item.category)}`} />
                  {item.articleSlug ? (
                    <Link className="ti-title" href={newsHref(item.articleSlug)}>
                      {item.title}
                    </Link>
                  ) : (
                    <a className="ti-title" href={item.link ?? "/news"}>
                      {item.title}
                    </a>
                  )}
                </li>
              ))
            ) : (
              <li className="ticker-empty">Свежие события появятся после обновления ленты.</li>
            )}
          </ul>
        </aside>
      </section>

      <div className="content-layout container-wide">
        <section className="news-feed" aria-label="Главные новости">
          <div className="section-header">
            <h2 className="section-title">Главные новости</h2>
            <Link href="/news" className="section-link">
              Все новости
            </Link>
          </div>
          <div className="news-list">
            {featuredNews.length ? (
              featuredNews.map((item) => <NewsCard key={item.id} item={item} />)
            ) : (
              <article className="news-item">
                <div className="ni-meta">
                  <span className="ni-time">Сейчас</span>
                  <span className="cat-pill cat-pill--football">ezbet</span>
                </div>
                <h3 className="ni-title">Лента скоро наполнится новыми публикациями</h3>
                <p className="ni-desc">Проверьте подключение API или дождитесь следующего редакционного прогона.</p>
              </article>
            )}
          </div>
          <Link href="/news" className="load-more-btn">
            Перейти ко всей ленте
          </Link>
        </section>

        <aside className="sidebar">
          <div className="sidebar-block">
            <h3 className="sidebar-block-title">Популярное сегодня</h3>
            <ol className="popular-list" role="list">
              {popularNews.map((item, index) => (
                <li className="popular-item" key={item.id}>
                  <span className="popular-num">{index + 1}</span>
                  {item.articleSlug ? (
                    <Link className="popular-link" href={newsHref(item.articleSlug)}>
                      {item.title}
                    </Link>
                  ) : (
                    <a className="popular-link" href={item.link ?? "/news"}>
                      {item.title}
                    </a>
                  )}
                </li>
              ))}
            </ol>
          </div>

          <div className="sidebar-block">
            <h3 className="sidebar-block-title">Рубрики</h3>
            <div className="topic-cloud">
              {["Футбол", "Хоккей", "Баскетбол", "Теннис", "Беттинг", "Киберспорт"].map((topic) => (
                <Link key={topic} href={`/news?query=${encodeURIComponent(topic)}`} className="topic-chip">
                  {topic}
                </Link>
              ))}
            </div>
          </div>
        </aside>
      </div>

      <section className="guides-section container-wide" aria-labelledby="guides-heading">
        <div className="section-header">
          <h2 className="section-title" id="guides-heading">
            Полезные статьи
          </h2>
          <Link href="/news?type=guides" className="section-link">
            Все материалы
          </Link>
        </div>

        <div className="guides-grid">
          {guideNews.length
            ? guideNews.map((item, index) => (
                <article key={item.id} className={`guide-card${index === 0 ? " guide-card--featured" : ""}`}>
                  <div className={`guide-cat cat-pill cat-pill--${categoryTone(item.category)}`}>
                    {index === 0 ? "Аналитика" : "Гайд"}
                  </div>
                  <h3 className="guide-title">{item.title}</h3>
                  <p className="guide-desc">{item.description}</p>
                  <div className="guide-meta">
                    <span className="guide-read-time">{formatRelativeTime(item.publishedAt)}</span>
                    <Link href={newsHref(item.articleSlug)} className="guide-read">
                      Читать
                    </Link>
                  </div>
                </article>
              ))
            : guideItems.map((item) => (
                <article key={item.title} className={`guide-card${item.featured ? " guide-card--featured" : ""}`}>
                  <div className={`guide-cat cat-pill cat-pill--${item.tone}`}>{item.label}</div>
                  <h3 className="guide-title">{item.title}</h3>
                  <p className="guide-desc">{item.description}</p>
                  <div className="guide-meta">
                    <span className="guide-read-time">{item.readTime}</span>
                    <Link href={item.href} className="guide-read">
                      Читать
                    </Link>
                  </div>
                </article>
              ))}
        </div>
      </section>
    </main>
  );
}
