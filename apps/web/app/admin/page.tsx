import Link from "next/link";
import type { Metadata } from "next";

import { PendingSubmitButton } from "@/components/pending-submit-button";
import { formatCategoryLabel } from "@/lib/category";
import { formatMoscowDateTime } from "@/lib/dates";
import { getEditorialStudioData, type DraftArticle, type RawItem } from "@/lib/editorial";
import { requireAdminSession } from "@/lib/auth";
import { logoutAdminNow } from "@/app/auth-actions";

import {
  createSourceNow,
  cleanupPromptVersionsNow,
  deleteSourceNow,
  probeNewSourceNow,
  resetDatabaseNow,
  runEditorialSchedulerNow,
  runManualPipelineNow,
  runEnrichmentNow,
  runEnrichmentSchedulerNow,
  runPublishSchedulerNow,
  runSchedulerNow,
  savePublishSchedulerSettingsNow,
  saveEditorialSchedulerSettingsNow,
  saveEnrichmentSchedulerSettingsNow,
  saveSchedulerSettingsNow,
  savePromptVersion
} from "./actions";

export const dynamic = "force-dynamic";
export const revalidate = 0;
export const metadata: Metadata = {
  title: "Админка",
  robots: {
    index: false,
    follow: false
  }
};

type AdminSearchParams = {
  notice?: string;
  detail?: string;
  tab?: string;
  sourceKey?: string;
  sourceTitle?: string;
  sourceUrl?: string;
  sourceType?: string;
  resolvedSourceType?: string;
  resolvedSourceUrl?: string;
  sourceNotes?: string;
  probeOk?: string;
  probeReadiness?: string;
  probeCount?: string;
  supportsRss?: string;
  supportsNewsSitemap?: string;
  supportsSitemap?: string;
  supportsScraping?: string;
  probeFullTextOk?: string;
  probeFullTextMethod?: string;
  probeLeadOk?: string;
  probeTagsCount?: string;
  probeSampleTitle?: string;
  probeSampleUrl?: string;
};

type AdminTab = "pipeline" | "sources" | "prompts" | "diagnostics" | "costs";

