export function SearchForm({ initialQuery = "", type = "" }: { initialQuery?: string; type?: string }) {
  return (
    <form className="search-bar" action="/news" method="get">
      {type ? <input type="hidden" name="type" value={type} /> : null}
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
