import { resolveApiBaseUrl } from "@/lib/api";

export type RawItem = {
  id: string;
  sourceKey: string;
  sourceTitle: string;
  sourceUrl: string;
  category: string;
  normalizedCategory: string;
  title: string;
  summary: string;
  lead?: string;
  fullText?: string;
  fullTextSourceUrl?: string;
  fullTextSourceTitle?: string;
  referenceUrls: string[];
  extractionMode?: string;
  enrichmentStatus?: string;
  enrichmentError?: string;
  tags: string[];
  url?: string;
  publishedAt: string;
  fetchedAt: string;
  importanceScore: number;
  triageLabel: string;
  isDuplicate: boolean;
  duplicateOf?: string;
  contentPlanStatus?: string;
  contentPlanReason?: string;
  contentPlanPriorityLabel?: string;
};

export type PromptConfig = {
  id: string;
  agentKey: string;
  name: string;
  version: number;
  status: string;
  systemPrompt: string;
  userPromptTemplate: string;
  model: string;
  provider: string;
  notes: string;
  createdAt: string;
};

export type DraftArticle = {
  id: string;
  rawItemId: string;
  title: string;
  dek: string;
  body: string;
  category: string;
  sourceTitle: string;
  sourceUrl?: string;
  publishedAt: string;
  status: string;
  reviewStatus: string;
  reviewSummary?: string;
  publishDecision: string;
  publishReason?: string;
  promptConfigId: string;
  promptName: string;
  model: string;
  generationMode: string;
  createdAt: string;
  updatedAt: string;
};

export type EditorReview = {
  id: string;
  draftId: string;
  status: string;
  summary: string;
  notes: string;
  promptConfigId: string;
  promptName: string;
  model: string;
  createdAt: string;
};

export type ContentPlanItem = {
  id: string;
  rawItemId: string;
  title: string;
  sourceTitle: string;
  category: string;
  priorityScore: number;
  priorityLabel: string;
  plannedFormat: string;
  status: string;
  reason: string;
  createdAt: string;
  updatedAt: string;
};

export type EditorialStatus = {
  openaiEnabled: boolean;
  openaiModel: string;
  openaiSearchModel: string;
  fallbackMode: boolean;
  providerLabel: string;
  apiStyle: string;
  webSearchEnabled: boolean;
};

export type SourceSyncState = {
  sourceKey: string;
  sourceTitle: string;
  lastFetchedAt?: string;
  lastSuccessfulFetchAt?: string;
  lastSuccessfulParseAt?: string;
  lastPublishedAt?: string;
  lastExternalId?: string;
  lastItemCount: number;
  fetchStatus: string;
  parseStatus: string;
  fetchErrorCount: number;
  parseErrorCount: number;
  consecutiveFailures: number;
  retryCount: number;
  lastProbeAt?: string;
  lastProbeCount: number;
  lastProbeReadiness: string;
  preferredAdapter?: string;
  preferredAdapterUrl?: string;
  supportsRss: boolean;
  supportsNewsSitemap: boolean;
  supportsSitemap: boolean;
  supportsScraping: boolean;
  lastProbeFullTextOk: boolean;
  lastProbeLeadOk: boolean;
  lastProbeTagsCount: number;
  lastProbeSampleTitle?: string;
  lastProbeSampleUrl?: string;
  lastStatus: string;
  lastError?: string;
  updatedAt: string;
};

export type SourceConfig = {
  key: string;
  title: string;
  url: string;
  category: string;
  sourceType: string;
  status: string;
  notes: string;
};

export type SchedulerSettings = {
  enabled: boolean;
  intervalMinutes: number;
  batchSize: number;
  runEnrichment: boolean;
  lastRunAt?: string;
  nextRunAt?: string;
  lastStatus: string;
  lastError?: string;
  lastFoundCount: number;
  lastSavedCount: number;
  lastPublishedCount: number;
  updatedAt: string;
};

export type EnrichmentSchedulerSettings = {
  enabled: boolean;
  intervalMinutes: number;
  batchSize: number;
  lastRunAt?: string;
  nextRunAt?: string;
  lastStatus: string;
  lastError?: string;
  lastProcessedCount: number;
  lastEnrichedCount: number;
  updatedAt: string;
};