export default async function AdminPage({
  searchParams
}: {
  searchParams?: Promise<AdminSearchParams>;
}) {
  await requireAdminSession("/admin");
  const params = (await searchParams) ?? {};
  const notice = getNoticeMessage(params.notice, params.detail);
  const sourceDraft = {
    key: params.sourceKey ?? "",
    title: params.sourceTitle ?? "",
    url: params.resolvedSourceUrl ?? params.sourceUrl ?? "",
    type: params.resolvedSourceType ?? params.sourceType ?? "auto",
    notes: params.sourceNotes ?? "",
  };
  const draftProbe =
    params.notice === "source-draft-probed" || params.notice === "source-draft-probe-error"
      ? {
          ok: params.probeOk === "true",
          readiness: params.probeReadiness ?? "unknown",
          count: params.probeCount ?? "0",
          supportsRss: params.supportsRss === "true",
          supportsNewsSitemap: params.supportsNewsSitemap === "true",
          supportsSitemap: params.supportsSitemap === "true",
          supportsScraping: params.supportsScraping === "true",
          fullTextOk: params.probeFullTextOk === "true",
          fullTextMethod: params.probeFullTextMethod,
          leadOk: params.probeLeadOk === "true",
          tagsCount: params.probeTagsCount ?? "0",
          sampleTitle: params.probeSampleTitle,
          sampleUrl: params.probeSampleUrl
        }
      : null;
  const {
    prompts,
    rawItems,
    drafts,
    reviews,
    contentPlan,
    editorialStatus,
    sourceStates,
    sources,
    scheduler,
    enrichmentScheduler,
    editorialScheduler,
    publishScheduler,
    pipelineRuns,
    aiUsageSummary,
    isLive,
    liveError
  } = await getEditorialStudioData();
  const promptGroups = groupPrompts(prompts);
  const sourceStateMap = new Map(sourceStates.map((state) => [state.sourceKey, state]));
  const activeSources = sources.filter((source) => source.status === "active");
  const pipelineQueues = buildPipelineQueues(rawItems, drafts);
  const duplicateAudit = buildDuplicateAudit(rawItems);
  const activeTab = getAdminTab(params.tab);
  const currentRawItemIds = new Set(rawItems.map((item) => item.id));
  const currentPipelineContentPlan = contentPlan.filter((item) => currentRawItemIds.has(item.rawItemId));
  const aiUsageGroupTotals = buildAiUsageGroupTotals(aiUsageSummary.items);
  const aiUsageDailyTotals = buildAiUsageDailyTotals(aiUsageSummary.items);
  const latestPipelineFunnel = buildLatestPipelineFunnel({
    pipelineRuns,
    activeSourceCount: activeSources.length,
    ingestBatchSize: scheduler.batchSize,
    currentRawItems: rawItems,
    currentContentPlan: currentPipelineContentPlan
  });

  return (
    <main className="page-shell">
      <section className="hero" style={{ paddingBottom: 22 }}>
        <div className="eyebrow">Админка</div>
        <h1 style={{ fontSize: "clamp(2.2rem, 5vw, 4rem)" }}>Управление источниками, промптами и pipeline</h1>
            <p>
              {isLive
                ? "Админка уже подключена к живому editorial API. Здесь можно выпускать новые версии промптов и вручную запускать редакционный цикл."
                : "API сейчас недоступен, поэтому админка показывает fallback-состояние и не сможет сохранить изменения."}
            </p>
            {!isLive && liveError ? <p className="source-card-error">{liveError}</p> : null}
        <div className="hero-actions">
          <form action={logoutAdminNow}>
            <PendingSubmitButton
              className="button-secondary"
              idleLabel="Выйти"
              pendingLabel="Выходим..."
            />
          </form>
          <form action={resetDatabaseNow}>
            <PendingSubmitButton
              className="button-secondary"
              idleLabel="Очистить БД"
              pendingLabel="Очищаем БД..."
              disabled={!isLive}
            />
          </form>
          <Link className="button-secondary" href="/studio">
            Открыть studio
          </Link>
          <Link className="button-secondary" href="/news">
            К ленте
          </Link>
        </div>
        <div className="tab-row" style={{ marginTop: 18 }}>
          <Link
            className={`tab-link${activeTab === "pipeline" ? " is-active" : ""}`}
            href="/admin?tab=pipeline"
          >
            Запуски
          </Link>
          <Link
            className={`tab-link${activeTab === "sources" ? " is-active" : ""}`}
            href="/admin?tab=sources"
          >
            Источники
          </Link>
          <Link
            className={`tab-link${activeTab === "prompts" ? " is-active" : ""}`}
            href="/admin?tab=prompts"
          >
            Промпты
          </Link>
          <Link
            className={`tab-link${activeTab === "diagnostics" ? " is-active" : ""}`}
            href="/admin?tab=diagnostics"
          >
            Диагностика
          </Link>
          <Link
            className={`tab-link${activeTab === "costs" ? " is-active" : ""}`}
            href="/admin?tab=costs"
          >
            Стоимость
          </Link>
        </div>
        {notice ? (
          <div className="section-card" style={{ marginTop: 18 }}>
            <p style={{ margin: 0 }}>{notice}</p>
          </div>
        ) : null}
      </section>

      {activeTab === "pipeline" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Воронка последнего pipeline</h2>
            <p>
              Быстрый ответ на главный вопрос: сколько новостей могли взять, сколько реально нашли и где они отсеклись.
            </p>
          </div>
        </div>
        {latestPipelineFunnel ? (
          <>
            <div className="stats-grid" style={{ marginBottom: 18 }}>
              {latestPipelineFunnel.steps.map((step) => (
                <div key={step.label} className="stat">
                  <strong>{formatNumber(step.value)}</strong>
                  <span>{step.label}</span>
                </div>
              ))}
            </div>
            <div className="admin-table-wrap" style={{ marginBottom: 24 }}>
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Источник</th>
                    <th>Лимит</th>
                    <th>Прочитано</th>
                    <th>Свежие</th>
                    <th>Отсечено</th>
                    <th>Причины</th>
                  </tr>
                </thead>
                <tbody>
                  {latestPipelineFunnel.sources.map((source) => (
                    <tr key={source.key}>
                      <td>{source.title}</td>
                      <td>{formatNumber(source.limit)}</td>
                      <td>{formatNumber(source.parsed)}</td>
                      <td>{formatNumber(source.fresh)}</td>
                      <td>{formatNumber(source.filtered)}</td>
                      <td>{source.reasons || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {latestPipelineFunnel.notes.length ? (
              <div className="news-grid" style={{ gridTemplateColumns: "1fr", marginBottom: 28 }}>
                <article className="news-card">
                  <span>вывод</span>
                  <h3>Где сузилась воронка</h3>
                  <ul style={{ margin: "10px 0 0", paddingLeft: 18, display: "grid", gap: 8 }}>
                    {latestPipelineFunnel.notes.map((note) => (
                      <li key={note} className="footer-note">{note}</li>
                    ))}
                  </ul>
                </article>
              </div>
            ) : null}
            {latestPipelineFunnel.skippedItems.length ? (
              <div className="news-grid" style={{ gridTemplateColumns: "1fr", marginBottom: 28 }}>
                <article className="news-card">
                  <span>отсеченные новости</span>
                  <h3>Конкретные причины по материалам</h3>
                  <ul style={{ margin: "10px 0 0", paddingLeft: 18, display: "grid", gap: 8 }}>
                    {latestPipelineFunnel.skippedItems.slice(0, 10).map((item, index) => (
                      <li key={`${item.title}-${index}`} className="footer-note">
                        <strong>{item.title}</strong>
                        {item.reason ? ` — ${item.reason}` : ""}
                      </li>
                    ))}
                  </ul>
                  {latestPipelineFunnel.skippedItems.length > 10 ? (
                    <p className="footer-note" style={{ marginTop: 10 }}>
                      И ещё {latestPipelineFunnel.skippedItems.length - 10}.
                    </p>
                  ) : null}
                </article>
              </div>
            ) : null}
          </>
        ) : (
          <article className="news-card" style={{ marginBottom: 24 }}>
            <h3>Последний ingest еще не найден</h3>
            <p>После следующего запуска pipeline здесь появится воронка по источникам и этапам.</p>
          </article>
        )}

        <div className="section-head">
          <div>
            <h2>История прогонов</h2>
            <p>Последние прогоны ingest, enrichment и editorial, чтобы быстро понимать, что сработало, сколько заняло и где была ошибка.</p>
          </div>
        </div>
        <div
          className="news-grid"
          style={{ gridTemplateColumns: "1fr", maxHeight: 520, overflowY: "auto", paddingRight: 4 }}
        >
          {pipelineRuns.length ? (
            pipelineRuns.map((run) => (
              <article key={run.id} className="news-card">
                <span>
                  {formatPipelinePhase(run.phase)} · {formatPipelineTrigger(run.trigger)} · {run.status}
                </span>
                <h3>{formatDateTime(run.startedAt)}</h3>
                <p className="footer-note">
                  Длительность: {formatDuration(run.durationMs)} · завершен: {formatDateTime(run.finishedAt)}
                </p>
                {renderPipelineRunMetrics(run)}
                {run.error ? <p className="source-card-error">{run.error}</p> : null}
              </article>
            ))
          ) : (
            <article className="news-card">
              <h3>История прогонов пока пуста</h3>
              <p>После первого ingest, enrichment или editorial run здесь появятся записи со статусом, длительностью и счетчиками.</p>
            </article>
          )}
        </div>
      </section>
      ) : null}

      {activeTab === "diagnostics" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Очереди pipeline</h2>
            <p>
              Здесь видно, какие новости уже ждут следующий этап: добор full text, генерацию материала или
              автопубликацию. Это особенно полезно во время <code>pipeline:loop</code>, когда этапы идут по своему
              расписанию.
            </p>
          </div>
        </div>
        <div className="stats-grid" style={{ marginBottom: 18 }}>
          <div className="stat">
            <strong>{pipelineQueues.waitingEnrichment.length}</strong>
            <span>ждут full text</span>
          </div>
          <div className="stat">
            <strong>{pipelineQueues.waitingEditorial.length}</strong>
            <span>ждут editorial</span>
          </div>
          <div className="stat">
            <strong>{pipelineQueues.waitingPublish.length}</strong>
            <span>ждут publish</span>
          </div>
        </div>
        <div className="admin-grid">
          <article className="news-card">
            <span>queue</span>
            <h3>Ждут full text</h3>
            <p className="footer-note">
              Следующий enrichment: {formatDateTime(enrichmentScheduler.nextRunAt)}
            </p>
            {renderQueueList(
              pipelineQueues.waitingEnrichment,
              (item) => `${item.title} — ${item.sourceTitle}`
            )}
          </article>
          <article className="news-card">
            <span>queue</span>
            <h3>Ждут editorial</h3>
            <p className="footer-note">
              Следующий editorial: {formatDateTime(editorialScheduler.nextRunAt)}
            </p>
            {renderQueueList(
              pipelineQueues.waitingEditorial,
              (item) => `${item.title} — ${item.sourceTitle}`
            )}
          </article>
          <article className="news-card">
            <span>queue</span>
            <h3>Ждут publish</h3>
            <p className="footer-note">
              Следующий publish: {formatDateTime(publishScheduler.nextRunAt)}
            </p>
            {renderQueueList(
              pipelineQueues.waitingPublish,
              (item) => `${item.title} — ${item.sourceTitle}`
            )}
          </article>
        </div>
      </section>
      ) : null}

      {activeTab === "diagnostics" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Duplicate audit</h2>
            <p>
              Здесь видно, сколько новостей отсеклось как дубликаты на каждом этапе и по каким свежим кейсам
              сработало совпадение.
            </p>
          </div>
        </div>
        <div className="stats-grid" style={{ marginBottom: 18 }}>
          <div className="stat">
            <strong>{duplicateAudit.ingest.length}</strong>
            <span>дубли на ingest</span>
          </div>
          <div className="stat">
            <strong>{duplicateAudit.afterEnrichment.length}</strong>
            <span>дубли после enrichment</span>
          </div>
          <div className="stat">
            <strong>{duplicateAudit.other.length}</strong>
            <span>прочие duplicate-кейсы</span>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "1fr" }}>
          {duplicateAudit.all.length ? (
            duplicateAudit.all.slice(0, 8).map((item) => (
              <article key={item.id} className="news-card">
                <span>{formatDuplicateStage(item.duplicateStage)}</span>
                <h3>{item.title}</h3>
                <p>{item.duplicateReason || "Новость помечена как дубликат."}</p>
                <p className="footer-note" style={{ marginTop: 12 }}>
                  {item.sourceTitle} · {item.triageLabel} · score {item.importanceScore}
                </p>
              </article>
            ))
          ) : (
            <article className="news-card">
              <h3>Свежих duplicate-кейсов пока нет</h3>
              <p>После следующего прогона ingest/enrichment здесь появятся последние отсеченные дубли с причиной.</p>
            </article>
          )}
        </div>
      </section>
      ) : null}

      {activeTab === "pipeline" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Статус AI</h2>
            <p>Здесь видно, используем ли мы живой OpenAI-слой или работаем на шаблонном fallback.</p>
          </div>
        </div>
        <div className="stats-grid">
          <div className="stat">
            <strong>{editorialStatus.openaiEnabled ? "Live" : "Fallback"}</strong>
            <span>
              {editorialStatus.openaiEnabled
                ? `${editorialStatus.providerLabel} · ${editorialStatus.apiStyle}`
                : "живой AI сейчас не активен"}
            </span>
          </div>
          <div className="stat">
            <strong>{editorialStatus.openaiModel}</strong>
            <span>текущая модель writer/editor</span>
          </div>
          <div className="stat">
            <strong>{editorialStatus.openaiSearchModel}</strong>
            <span>текущая модель search/extraction fallback</span>
          </div>
          <div className="stat">
            <strong>{editorialStatus.webSearchEnabled ? "On" : "Off"}</strong>
            <span>web search для extraction fallback</span>
          </div>
          <div className="stat">
            <strong>{drafts.filter((draft) => draft.generationMode !== "template").length}</strong>
            <span>drafts в выборке, сгенерированные живой моделью</span>
          </div>
          <div className="stat">
            <strong>{drafts.filter((draft) => draft.status === "fallback_only").length}</strong>
            <span>template fallback-only, внутренние и непубликуемые</span>
          </div>
        </div>
      </section>
      ) : null}

      {activeTab === "pipeline" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Расписание pipeline</h2>
            <p>
              Автосбор должен запускать ingestion только по расписанию и забирать только новые новости относительно
              текущего source-state, а не всю ленту заново.
            </p>
          </div>
          <form action={runManualPipelineNow}>
            <PendingSubmitButton
              className="button-primary"
              idleLabel="Прогнать ingest -> full text -> editorial"
              pendingLabel="Прогоняем pipeline..."
              disabled={!isLive}
            />
          </form>
        </div>
        <div className="admin-grid" style={{ gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 0.9fr)" }}>
          <article className="news-card">
            <span>scheduler config</span>
            <h3>Автозагрузка новостей</h3>
            <form action={saveSchedulerSettingsNow} className="prompt-form">
              <label className="checkbox-row">
                <input name="enabled" type="checkbox" defaultChecked={scheduler.enabled} />
                <span>Включить автоматический сбор новостей</span>
              </label>
              <label className="field field-compact">
                <span>Интервал в минутах</span>
                <select name="intervalMinutes" defaultValue={String(scheduler.intervalMinutes)}>
                  <option value="5">5 минут</option>
                  <option value="10">10 минут</option>
                  <option value="15">15 минут</option>
                  <option value="20">20 минут</option>
                  <option value="30">30 минут</option>
                  <option value="60">60 минут</option>
                  <option value="120">120 минут</option>
                  <option value="180">180 минут</option>
                  <option value="360">360 минут</option>
                </select>
              </label>
              <label className="field field-compact">
                <span>Размер пачки на источник</span>
                <select name="batchSize" defaultValue={String(scheduler.batchSize)}>
                  <option value="3">3 новости</option>
                  <option value="5">5 новостей</option>
                  <option value="10">10 новостей</option>
                  <option value="15">15 новостей</option>
                  <option value="20">20 новостей</option>
                </select>
              </label>
              <label className="checkbox-row">
                <input name="runEnrichment" type="checkbox" defaultChecked={scheduler.runEnrichment} />
                <span>Сразу добирать full text и enrichment в автозапуске</span>
              </label>
              <p className="footer-note">
                В production внешний cron/job должен периодически дёргать scheduler tick, а backend сам решает,
                пора ли реально запускать ingestion.
              </p>
              <p className="footer-note">
                Если enrichment выключен, автозапуск работает быстрее и стабильнее, а тяжелое добирание текста можно
                выносить в отдельный фоновый шаг.
              </p>
              <div className="source-button-row">
                <PendingSubmitButton
                  className="button-primary"
                  idleLabel="Сохранить scheduler"
                  pendingLabel="Сохраняем scheduler..."
                  disabled={!isLive}
                />
                <PendingSubmitButton
                  className="button-secondary"
                  formAction={runSchedulerNow}
                  idleLabel="Запустить сейчас"
                  pendingLabel="Запускаем scheduler..."
                  disabled={!isLive}
                />
                <PendingSubmitButton
                  className="button-secondary"
                  formAction={runEnrichmentNow}
                  idleLabel="Запустить enrichment"
                  pendingLabel="Запускаем enrichment..."
                  disabled={!isLive}
                />
              </div>
            </form>
          </article>
          <article className="news-card">
            <span>scheduler state</span>
            <h3>{scheduler.enabled ? "Scheduler включён" : "Scheduler выключен"}</h3>
            <p className="footer-note">Интервал: {scheduler.intervalMinutes} мин.</p>
            <p className="footer-note">Размер пачки: {scheduler.batchSize} новостей на источник</p>
            <p className="footer-note">
              Enrichment в автозапуске: {scheduler.runEnrichment ? "включён" : "выключен"}
            </p>
            <p className="footer-note">Последний запуск: {formatDateTime(scheduler.lastRunAt)}</p>
            <p className="footer-note">Следующий запуск: {formatDateTime(scheduler.nextRunAt)}</p>
            <p className="footer-note">Последний статус: {scheduler.lastStatus}</p>
            <p className="footer-note">Найдено новых новостей: {scheduler.lastFoundCount}</p>
            <p className="footer-note">Сохранено в сырой поток: {scheduler.lastSavedCount}</p>
            <p className="footer-note">Добавлено в ленту: {scheduler.lastPublishedCount}</p>
            {scheduler.lastError ? <p className="source-card-error">{scheduler.lastError}</p> : null}
          </article>
        </div>
        <div className="admin-grid" style={{ gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 0.9fr)", marginTop: 20 }}>
          <article className="news-card">
            <span>enrichment scheduler config</span>
            <h3>Автодобор full text</h3>
            <form action={saveEnrichmentSchedulerSettingsNow} className="prompt-form">
              <label className="checkbox-row">
                <input name="enabled" type="checkbox" defaultChecked={enrichmentScheduler.enabled} />
                <span>Включить автоматический enrichment</span>
              </label>
              <label className="field field-compact">
                <span>Интервал в минутах</span>
                <select name="intervalMinutes" defaultValue={String(enrichmentScheduler.intervalMinutes)}>
                  <option value="5">5 минут</option>
                  <option value="10">10 минут</option>
                  <option value="15">15 минут</option>
                  <option value="20">20 минут</option>
                  <option value="30">30 минут</option>
                  <option value="60">60 минут</option>
                  <option value="120">120 минут</option>
                  <option value="180">180 минут</option>
                  <option value="360">360 минут</option>
                </select>
              </label>
              <label className="field field-compact">
                <span>Размер пачки raw_items</span>
                <select name="batchSize" defaultValue={String(enrichmentScheduler.batchSize)}>
                  <option value="5">5 новостей</option>
                  <option value="10">10 новостей</option>
                  <option value="15">15 новостей</option>
                  <option value="20">20 новостей</option>
                  <option value="30">30 новостей</option>
                  <option value="50">50 новостей</option>
                </select>
              </label>
              <p className="footer-note">
                Этот этап отдельно добирает <strong>full text</strong>, <strong>lead</strong> и <strong>tags</strong>
                для уже собранных raw_items. Сейчас он работает по мягкому shortlist: сначала берет самые неполные и более
                приоритетные новости, а свежие low-элементы оставляет как fallback, если в пачке остается место.
              </p>
              <div className="source-button-row">
                <PendingSubmitButton
                  className="button-primary"
                  idleLabel="Сохранить enrichment scheduler"
                  pendingLabel="Сохраняем enrichment scheduler..."
                  disabled={!isLive}
                />
                <PendingSubmitButton
                  className="button-secondary"
                  formAction={runEnrichmentSchedulerNow}
                  idleLabel="Запустить enrichment scheduler"
                  pendingLabel="Запускаем enrichment scheduler..."
                  disabled={!isLive}
                />
              </div>
            </form>
          </article>
          <article className="news-card">
            <span>enrichment scheduler state</span>
            <h3>{enrichmentScheduler.enabled ? "Enrichment scheduler включён" : "Enrichment scheduler выключен"}</h3>
            <p className="footer-note">Интервал: {enrichmentScheduler.intervalMinutes} мин.</p>
            <p className="footer-note">Размер пачки: {enrichmentScheduler.batchSize} raw_items</p>
            <p className="footer-note">Последний запуск: {formatDateTime(enrichmentScheduler.lastRunAt)}</p>
            <p className="footer-note">Следующий запуск: {formatDateTime(enrichmentScheduler.nextRunAt)}</p>
            <p className="footer-note">Последний статус: {enrichmentScheduler.lastStatus}</p>
            <p className="footer-note">Обработано raw_items: {enrichmentScheduler.lastProcessedCount}</p>
            <p className="footer-note">Реально обогащено: {enrichmentScheduler.lastEnrichedCount}</p>
            {enrichmentScheduler.lastError ? <p className="source-card-error">{enrichmentScheduler.lastError}</p> : null}
          </article>
        </div>
        <div className="admin-grid" style={{ gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 0.9fr)", marginTop: 20 }}>
          <article className="news-card">
            <span>editorial scheduler config</span>
            <h3>Автогенерация материалов</h3>
            <form action={saveEditorialSchedulerSettingsNow} className="prompt-form">
              <label className="checkbox-row">
                <input name="enabled" type="checkbox" defaultChecked={editorialScheduler.enabled} />
                <span>Включить автоматический editorial</span>
              </label>
              <label className="field field-compact">
                <span>Интервал в минутах</span>
                <select name="intervalMinutes" defaultValue={String(editorialScheduler.intervalMinutes)}>
                  <option value="5">5 минут</option>
                  <option value="10">10 минут</option>
                  <option value="15">15 минут</option>
                  <option value="20">20 минут</option>
                  <option value="30">30 минут</option>
                  <option value="60">60 минут</option>
                  <option value="120">120 минут</option>
                  <option value="180">180 минут</option>
                  <option value="360">360 минут</option>
                </select>
              </label>
              <label className="field field-compact">
                <span>Размер пачки</span>
                <select name="batchSize" defaultValue={String(editorialScheduler.batchSize)}>
                  <option value="2">2 новости</option>
                  <option value="3">3 новости</option>
                  <option value="5">5 новостей</option>
                  <option value="10">10 новостей</option>
                  <option value="15">15 новостей</option>
                </select>
              </label>
              <p className="footer-note">
                Этот этап сначала обновляет <strong>content plan</strong> для shortlisted-новостей, а затем запускает
                <strong> writer/editor</strong> и переводит готовые материалы дальше по pipeline.
              </p>
              <div className="source-button-row">
                <PendingSubmitButton
                  className="button-primary"
                  idleLabel="Сохранить editorial scheduler"
                  pendingLabel="Сохраняем editorial scheduler..."
                  disabled={!isLive}
                />
                <PendingSubmitButton
                  className="button-secondary"
                  formAction={runEditorialSchedulerNow}
                  idleLabel="Запустить editorial scheduler"
                  pendingLabel="Запускаем editorial scheduler..."
                  disabled={!isLive}
                />
              </div>
            </form>
          </article>
          <article className="news-card">
            <span>editorial scheduler state</span>
            <h3>{editorialScheduler.enabled ? "Editorial scheduler включён" : "Editorial scheduler выключен"}</h3>
            <p className="footer-note">Интервал: {editorialScheduler.intervalMinutes} мин.</p>
            <p className="footer-note">Размер пачки: {editorialScheduler.batchSize} новостей</p>
            <p className="footer-note">Последний запуск: {formatDateTime(editorialScheduler.lastRunAt)}</p>
            <p className="footer-note">Следующий запуск: {formatDateTime(editorialScheduler.nextRunAt)}</p>
            <p className="footer-note">Последний статус: {editorialScheduler.lastStatus}</p>
            <p className="footer-note">Добавлено в content plan: {editorialScheduler.lastPlannedCount}</p>
            <p className="footer-note">Сгенерировано draft: {editorialScheduler.lastGeneratedCount}</p>
            <p className="footer-note">Проверено editor-review: {editorialScheduler.lastReviewedCount}</p>
            {editorialScheduler.lastError ? <p className="source-card-error">{editorialScheduler.lastError}</p> : null}
          </article>
        </div>
        <div className="admin-grid" style={{ gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 0.9fr)", marginTop: 20 }}>
          <article className="news-card">
            <span>publish scheduler config</span>
            <h3>Автопубликация</h3>
            <form action={savePublishSchedulerSettingsNow} className="prompt-form">
              <label className="checkbox-row">
                <input name="enabled" type="checkbox" defaultChecked={publishScheduler.enabled} />
                <span>Включить автоматическую публикацию</span>
              </label>
              <label className="field field-compact">
                <span>Интервал в минутах</span>
                <select name="intervalMinutes" defaultValue={String(publishScheduler.intervalMinutes)}>
                  <option value="5">5 минут</option>
                  <option value="10">10 минут</option>
                  <option value="15">15 минут</option>
                  <option value="20">20 минут</option>
                  <option value="30">30 минут</option>
                  <option value="60">60 минут</option>
                  <option value="120">120 минут</option>
                  <option value="180">180 минут</option>
                  <option value="360">360 минут</option>
                </select>
              </label>
              <label className="field field-compact">
                <span>Размер пачки</span>
                <select name="batchSize" defaultValue={String(publishScheduler.batchSize)}>
                  <option value="1">1 материал</option>
                  <option value="2">2 материала</option>
                  <option value="5">5 материалов</option>
                  <option value="10">10 материалов</option>
                  <option value="15">15 материалов</option>
                </select>
              </label>
              <p className="footer-note">
                Этот этап публикует только материалы со статусом <strong>ready_for_publish</strong> и
                <strong> publish decision = publish_auto</strong>. Все `hold` и `skip` остаются вне ленты.
              </p>
              <div className="source-button-row">
                <PendingSubmitButton
                  className="button-primary"
                  idleLabel="Сохранить publish scheduler"
                  pendingLabel="Сохраняем publish scheduler..."
                  disabled={!isLive}
                />
                <PendingSubmitButton
                  className="button-secondary"
                  formAction={runPublishSchedulerNow}
                  idleLabel="Запустить publish scheduler"
                  pendingLabel="Запускаем publish scheduler..."
                  disabled={!isLive}
                />
              </div>
            </form>
          </article>
          <article className="news-card">
            <span>publish scheduler state</span>
            <h3>{publishScheduler.enabled ? "Publish scheduler включён" : "Publish scheduler выключен"}</h3>
            <p className="footer-note">Интервал: {publishScheduler.intervalMinutes} мин.</p>
            <p className="footer-note">Размер пачки: {publishScheduler.batchSize} материалов</p>
            <p className="footer-note">Последний запуск: {formatDateTime(publishScheduler.lastRunAt)}</p>
            <p className="footer-note">Следующий запуск: {formatDateTime(publishScheduler.nextRunAt)}</p>
            <p className="footer-note">Последний статус: {publishScheduler.lastStatus}</p>
            <p className="footer-note">Опубликовано материалов: {publishScheduler.lastPublishedCount}</p>
            {publishScheduler.lastError ? <p className="source-card-error">{publishScheduler.lastError}</p> : null}
          </article>
        </div>
      </section>
      ) : null}

      {activeTab === "sources" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Источники</h2>
            <p>
              Здесь управляется список рабочих источников. Сначала источник проходит проверку, и только после
              успешного результата его можно добавить. В списке ниже показываются только активные источники.
            </p>
          </div>
        </div>
        <div style={{ marginBottom: 24 }}>
            <article className="news-card source-create-card">
              <span>new source</span>
              <h3>Добавить источник</h3>
              <form action={createSourceNow} className="prompt-form">
                <input type="hidden" name="tab" value={activeTab} />
                <label className="field">
                  <span>Key</span>
                  <input name="key" placeholder="championat-news" defaultValue={sourceDraft.key} required />
              </label>
              <label className="field">
                <span>Title</span>
                <input name="title" placeholder="Championat" defaultValue={sourceDraft.title} required />
              </label>
              <label className="field">
                <span>URL</span>
                <input name="url" placeholder="https://example.com/feed.xml" defaultValue={sourceDraft.url} required />
              </label>
              <input type="hidden" name="probeOk" value={draftProbe?.ok ? "true" : "false"} />
              <input type="hidden" name="probeReadiness" value={draftProbe?.readiness ?? "unknown"} />
              <input type="hidden" name="probeItemCount" value={String(draftProbe?.count ?? 0)} />
              <input type="hidden" name="probedKey" value={sourceDraft.key} />
              <input type="hidden" name="probedUrl" value={sourceDraft.url} />
              <input type="hidden" name="resolvedSourceType" value={sourceDraft.type} />
              <input type="hidden" name="resolvedSourceUrl" value={sourceDraft.url} />
              <input type="hidden" name="supportsRss" value={draftProbe?.supportsRss ? "true" : "false"} />
              <input type="hidden" name="supportsNewsSitemap" value={draftProbe?.supportsNewsSitemap ? "true" : "false"} />
              <input type="hidden" name="supportsSitemap" value={draftProbe?.supportsSitemap ? "true" : "false"} />
              <input type="hidden" name="supportsScraping" value={draftProbe?.supportsScraping ? "true" : "false"} />
              <input type="hidden" name="fullTextOk" value={draftProbe?.fullTextOk ? "true" : "false"} />
              <input type="hidden" name="fullTextMethod" value={draftProbe?.fullTextMethod ?? ""} />
              <input type="hidden" name="leadOk" value={draftProbe?.leadOk ? "true" : "false"} />
              <input type="hidden" name="tagsCount" value={String(draftProbe?.tagsCount ?? 0)} />
              <input type="hidden" name="sampleTitle" value={draftProbe?.sampleTitle ?? ""} />
              <input type="hidden" name="sampleUrl" value={draftProbe?.sampleUrl ?? ""} />
              <div className="source-inline-fields">
                <label className="field field-compact">
                  <span>Type</span>
                  <select name="sourceType" defaultValue={sourceDraft.type}>
                    <option value="auto">auto detect</option>
                    <option value="rss">rss</option>
                    <option value="news_sitemap">news sitemap</option>
                    <option value="scraping">scraping</option>
                    <option value="ai_research">ai search</option>
                  </select>
                </label>
              </div>
              <p className="footer-note">
                Сначала проверьте источник. Если проверка успешна, кнопка добавления станет доступна и источник
                сохранится сразу как <strong>active</strong>.
              </p>
              <label className="field field-compact">
                <span>Source hints</span>
                <textarea
                  name="notes"
                  rows={3}
                  defaultValue={sourceDraft.notes}
                  placeholder="Например: искать только футбольные новости, исключить видео и трансляции"
                />
              </label>
              {draftProbe ? (
                <div className={draftProbe.ok ? "source-probe-preview" : "source-card-error"}>
                  <strong>Проверка:</strong> {draftProbe.readiness} · элементов: {draftProbe.count} · full text:{" "}
                  {draftProbe.fullTextOk ? "ok" : "нет"}
                  {draftProbe.fullTextMethod ? ` (${formatProbeFullTextMethod(draftProbe.fullTextMethod)})` : ""}
                  {" · "}lead: {draftProbe.leadOk ? "ok" : "нет"} · tags: {draftProbe.tagsCount}
                  <br />
                  Capability profile: rss {draftProbe.supportsRss ? "yes" : "no"} · news sitemap{" "}
                  {draftProbe.supportsNewsSitemap ? "yes" : "no"} · scraping {draftProbe.supportsScraping ? "yes" : "no"}
                  {draftProbe.sampleTitle ? (
                    <>
                      <br />
                      Sample: {draftProbe.sampleTitle}
                      {draftProbe.sampleUrl ? (
                        <>
                          {" · "}
                          <a href={draftProbe.sampleUrl} target="_blank" rel="noreferrer">
                            открыть
                          </a>
                        </>
                      ) : null}
                    </>
                  ) : null}
                </div>
              ) : null}
              <div className="source-button-row">
                <PendingSubmitButton
                  className="button-secondary"
                  formAction={probeNewSourceNow}
                  idleLabel="Проверить"
                  pendingLabel="Проверяем..."
                />
                <PendingSubmitButton
                  className="button-primary"
                  idleLabel="Добавить"
                  pendingLabel="Добавляем..."
                  disabled={!draftProbe?.ok}
                />
              </div>
            </form>
          </article>
        </div>
        <div className="source-grid">
          {activeSources.map((source) => {
            const state = sourceStateMap.get(source.key);
            const lamp = getSourceLamp(
              state?.lastStatus,
              state?.lastProbeReadiness,
              state?.lastSuccessfulFetchAt,
              state?.lastSuccessfulParseAt
            );
            const readiness = getReadinessBadge(state?.lastProbeReadiness);
            const needsPreflightWarning =
              (source.sourceType === "scraping" || source.sourceType === "news_sitemap") &&
              (
                source.status === "draft" ||
                (
                  !state?.lastSuccessfulFetchAt &&
                  !state?.lastSuccessfulParseAt &&
                  (state?.lastProbeReadiness === "unknown" ||
                    state?.lastProbeReadiness === "empty" ||
                    state?.lastProbeReadiness === "fetch_error")
                )
              );

            return (
            <article key={source.key} className="news-card source-card">
              <div className="source-card-top">
                <div className="source-status-wrap">
                <span className={`source-lamp source-lamp-${lamp.tone}`} />
                  <span>{lamp.label}</span>
                </div>
                <span>
                  {formatSourceType(source.sourceType)} · active
                </span>
              </div>
              <h3>{source.title}</h3>
              <p className="source-card-url">{source.url}</p>
              <p className="footer-note">Key: {source.key}</p>
              {source.notes ? <p className="footer-note">{source.notes}</p> : null}
              <div className="source-button-row">
                <form action={deleteSourceNow}>
                  <input type="hidden" name="tab" value={activeTab} />
                  <input type="hidden" name="sourceKey" value={source.key} />
                  <PendingSubmitButton
                    className="button-secondary"
                    idleLabel="Удалить"
                    pendingLabel="Удаляем..."
                  />
                </form>
              </div>
              <p className="footer-note" style={{ marginTop: 10 }}>
                Последняя проверка: {formatDateTime(state?.lastProbeAt)} · элементов: {state?.lastProbeCount ?? 0}
              </p>
              <p className="footer-note">
                Preflight: <strong>{readiness.label}</strong> · full text:{" "}
                {state?.lastProbeFullTextOk ? "ok" : "нет"}
                {state?.lastProbeFullTextMethod ? ` (${formatProbeFullTextMethod(state.lastProbeFullTextMethod)})` : ""}
                {" · "}lead: {state?.lastProbeLeadOk ? "ok" : "нет"} · tags: {state?.lastProbeTagsCount ?? 0}
              </p>
              <p className="footer-note">
                Capability profile: preferred {formatSourceType(state?.preferredAdapter ?? "unknown")} · rss{" "}
                {state?.supportsRss ? "yes" : "no"} · news sitemap {state?.supportsNewsSitemap ? "yes" : "no"} · scraping{" "}
                {state?.supportsScraping ? "yes" : "no"}
              </p>
              {state?.preferredAdapterUrl ? (
                <p className="footer-note">
                  Preferred URL: <a href={state.preferredAdapterUrl} target="_blank" rel="noreferrer">{state.preferredAdapterUrl}</a>
                </p>
              ) : null}
              {state?.lastProbeSampleTitle ? (
                <p className="footer-note">
                  Sample: {state.lastProbeSampleTitle}
                  {state.lastProbeSampleUrl ? (
                    <>
                      {" · "}
                      <a href={state.lastProbeSampleUrl} target="_blank" rel="noreferrer">
                        открыть
                      </a>
                    </>
                  ) : null}
                </p>
              ) : null}
              <p className="footer-note">
                Fetch: {state?.fetchStatus ?? "idle"} · Parse: {state?.parseStatus ?? "idle"} · retry:{" "}
                {state?.retryCount ?? 0}
              </p>
              <p className="footer-note">
                Последний удачный fetch: {formatDateTime(state?.lastSuccessfulFetchAt)} · parse:{" "}
                {formatDateTime(state?.lastSuccessfulParseAt)}
              </p>
              <p className="footer-note">
                Последний batch: {state?.lastItemCount ?? 0} · failures подряд: {state?.consecutiveFailures ?? 0}
              </p>
              {needsPreflightWarning ? (
                <p className="source-card-error">
                  Для этого источника нужен успешный preflight, который подтверждает, что сайт действительно отдает новости.
                </p>
              ) : null}
              {state?.lastError ? <p className="source-card-error">{state.lastError}</p> : null}
            </article>
            );
          })}
        </div>
      </section>
      ) : null}

      {activeTab === "prompts" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Промпты</h2>
            <p>Каждое сохранение создаёт новую версию prompt’а. При активации она сразу становится рабочей.</p>
          </div>
          <form action={cleanupPromptVersionsNow}>
            <PendingSubmitButton
              className="button-secondary"
              idleLabel="Удалить старые версии"
              pendingLabel="Чистим старые версии..."
              disabled={!isLive}
            />
          </form>
        </div>
        <div className="admin-grid">
          {promptGroups.map((group) => (
            <article key={group.agentKey} className="news-card">
              <span>{group.agentKey}</span>
              <h3>{group.active?.name ?? group.agentKey}</h3>
              <form action={savePromptVersion} className="prompt-form">
                <input type="hidden" name="agentKey" value={group.agentKey} />

                <label className="field">
                  <span>Name</span>
                  <input name="name" defaultValue={group.active?.name ?? `${group.agentKey} prompt`} required />
                </label>

                <label className="field">
                  <span>Model</span>
                  <input name="model" defaultValue={group.active?.model ?? "local-editor-mvp"} required />
                </label>

                <label className="field">
                  <span>System prompt</span>
                  <textarea
                    name="systemPrompt"
                    defaultValue={group.active?.systemPrompt ?? ""}
                    rows={5}
                    required
                  />
                </label>

                <label className="field">
                  <span>User template</span>
                  <textarea
                    name="userPromptTemplate"
                    defaultValue={group.active?.userPromptTemplate ?? ""}
                    rows={4}
                    required
                  />
                </label>

                <label className="field">
                  <span>Notes</span>
                  <textarea name="notes" defaultValue={group.active?.notes ?? ""} rows={3} />
                </label>

                <label className="checkbox-row">
                  <input name="activate" type="checkbox" defaultChecked />
                  <span>Сразу активировать новую версию</span>
                </label>

                <PendingSubmitButton
                  className="button-primary"
                  idleLabel="Сохранить новую версию"
                  pendingLabel="Сохраняем prompt..."
                />
              </form>
            </article>
          ))}
        </div>
      </section>
      ) : null}

      {activeTab === "diagnostics" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Контент-план</h2>
            <p>
              Планировщик выбирает, какие raw_items последнего pipeline идут в редакционный контур и в каком формате.
            </p>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "1fr" }}>
          {currentPipelineContentPlan.length ? currentPipelineContentPlan.slice(0, 8).map((item) => (
            <article key={item.id} className="news-card">
              <span>
                {item.priorityLabel} · {item.plannedFormat} · {item.status}
              </span>
              <h3>{item.title}</h3>
              <p>{item.reason}</p>
              <p className="footer-note" style={{ marginTop: 12 }}>
                {item.sourceTitle} · score {item.priorityScore}
              </p>
            </article>
          )) : (
            <article className="news-card">
              <h3>Для последнего pipeline записей content plan нет</h3>
              <p>
                Если в диагностике есть raw-новости, но здесь пусто, значит planner ещё не выбрал их в editorial batch.
              </p>
            </article>
          )}
        </div>
      </section>
      ) : null}

      {activeTab === "diagnostics" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Редакционная очередь</h2>
            <p>Последние drafts и reviews прямо в админке, если нужно быстро посмотреть состояние без перехода в студию.</p>
          </div>
        </div>
        <div className="stats-grid" style={{ marginBottom: 18 }}>
          <div className="stat">
            <strong>{drafts.length}</strong>
            <span>drafts в текущей выборке</span>
          </div>
          <div className="stat">
            <strong>{reviews.length}</strong>
            <span>review entries в текущей выборке</span>
          </div>
          <div className="stat">
            <strong>{currentPipelineContentPlan.length}</strong>
            <span>content plan items последнего pipeline</span>
          </div>
        </div>
        <div className="news-grid" style={{ gridTemplateColumns: "1fr" }}>
          {drafts.slice(0, 4).map((draft) => (
            <article key={draft.id} className="news-card">
              <span>
                {formatCategoryLabel(draft.category)} · {draft.status} · {draft.reviewStatus} · {draft.generationMode}
              </span>
              <h3>{draft.title}</h3>
              <p>{draft.dek}</p>
              {draft.status === "fallback_only" ? (
                <p className="source-card-error">
                  Fallback-only: этот draft оставлен только для внутреннего просмотра и никогда не должен публиковаться.
                </p>
              ) : null}
              {draft.generationMode === "template" ? (
                <p className="source-card-error">
                  Template fallback: такой draft не должен автоматически публиковаться.
                </p>
              ) : null}
              <p className="footer-note" style={{ marginTop: 12 }}>
                {draft.sourceTitle} · {draft.promptName}
              </p>
            </article>
          ))}
        </div>
      </section>
      ) : null}

      {activeTab === "costs" ? (
      <section>
        <div className="section-head">
          <div>
            <h2>Стоимость AI</h2>
            <p>
              Учет строится по фактическим token usage из ответов OpenAI. Стоимость расчетная по ставкам модели и web search.
            </p>
          </div>
        </div>
        <div className="stats-grid" style={{ marginBottom: 18 }}>
          <div className="stat">
            <strong>{formatUsd(aiUsageSummary.totals.estimatedCostUsd)}</strong>
            <span>за последние {aiUsageSummary.days} дней</span>
          </div>
          <div className="stat">
            <strong>{formatNumber(aiUsageSummary.totals.requestCount)}</strong>
            <span>AI-запросов</span>
          </div>
          <div className="stat">
            <strong>{formatCompactNumber(aiUsageSummary.totals.totalTokens)}</strong>
            <span>токенов всего</span>
          </div>
          <div className="stat">
            <strong>{formatNumber(aiUsageSummary.totals.webSearchCalls)}</strong>
            <span>web search вызовов</span>
          </div>
        </div>

        <div className="news-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", marginBottom: 24 }}>
          {aiUsageGroupTotals.map((group) => (
            <article key={group.usageGroup} className="news-card">
              <span>{formatAiUsageGroup(group.usageGroup)}</span>
              <h3>{formatUsd(group.estimatedCostUsd)}</h3>
              <p>
                {formatNumber(group.requestCount)} запросов · {formatCompactNumber(group.totalTokens)} токенов
              </p>
              <p className="footer-note">
                input {formatCompactNumber(group.inputTokens)} · output {formatCompactNumber(group.outputTokens)}
              </p>
            </article>
          ))}
          {!aiUsageGroupTotals.length ? (
            <article className="news-card">
              <span>Данных пока нет</span>
              <h3>Статистика начнёт наполняться после новых AI-запросов</h3>
              <p>Старые расходы из OpenAI CSV здесь не разложить по операциям, потому что раньше проект не сохранял тип запроса.</p>
            </article>
          ) : null}
        </div>

        <div className="section-head">
          <div>
            <h2>По дням</h2>
            <p>Даты сгруппированы по московскому времени: {aiUsageSummary.timezone}.</p>
          </div>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>День</th>
                <th>Стоимость</th>
                <th>Запросы</th>
                <th>Токены</th>
                <th>Web search</th>
              </tr>
            </thead>
            <tbody>
              {aiUsageDailyTotals.map((day) => (
                <tr key={day.usageDate ?? "unknown"}>
                  <td>{formatShortDate(day.usageDate ?? "")}</td>
                  <td>{formatUsd(day.estimatedCostUsd)}</td>
                  <td>{formatNumber(day.requestCount)}</td>
                  <td>{formatCompactNumber(day.totalTokens)}</td>
                  <td>{formatNumber(day.webSearchCalls)}</td>
                </tr>
              ))}
              {!aiUsageDailyTotals.length ? (
                <tr>
                  <td colSpan={5}>Пока нет записанных AI-запросов.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="section-head" style={{ marginTop: 28 }}>
          <div>
            <h2>По операциям</h2>
            <p>Здесь видно, что дороже: новости, статьи, редактор, rewrite или добор full text.</p>
          </div>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>День</th>
                <th>Группа</th>
                <th>Операция</th>
                <th>Модель</th>
                <th>Стоимость</th>
                <th>Запросы</th>
                <th>Input</th>
                <th>Output</th>
                <th>Cached</th>
              </tr>
            </thead>
            <tbody>
              {aiUsageSummary.items.map((row) => (
                <tr key={`${row.usageDate}:${row.usageGroup}:${row.operation}:${row.model}`}>
                  <td>{formatShortDate(row.usageDate)}</td>
                  <td>{formatAiUsageGroup(row.usageGroup)}</td>
                  <td>{formatAiOperation(row.operation)}</td>
                  <td>{formatAiModel(row.model)}</td>
                  <td>{formatUsd(row.estimatedCostUsd)}</td>
                  <td>{formatNumber(row.requestCount)}</td>
                  <td>{formatCompactNumber(row.inputTokens)}</td>
                  <td>{formatCompactNumber(row.outputTokens)}</td>
                  <td>{formatCompactNumber(row.cachedInputTokens)}</td>
                </tr>
              ))}
              {!aiUsageSummary.items.length ? (
                <tr>
                  <td colSpan={9}>После первого нового AI-запроса здесь появится разбивка.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
      ) : null}
    </main>
  );
}

