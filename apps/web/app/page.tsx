import Link from "next/link";
import { NewsCard } from "@/components/news-card";
import { getNews } from "@/lib/news";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const { items: news, isLive } = await getNews(undefined, { aiOnly: true });
  const featuredNews = news.slice(0, 12);

  return (
    <main className="page-shell">
      <section className="hero">
        <div className="hero-grid">
          <div>
            <div className="eyebrow">
              <span>ezbet.ru</span>
              <span>AI-assisted sports media MVP</span>
            </div>
            <h1>Новости спорта и беттинга, собранные в один живой поток.</h1>
            <p>
              Первый MVP объединяет автосбор новостей, поиск по ленте и быструю
              публикацию материалов. AI уже участвует в редактуре черновика
              перед публикацией, чтобы на старте автоматизация была реальной, а
              не декоративной.
            </p>
            <div className="hero-actions">
              <Link className="button-primary" href="/news">
                Смотреть ленту
              </Link>
              <Link className="button-secondary" href="/studio">
                Открыть AI Studio
              </Link>
              <Link className="button-secondary" href="/admin">
                Открыть админку
              </Link>
            </div>
          </div>
          <aside className="hero-card">
            <div className="eyebrow">Стартовый контур MVP</div>
            <strong>4 шага</strong>
            <p>Сбор новостей, поиск, AI-редактура и публикация без ручной рутины.</p>
            <div className="section-card">
              <p style={{ margin: 0 }}>
                В следующих итерациях сюда добавятся карточки букмекеров,
                контент-план и AI-генерация lead image для статей.
              </p>
            </div>
          </aside>
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>Сигналы системы</h2>
            <p>Минимальные KPI, которые будут расти вместе с реальным ingestion-потоком.</p>
          </div>
        </div>
        <div className="stats-grid">
          <div className="stat">
            <strong>12</strong>
            <span>источников в стартовом пуле</span>
          </div>
          <div className="stat">
            <strong>10 мин</strong>
            <span>целевой интервал scheduler для проверки новых публикаций</span>
          </div>
          <div className="stat">
            <strong>1 AI-pass</strong>
            <span>редакторская обработка перед публикацией в MVP</span>
          </div>
          <div className="stat">
            <strong>2 prompts</strong>
            <span>writer и editor уже подняты в отдельный prompt-driven слой</span>
          </div>
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h3>Последние новости</h3>
            <p>
              {isLive
                ? "Главная показывает только новости, которые уже прошли AI-редактуру и попали в публичную витрину."
                : "API сейчас недоступен, поэтому показывается fallback-лента для локальной разработки."}
            </p>
          </div>
          <Link href="/news">Вся лента</Link>
        </div>
        <div className="news-grid">
          {featuredNews.map((item, index) => (
            <div key={item.id} className={index >= 8 ? "home-news-desktop-only" : undefined}>
              <NewsCard item={item} />
            </div>
          ))}
        </div>
      </section>

      <p className="footer-note">
        {isLive
          ? "MVP сейчас работает на живом контуре: RSS -> raw_items -> news_items -> API -> frontend."
          : "MVP может работать и без API, но для реальных новостей нужно поднять backend-контур."}
      </p>
    </main>
  );
}
