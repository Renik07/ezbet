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
  duplicateStage?: string;
  duplicateReason?: string;
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

export type PromptLabItem = {
  id: string;
  runId: string;
  rawItemId: string;
  sourceTitle: string;
  sourceUrl?: string;
  rawTitle: string;
  rawSummary: string;
  rawFullText?: string;
  rawLead?: string;
  rawUrl?: string;
  rawPublishedAt: string;
  importanceScore: number;
  triageLabel: string;
  writerTitle: string;
  writerDek: string;
  writerBody: string;
  writerModel: string;
  writerGenerationMode: string;
  writerPromptId: string;
  writerPromptName: string;
  editorSummary: string;
  editorNotes: string;
  editorModel: string;
  editorPromptId: string;
  editorPromptName: string;
  qualityGateDecision: string;
  qualityGateReason: string;
  createdAt: string;
};

export type PromptLabRun = {
  id: string;
  status: string;
  requestedLimit: number;
  selectedCount: number;
  freshCount: number;
  reusedCount: number;
  writerPromptId: string;
  writerPromptName: string;
  editorPromptId: string;
  editorPromptName: string;
  notes: string;
  createdAt: string;
  items: PromptLabItem[];
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
  promptLab: PromptLabRun;
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
    sourceUrl: "https://example.com",
    category: "general",
    normalizedCategory: "general",
    title: "Исходная RSS-новость для compare-режима",
    summary: "Это fallback summary, который показывает, как мы будем сравнивать сырой RSS-вход и итоговый AI draft.",
    lead: "Fallback lead показывает, что enrichment может добавлять к сырой новости более аккуратный краткий контекст.",
    fullText:
      "Это fallback full text. Здесь должен быть полный текст исходной новости или полный текст, вытянутый со страницы-источника.\n\nНа боевом потоке этот блок помогает сравнивать не только короткий summary, но и фактическую основу, из которой writer и editor собирают итоговую статью.",
    referenceUrls: ["https://example.com/news/1"],
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
const fallbackPromptLab: PromptLabRun = {
  id: "prompt-lab:fallback",
  status: "idle",
  requestedLimit: 3,
  selectedCount: 1,
  freshCount: 0,
  reusedCount: 1,
  writerPromptId: "prompt:writer:v1",
  writerPromptName: "Writer MVP v1",
  editorPromptId: "prompt:editor:v1",
  editorPromptName: "Editor MVP v1",
  notes: "TEMP prompt lab flow for rapid prompt testing. Remove or replace this path after prompt tuning is complete.",
  createdAt: "2026-05-05T10:00:00.000Z",
  items: [
    {
      id: "prompt-lab:fallback:item:1",
      runId: "prompt-lab:fallback",
      rawItemId: "raw:fallback:1",
      sourceTitle: "fallback source",
      sourceUrl: "https://example.com",
      rawTitle: "Исходная RSS-новость для compare-режима",
      rawSummary: "Это fallback summary, который показывает, как мы будем сравнивать сырой RSS-вход и итоговый AI draft.",
      rawFullText:
        "Это fallback full text. Здесь должен быть полный текст исходной новости или полный текст, вытянутый со страницы-источника.",
      rawLead: "Fallback lead для demo prompt lab.",
      rawUrl: "https://example.com/news/1",
      rawPublishedAt: "2026-05-03T00:00:00.000Z",
      importanceScore: 72,
      triageLabel: "medium",
      writerTitle: "Черновик статьи для MVP-редакции",
      writerDek: "Fallback-черновик показывает, как будет выглядеть AI-редакция на следующем этапе.",
      writerBody:
        "Сначала ingestion собирает новость и сохраняет ее в raw_items.\n\nЗатем writer prompt превращает короткий summary в читабельный черновик.",
      writerModel: "local-editor-mvp",
      writerGenerationMode: "template",
      writerPromptId: "prompt:writer:v1",
      writerPromptName: "Writer MVP v1",
      editorSummary: "Структура читается, factual expansion не замечен.",
      editorNotes: "Editor prompt в текущем флоу только ревьюит текст и не пишет отдельную вторую статью.",
      editorModel: "local-editor-mvp",
      editorPromptId: "prompt:editor:v1",
      editorPromptName: "Editor MVP v1",
      qualityGateDecision: "hold",
      qualityGateReason: "Fallback preview не публикуется автоматически.",
      createdAt: "2026-05-05T10:00:00.000Z"
    }
  ]
};

async function loadStudioResource<T>(
  baseUrl: string,
  path: string,
  parse: (payload: unknown) => T,
  fallback: T
): Promise<{ data: T; error?: string }> {
  try {
    const response = await fetch(new URL(path, baseUrl).toString(), { cache: "no-store" });
    if (!response.ok) {
      return { data: fallback, error: `${path}: ${response.status}` };
    }
    return { data: parse(await response.json()), error: undefined };
  } catch (error) {
    return {
      data: fallback,
      error: `${path}: ${error instanceof Error ? error.message : "Unknown API error"}`
    };
  }
}

export async function getEditorialStudioData(options?: { includePromptLab?: boolean }): Promise<EditorialStudioData> {
  const baseUrl = resolveApiBaseUrl();
  const includePromptLab = options?.includePromptLab ?? true;

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
      promptLab: fallbackPromptLab,
      isLive: false,
      liveError: "EZBET_API_BASE_URL is not configured."
    };
  }

  const [
    promptsResult,
    rawItemsResult,
    draftsResult,
    reviewsResult,
    contentPlanResult,
    statusResult,
    sourceStatesResult,
    sourcesResult,
    schedulerResult,
    enrichmentSchedulerResult,
    editorialSchedulerResult,
    publishSchedulerResult,
    pipelineRunsResult,
    promptLabResult
  ] = await Promise.all([
    loadStudioResource(baseUrl, "/api/v1/prompts", (payload) => (payload as { items: PromptConfig[] }).items, fallbackPrompts),
    loadStudioResource(
      baseUrl,
      "/api/v1/raw-items/preview?limit=50",
      (payload) => (payload as { items: RawItem[] }).items,
      fallbackRawItems
    ),
    loadStudioResource(baseUrl, "/api/v1/drafts", (payload) => (payload as { items: DraftArticle[] }).items, fallbackDrafts),
    loadStudioResource(baseUrl, "/api/v1/reviews", (payload) => (payload as { items: EditorReview[] }).items, fallbackReviews),
    loadStudioResource(
      baseUrl,
      "/api/v1/content-plan",
      (payload) => (payload as { items: ContentPlanItem[] }).items,
      fallbackContentPlan
    ),
    loadStudioResource(baseUrl, "/api/v1/editorial/status", (payload) => payload as EditorialStatus, fallbackEditorialStatus),
    loadStudioResource(
      baseUrl,
      "/api/v1/source-states",
      (payload) => (payload as { items: SourceSyncState[] }).items,
      fallbackSourceStates
    ),
    loadStudioResource(baseUrl, "/api/v1/sources", (payload) => (payload as { items: SourceConfig[] }).items, fallbackSources),
    loadStudioResource(baseUrl, "/api/v1/scheduler", (payload) => payload as SchedulerSettings, fallbackScheduler),
    loadStudioResource(
      baseUrl,
      "/api/v1/enrichment-scheduler",
      (payload) => payload as EnrichmentSchedulerSettings,
      fallbackEnrichmentScheduler
    ),
    loadStudioResource(
      baseUrl,
      "/api/v1/editorial-scheduler",
      (payload) => payload as EditorialSchedulerSettings,
      fallbackEditorialScheduler
    ),
    loadStudioResource(
      baseUrl,
      "/api/v1/publish-scheduler",
      (payload) => payload as PublishSchedulerSettings,
      fallbackPublishScheduler
    ),
    loadStudioResource(
      baseUrl,
      "/api/v1/pipeline-runs?limit=12",
      (payload) => (payload as { items: PipelineRun[] }).items,
      fallbackPipelineRuns
    ),
    includePromptLab
      ? loadStudioResource(
          baseUrl,
          "/api/v1/prompt-lab/latest",
          (payload) => (payload as { item: PromptLabRun }).item,
          fallbackPromptLab
        )
      : Promise.resolve({ data: fallbackPromptLab, error: undefined })
  ]);

  const partialErrors = [
    promptsResult.error,
    rawItemsResult.error,
    draftsResult.error,
    reviewsResult.error,
    contentPlanResult.error,
    statusResult.error,
    sourceStatesResult.error,
    sourcesResult.error,
    schedulerResult.error,
    enrichmentSchedulerResult.error,
    editorialSchedulerResult.error,
    publishSchedulerResult.error,
    pipelineRunsResult.error,
    includePromptLab ? promptLabResult.error : undefined
  ].filter((value): value is string => Boolean(value));

  const expectedResourceCount = includePromptLab ? 14 : 13;
  const isLive = partialErrors.length < expectedResourceCount;

  return {
    prompts: promptsResult.data,
    rawItems: rawItemsResult.data,
    drafts: draftsResult.data,
    reviews: reviewsResult.data,
    contentPlan: contentPlanResult.data,
    editorialStatus: statusResult.data,
    sourceStates: sourceStatesResult.data,
    sources: sourcesResult.data,
    scheduler: schedulerResult.data,
    enrichmentScheduler: enrichmentSchedulerResult.data,
    editorialScheduler: editorialSchedulerResult.data,
    publishScheduler: publishSchedulerResult.data,
    pipelineRuns: pipelineRunsResult.data,
    promptLab: promptLabResult.data,
    isLive,
    liveError: partialErrors.length ? partialErrors.join("; ") : undefined
  };
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