type Prompt = Awaited<ReturnType<typeof getEditorialStudioData>>["prompts"][number];

function getAdminTab(tab?: string): AdminTab {
  if (tab === "sources" || tab === "prompts" || tab === "diagnostics" || tab === "costs") {
    return tab;
  }

  return "pipeline";
}

type AiUsageAggregate = {
  usageGroup: string;
  usageDate?: string;
  requestCount: number;
  inputTokens: number;
  outputTokens: number;
  cachedInputTokens: number;
  totalTokens: number;
  webSearchCalls: number;
  estimatedCostUsd: number;
};

type PipelineRunRecord = Awaited<ReturnType<typeof getEditorialStudioData>>["pipelineRuns"][number];

function buildLatestPipelineFunnel({
  pipelineRuns,
  activeSourceCount,
  ingestBatchSize,
  currentRawItems,
  currentContentPlan
}: {
  pipelineRuns: PipelineRunRecord[];
  activeSourceCount: number;
  ingestBatchSize: number;
  currentRawItems: RawItem[];
  currentContentPlan: Awaited<ReturnType<typeof getEditorialStudioData>>["contentPlan"];
}) {
  const latestIngest = pipelineRuns.find((run) => run.phase === "ingest" && run.status === "ok");
  if (!latestIngest) {
    return null;
  }

  const ingestStartedAt = new Date(latestIngest.startedAt).getTime();
  const latestEnrichment = findStageAfterIngest(pipelineRuns, "enrichment", ingestStartedAt);
  const latestEditorial = findStageAfterIngest(pipelineRuns, "editorial", ingestStartedAt);
  const latestPublish = findStageAfterIngest(pipelineRuns, "publish", ingestStartedAt);
  const expectedMax = Math.max(0, activeSourceCount * Math.max(1, ingestBatchSize));
  const sourceParsedTotal = sumSourceMetric(latestIngest, "parsedCount");
  const rawParsedFromRun = sourceParsedTotal || latestIngest.foundCount;
  const parsedCounterLooksSuspicious = expectedMax > 0 && rawParsedFromRun > expectedMax * 3;
  const parsedFromSources = parsedCounterLooksSuspicious ? Math.max(latestIngest.savedCount, latestIngest.publishedCount) : rawParsedFromRun;
  const freshFromSources = sumSourceMetric(latestIngest, "freshCount") || latestIngest.savedCount || latestIngest.publishedCount;
  const duplicateCount = latestIngest.skippedItems.length;
  const contentPlanCount = latestEditorial?.plannedCount || currentContentPlan.length;
  const generatedCount = latestEditorial?.generatedCount || 0;
  const reviewedCount = latestEditorial?.reviewedCount || 0;
  const publishedCount = latestPublish?.publishedCount || latestEditorial?.publishedCount || 0;
  const waitingEditorial = currentRawItems.filter((item) => !item.isDuplicate && !item.contentPlanStatus).length;

  const steps = [
    { label: "максимум по настройкам", value: expectedMax },
    { label: "прочитано из источников", value: parsedFromSources },
    { label: "свежие после фильтров", value: freshFromSources },
    { label: "сохранено raw_items", value: latestIngest.savedCount },
    { label: "отсечено/дубли", value: duplicateCount },
    { label: "content plan", value: contentPlanCount },
    { label: "writer создал drafts", value: generatedCount },
    { label: "editor проверил", value: reviewedCount },
    { label: "опубликовано", value: publishedCount }
  ];

  const sources = latestIngest.sourceBreakdown.map((source) => ({
    key: source.sourceKey,
    title: source.sourceTitle,
    limit: Math.max(1, ingestBatchSize),
    parsed: source.parsedCount ?? source.foundCount,
    fresh: source.freshCount ?? source.foundCount,
    filtered: source.filteredCount ?? Math.max(0, (source.parsedCount ?? source.foundCount) - (source.freshCount ?? source.foundCount)),
    reasons: formatSourceFilterReasons(source.filterReasons)
  }));

  const funnelNotes = [
    expectedMax > parsedFromSources
      ? `Источники отдали меньше максимума: ${expectedMax - parsedFromSources} материалов не нашлись или не распарсились.`
      : "",
    parsedFromSources > freshFromSources
      ? `Фильтр свежести/известных материалов отсек ${parsedFromSources - freshFromSources}.`
      : "",
    parsedCounterLooksSuspicious
      ? "Счетчик прочитанных материалов в старой записи ingest выглядит некорректно, поэтому воронка использует безопасную оценку по сохраненным raw_items."
      : "",
    freshFromSources > latestIngest.savedCount
      ? `До raw_items не дошло ${freshFromSources - latestIngest.savedCount}: чаще всего это уже существующие записи или дубли.`
      : "",
    latestIngest.savedCount > contentPlanCount
      ? `Content plan не взял ${latestIngest.savedCount - contentPlanCount}; ${waitingEditorial} из текущей диагностики еще без content plan status.`
      : "",
    contentPlanCount > generatedCount
      ? `Writer не создал draft для ${contentPlanCount - generatedCount} материалов.`
      : "",
    generatedCount > publishedCount
      ? `До publish не дошло ${generatedCount - publishedCount} drafts: проверь review_status/quality gate.`
      : ""
  ].filter(Boolean);

  return {
    steps,
    sources,
    skippedItems: latestIngest.skippedItems,
    notes: funnelNotes,
    startedAt: latestIngest.startedAt,
    enrichment: latestEnrichment,
    editorial: latestEditorial,
    publish: latestPublish
  };
}

