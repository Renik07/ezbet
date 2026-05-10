import { NewsCard } from "@/components/news-card";
import { SearchForm } from "@/components/search-form";
import { getNews } from "@/lib/news";

export default async function NewsPage({
  searchParams
}: {
  searchParams?: Promise<{ query?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const query = params.query ?? "";
  const { items, isLive } = await getNews(query, { aiOnly: true });

  return (
    <main className="page-shell">
      <section className="hero" style={{ paddingBottom: 22 }}>
        <div className="eyebrow">Поиск по новостям</div>
        <h1 style={{ fontSize: "clamp(2.2rem, 5vw, 4rem)" }}>Живая лента MVP</h1>
        <p>
          {isLive
            ? "Страница показывает опубликованные AI-обработанные материалы и поддерживает поиск по внутренним статьям."
            : "Если API недоступен, страница временно показывает fallback-материалы, чтобы интерфейс не пустовал."}
        </p>
        <SearchForm initialQuery={query} />
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>{query ? `Результаты по запросу: ${query}` : "Все новости"}</h2>
            <p>
              Найдено: {items.length}. Сейчас здесь показываются только внутренние статьи, у которых уже есть полная article page.
            </p>
          </div>
        </div>
        <div className="news-grid">
          {items.map((item) => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      </section>
    </main>
  );
}
