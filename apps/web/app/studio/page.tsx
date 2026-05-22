import Link from "next/link";

import { buildRawDraftPairs, getEditorialStudioData } from "@/lib/editorial";

function formatExtractionMode(mode?: string) {
  switch (mode) {
    case "direct_html":
      return "direct parser";
    case "llm_responses_web_search_brief":
    case "llm_chat_completions_web_search_brief":
      return "web search brief";
    case "llm_responses_html_extraction":
    case "llm_chat_completions_html_extraction":
      return "legacy ai html";
    case "llm_responses_web_search_extraction":
    case "llm_chat_completions_web_search_extraction":
      return "legacy web search extraction";
    default:
      return mode ?? "ещё не извлечён";
  }
}

function formatEnrichmentStatus(status?: string) {
  switch (status) {
    case "direct_html_ok":
      return "direct parser ok";
    case "web_search_brief_ok":
      return "web search brief ok";
    case "search_partial_only":
      return "web search partial";
    case "search_no_match":
      return "web search no match";
    case "enrichment_error":
      return "enrichment error";
    case "ai_html_ok":
      return "legacy ai html ok";
    case "ai_html_partial_only":
      return "legacy ai html partial";
    default:
      return status ?? "ещё не запускался или не сохранил статус";
  }
}

function formatContentPlanStatus(status?: string) {
  switch (status) {
    case "planned":
      return "запланировано";
    case "drafted":
      return "черновик создан";
    case "ready_to_publish":
      return "готово к publish-этапу";
    case "published":
      return "опубликовано";
    case "hold":
      return "остановлено на quality hold";
    case "rewrite_needed":
      return "нужен rewrite";
    case "fallback_only":
      return "template fallback only";
    default:
      return status ?? "ещё не попадало в content plan";
  }
}

function formatDraftStatus(status?: string) {
  switch (status) {
    case "draft":
      return "черновик";
    case "ready_for_publish":
      return "готово к публикации";
    case "published":
      return "опубликовано";
    case "hold":
      return "удержано quality gate";
    case "rewrite_needed":
      return "ожидает rewrite";
    case "fallback_only":
      return "только внутренний fallback";
    default:
      return status ?? "черновик ещё не создан";
  }
}

function formatReviewStatus(status?: string) {
  switch (status) {
    case "pending":
      return "ещё не проверено";
    case "reviewed":
      return "проверено";
    case "quality_hold":
      return "quality hold";
    case "quality_rewrite":
      return "нужен rewrite по quality gate";
    case "fallback_only":
      return "fallback only";
    default:
      return status ?? "нет review";
  }
}

function formatPublishDecision(decision?: string) {
  switch (decision) {
    case "publish_auto":
      return "автопубликация разрешена";
    case "publish_hold":
      return "удержано перед публикацией";
    case "publish_skip":
      return "автопубликация запрещена";
    case "publish_pending":
      return "решение о публикации еще не принято";
    default:
      return decision ?? "нет publish decision";
  }
}

function describePipelineState(rawItem: {
  isDuplicate: boolean;
  duplicateOf?: string;
  duplicateStage?: string;
  duplicateReason?: string;
  fullText?: string;
  contentPlanStatus?: string;
  contentPlanPriorityLabel?: string;
  contentPlanReason?: string;
}) {
  if (rawItem.isDuplicate) {
    const stageLabel =
      rawItem.duplicateStage === "ingest"
        ? "Дубликат найден при первичной загрузке."
        : rawItem.duplicateStage === "after_enrichment"
          ? "Дубликат найден после добора full text."
          : rawItem.duplicateStage === "before_publish"
            ? "Дубликат найден перед публикацией."
            : "Новость помечена как дубликат.";
    const reason = rawItem.duplicateReason ? ` ${rawItem.duplicateReason}` : "";
    const duplicateOf = rawItem.duplicateOf ? ` Связана с записью ${rawItem.duplicateOf}.` : "";
    return `${stageLabel}${reason}${duplicateOf}`;
  }
  if (!rawItem.fullText) {
    return "Ожидает enrichment: полный текст еще не получен.";
  }
  if (!rawItem.contentPlanStatus) {
    return "Полный текст уже есть, но новость еще не попала в content plan.";
  }
  return `В content plan: ${rawItem.contentPlanStatus}${rawItem.contentPlanPriorityLabel ? ` (${rawItem.contentPlanPriorityLabel})` : ""}.`;
}