function findStageAfterIngest(pipelineRuns: PipelineRunRecord[], phase: string, ingestStartedAt: number) {
  return pipelineRuns.find((run) => run.phase === phase && run.status === "ok" && new Date(run.startedAt).getTime() >= ingestStartedAt);
}

function sumSourceMetric(run: PipelineRunRecord, key: "parsedCount" | "freshCount" | "filteredCount") {
  return run.sourceBreakdown.reduce((sum, source) => sum + (source[key] ?? 0), 0);
}

function buildAiUsageGroupTotals(items: Awaited<ReturnType<typeof getEditorialStudioData>>["aiUsageSummary"]["items"]) {
  const grouped = new Map<string, AiUsageAggregate>();

  for (const item of items) {
    const current = grouped.get(item.usageGroup) ?? {
      usageGroup: item.usageGroup,
      requestCount: 0,
      inputTokens: 0,
      outputTokens: 0,
      cachedInputTokens: 0,
      totalTokens: 0,
      webSearchCalls: 0,
      estimatedCostUsd: 0
    };
    current.requestCount += item.requestCount;
    current.inputTokens += item.inputTokens;
    current.outputTokens += item.outputTokens;
    current.cachedInputTokens += item.cachedInputTokens;
    current.totalTokens += item.totalTokens;
    current.webSearchCalls += item.webSearchCalls;
    current.estimatedCostUsd += item.estimatedCostUsd;
    grouped.set(item.usageGroup, current);
  }

  return Array.from(grouped.values()).sort((left, right) => right.estimatedCostUsd - left.estimatedCostUsd);
}