export type EditorialSchedulerSettings = {
  enabled: boolean;
  intervalMinutes: number;
  batchSize: number;
  lastRunAt?: string;
  nextRunAt?: string;
  lastStatus: string;
  lastError?: string;
  lastPlannedCount: number;
  lastGeneratedCount: number;
  lastReviewedCount: number;
  updatedAt: string;
};

export type PublishSchedulerSettings = {
  enabled: boolean;
  intervalMinutes: number;
  batchSize: number;
  lastRunAt?: string;
  nextRunAt?: string;
  lastStatus: string;
  lastError?: string;
  lastPublishedCount: number;
  updatedAt: string;
};

export type PipelineRun = {
  id: string;
  phase: string;
  trigger: string;
  status: string;
  startedAt: string;
  finishedAt: string;
  durationMs: number;
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
  }>;
  error?: string;
};

export type EditorialStudioData = {
  prompts: PromptConfig[];
  rawItems: RawItem[];
  drafts: DraftArticle[];
  reviews: EditorReview[];
  contentPlan: ContentPlanItem[];
  editorialStatus: EditorialStatus;
  sourceStates: SourceSyncState[];
  sources: SourceConfig[];
  scheduler: SchedulerSettings;
  enrichmentScheduler: EnrichmentSchedulerSettings;
  editorialScheduler: EditorialSchedulerSettings;
  publishScheduler: PublishSchedulerSettings;
  pipelineRuns: PipelineRun[];
  isLive: boolean;
  liveError?: string;
};

export type RawDraftPair = {
  rawItem: RawItem;
  draft?: DraftArticle;
};

const fallbackPrompts: PromptConfig[] = [
  {
    id: "prompt:writer:v1",
    agentKey: "writer",
    name: "Writer MVP v1",
    version: 1,
    status: "active",
    systemPrompt:
      "Ты спортивный редактор ezbet.ru. На MVP собираешь из сырой новости чистый черновик.",
    userPromptTemplate: "Сделай dek и короткий body на основе title и summary.",
    model: "local-editor-mvp",
    provider: "internal",
    notes: "Fallback preview",
    createdAt: "2026-05-03T00:00:00.000Z"
  },
  {
    id: "prompt:editor:v1",
    agentKey: "editor",
    name: "Editor MVP v1",
    version: 1,
    status: "active",
    systemPrompt: "Ты редактор-корректор ezbet.ru.",
    userPromptTemplate: "Проверь черновик и верни короткий review summary.",
    model: "local-editor-mvp",
    provider: "internal",
    notes: "Fallback preview",
    createdAt: "2026-05-03T00:00:00.000Z"
  }
];

const fallbackRawItems: RawItem[] = [
  {
    id: "raw:fallback:1",
    sourceKey: "fallback",
    sourceTitle: "fallback source",
    category: "general",
    normalizedCategory: "general",
    title: "Исходная RSS-новость для compare-режима",
    summary: "Это fallback summary, который показывает, как мы будем сравнивать сырой RSS-вход и итоговый AI draft.",
    lead: "Fallback lead показывает, что enrichment может добавлять к сырой новости более аккуратный краткий контекст.",
    fullText:
      "Это fallback full text. Здесь должен быть полный текст исходной новости или полный текст, вытянутый со страницы-источника.\n\nНа боевом потоке этот блок помогает сравнивать не только короткий summary, но и фактическую основу, из которой writer и editor собирают итоговую статью.",
    tags: ["Fallback", "AI", "Editorial"],
    url: "https://example.com/news/1",
    publishedAt: "2026-05-03T00:00:00.000Z",
    fetchedAt: "2026-05-03T00:00:00.000Z",
    importanceScore: 72,
    triageLabel: "medium",
    isDuplicate: false
  }
];

const fallbackDrafts: DraftArticle[] = [
  {
    id: "draft:fallback:1",
    rawItemId: "raw:fallback:1",
    title: "Черновик статьи для MVP-редакции",
    dek: "Fallback-черновик показывает, как будет выглядеть AI-редакция на следующем этапе.",
    body:
      "Сначала ingestion собирает новость и сохраняет ее в raw_items.\n\nЗатем editorial-слой превращает короткий summary в компактный черновик.\n\nПосле review такой материал можно либо отправить в публикацию, либо отдать редактору на ручную доработку.",
    category: "general",
    sourceTitle: "fallback source",
    sourceUrl: "https://example.com",
    publishedAt: "2026-05-03T00:00:00.000Z",
    status: "ready_for_publish",
    reviewStatus: "reviewed",
    reviewSummary: "Структура читается, factual expansion не замечен.",
    publishDecision: "publish_skip",
    publishReason: "Fallback preview не публикуется автоматически.",
    promptConfigId: "prompt:writer:v1",
    promptName: "Writer MVP v1",
    model: "local-editor-mvp",
    generationMode: "template",
    createdAt: "2026-05-03T00:00:00.000Z",
    updatedAt: "2026-05-03T00:00:00.000Z"
  }
];

