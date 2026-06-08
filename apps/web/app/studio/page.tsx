import Link from "next/link";
import type { Metadata } from "next";

import { logoutAdminNow } from "@/app/auth-actions";
import { hidePublishedNewsNow, unhidePublishedNewsNow } from "@/app/admin/actions";
import { PendingSubmitButton } from "@/components/pending-submit-button";
import { StudioDiagnosticsRefresh } from "@/components/studio-diagnostics-refresh";
import { requireAdminSession } from "@/lib/auth";
import { formatCategoryLabel } from "@/lib/category";
import { formatMoscowDateTime } from "@/lib/dates";
import { buildRawDraftPairs, getEditorialStudioData } from "@/lib/editorial";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata: Metadata = {
  title: "Studio",
  robots: {
    index: false,
    follow: false
  }
};

function formatExtractionMode(mode?: string) {
  switch (mode) {
    case "direct_html":
      return "direct parser";
    case "llm_responses_web_search_brief":
    case "llm_chat_completions_web_search_brief":
      return "web search brief";
    case "llm_responses_html_extraction":
    case "llm_chat_completions_html_extraction":
      return "ai html extraction";
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
    case "search_skipped_budget":
      return "web search skipped by budget";
    case "search_skipped_run_cap":
      return "web search skipped by run cap";
    case "enrichment_error":
      return "enrichment error";
    case "ai_html_ok":
      return "ai html ok";
    case "ai_html_partial_only":
      return "ai html partial";
    case "direct_html_partial_only":
      return "direct parser partial";
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
      return "только шаблонный fallback";
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
      return "удержано quality gate";
    case "quality_rewrite":
      return "нужен rewrite по quality gate";
    case "fallback_only":
      return "только fallback";
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

function formatNewsVisibility(visibility?: string) {
  switch (visibility) {
    case "hidden":
      return "скрыта";
    case "public":
    default:
      return "в ленте";
  }
}

function hasEditorChanges(draft: {
  title: string;
  dek: string;
  body: string;
  writerTitle?: string;
  writerDek?: string;
  writerBody?: string;
}) {
  return Boolean(
    draft.writerBody &&
      (draft.writerTitle !== draft.title || draft.writerDek !== draft.dek || draft.writerBody !== draft.body)
  );
}

function isNeedsAttentionDraft(draft: {
  status: string;
  reviewStatus: string;
  publishDecision: string;
}) {
  return (
    draft.status === "hold" ||
    draft.status === "rewrite_needed" ||
    draft.status === "fallback_only" ||
    draft.reviewStatus === "quality_hold" ||
    draft.reviewStatus === "quality_rewrite" ||
    draft.reviewStatus === "fallback_only" ||
    draft.publishDecision === "publish_hold" ||
    draft.publishDecision === "publish_skip"
  );
}

function formatEditorDecision(decision?: string) {
  switch (decision) {
    case "approve":
      return "оставить как есть";
    case "light_edit":
      return "точечная правка";
    case "rewrite":
      return "переписать";
    default:
      return decision ?? "нет решения";
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

function describeEnrichmentBlock(rawItem: {
  isDuplicate: boolean;
  duplicateReason?: string;
  duplicateStage?: string;
  fullText?: string;
  enrichmentStatus?: string;
  enrichmentError?: string;
  extractionMode?: string;
}) {
  if (rawItem.isDuplicate && rawItem.duplicateStage === "ingest") {
    return `Добор full text не запускался: новость была отсечена как дубликат еще при первичной загрузке${rawItem.duplicateReason ? ` (${rawItem.duplicateReason})` : "."}`;
  }
  if (rawItem.fullText) {
    return `Полный текст уже получен через ${formatExtractionMode(rawItem.extractionMode)}.`;
  }
  if (rawItem.enrichmentError) {
    return `Добор full text завершился ошибкой: ${rawItem.enrichmentError}`;
  }
  switch (rawItem.enrichmentStatus) {
    case "search_no_match":
      return "Добор full text запускался, но источник текста не нашелся даже через web search.";
    case "search_skipped_budget":
      return "web search fallback был сознательно пропущен по budget-правилу: для этой low-priority новости используем только локальный extraction без внешнего поиска.";
    case "search_skipped_run_cap":
      return "web search fallback был пропущен из-за лимита на текущий enrichment batch: в этом прогоне внешний поиск уже израсходовал свою квоту.";
    case "search_partial_only":
      return "Полный текст не найден: удалось получить только частичный web-search brief.";
    case "direct_html_ok":
      return "Direct parser отработал, но сохранил только частичный контекст без полноценного full text.";
    case "direct_html_partial_only":
      return "Direct parser нашел только часть контекста: заголовок, lead или короткий фрагмент, но не полный текст статьи.";
    case "ai_html_partial_only":
      return "AI extraction по HTML запускался, но смог поднять только частичный контекст без полноценного full text.";
    case "ai_html_ok":
      return "Полный текст уже получен через AI extraction по HTML самой страницы.";
    case "enrichment_error":
      return "Добор full text не завершился успешно и требует повторного запуска или другого extraction path.";
    default:
      return "Full text пока не получен: новость либо еще не дошла до enrichment batch, либо источник пока не дал достаточно качественный текст для сохранения.";
  }
}

function describeEditorialBlock(
  rawItem: {
    isDuplicate: boolean;
    duplicateReason?: string;
    fullText?: string;
    contentPlanStatus?: string;
    contentPlanReason?: string;
    contentPlanPriorityLabel?: string;
  },
  draft?: {
    status: string;
    reviewStatus: string;
    reviewSummary?: string;
    generationMode: string;
  }
) {
  if (rawItem.isDuplicate) {
    return `До editorial новость не допускается: она уже помечена как дубликат${rawItem.duplicateReason ? ` (${rawItem.duplicateReason})` : "."}`;
  }
  if (!rawItem.fullText) {
    return "Editorial еще не стартовал: сначала нужен full text или хотя бы достаточный enrichment-контекст.";
  }
  if (!rawItem.contentPlanStatus) {
    return rawItem.contentPlanReason
      ? `Editorial еще не стартовал: планировщик пока не взял новость в content plan (${rawItem.contentPlanReason}).`
      : "Editorial еще не стартовал: новость пока не попала в content plan и ждет планировщик.";
  }
  if (rawItem.contentPlanStatus === "hold") {
    return `Editorial остановлен еще на content plan: ${rawItem.contentPlanReason ?? "новость удержана правилами планировщика."}`;
  }
  if (rawItem.contentPlanStatus === "rewrite_needed") {
    return `Editorial требует доработки уже на планировщике: ${rawItem.contentPlanReason ?? "нужен rewrite до writer-этапа."}`;
  }
  if (rawItem.contentPlanStatus === "fallback_only") {
    return `Editorial не пойдет в обычный AI-поток: ${rawItem.contentPlanReason ?? "новость оставлена только во fallback-режиме."}`;
  }
  if (!draft) {
    if (rawItem.contentPlanStatus === "planned") {
      return `Editorial еще не стартовал: новость уже отобрана в content plan${rawItem.contentPlanPriorityLabel ? ` (${rawItem.contentPlanPriorityLabel})` : ""} и ждет своей очереди в batch.`;
    }
    return "Draft еще не создан: новость находится между content plan и writer-этапом.";
  }
  if (draft.reviewStatus === "pending") {
    return "Editorial уже идет: draft создан, но review-этап еще не завершен.";
  }
  if (draft.status === "fallback_only" || draft.generationMode === "template") {
    return `Живой AI-draft не получился: система оставила только template fallback для внутреннего просмотра${draft.reviewSummary ? ` (${draft.reviewSummary})` : "."}`;
  }
  if (draft.status === "hold") {
    return `Editorial остановлен quality gate: ${draft.reviewSummary ?? "нужна дополнительная проверка редакционного качества."}`;
  }
  if (draft.status === "rewrite_needed") {
    return `Editorial требует rewrite: ${draft.reviewSummary ?? "качество черновика пока недостаточно для публикации."}`;
  }
  if (draft.status === "ready_for_publish") {
    return "Editorial-этап завершен успешно: материал готов к publish-этапу.";
  }
  return "Editorial-этап для этой новости уже отработал.";
}

function describePublishBlock(draft?: {
  status: string;
  reviewStatus: string;
  publishDecision: string;
  publishReason?: string;
}) {
  if (!draft) {
    return "До publish новость еще не дошла: сначала должен появиться editorial draft.";
  }
  if (draft.status === "published") {
    return "Публикация уже произошла: материал находится в ленте.";
  }
  if (draft.publishDecision === "publish_auto" && draft.status === "ready_for_publish") {
    return "Публикация еще не случилась, но материал уже готов и ждет следующий publish run.";
  }
  if (draft.publishDecision === "publish_hold") {
    return `Публикация остановлена правилом hold${draft.publishReason ? `: ${draft.publishReason}` : "."}`;
  }
  if (draft.publishDecision === "publish_skip") {
    return `Автопубликация запрещена${draft.publishReason ? `: ${draft.publishReason}` : "."}`;
  }
  if (draft.status === "hold") {
    return `Публикация не началась, потому что editorial удержал материал${draft.publishReason ? `: ${draft.publishReason}` : "."}`;
  }
  if (draft.status === "rewrite_needed") {
    return `Публикация не началась, потому что материал отправлен на rewrite${draft.publishReason ? `: ${draft.publishReason}` : "."}`;
  }
  if (draft.status === "fallback_only") {
    return "Публикация не началась, потому что у материала остался только внутренний template fallback.";
  }
  if (draft.reviewStatus === "pending" || draft.publishDecision === "publish_pending") {
    return "Публикация еще не решена: editorial/review-цикл не дошел до финального publish decision.";
  }
  return draft.publishReason ?? "Публикация для этой новости пока не произошла.";
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

type StudioSearchParams = {
  notice?: string;
  detail?: string;
  tab?: string;
};

function getStudioNotice(notice?: string, detail?: string) {
  switch (notice) {
    case "news-hidden":
      return detail ?? "Новость скрыта из публичной ленты.";
    case "news-unhidden":
      return detail ?? "Новость возвращена в публичную ленту.";
    case "hide-news-error":
    case "unhide-news-error":
      return detail ?? "Не удалось изменить видимость новости.";
    default:
      return detail ?? null;
  }
}

type StudioTab = "attention" | "published" | "diagnostics";

function getStudioTab(tab?: string): StudioTab {
  switch (tab) {
    case "attention":
    case "published":
    case "diagnostics":
      return tab;
    default:
      return "published";
  }
}

export default async function StudioPage({
  searchParams
}: {
  searchParams?: Promise<StudioSearchParams>;
}) {
  await requireAdminSession("/studio");
  const params = (await searchParams) ?? {};
  const data = await getEditorialStudioData();
  const { drafts, contentPlan, editorialStatus, isLive, publishedNews } = data;
  const rawDraftPairs = buildRawDraftPairs(data, 8);
  const notice = getStudioNotice(params.notice, params.detail);
  const activeTab = getStudioTab(params.tab);
  const cutoff24h = Date.now() - 24 * 60 * 60 * 1000;
  const cutoff48h = Date.now() - 48 * 60 * 60 * 1000;
  const needsAttentionDrafts = drafts.filter(
    (draft) => isNeedsAttentionDraft(draft) && Date.parse(draft.publishedAt) >= cutoff24h
  );
  const recentPublishedNews = publishedNews.filter((item) => Date.parse(item.publishedAt) >= cutoff48h);
  const recentContentPlan = contentPlan
    .filter((item) => Date.parse(item.updatedAt || item.createdAt) >= cutoff24h)
    .slice(0, 8);
  const publishedVisibleNews = recentPublishedNews.filter((item) => item.visibility !== "hidden");
  const hiddenPublishedNews = recentPublishedNews.filter((item) => item.visibility === "hidden");

  return (
    <main className="page-shell">
      <StudioDiagnosticsRefresh enabled={activeTab === "diagnostics"} />
      <section className="hero" style={{ paddingBottom: 22 }}>
        <div className="eyebrow">Редакторская студия</div>
        <h1 style={{ fontSize: "clamp(2.2rem, 5vw, 4rem)" }}>Редакторский workspace</h1>
        <p>
          {isLive
            ? "Студия читает живые данные из editorial API: prompt configs, draft articles и review-результаты."
            : "API editorial-слоя сейчас недоступен, поэтому показывается резервный режим просмотра."}
        </p>
        {notice ? <p className="source-card-error">{notice}</p> : null}
        {data.liveError ? <p className="source-card-error">Ошибка загрузки live-данных: {data.liveError}</p> : null}
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
          <form action={logoutAdminNow}>
            <PendingSubmitButton
              className="button-secondary"
              idleLabel="Выйти"
              pendingLabel="Выходим..."
            />
          </form>
        </div>
        <div className="section-card" style={{ marginTop: 18 }}>
          <p style={{ margin: 0 }}>
            Режим AI:{" "}
            <strong>
              {editorialStatus.openaiEnabled
                ? `${editorialStatus.providerLabel} live (editorial: ${editorialStatus.openaiModel}, search: ${editorialStatus.openaiSearchModel}, ${editorialStatus.apiStyle})`
                : "шаблонный fallback"}
            </strong>
          </p>
          <p style={{ margin: "6px 0 0 0" }}>
            Веб-поиск: <strong>{editorialStatus.webSearchEnabled ? "включен" : "выключен"}</strong>
          </p>
        </div>
        <div className="stats-grid" style={{ marginTop: 18 }}>
          <div className="stat">
            <strong>{publishedVisibleNews.length}</strong>
            <span>в ленте за 48 часов</span>
          </div>
          <div className="stat">
            <strong>{hiddenPublishedNews.length}</strong>
            <span>скрыты за 48 часов</span>
          </div>
          <div className="stat">
            <strong>{rawDraftPairs.length}</strong>
            <span>карточек в диагностике</span>
          </div>
        </div>
        <div className="tab-row" style={{ marginTop: 18 }}>
          <Link className={`tab-link ${activeTab === "published" ? "is-active" : ""}`} href="/studio?tab=published">
            Опубликованные
          </Link>
          <Link className={`tab-link ${activeTab === "diagnostics" ? "is-active" : ""}`} href="/studio?tab=diagnostics">
            Диагностика
          </Link>
        </div>
      </section>

      {activeTab === "attention" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Требуют внимания</h2>
            <p>
              Главный рабочий список редактора: hold, rewrite, skip, fallback и спорные случаи перед публикацией.
              Показываем только свежие кейсы за последние 24 часа.
            </p>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          {needsAttentionDrafts.length ? (
            needsAttentionDrafts.map((draft) => (
              <article key={draft.id} className="news-card">
                <span>
                  {formatCategoryLabel(draft.category)} · {formatDraftStatus(draft.status)} · {formatPublishDecision(draft.publishDecision)}
                </span>
                <h3>{draft.title}</h3>
                <p>{draft.reviewSummary ?? draft.publishReason ?? "Материал требует внимания редактора."}</p>
                <p className="footer-note" style={{ marginTop: 12 }}>
                  {draft.sourceTitle} ·{" "}
                  <time dateTime={draft.publishedAt}>
                    {formatMoscowDateTime(draft.publishedAt)}
                  </time>
                </p>
                <p className="footer-note">
                  Review: {formatReviewStatus(draft.reviewStatus)} · Mode: {draft.generationMode}
                </p>
              </article>
            ))
          ) : (
            <article className="news-card">
              <h3>Сейчас всё спокойно</h3>
              <p>Свежих материалов с hold/rewrite/skip на текущем срезе нет.</p>
            </article>
          )}
        </div>
      </section>
      ) : null}

      {activeTab === "published" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Опубликованные материалы</h2>
            <p>Публичная лента и скрытые материалы для moderation. Показываем только свежие за последние 48 часов.</p>
          </div>
        </div>
        <div className="stats-grid" style={{ marginBottom: 18 }}>
          <div className="stat">
            <strong>{publishedVisibleNews.length}</strong>
            <span>видны в ленте</span>
          </div>
          <div className="stat">
            <strong>{hiddenPublishedNews.length}</strong>
            <span>скрыты</span>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          {recentPublishedNews.length ? (
            recentPublishedNews.map((item) => (
              <article key={item.id} className="news-card">
                <span>
                  {formatCategoryLabel(item.category)} · {formatNewsVisibility(item.visibility)} · {item.aiReviewed ? "прошла AI-редактуру" : "публичная запись"}
                </span>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
                <p className="footer-note" style={{ marginTop: 12 }}>
                  {item.source} ·{" "}
                  <time dateTime={item.publishedAt}>
                    {formatMoscowDateTime(item.publishedAt)}
                  </time>
                </p>
                <div className="hero-actions" style={{ marginTop: 16 }}>
                  {item.articleSlug && item.visibility !== "hidden" ? (
                    <Link className="button-secondary" href={`/news/${item.articleSlug}`}>
                      Открыть статью
                    </Link>
                  ) : null}
                  {item.link ? (
                    <a className="button-secondary" href={item.link} target="_blank" rel="noreferrer">
                      Первоисточник
                    </a>
                  ) : null}
                  <form action={item.visibility === "hidden" ? unhidePublishedNewsNow : hidePublishedNewsNow}>
                    <input type="hidden" name="newsItemId" value={item.id} />
                    <PendingSubmitButton
                      className={item.visibility === "hidden" ? "button-primary" : "button-secondary"}
                      idleLabel={item.visibility === "hidden" ? "Вернуть в ленту" : "Скрыть"}
                      pendingLabel={item.visibility === "hidden" ? "Возвращаем..." : "Скрываем..."}
                    />
                  </form>
                </div>
              </article>
            ))
          ) : (
            <article className="news-card">
              <h3>Опубликованных материалов пока нет</h3>
              <p>Когда publish-этап выпустит новости, здесь появится moderation-блок по публичной ленте.</p>
            </article>
          )}
        </div>
      </section>
      ) : null}

      {activeTab === "diagnostics" ? (
      <>
      <section>
        <div className="section-head">
          <div>
            <h2>Исходник и AI-версия последнего pipeline</h2>
            <p>
              Глубокая диагностика последнего ingest-прогона: слева сырой RSS-вход, справа результат writer/editor.
              Вкладка обновляется автоматически каждые 30 секунд.
            </p>
          </div>
        </div>
        <div className="compare-grid">
          {rawDraftPairs.length ? rawDraftPairs.map(({ rawItem, draft }) => (
            <article key={rawItem.id} className="compare-card">
              <div className="compare-panel">
                <span>Сырой RSS-вход</span>
                <h3>{rawItem.title}</h3>
                <div className="compare-block">
                  <strong>Исходный заголовок</strong>
                  <p>{rawItem.title}</p>
                </div>
                <div className="compare-block">
                  <strong>Исходное summary</strong>
                  <p>{rawItem.summary}</p>
                </div>
                {rawItem.lead ? (
                  <div className="compare-block">
                    <strong>Исходный lead</strong>
                    <p>{rawItem.lead}</p>
                  </div>
                ) : null}
                {rawItem.tags.length ? (
                  <div className="compare-block">
                    <strong>Исходные теги</strong>
                    <p>{rawItem.tags.join(", ")}</p>
                  </div>
                ) : null}
                <div className="compare-block">
                  <strong>Данные источника</strong>
                  <p>
                    Дата публикации:{" "}
                    <time dateTime={rawItem.publishedAt}>
                      {formatMoscowDateTime(rawItem.publishedAt)}
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
                  <strong>Исходный full text / search brief</strong>
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
                  <strong>Происхождение full text</strong>
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
                      <p>Источники веб-поиска:</p>
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
                  <strong>Статус pipeline</strong>
                  <p>{describePipelineState(rawItem)}</p>
                  <p>
                    <strong>Full text:</strong> {describeEnrichmentBlock(rawItem)}
                  </p>
                  <p>
                    <strong>Editorial:</strong> {describeEditorialBlock(rawItem, draft)}
                  </p>
                  <p>
                    <strong>Publish:</strong> {describePublishBlock(draft)}
                  </p>
                  {rawItem.contentPlanReason ? <p>Причина отбора: {rawItem.contentPlanReason}</p> : null}
                </div>
                <p className="footer-note">
                  {rawItem.sourceTitle} · {rawItem.triageLabel} · score {rawItem.importanceScore}
                </p>
                {rawItem.scoreBreakdown?.length ? (
                  <div className="compare-block">
                    <strong>Почему такой score</strong>
                    {rawItem.scoreBreakdown.map((line) => (
                      <p key={`${rawItem.id}-score-${line}`}>{line}</p>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="compare-panel">
                <span>{draft ? `AI-черновик · ${draft.generationMode}` : "AI-черновик еще не создан"}</span>
                <h3>{draft?.title ?? "Черновик ещё не создан"}</h3>
                <div className="compare-block">
                  <strong>Заголовок writer</strong>
                  <p>{draft?.writerTitle ?? draft?.title ?? "Для этой новости пока нет draft-версии."}</p>
                </div>
                <div className="compare-block">
                  <strong>Dek от writer</strong>
                  <p>{draft?.writerDek ?? draft?.dek ?? "Запустите editorial run, чтобы получить AI-версию."}</p>
                </div>
                {draft?.status === "fallback_only" ? (
                  <p className="source-card-error">
                    Только fallback: этот draft сохранен только для внутреннего просмотра и не может попасть в публикацию.
                  </p>
                ) : null}
                {draft?.generationMode === "template" ? (
                  <p className="source-card-error">
                    Это шаблонный fallback. Такой draft не должен автоматически попадать в публикацию.
                  </p>
                ) : null}
                <div className="compare-block">
                  <strong>Редакционный статус</strong>
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
                  <strong>Черновик writer</strong>
                  <div className="compare-text-surface">
                    {draft?.writerBody || draft?.body ? (
                      (draft?.writerBody ?? draft?.body ?? "")
                        .split("\n\n")
                        .filter(Boolean)
                        .map((paragraph, index) => <p key={`${draft.id}-${index}`}>{paragraph}</p>)
                    ) : (
                      <p>Для этой новости пока нет draft-версии. Запустите editorial run.</p>
                    )}
                  </div>
                </div>
                {draft && hasEditorChanges(draft) ? (
                  <div className="compare-block">
                    <strong>Финальная версия editor</strong>
                    <p><strong>Title:</strong> {draft.title}</p>
                    <p><strong>Dek:</strong> {draft.dek}</p>
                    <div className="compare-text-surface">
                      {draft.body
                        .split("\n\n")
                        .filter(Boolean)
                        .map((paragraph, index) => <p key={`${draft.id}-editor-${index}`}>{paragraph}</p>)}
                    </div>
                  </div>
                ) : null}
              </div>
            </article>
          )) : (
            <article className="news-card">
              <h3>В последнем pipeline не было новых raw-новостей</h3>
              <p>
                Когда следующий ingest сохранит свежие материалы, они появятся здесь вместе с draft/review/publish-статусами.
              </p>
            </article>
          )}
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <h2>Контент-план</h2>
            <p>Это промежуточный слой между triage raw_items и генерацией draft-статей. Показываем только свежие записи за последние 24 часа.</p>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          {recentContentPlan.length ? (
            recentContentPlan.map((item) => (
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
            ))
          ) : (
            <article className="news-card">
              <h3>Свежих записей контент-плана нет</h3>
              <p>Здесь показываются только недавние записи за последние 24 часа, чтобы диагностика не превращалась в архив.</p>
            </article>
          )}
        </div>
      </section>
      </>
      ) : null}

    </main>
  );
}