function buildAiUsageDailyTotals(items: Awaited<ReturnType<typeof getEditorialStudioData>>["aiUsageSummary"]["items"]) {
  const grouped = new Map<string, AiUsageAggregate>();

  for (const item of items) {
    const current = grouped.get(item.usageDate) ?? {
      usageGroup: "daily",
      usageDate: item.usageDate,
      requestCount: 0,
      inputTokens: 0,
      outputTokens: 0,
      cachedInputTokens: 0,
      totalTokens: 0,
      webSearchCalls: 0,
      estimatedCostUsd: 0
    };
    current.requestCount += item.requestCount;
    current.inputTokens += item.inputTokens;
    current.outputTokens += item.outputTokens;
    current.cachedInputTokens += item.cachedInputTokens;
    current.totalTokens += item.totalTokens;
    current.webSearchCalls += item.webSearchCalls;
    current.estimatedCostUsd += item.estimatedCostUsd;
    grouped.set(item.usageDate, current);
  }

  return Array.from(grouped.values()).sort((left, right) => (right.usageDate ?? "").localeCompare(left.usageDate ?? ""));
}

function formatUsd(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 1 ? 4 : 2,
    maximumFractionDigits: value < 1 ? 4 : 2
  }).format(value);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat("ru-RU", {
    notation: "compact",
    maximumFractionDigits: 1
  }).format(value);
}