const fallbackReviews: EditorReview[] = [
  {
    id: "review:fallback:1",
    draftId: "draft:fallback:1",
    status: "reviewed",
    summary: "Структура читается, factual expansion не замечен.",
    notes: "Fallback review",
    promptConfigId: "prompt:editor:v1",
    promptName: "Editor MVP v1",
    model: "local-editor-mvp",
    createdAt: "2026-05-03T00:00:00.000Z"
  }
];

const fallbackContentPlan: ContentPlanItem[] = [
  {
    id: "plan:fallback:1",
    rawItemId: "raw:fallback:1",
    title: "Fallback content plan item",
    sourceTitle: "fallback source",
    category: "general",
    priorityScore: 72,
    priorityLabel: "medium",
    plannedFormat: "news_update",
    status: "ready_for_publish",
    reason: "Fallback planner preview for the admin and studio screens.",
    createdAt: "2026-05-03T00:00:00.000Z",
    updatedAt: "2026-05-03T00:00:00.000Z"
  }
];

const fallbackEditorialStatus: EditorialStatus = {
  openaiEnabled: false,
  openaiModel: "gpt-5-mini",
  openaiSearchModel: "gpt-5-mini",
  fallbackMode: true,
  providerLabel: "OpenAI",
  apiStyle: "responses",
  webSearchEnabled: false
};

const fallbackSourceStates: SourceSyncState[] = [
  {
    sourceKey: "sports-ru-topnews",
    sourceTitle: "Sports.ru",
    lastFetchedAt: "2026-05-05T10:00:00.000Z",
    lastSuccessfulFetchAt: "2026-05-05T10:00:00.000Z",
    lastSuccessfulParseAt: "2026-05-05T10:00:00.000Z",
    lastPublishedAt: "2026-05-05T09:55:00.000Z",
    lastExternalId: "https://www.sports.ru/news/example-1/",
    lastItemCount: 24,
    fetchStatus: "ok",
    parseStatus: "ok",
    fetchErrorCount: 0,
    parseErrorCount: 0,
    consecutiveFailures: 0,
    retryCount: 0,
    lastProbeAt: "2026-05-05T10:01:00.000Z",
    lastProbeCount: 24,
    lastProbeReadiness: "ready",
    preferredAdapter: "rss",
    preferredAdapterUrl: "https://www.sports.ru/rss/topnews.xml",
    supportsRss: true,
    supportsNewsSitemap: false,
    supportsSitemap: false,
    supportsScraping: false,
    lastProbeFullTextOk: true,
    lastProbeLeadOk: true,
    lastProbeTagsCount: 3,
    lastProbeSampleTitle: "Пример новости Sports.ru",
    lastProbeSampleUrl: "https://www.sports.ru/news/example-1/",
    lastStatus: "ok",
    updatedAt: "2026-05-05T10:00:00.000Z"
  },
  {
    sourceKey: "sport-express-news",
    sourceTitle: "Спорт-Экспресс",
    lastFetchedAt: "2026-05-05T10:00:00.000Z",
    lastSuccessfulFetchAt: "2026-05-05T10:00:00.000Z",
    lastSuccessfulParseAt: "2026-05-05T10:00:00.000Z",
    lastPublishedAt: "2026-05-05T09:50:00.000Z",
    lastExternalId: "https://www.sport-express.ru/news/example-2/",
    lastItemCount: 31,
    fetchStatus: "ok",
    parseStatus: "ok",
    fetchErrorCount: 0,
    parseErrorCount: 0,
    consecutiveFailures: 0,
    retryCount: 0,
    lastProbeAt: "2026-05-05T10:01:00.000Z",
    lastProbeCount: 31,
    lastProbeReadiness: "ready",
    preferredAdapter: "scraping",
    preferredAdapterUrl: "https://www.sport-express.ru/services/materials/news/se/",
    supportsRss: false,
    supportsNewsSitemap: false,
    supportsSitemap: false,
    supportsScraping: true,
    lastProbeFullTextOk: true,
    lastProbeLeadOk: true,
    lastProbeTagsCount: 2,
    lastProbeSampleTitle: "Пример новости Спорт-Экспресс",
    lastProbeSampleUrl: "https://www.sport-express.ru/news/example-2/",
    lastStatus: "ok",
    updatedAt: "2026-05-05T10:00:00.000Z"
  }
];

