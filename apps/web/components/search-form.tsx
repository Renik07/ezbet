export function SearchForm({ initialQuery = "" }: { initialQuery?: string }) {
  return (
    <form className="search-bar" action="/news" method="get">
      <input
        type="search"
        name="query"
        defaultValue={initialQuery}
        placeholder="Искать новости, темы и сигналы"
        aria-label="Поиск новостей"
      />
      <button className="button-primary" type="submit">
        Найти
      </button>
    </form>
  );
}