function formatShortDate(value: string) {
  const [year, month, day] = value.split("-").map((part) => Number(part));
  if (!year || !month || !day) {
    return value || "—";
  }
  const monthNames = [
    "янв.",
    "февр.",
    "мар.",
    "апр.",
    "мая",
    "июн.",
    "июл.",
    "авг.",
    "сент.",
    "окт.",
    "нояб.",
    "дек."
  ];
  return `${day} ${monthNames[month - 1] ?? ""} ${year} г.`;
}

function formatAiUsageGroup(group: string) {
  switch (group) {
    case "news":
      return "Новости";
    case "guides":
      return "Статьи";
    case "enrichment":
      return "Full text / поиск";
    case "planning":
      return "Контент-план";
    default:
      return "Другое";
  }
}

function formatAiOperation(operation: string) {
  switch (operation) {
    case "news_writer":
      return "Новости: writer";
    case "news_editor":
      return "Новости: editor";
    case "news_rewrite":
      return "Новости: rewrite";
    case "guide_writer":
      return "Статьи: writer";
    case "content_plan_rerank":
      return "Content plan rerank";
    case "source_discovery":
      return "Поиск новостей";
    case "source_resolve_url":
      return "Поиск canonical URL";
    case "enrichment_html_extract":
      return "Full text из HTML";
    case "enrichment_web_extract":
      return "Full text + web search";
    case "enrichment_search_extract":
      return "Full text через search";
    default:
      return operation;
  }
}

