import Link from "next/link";
import { NewsCard } from "@/components/news-card";
import { SearchForm } from "@/components/search-form";
import { getNews } from "@/lib/news";

const NEWS_PER_PAGE = 20;

function buildNewsPageHref(page: number, query: string) {
  const params = new URLSearchParams();
  if (query) {
    params.set("query", query);
  }
  if (page > 1) {
    params.set("page", String(page));
  }
  const search = params.toString();
  return search ? `/news?${search}` : "/news";
}

export default async function NewsPage({
  searchParams
}: {
  searchParams?: Promise<{ query?: string; page?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const query = params.query ?? "";
  const requestedPage = Number(params.page ?? "1");
  const safeRequestedPage = Number.isFinite(requestedPage) && requestedPage > 0 ? Math.floor(requestedPage) : 1;
  const { items, isLive } = await getNews(query, { aiOnly: true });
  const totalPages = Math.max(1, Math.ceil(items.length / NEWS_PER_PAGE));
  const currentPage = Math.min(safeRequestedPage, totalPages);
  const startIndex = (currentPage - 1) * NEWS_PER_PAGE;
  const pagedItems = items.slice(startIndex, startIndex + NEWS_PER_PAGE);
  const fromItem = items.length ? startIndex + 1 : 0;
  const toItem = Math.min(startIndex + NEWS_PER_PAGE, items.length);

  return (
    <main className="page-shell">
      <section className="hero" style={{ paddingBottom: 22 }}>
        <div className="eyebrow">Поиск по новостям</div>
        <h1 style={{ fontSize: "clamp(2.2rem, 5vw, 4rem)" }}>Лента новостей</h1>
        <p>{isLive ? "Свежие публикации с поиском по ленте и удобной навигацией по страницам." : "Лента временно недоступна."}</p>
        <SearchForm initialQuery={query} />
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>{query ? `Результаты по запросу: ${query}` : "Все новости"}</h2>
          </div>
        </div>
        <div className="section-head" style={{ marginTop: 0, alignItems: "center" }}>
          <p style={{ margin: 0, color: "var(--muted)" }}>
            {items.length
              ? `Показаны ${fromItem}-${toItem} из ${items.length}`
              : "По этому запросу пока ничего не найдено."}
          </p>
          {totalPages > 1 ? (
            <div className="pagination-row">
              {currentPage > 1 ? (
                <a className="button-secondary" href={buildNewsPageHref(currentPage - 1, query)}>
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
                <a className="button-secondary" href={buildNewsPageHref(currentPage + 1, query)}>
                  Вперед
                </a>
              ) : (
                <span className="button-secondary is-disabled" aria-disabled="true">
                  Вперед
                </span>
              )}
            </div>
          ) : null}
        </div>
        <div className="news-grid">
          {pagedItems.map((item) => (
            <NewsCard key={item.id} item={item} />
          ))}
        </div>
      </section>
    </main>
  );
}