const fallbackSources: SourceConfig[] = [
  {
    key: "sports-ru-topnews",
    title: "Sports.ru",
    url: "https://www.sports.ru/rss/topnews.xml",
    category: "Спорт",
    sourceType: "rss",
    status: "active",
    notes: "Fallback source"
  },
  {
    key: "sport-express-news",
    title: "Спорт-Экспресс",
    url: "https://www.sport-express.ru/services/materials/news/se/",
    category: "Спорт",
    sourceType: "rss",
    status: "active",
    notes: "Fallback source"
  }
];

const fallbackScheduler: SchedulerSettings = {
  enabled: false,
  intervalMinutes: 60,
  batchSize: 5,
  runEnrichment: false,
  lastStatus: "idle",
  lastFoundCount: 0,
  lastSavedCount: 0,
  lastPublishedCount: 0,
  updatedAt: "2026-05-05T10:00:00.000Z"
};

const fallbackEnrichmentScheduler: EnrichmentSchedulerSettings = {
  enabled: false,
  intervalMinutes: 60,
  batchSize: 10,
  lastStatus: "idle",
  lastProcessedCount: 0,
  lastEnrichedCount: 0,
  updatedAt: "2026-05-05T10:00:00.000Z"
};

const fallbackEditorialScheduler: EditorialSchedulerSettings = {
  enabled: false,
  intervalMinutes: 60,
  batchSize: 5,
  lastStatus: "idle",
  lastPlannedCount: 0,
  lastGeneratedCount: 0,
  lastReviewedCount: 0,
  updatedAt: "2026-05-05T10:00:00.000Z"
};

const fallbackPublishScheduler: PublishSchedulerSettings = {
  enabled: false,
  intervalMinutes: 60,
  batchSize: 5,
  lastStatus: "idle",
  lastPublishedCount: 0,
  updatedAt: "2026-05-05T10:00:00.000Z"
};

const fallbackPipelineRuns: PipelineRun[] = [];