function formatAiModel(model: string) {
  return model.replace("-2025-08-07", "");
}

function getNoticeMessage(notice?: string, detail?: string) {
  switch (notice) {
    case "db-reset":
      return "Локальная БД очищена, source-state сброшен.";
    case "db-reset-error":
      return detail ? `Очистка БД не удалась: ${detail}` : "Очистка БД не удалась.";
    case "sources-ingested":
      return "Тестовая пачка новостей из активных источников загружена в систему.";
    case "sources-ingest-error":
      return detail ? `Загрузка источников не удалась: ${detail}` : "Загрузка источников не удалась.";
    case "scheduler-saved":
      return "Настройки автозагрузки новостей сохранены.";
    case "scheduler-save-error":
      return detail ? `Scheduler не сохранён: ${detail}` : "Scheduler не сохранён.";
    case "scheduler-run":
      return "Scheduler запущен вручную.";
    case "scheduler-run-error":
      return detail ? `Scheduler не выполнен: ${detail}` : "Scheduler не выполнен.";
    case "enrichment-scheduler-saved":
      return "Настройки enrichment scheduler сохранены.";
    case "enrichment-scheduler-save-error":
      return detail ? `Enrichment scheduler не сохранён: ${detail}` : "Enrichment scheduler не сохранён.";
    case "enrichment-scheduler-run":
      return detail ? `Enrichment scheduler выполнен: ${detail}` : "Enrichment scheduler выполнен.";
    case "enrichment-scheduler-run-error":
      return detail ? `Enrichment scheduler не выполнен: ${detail}` : "Enrichment scheduler не выполнен.";
    case "enrichment-run":
      return detail ? `Отдельный enrichment завершён: ${detail}` : "Отдельный enrichment завершён.";
    case "enrichment-run-error":
      return detail ? `Enrichment не выполнен: ${detail}` : "Enrichment не выполнен.";
    case "source-created":
      return "Новый источник добавлен и сразу активирован.";
    case "source-deleted":
      return "Источник удалён.";
    case "source-delete-error":
      return detail ? `Источник не удалён: ${detail}` : "Источник не удалён.";
    case "source-probed":
      return "Проверка источника завершена, статус обновлён.";
    case "source-probe-error":
      return detail ? `Проверка источника не удалась: ${detail}` : "Проверка источника не удалась.";
    case "source-draft-probed":
      return detail ? `Проверка нового источника завершена: ${detail}` : "Проверка нового источника прошла успешно.";
    case "source-draft-probe-error":
      return detail
        ? `Проверка нового источника не удалась: ${detail}`
        : "Проверка нового источника не удалась.";
    case "source-activation-blocked":
      return "Источник не переведён в active: сначала нужен успешный preflight-check для news sitemap или scraping.";
    case "source-save-error":
      return detail
        ? `Источник не сохранён: ${detail}`
        : "Источник не сохранён: проверьте тип, статус и preflight.";
    case "content-plan-run":
      return "Content plan успешно обновлён.";
    case "content-plan-run-error":
      return detail ? `Content plan не обновлён: ${detail}` : "Content plan не обновлён.";
    case "editorial-scheduler-saved":
      return "Настройки editorial scheduler сохранены.";
    case "editorial-scheduler-save-error":
      return detail ? `Editorial scheduler не сохранён: ${detail}` : "Editorial scheduler не сохранён.";
    case "editorial-scheduler-run":
      return detail ? `Editorial scheduler выполнен: ${detail}` : "Editorial scheduler выполнен.";
    case "editorial-scheduler-run-error":
      return detail ? `Editorial scheduler не выполнен: ${detail}` : "Editorial scheduler не выполнен.";
    case "manual-pipeline-run":
      return detail
        ? `Ручной pipeline ingest -> enrichment -> editorial выполнен: ${detail}`
        : "Ручной pipeline ingest -> enrichment -> editorial выполнен.";
    case "manual-pipeline-run-error":
      return detail
        ? `Ручной pipeline ingest -> enrichment -> editorial не выполнен: ${detail}`
        : "Ручной pipeline ingest -> enrichment -> editorial не выполнен.";
    case "publish-scheduler-saved":
      return "Настройки publish scheduler сохранены.";
    case "publish-scheduler-save-error":
      return detail ? `Publish scheduler не сохранён: ${detail}` : "Publish scheduler не сохранён.";
    case "publish-scheduler-run":
      return detail ? `Publish scheduler выполнен: ${detail}` : "Publish scheduler выполнен.";
    case "publish-scheduler-run-error":
      return detail ? `Publish scheduler не выполнен: ${detail}` : "Publish scheduler не выполнен.";
    case "publish-run":
      return detail ? `Публикация завершена: ${detail}` : "Публикация завершена.";
    case "publish-run-error":
      return detail ? `Публикация не выполнена: ${detail}` : "Публикация не выполнена.";
    case "editorial-run":
      return "Editorial run завершён, новые draft-материалы и review-результаты подтянуты.";
    case "editorial-run-error":
      return detail ? `Editorial run не выполнен: ${detail}` : "Editorial run не выполнен.";
    case "prompt-saved":
      return "Новая версия prompt’а сохранена.";
    case "prompt-save-error":
      return detail ? `Новая версия prompt’а не сохранена: ${detail}` : "Новая версия prompt’а не сохранена.";
    case "prompt-activated":
      return "Версия prompt’а активирована.";
    case "prompt-activate-error":
      return detail ? `Версия prompt’а не активирована: ${detail}` : "Версия prompt’а не активирована.";
    case "prompt-archived":
      return "Версия prompt’а отправлена в архив.";
    case "prompt-archive-error":
      return detail ? `Версия prompt’а не архивирована: ${detail}` : "Версия prompt’а не архивирована.";
    case "prompt-cleanup":
      return detail ? `Старые версии prompt’ов удалены: ${detail}` : "Старые версии prompt’ов удалены.";
    case "prompt-cleanup-error":
      return detail ? `Старые версии prompt’ов не удалены: ${detail}` : "Старые версии prompt’ов не удалены.";
    default:
      return null;
  }
}

function formatDateTime(value?: string) {
  if (!value) {
    return "ещё не было";
  }

  return formatMoscowDateTime(value);
}