function describeEditorialState(rawItem: {
  contentPlanStatus?: string;
  contentPlanReason?: string;
}, draft?: {
  status: string;
  reviewStatus: string;
  reviewSummary?: string;
  generationMode: string;
}) {
  if (!draft) {
    if (!rawItem.contentPlanStatus) {
      return "До editorial-слоя новость еще не дошла: сначала она должна попасть в content plan.";
    }
    if (rawItem.contentPlanStatus === "planned") {
      return "Новость уже в content plan и ждет генерации AI draft.";
    }
    return "Draft для этой новости пока не создан.";
  }

  if (draft.status === "published") {
    return "Материал прошел editorial-цикл и уже опубликован в ленте.";
  }
  if (draft.status === "ready_for_publish") {
    return "Материал прошел editorial и готов к публикации.";
  }
  if (draft.status === "rewrite_needed") {
    return `Материал остановлен на rewrite: ${draft.reviewSummary ?? "quality gate попросил переписать текст."}`;
  }
  if (draft.status === "hold") {
    return `Материал удержан quality gate: ${draft.reviewSummary ?? "нужна дополнительная проверка."}`;
  }
  if (draft.status === "fallback_only" || draft.generationMode === "template") {
    return `Материал остался во внутреннем fallback-режиме и не должен публиковаться автоматически${draft.reviewSummary ? `: ${draft.reviewSummary}` : "."}`;
  }
  if (draft.reviewStatus === "pending") {
    return "AI draft уже создан, но review-этап еще не завершен.";
  }
  return draft.reviewSummary ?? "Материал находится в editorial-пайплайне.";
}

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
                  <strong>Original full text / search brief</strong>
                  <div className="compare-text-surface">
                    {rawItem.fullText ? (
                      rawItem.fullText
                        .split("\n\n")
                        .filter(Boolean)
                        .map((paragraph, index) => <p key={`${rawItem.id}-full-${index}`}>{paragraph}</p>)
                    ) : (
                      <p>Текст для этой новости пока не извлечён.</p>
                    )}
                  </div>
                </div>
                <div className="compare-block">
                  <strong>Full text provenance</strong>
                  <p>
                    Способ:{" "}
                    <strong>{formatExtractionMode(rawItem.extractionMode)}</strong>
                  </p>
                  <p>
                    Статус enrichment:{" "}
                    <strong>{formatEnrichmentStatus(rawItem.enrichmentStatus)}</strong>
                  </p>
                  <p>
                    Источник текста:{" "}
                    <strong>{rawItem.fullTextSourceTitle ?? rawItem.sourceTitle}</strong>
                  </p>
                  <p>
                    URL текста:{" "}
                    {rawItem.fullTextSourceUrl ? (
                      <a href={rawItem.fullTextSourceUrl} target="_blank" rel="noreferrer">
                        открыть основной источник текста
                      </a>
                    ) : rawItem.fullText ? (
                      "не сохранён"
                    ) : (
                      "ещё не определён"
                    )}
                  </p>
                  {rawItem.referenceUrls.length ? (
                    <div>
                      <p>Источники web search:</p>
                      {rawItem.referenceUrls.map((url) => (
                        <p key={`${rawItem.id}-${url}`}>
                          <a href={url} target="_blank" rel="noreferrer">
                            {url}
                          </a>
                        </p>
                      ))}
                    </div>
                  ) : null}
                  {rawItem.enrichmentError ? <p>Причина: {rawItem.enrichmentError}</p> : null}
                </div>
                <div className="compare-block">
                  <strong>Pipeline status</strong>
                  <p>{describePipelineState(rawItem)}</p>
                  {rawItem.contentPlanReason ? <p>Причина отбора: {rawItem.contentPlanReason}</p> : null}
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
                  <strong>Editorial status</strong>
                  <p>
                    Content plan: <strong>{formatContentPlanStatus(rawItem.contentPlanStatus)}</strong>
                  </p>
                  <p>
                    Draft: <strong>{formatDraftStatus(draft?.status)}</strong>
                  </p>
                  <p>
                    Review: <strong>{formatReviewStatus(draft?.reviewStatus)}</strong>
                  </p>
                  <p>
                    Publish: <strong>{formatPublishDecision(draft?.publishDecision)}</strong>
                  </p>
                  <p>{describeEditorialState(rawItem, draft)}</p>
                  {draft?.reviewSummary ? <p>Причина/итог review: {draft.reviewSummary}</p> : null}
                  {draft?.publishReason ? <p>Причина publish decision: {draft.publishReason}</p> : null}
                </div>
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
