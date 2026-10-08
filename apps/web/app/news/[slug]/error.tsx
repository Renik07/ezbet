"use client";

export default function ArticleError({ reset }: { reset: () => void }) {
  return (
    <main className="article-page container-wide">
      <h1>Материал временно недоступен</h1>
      <p>Не удалось загрузить статью. Попробуйте ещё раз чуть позже.</p>
      <button type="button" onClick={reset}>Попробовать снова</button>
    </main>
  );
}