function buildPipelineQueues(rawItems: RawItem[], drafts: DraftArticle[]) {
  const draftsByRawId = new Map(drafts.map((draft) => [draft.rawItemId, draft]));
  const waitingEnrichment = rawItems.filter((item) => !item.isDuplicate && !item.fullText);
  const waitingEditorial = rawItems.filter(
    (item) => !item.isDuplicate && Boolean(item.fullText) && !draftsByRawId.has(item.id)
  );
  const waitingPublish = drafts.filter(
    (draft) => draft.status === "ready_for_publish" && draft.publishDecision === "publish_auto"
  );

  return {
    waitingEnrichment,
    waitingEditorial,
    waitingPublish
  };
}

function buildDuplicateAudit(rawItems: RawItem[]) {
  const all = rawItems.filter((item) => item.isDuplicate);
  return {
    all,
    ingest: all.filter((item) => item.duplicateStage === "ingest"),
    afterEnrichment: all.filter((item) => item.duplicateStage === "after_enrichment"),
    other: all.filter((item) => item.duplicateStage !== "ingest" && item.duplicateStage !== "after_enrichment"),
  };
}

function renderQueueList<T>(items: T[], formatItem: (item: T) => string) {
  if (!items.length) {
    return <p className="footer-note">Сейчас пусто.</p>;
  }

  return (
    <>
      <ul style={{ margin: "10px 0 0", paddingLeft: 18, display: "grid", gap: 6 }}>
        {items.slice(0, 6).map((item, index) => (
          <li key={index} className="footer-note">
            {formatItem(item)}
          </li>
        ))}
      </ul>
      {items.length > 6 ? (
        <p className="footer-note" style={{ marginTop: 8 }}>
          И ещё {items.length - 6}.
        </p>
      ) : null}
    </>
  );
}

function formatDuration(durationMs: number) {
  if (durationMs < 1000) {
    return `${durationMs} мс`;
  }

  const totalSeconds = Math.round(durationMs / 1000);
  if (totalSeconds < 60) {
    return `${totalSeconds} сек`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} мин ${seconds} сек`;
}

function formatDuplicateStage(value?: string) {
  switch (value) {
    case "ingest":
      return "дубликат на ingest";
    case "after_enrichment":
      return "дубликат после enrichment";
    case "before_publish":
      return "дубликат перед публикацией";
    default:
      return value ?? "дубликат";
  }
}

function formatPipelinePhase(value: string) {
  switch (value) {
    case "ingest":
      return "Сбор новостей";
    case "enrichment":
      return "Добор full text";
    case "editorial":
      return "Генерация материалов";
    case "publish":
      return "Публикация материалов";
    default:
      return value;
  }
}

function formatPipelineTrigger(value: string) {
  switch (value) {
    case "scheduler":
      return "scheduler";
    case "manual":
      return "ручной запуск";
    default:
      return value;
  }
}

function formatSourceFilterReasons(reasons?: Record<string, number>) {
  if (!reasons) {
    return "";
  }

  const labels: Record<string, string> = {
    older_than_max_age: "старше окна свежести",
    reached_last_external_id: "достигли последней известной новости",
    known_external_id: "уже известный external_id",
    known_dedupe_key: "уже известный дубль",
    not_newer_than_last_published: "не новее последней сохранённой",
    batch_limit: "срезано лимитом batchSize"
  };

  return Object.entries(reasons)
    .filter(([, count]) => count > 0)
    .map(([reason, count]) => `${labels[reason] ?? reason}: ${count}`)
    .join(" · ");
}

function renderPipelineRunMetrics(run: {
  phase: string;
  foundCount: number;
  savedCount: number;
  publishedCount: number;
  processedCount: number;
  enrichedCount: number;
  plannedCount: number;
  generatedCount: number;
  reviewedCount: number;
  skippedItems: Array<{
    title: string;
    reason?: string;
  }>;
  sourceBreakdown: Array<{
    sourceKey: string;
    sourceTitle: string;
    foundCount: number;
    parsedCount?: number;
    freshCount?: number;
    filteredCount?: number;
    filterReasons?: Record<string, number>;
  }>;
}) {
  switch (run.phase) {
    case "ingest":
      return (
        <>
          <p className="footer-note">
            Найдено: {run.foundCount} · сохранено: {run.savedCount} · добавлено в ленту: {run.publishedCount}
          </p>
          {run.sourceBreakdown.length ? (
            <p className="footer-note">
              По источникам:{" "}
              {run.sourceBreakdown
                .map((item) => {
                  if (
                    typeof item.parsedCount === "number" ||
                    typeof item.freshCount === "number" ||
                    typeof item.filteredCount === "number"
                  ) {
                    return `${item.sourceTitle}: свежих ${item.freshCount ?? item.foundCount} / прочитано ${item.parsedCount ?? item.foundCount} / отсечено ${item.filteredCount ?? 0}`;
                  }
                  return `${item.sourceTitle}: ${item.foundCount}`;
                })
                .join(" · ")}
            </p>
          ) : null}
          {run.sourceBreakdown.some((item) => item.filterReasons && Object.keys(item.filterReasons).length > 0) ? (
            <div style={{ marginTop: 8 }}>
              {run.sourceBreakdown.map((item) => {
                const reasons = formatSourceFilterReasons(item.filterReasons);
                return reasons ? (
                  <p key={`${item.sourceKey}-filters`} className="footer-note">
                    {item.sourceTitle}: {reasons}
                  </p>
                ) : null;
              })}
            </div>
          ) : null}
          {run.skippedItems.length ? (
            <div style={{ marginTop: 10 }}>
              <p className="footer-note" style={{ marginBottom: 6 }}>
                Отсечено новостей: {run.skippedItems.length}
              </p>
              <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
                {run.skippedItems.slice(0, 6).map((item, index) => (
                  <li key={`${item.title}-${index}`} className="footer-note">
                    <strong>{item.title}</strong>
                    {item.reason ? ` — ${item.reason}` : ""}
                  </li>
                ))}
              </ul>
              {run.skippedItems.length > 6 ? (
                <p className="footer-note" style={{ marginTop: 8 }}>
                  И ещё {run.skippedItems.length - 6}.
                </p>
              ) : null}
            </div>
          ) : null}
        </>
      );
    case "enrichment":
      return (
        <p className="footer-note">
          Обработано кандидатов: {run.processedCount} · реально обогащено: {run.enrichedCount}
        </p>
      );
    case "editorial":
      return (
        <>
          <p className="footer-note">
            Запланировано: {run.plannedCount} · draft-ов создано: {run.generatedCount} · review завершено: {run.reviewedCount}
          </p>
          <p className="footer-note">Автоматически опубликовано: {run.publishedCount}</p>
        </>
      );
    case "publish":
      return <p className="footer-note">Опубликовано материалов: {run.publishedCount}</p>;
    default:
      return (
        <>
          <p className="footer-note">
            Найдено: {run.foundCount} · сохранено: {run.savedCount} · опубликовано: {run.publishedCount}
          </p>
          <p className="footer-note">
            Обработано: {run.processedCount} · обогащено: {run.enrichedCount} · planned: {run.plannedCount}
          </p>
          <p className="footer-note">
            drafts: {run.generatedCount} · reviews: {run.reviewedCount}
          </p>
        </>
      );
  }
}

function formatSourceType(value: string) {
  switch (value) {
    case "auto":
      return "auto detect";
    case "news_sitemap":
      return "news sitemap";
    case "ai_research":
    case "ai_search":
      return "ai search";
    default:
      return value;
  }
}

function groupPrompts(prompts: Prompt[]) {
  const grouped = new Map<string, { agentKey: string; active?: Prompt; versions: Prompt[] }>();

  for (const prompt of prompts) {
    const entry = grouped.get(prompt.agentKey) ?? {
      agentKey: prompt.agentKey,
      active: undefined,
      versions: []
    };

    entry.versions.push(prompt);
    if (prompt.status === "active") {
      entry.active = prompt;
    }

    grouped.set(prompt.agentKey, entry);
  }

  return Array.from(grouped.values()).sort((left, right) => left.agentKey.localeCompare(right.agentKey));
}

function getSourceLamp(
  status?: string,
  readiness?: string,
  lastSuccessfulFetchAt?: string,
  lastSuccessfulParseAt?: string
) {
  if (readiness === "ready") {
    return { tone: "green", label: "готов" };
  }
  if (readiness === "ready_ai") {
    return { tone: "green", label: "готов через веб-поиск" };
  }
  if (readiness === "partial" || readiness === "feed_only") {
    return {
      tone: "amber",
      label: readiness === "partial" ? "частично готов" : "только фид"
    };
  }
  if (lastSuccessfulFetchAt || lastSuccessfulParseAt) {
    return { tone: "green", label: "работает" };
  }
  switch (status) {
    case "probe_ok":
    case "ok":
      return { tone: "green", label: "в порядке" };
    case "probe_error":
      return { tone: "red", label: "ошибка" };
    default:
      return { tone: "amber", label: "ожидает запуск" };
  }
}

function getReadinessBadge(readiness?: string) {
  switch (readiness) {
    case "ready":
      return { label: "ready" };
    case "ready_ai":
      return { label: "ready via web search" };
    case "partial":
      return { label: "partial" };
    case "feed_only":
      return { label: "feed-only" };
    case "fetch_error":
      return { label: "fetch error" };
    case "empty":
      return { label: "empty" };
    case "unsupported":
      return { label: "unsupported" };
    default:
      return { label: "unknown" };
  }
}

function formatProbeFullTextMethod(value?: string) {
  switch (value) {
    case "direct_parser":
      return "direct parser";
    case "web_search":
      return "web search";
    case "ai_search":
      return "ai search";
    default:
      return value ?? "не указан";
  }
}
