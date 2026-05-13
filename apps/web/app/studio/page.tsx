import Link from "next/link";

import { buildRawDraftPairs, getEditorialStudioData } from "@/lib/editorial";

export default async function StudioPage() {
  const data = await getEditorialStudioData();
  const { prompts, drafts, reviews, contentPlan, editorialStatus, isLive } = data;
  const rawDraftPairs = buildRawDraftPairs(data, 10);

  return (
    <main className="page-shell">
      <section className="hero" style={{ paddingBottom: 22 }}>
        <div className="eyebrow">AI Studio</div>
        <h1 style={{ fontSize: "clamp(2.2rem, 5vw, 4rem)" }}>Черновики и prompt-слой</h1>
        <p>
          {isLive
            ? "Студия читает живые данные из editorial API: prompt configs, draft articles и review-результаты."
            : "API editorial-слоя сейчас недоступен, поэтому показывается fallback-просмотр структуры Stage 3."}
        </p>
        <div className="hero-actions">
          <Link className="button-primary" href="/admin">
            Открыть админку
          </Link>
          <Link className="button-secondary" href="/news">
            Назад к ленте
          </Link>
          <Link className="button-secondary" href="/">
            На главную
          </Link>
        </div>
        <div className="section-card" style={{ marginTop: 18 }}>
          <p style={{ margin: 0 }}>
            AI mode:{" "}
            <strong>
              {editorialStatus.openaiEnabled
                ? `${editorialStatus.providerLabel} live (editorial: ${editorialStatus.openaiModel}, search: ${editorialStatus.openaiSearchModel}, ${editorialStatus.apiStyle})`
                : "template fallback"}
            </strong>
          </p>
          <p style={{ margin: "6px 0 0 0" }}>
            Web search: <strong>{editorialStatus.webSearchEnabled ? "on" : "off"}</strong>
          </p>
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>Original vs AI</h2>
            <p>
              Здесь удобнее всего проверять, что модель реально работает: слева сырой RSS-вход, справа AI-черновик.
              Если справа ещё пусто, это нормально: один editorial run сейчас обрабатывает только часть очереди.
            </p>
          </div>
        </div>
        <div className="compare-grid">
          {rawDraftPairs.map(({ rawItem, draft }) => (
            <article key={rawItem.id} className="compare-card">
              <div className="compare-panel">
                <span>RAW RSS</span>
                <h3>{rawItem.title}</h3>
                <div className="compare-block">
                  <strong>Original title</strong>
                  <p>{rawItem.title}</p>
                </div>
                <div className="compare-block">
                  <strong>Original summary</strong>
                  <p>{rawItem.summary}</p>
                </div>
                {rawItem.lead ? (
                  <div className="compare-block">
                    <strong>Original lead</strong>
                    <p>{rawItem.lead}</p>
                  </div>
                ) : null}
                {rawItem.tags.length ? (
                  <div className="compare-block">
                    <strong>Original tags</strong>
                    <p>{rawItem.tags.join(", ")}</p>
                  </div>
                ) : null}
                <div className="compare-block">
                  <strong>Original meta</strong>
                  <p>
                    Дата публикации:{" "}
                    <time dateTime={rawItem.publishedAt}>
                      {new Date(rawItem.publishedAt).toLocaleString("ru-RU", {
                        dateStyle: "medium",
                        timeStyle: "short"
                      })}
                    </time>
                  </p>
                  <p>
                    Оригинал:{" "}
                    {rawItem.url ? (
                      <a href={rawItem.url} target="_blank" rel="noreferrer">
                        открыть источник
                      </a>
                    ) : (
                      "ссылка недоступна"
                    )}
                  </p>
                </div>
                <div className="compare-block">
                  <strong>Original full text</strong>
                  <div className="compare-text-surface">
                    {rawItem.fullText ? (
                      rawItem.fullText
                        .split("\n\n")
                        .filter(Boolean)
                        .map((paragraph, index) => <p key={`${rawItem.id}-full-${index}`}>{paragraph}</p>)
                    ) : (
                      <p>Полный текст для этой новости пока не извлечён.</p>
                    )}
                  </div>
                </div>
                <p className="footer-note">
                  {rawItem.sourceTitle} · {rawItem.triageLabel} · score {rawItem.importanceScore}
                </p>
              </div>
              <div className="compare-panel">
                <span>{draft ? `AI DRAFT · ${draft.generationMode}` : "AI DRAFT PENDING"}</span>
                <h3>{draft?.title ?? "Черновик ещё не создан"}</h3>
                <div className="compare-block">
                  <strong>AI title</strong>
                  <p>{draft?.title ?? "Для этой новости пока нет draft-версии."}</p>
                </div>
                <div className="compare-block">
                  <strong>AI dek</strong>
                  <p>{draft?.dek ?? "Запустите editorial run, чтобы получить AI-версию."}</p>
                </div>
                {draft?.status === "fallback_only" ? (
                  <p className="source-card-error">
                    Fallback-only: этот draft сохранён только для внутреннего просмотра и не может попасть в публикацию.
                  </p>
                ) : null}
                {draft?.generationMode === "template" ? (
                  <p className="source-card-error">
                    Это template fallback. Такой draft не должен автоматически попадать в публикацию.
                  </p>
                ) : null}
                <div className="compare-block">
                  <strong>AI full text</strong>
                  <div className="compare-text-surface">
                    {draft?.body ? (
                      draft.body
                        .split("\n\n")
                        .filter(Boolean)
                        .map((paragraph, index) => <p key={`${draft.id}-${index}`}>{paragraph}</p>)
                    ) : (
                      <p>Для этой новости пока нет draft-версии. Запустите editorial run.</p>
                    )}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>Content plan</h2>
            <p>Это промежуточный слой между triage raw_items и генерацией draft-статей.</p>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          {contentPlan.map((item) => (
            <article key={item.id} className="news-card">
              <span>
                {item.priorityLabel} · {item.plannedFormat}
              </span>
              <h3>{item.title}</h3>
              <p>{item.reason}</p>
              <p className="footer-note" style={{ marginTop: 12 }}>
                {item.sourceTitle} · {item.status} · score {item.priorityScore}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>Prompt configs</h2>
            <p>На MVP уже есть отдельные конфиги для writer и editor.</p>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          {prompts.map((prompt) => (
            <article key={prompt.id} className="news-card">
              <span>
                {prompt.agentKey} · v{prompt.version}
              </span>
              <h3>{prompt.name}</h3>
              <p>{prompt.systemPrompt}</p>
              <p>
                <strong>Model:</strong> {prompt.model}
              </p>
              <p>
                <strong>Template:</strong> {prompt.userPromptTemplate}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>Latest drafts</h2>
            <p>Это черновики, которые появились после RSS-ingestion и editorial pass.</p>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "1fr" }}>
          {drafts.map((draft) => (
            <article key={draft.id} className="news-card">
              <span>
                {draft.category} · {draft.status} · {draft.reviewStatus}
              </span>
              <h3>{draft.title}</h3>
              <p>
                <strong>Dek:</strong> {draft.dek}
              </p>
              {draft.body.split("\n\n").map((paragraph, index) => (
                <p key={`${draft.id}-${index}`}>{paragraph}</p>
              ))}
              <div className="section-head" style={{ margin: "16px 0 0" }}>
                <span>{draft.sourceTitle}</span>
                <time dateTime={draft.publishedAt}>
                  {new Date(draft.publishedAt).toLocaleString("ru-RU", {
                    dateStyle: "medium",
                    timeStyle: "short"
                  })}
                </time>
              </div>
              <p className="footer-note" style={{ marginTop: 12 }}>
                Prompt: {draft.promptName} · Mode: {draft.generationMode}
              </p>
              {draft.status === "fallback_only" ? (
                <p className="source-card-error">
                  Fallback-only: материал оставлен только для studio/admin и исключён из публикации.
                </p>
              ) : null}
              {draft.generationMode === "template" ? (
                <p className="source-card-error">
                  Template fallback: материал требует живой генерации или ручной доработки.
                </p>
              ) : null}
              {draft.reviewSummary ? <p>{draft.reviewSummary}</p> : null}
            </article>
          ))}
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>Review log</h2>
            <p>Короткие summary редакторского прохода по каждому черновику.</p>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          {reviews.map((review) => (
            <article key={review.id} className="news-card">
              <span>{review.status}</span>
              <h3>{review.promptName}</h3>
              <p>{review.summary}</p>
              <p>{review.notes}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
