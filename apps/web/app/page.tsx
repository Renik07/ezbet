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
              <span>Новости спорта и беттинга</span>
            </div>
            <h1>Свежие новости спорта в одной живой ленте.</h1>
            <p>Короткий срез последних публикаций на главной и полная лента новостей в отдельном разделе.</p>
          </div>
          <aside className="hero-card">
            <div className="eyebrow">Сейчас в эфире</div>
            <strong>{featuredNews.length || 0} новостей</strong>
            <p>
              {isLive
                ? "Свежие публикации появляются здесь автоматически по мере обновления ленты."
                : "Лента временно недоступна. После восстановления API публикации снова появятся автоматически."}
            </p>
          </aside>
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h3>Последние новости</h3>
            <p>{isLive ? "Полная лента доступна в отдельном разделе новостей." : "Сейчас показывается резервная лента."}</p>
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
    </main>
  );
}