export async function getEditorialStudioData(): Promise<EditorialStudioData> {
  const baseUrl = resolveApiBaseUrl();

  if (!baseUrl) {
    return {
      prompts: fallbackPrompts,
      rawItems: fallbackRawItems,
      drafts: fallbackDrafts,
      reviews: fallbackReviews,
      contentPlan: fallbackContentPlan,
      editorialStatus: fallbackEditorialStatus,
      sourceStates: fallbackSourceStates,
      sources: fallbackSources,
      scheduler: fallbackScheduler,
      enrichmentScheduler: fallbackEnrichmentScheduler,
      editorialScheduler: fallbackEditorialScheduler,
      publishScheduler: fallbackPublishScheduler,
      pipelineRuns: fallbackPipelineRuns,
      isLive: false,
      liveError: "EZBET_API_BASE_URL is not configured."
    };
  }

  try {
    const [
      promptsResponse,
      rawItemsResponse,
      draftsResponse,
      reviewsResponse,
      contentPlanResponse,
      statusResponse,
      sourceStatesResponse,
      sourcesResponse,
      schedulerResponse,
      enrichmentSchedulerResponse,
      editorialSchedulerResponse,
      publishSchedulerResponse,
      pipelineRunsResponse
    ] =
      await Promise.all([
      fetch(new URL("/api/v1/prompts", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/raw-items/preview?limit=50", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/drafts", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/reviews", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/content-plan", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/editorial/status", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/source-states", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/sources", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/scheduler", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/enrichment-scheduler", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/editorial-scheduler", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/publish-scheduler", baseUrl).toString(), { next: { revalidate: 30 } }),
      fetch(new URL("/api/v1/pipeline-runs?limit=12", baseUrl).toString(), { next: { revalidate: 15 } })
    ]);

    if (
      !promptsResponse.ok ||
      !rawItemsResponse.ok ||
      !draftsResponse.ok ||
      !reviewsResponse.ok ||
      !contentPlanResponse.ok ||
      !statusResponse.ok ||
      !sourceStatesResponse.ok ||
      !sourcesResponse.ok ||
      !schedulerResponse.ok ||
      !enrichmentSchedulerResponse.ok ||
      !editorialSchedulerResponse.ok ||
      !publishSchedulerResponse.ok ||
      !pipelineRunsResponse.ok
    ) {
      const responses: Array<[string, number]> = [
        ["prompts", promptsResponse.status],
        ["raw-items", rawItemsResponse.status],
        ["drafts", draftsResponse.status],
        ["reviews", reviewsResponse.status],
        ["content-plan", contentPlanResponse.status],
        ["status", statusResponse.status],
        ["source-states", sourceStatesResponse.status],
        ["sources", sourcesResponse.status],
        ["scheduler", schedulerResponse.status],
        ["enrichment-scheduler", enrichmentSchedulerResponse.status],
        ["editorial-scheduler", editorialSchedulerResponse.status],
        ["publish-scheduler", publishSchedulerResponse.status],
        ["pipeline-runs", pipelineRunsResponse.status]
      ];
      const failedStatuses = responses
        .filter(([, status]) => status >= 400)
        .map(([name, status]) => `${name}: ${status}`)
        .join(", ");
      throw new Error(failedStatuses || "Editorial endpoints unavailable");
    }

    const promptsPayload = (await promptsResponse.json()) as { items: PromptConfig[] };
    const rawItemsPayload = (await rawItemsResponse.json()) as { items: RawItem[] };
    const draftsPayload = (await draftsResponse.json()) as { items: DraftArticle[] };
    const reviewsPayload = (await reviewsResponse.json()) as { items: EditorReview[] };
    const contentPlanPayload = (await contentPlanResponse.json()) as { items: ContentPlanItem[] };
    const statusPayload = (await statusResponse.json()) as EditorialStatus;
    const sourceStatesPayload = (await sourceStatesResponse.json()) as { items: SourceSyncState[] };
    const sourcesPayload = (await sourcesResponse.json()) as { items: SourceConfig[] };
    const schedulerPayload = (await schedulerResponse.json()) as SchedulerSettings;
    const enrichmentSchedulerPayload = (await enrichmentSchedulerResponse.json()) as EnrichmentSchedulerSettings;
    const editorialSchedulerPayload = (await editorialSchedulerResponse.json()) as EditorialSchedulerSettings;
    const publishSchedulerPayload = (await publishSchedulerResponse.json()) as PublishSchedulerSettings;
    const pipelineRunsPayload = (await pipelineRunsResponse.json()) as { items: PipelineRun[] };

    return {
      prompts: promptsPayload.items,
      rawItems: rawItemsPayload.items,
      drafts: draftsPayload.items,
      reviews: reviewsPayload.items,
      contentPlan: contentPlanPayload.items,
      editorialStatus: statusPayload,
      sourceStates: sourceStatesPayload.items,
      sources: sourcesPayload.items,
      scheduler: schedulerPayload,
      enrichmentScheduler: enrichmentSchedulerPayload,
      editorialScheduler: editorialSchedulerPayload,
      publishScheduler: publishSchedulerPayload,
      pipelineRuns: pipelineRunsPayload.items,
      isLive: true
    };
  } catch (error) {
    return {
      prompts: fallbackPrompts,
      rawItems: fallbackRawItems,
      drafts: fallbackDrafts,
      reviews: fallbackReviews,
      contentPlan: fallbackContentPlan,
      editorialStatus: fallbackEditorialStatus,
      sourceStates: fallbackSourceStates,
      sources: fallbackSources,
      scheduler: fallbackScheduler,
      enrichmentScheduler: fallbackEnrichmentScheduler,
      editorialScheduler: fallbackEditorialScheduler,
      publishScheduler: fallbackPublishScheduler,
      pipelineRuns: fallbackPipelineRuns,
      isLive: false,
      liveError: error instanceof Error ? error.message : "Unknown API error."
    };
  }
}

export function buildRawDraftPairs(data: EditorialStudioData, limit = 10): RawDraftPair[] {
  const draftsByRawId = new Map(data.drafts.map((draft) => [draft.rawItemId, draft]));
  const pairs: RawDraftPair[] = [];

  for (const rawItem of data.rawItems) {
    pairs.push({
      rawItem,
      draft: draftsByRawId.get(rawItem.id)
    });

    if (pairs.length >= limit) {
      break;
    }
  }

  return pairs;
}
