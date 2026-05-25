from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    id: str
    title: str
    description: str
    category: str
    published_at: datetime = Field(serialization_alias="publishedAt")
    source: str
    link: Optional[str] = None
    status: str = "published"
    ai_reviewed: bool = Field(default=False, serialization_alias="aiReviewed")
    article_slug: Optional[str] = Field(default=None, serialization_alias="articleSlug")


class Article(BaseModel):
    id: str
    slug: str
    news_item_id: str = Field(serialization_alias="newsItemId")
    raw_item_id: str = Field(serialization_alias="rawItemId")
    title: str
    lead: Optional[str] = None
    dek: str
    body: str
    category: str
    source_title: str = Field(serialization_alias="sourceTitle")
    source_url: Optional[str] = Field(default=None, serialization_alias="sourceUrl")
    tags: list[str] = Field(default_factory=list)
    published_at: datetime = Field(serialization_alias="publishedAt")
    ai_reviewed: bool = Field(default=True, serialization_alias="aiReviewed")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class RawItem(BaseModel):
    id: str
    source_key: str = Field(serialization_alias="sourceKey")
    source_title: str = Field(serialization_alias="sourceTitle")
    source_url: str = Field(serialization_alias="sourceUrl")
    category: str
    normalized_category: str = Field(serialization_alias="normalizedCategory")
    external_id: str = Field(serialization_alias="externalId")
    dedupe_key: str = Field(serialization_alias="dedupeKey")
    title: str
    summary: str
    lead: Optional[str] = None
    url: Optional[str] = None
    published_at: datetime = Field(serialization_alias="publishedAt")
    fetched_at: datetime = Field(serialization_alias="fetchedAt")
    importance_score: int = Field(serialization_alias="importanceScore")
    triage_label: str = Field(serialization_alias="triageLabel")
    is_duplicate: bool = Field(default=False, serialization_alias="isDuplicate")
    duplicate_of: Optional[str] = Field(default=None, serialization_alias="duplicateOf")
    duplicate_stage: Optional[str] = Field(default=None, serialization_alias="duplicateStage")
    duplicate_reason: Optional[str] = Field(default=None, serialization_alias="duplicateReason")
    full_text: Optional[str] = Field(default=None, serialization_alias="fullText")
    full_text_source_url: Optional[str] = Field(default=None, serialization_alias="fullTextSourceUrl")
    full_text_source_title: Optional[str] = Field(default=None, serialization_alias="fullTextSourceTitle")
    reference_urls: list[str] = Field(default_factory=list, serialization_alias="referenceUrls")
    extraction_mode: Optional[str] = Field(default=None, serialization_alias="extractionMode")
    enrichment_status: Optional[str] = Field(default=None, serialization_alias="enrichmentStatus")
    enrichment_error: Optional[str] = Field(default=None, serialization_alias="enrichmentError")
    tags: list[str] = Field(default_factory=list)
    payload: str


class RawItemPreview(BaseModel):
    id: str
    source_key: str = Field(serialization_alias="sourceKey")
    source_title: str = Field(serialization_alias="sourceTitle")
    category: str
    normalized_category: str = Field(serialization_alias="normalizedCategory")
    title: str
    summary: str
    lead: Optional[str] = None
    url: Optional[str] = None
    published_at: datetime = Field(serialization_alias="publishedAt")
    fetched_at: datetime = Field(serialization_alias="fetchedAt")
    importance_score: int = Field(serialization_alias="importanceScore")
    triage_label: str = Field(serialization_alias="triageLabel")
    is_duplicate: bool = Field(default=False, serialization_alias="isDuplicate")
    duplicate_of: Optional[str] = Field(default=None, serialization_alias="duplicateOf")
    duplicate_stage: Optional[str] = Field(default=None, serialization_alias="duplicateStage")
    duplicate_reason: Optional[str] = Field(default=None, serialization_alias="duplicateReason")
    full_text: Optional[str] = Field(default=None, serialization_alias="fullText")
    full_text_source_url: Optional[str] = Field(default=None, serialization_alias="fullTextSourceUrl")
    full_text_source_title: Optional[str] = Field(default=None, serialization_alias="fullTextSourceTitle")
    reference_urls: list[str] = Field(default_factory=list, serialization_alias="referenceUrls")
    extraction_mode: Optional[str] = Field(default=None, serialization_alias="extractionMode")
    enrichment_status: Optional[str] = Field(default=None, serialization_alias="enrichmentStatus")
    enrichment_error: Optional[str] = Field(default=None, serialization_alias="enrichmentError")
    content_plan_status: Optional[str] = Field(default=None, serialization_alias="contentPlanStatus")
    content_plan_reason: Optional[str] = Field(default=None, serialization_alias="contentPlanReason")
    content_plan_priority_label: Optional[str] = Field(default=None, serialization_alias="contentPlanPriorityLabel")
    tags: list[str] = Field(default_factory=list)


class PromptConfig(BaseModel):
    id: str
    agent_key: str = Field(serialization_alias="agentKey")
    name: str
    version: int
    status: str = "active"
    system_prompt: str = Field(serialization_alias="systemPrompt")
    user_prompt_template: str = Field(serialization_alias="userPromptTemplate")
    model: str
    provider: str = "internal"
    notes: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="createdAt",
    )


class DraftArticle(BaseModel):
    id: str
    raw_item_id: str = Field(serialization_alias="rawItemId")
    title: str
    dek: str
    body: str
    category: str
    source_title: str = Field(serialization_alias="sourceTitle")
    source_url: Optional[str] = Field(default=None, serialization_alias="sourceUrl")
    published_at: datetime = Field(serialization_alias="publishedAt")
    status: str = "draft"
    review_status: str = Field(default="pending", serialization_alias="reviewStatus")
    review_summary: Optional[str] = Field(default=None, serialization_alias="reviewSummary")
    publish_decision: str = Field(default="publish_pending", serialization_alias="publishDecision")
    publish_reason: Optional[str] = Field(default=None, serialization_alias="publishReason")
    prompt_config_id: str = Field(serialization_alias="promptConfigId")
    prompt_name: str = Field(serialization_alias="promptName")
    model: str
    generation_mode: str = Field(default="template", serialization_alias="generationMode")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class EditorReview(BaseModel):
    id: str
    draft_id: str = Field(serialization_alias="draftId")
    status: str = "reviewed"
    summary: str
    notes: str = ""
    prompt_config_id: str = Field(serialization_alias="promptConfigId")
    prompt_name: str = Field(serialization_alias="promptName")
    model: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="createdAt",
    )


class ContentPlanItem(BaseModel):
    id: str
    raw_item_id: str = Field(serialization_alias="rawItemId")
    title: str
    source_title: str = Field(serialization_alias="sourceTitle")
    category: str
    priority_score: int = Field(serialization_alias="priorityScore")
    priority_label: str = Field(serialization_alias="priorityLabel")
    planned_format: str = Field(serialization_alias="plannedFormat")
    status: str = "planned"
    reason: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class PipelineRun(BaseModel):
    id: str
    phase: str
    trigger: str
    status: str
    started_at: datetime = Field(serialization_alias="startedAt")
    finished_at: datetime = Field(serialization_alias="finishedAt")
    duration_ms: int = Field(serialization_alias="durationMs")
    found_count: int = Field(default=0, serialization_alias="foundCount")
    saved_count: int = Field(default=0, serialization_alias="savedCount")
    published_count: int = Field(default=0, serialization_alias="publishedCount")
    processed_count: int = Field(default=0, serialization_alias="processedCount")
    enriched_count: int = Field(default=0, serialization_alias="enrichedCount")
    planned_count: int = Field(default=0, serialization_alias="plannedCount")
    generated_count: int = Field(default=0, serialization_alias="generatedCount")
    reviewed_count: int = Field(default=0, serialization_alias="reviewedCount")
    skipped_items: list["PipelineSkippedItem"] = Field(default_factory=list, serialization_alias="skippedItems")
    source_breakdown: list["PipelineSourceBreakdownItem"] = Field(
        default_factory=list,
        serialization_alias="sourceBreakdown",
    )
    error: Optional[str] = None


class PipelineSkippedItem(BaseModel):
    title: str
    reason: Optional[str] = None


class PipelineSourceBreakdownItem(BaseModel):
    source_key: str = Field(serialization_alias="sourceKey")
    source_title: str = Field(serialization_alias="sourceTitle")
    found_count: int = Field(default=0, serialization_alias="foundCount")


class NewsListResponse(BaseModel):
    items: list[NewsItem]


class ArticleResponse(BaseModel):
    item: Article


class RawItemListResponse(BaseModel):
    items: list[RawItem]


class RawItemPreviewListResponse(BaseModel):
    items: list[RawItemPreview]


class PipelineRunListResponse(BaseModel):
    items: list[PipelineRun]


class IngestResponse(BaseModel):
    ingested: int
    published: int
    items: list[NewsItem]
    raw_items: int = Field(serialization_alias="rawItems")


class SourceItem(BaseModel):
    key: str
    title: str
    url: str
    category: str
    source_type: str = Field(default="rss", serialization_alias="sourceType")
    status: str = "active"
    notes: str = ""


class SourceListResponse(BaseModel):
    items: list[SourceItem]


class SourceCreateRequest(BaseModel):
    key: str
    title: str
    url: str
    category: str
    source_type: str = Field(default="rss", serialization_alias="sourceType")
    status: str = "draft"
    notes: str = ""
    probe_ok: bool = Field(default=False, alias="probeOk", serialization_alias="probeOk")
    probe_item_count: int = Field(default=0, alias="probeItemCount", serialization_alias="probeItemCount")
    probe_readiness: str = Field(default="unknown", alias="probeReadiness", serialization_alias="probeReadiness")
    resolved_source_type: Optional[str] = Field(default=None, alias="resolvedSourceType", serialization_alias="resolvedSourceType")
    resolved_source_url: Optional[str] = Field(default=None, alias="resolvedSourceUrl", serialization_alias="resolvedSourceUrl")
    supports_rss: bool = Field(default=False, alias="supportsRss", serialization_alias="supportsRss")
    supports_news_sitemap: bool = Field(default=False, alias="supportsNewsSitemap", serialization_alias="supportsNewsSitemap")
    supports_sitemap: bool = Field(default=False, alias="supportsSitemap", serialization_alias="supportsSitemap")
    supports_scraping: bool = Field(default=False, alias="supportsScraping", serialization_alias="supportsScraping")
    full_text_ok: bool = Field(default=False, alias="fullTextOk", serialization_alias="fullTextOk")
    lead_ok: bool = Field(default=False, alias="leadOk", serialization_alias="leadOk")
    tags_count: int = Field(default=0, alias="tagsCount", serialization_alias="tagsCount")
    sample_title: Optional[str] = Field(default=None, alias="sampleTitle", serialization_alias="sampleTitle")
    sample_url: Optional[str] = Field(default=None, alias="sampleUrl", serialization_alias="sampleUrl")


class SourceUpdateRequest(BaseModel):
    title: str
    url: str
    category: str
    source_type: str = Field(default="rss", serialization_alias="sourceType")
    status: str = "draft"
    notes: str = ""


class SourceSyncState(BaseModel):
    source_key: str = Field(serialization_alias="sourceKey")
    source_title: str = Field(serialization_alias="sourceTitle")
    last_fetched_at: Optional[datetime] = Field(default=None, serialization_alias="lastFetchedAt")
    last_successful_fetch_at: Optional[datetime] = Field(
        default=None, serialization_alias="lastSuccessfulFetchAt"
    )
    last_successful_parse_at: Optional[datetime] = Field(
        default=None, serialization_alias="lastSuccessfulParseAt"
    )
    last_published_at: Optional[datetime] = Field(default=None, serialization_alias="lastPublishedAt")
    last_external_id: Optional[str] = Field(default=None, serialization_alias="lastExternalId")
    last_item_count: int = Field(default=0, serialization_alias="lastItemCount")
    fetch_status: str = Field(default="idle", serialization_alias="fetchStatus")
    parse_status: str = Field(default="idle", serialization_alias="parseStatus")
    fetch_error_count: int = Field(default=0, serialization_alias="fetchErrorCount")
    parse_error_count: int = Field(default=0, serialization_alias="parseErrorCount")
    consecutive_failures: int = Field(default=0, serialization_alias="consecutiveFailures")
    retry_count: int = Field(default=0, serialization_alias="retryCount")
    last_probe_at: Optional[datetime] = Field(default=None, serialization_alias="lastProbeAt")
    last_probe_count: int = Field(default=0, serialization_alias="lastProbeCount")
    last_probe_readiness: str = Field(default="unknown", serialization_alias="lastProbeReadiness")
    preferred_adapter: Optional[str] = Field(default=None, serialization_alias="preferredAdapter")
    preferred_adapter_url: Optional[str] = Field(default=None, serialization_alias="preferredAdapterUrl")
    supports_rss: bool = Field(default=False, serialization_alias="supportsRss")
    supports_news_sitemap: bool = Field(default=False, serialization_alias="supportsNewsSitemap")
    supports_sitemap: bool = Field(default=False, serialization_alias="supportsSitemap")
    supports_scraping: bool = Field(default=False, serialization_alias="supportsScraping")
    last_probe_full_text_ok: bool = Field(default=False, serialization_alias="lastProbeFullTextOk")
    last_probe_lead_ok: bool = Field(default=False, serialization_alias="lastProbeLeadOk")
    last_probe_tags_count: int = Field(default=0, serialization_alias="lastProbeTagsCount")
    last_probe_sample_title: Optional[str] = Field(default=None, serialization_alias="lastProbeSampleTitle")
    last_probe_sample_url: Optional[str] = Field(default=None, serialization_alias="lastProbeSampleUrl")
    last_status: str = Field(default="idle", serialization_alias="lastStatus")
    last_error: Optional[str] = Field(default=None, serialization_alias="lastError")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class SourceProbeResponse(BaseModel):
    source_key: str = Field(serialization_alias="sourceKey")
    ok: bool
    item_count: int = Field(serialization_alias="itemCount")
    message: str
    readiness: str
    resolved_source_type: Optional[str] = Field(default=None, serialization_alias="resolvedSourceType")
    resolved_source_url: Optional[str] = Field(default=None, serialization_alias="resolvedSourceUrl")
    supports_rss: bool = Field(default=False, serialization_alias="supportsRss")
    supports_news_sitemap: bool = Field(default=False, serialization_alias="supportsNewsSitemap")
    supports_sitemap: bool = Field(default=False, serialization_alias="supportsSitemap")
    supports_scraping: bool = Field(default=False, serialization_alias="supportsScraping")
    full_text_ok: bool = Field(serialization_alias="fullTextOk")
    lead_ok: bool = Field(serialization_alias="leadOk")
    tags_count: int = Field(serialization_alias="tagsCount")
    sample_title: Optional[str] = Field(default=None, serialization_alias="sampleTitle")
    sample_url: Optional[str] = Field(default=None, serialization_alias="sampleUrl")


class SourceCapability(BaseModel):
    source_key: str = Field(serialization_alias="sourceKey")
    source_title: str = Field(serialization_alias="sourceTitle")
    configured_source_type: str = Field(serialization_alias="configuredSourceType")
    configured_url: str = Field(serialization_alias="configuredUrl")
    preferred_adapter: Optional[str] = Field(default=None, serialization_alias="preferredAdapter")
    preferred_adapter_url: Optional[str] = Field(default=None, serialization_alias="preferredAdapterUrl")
    effective_adapter: str = Field(serialization_alias="effectiveAdapter")
    effective_url: str = Field(serialization_alias="effectiveUrl")
    readiness: str
    supports_rss: bool = Field(default=False, serialization_alias="supportsRss")
    supports_news_sitemap: bool = Field(default=False, serialization_alias="supportsNewsSitemap")
    supports_sitemap: bool = Field(default=False, serialization_alias="supportsSitemap")
    supports_scraping: bool = Field(default=False, serialization_alias="supportsScraping")
    full_text_ok: bool = Field(default=False, serialization_alias="fullTextOk")
    lead_ok: bool = Field(default=False, serialization_alias="leadOk")
    tags_count: int = Field(default=0, serialization_alias="tagsCount")
    sample_title: Optional[str] = Field(default=None, serialization_alias="sampleTitle")
    sample_url: Optional[str] = Field(default=None, serialization_alias="sampleUrl")


class SourceCapabilityListResponse(BaseModel):
    items: list[SourceCapability]


class SourceSyncStateListResponse(BaseModel):
    items: list[SourceSyncState]


class SchedulerSettings(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=60, serialization_alias="intervalMinutes")
    batch_size: int = Field(default=5, serialization_alias="batchSize")
    run_enrichment: bool = Field(default=False, serialization_alias="runEnrichment")
    last_run_at: Optional[datetime] = Field(default=None, serialization_alias="lastRunAt")
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")
    last_status: str = Field(default="idle", serialization_alias="lastStatus")
    last_error: Optional[str] = Field(default=None, serialization_alias="lastError")
    last_found_count: int = Field(default=0, serialization_alias="lastFoundCount")
    last_saved_count: int = Field(default=0, serialization_alias="lastSavedCount")
    last_published_count: int = Field(default=0, serialization_alias="lastPublishedCount")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class SchedulerSettingsUpdateRequest(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=5, le=1440, alias="intervalMinutes", serialization_alias="intervalMinutes")
    batch_size: int = Field(default=5, ge=1, le=20, alias="batchSize", serialization_alias="batchSize")
    run_enrichment: bool = Field(default=False, alias="runEnrichment", serialization_alias="runEnrichment")


class SchedulerRunResponse(BaseModel):
    ran: bool
    reason: str
    ingested: int = 0
    published: int = 0
    raw_items: int = Field(default=0, serialization_alias="rawItems")
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")


class EnrichmentSchedulerSettings(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=60, serialization_alias="intervalMinutes")
    batch_size: int = Field(default=10, serialization_alias="batchSize")
    last_run_at: Optional[datetime] = Field(default=None, serialization_alias="lastRunAt")
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")
    last_status: str = Field(default="idle", serialization_alias="lastStatus")
    last_error: Optional[str] = Field(default=None, serialization_alias="lastError")
    last_processed_count: int = Field(default=0, serialization_alias="lastProcessedCount")
    last_enriched_count: int = Field(default=0, serialization_alias="lastEnrichedCount")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class EnrichmentSchedulerSettingsUpdateRequest(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=5, le=1440, alias="intervalMinutes", serialization_alias="intervalMinutes")
    batch_size: int = Field(default=10, ge=1, le=50, alias="batchSize", serialization_alias="batchSize")


class EnrichmentSchedulerRunResponse(BaseModel):
    ran: bool
    reason: str
    processed: int = 0
    enriched: int = 0
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")


class EditorialSchedulerSettings(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=60, serialization_alias="intervalMinutes")
    batch_size: int = Field(default=5, serialization_alias="batchSize")
    last_run_at: Optional[datetime] = Field(default=None, serialization_alias="lastRunAt")
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")
    last_status: str = Field(default="idle", serialization_alias="lastStatus")
    last_error: Optional[str] = Field(default=None, serialization_alias="lastError")
    last_planned_count: int = Field(default=0, serialization_alias="lastPlannedCount")
    last_generated_count: int = Field(default=0, serialization_alias="lastGeneratedCount")
    last_reviewed_count: int = Field(default=0, serialization_alias="lastReviewedCount")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class EditorialSchedulerSettingsUpdateRequest(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=5, le=1440, alias="intervalMinutes", serialization_alias="intervalMinutes")
    batch_size: int = Field(default=5, ge=1, le=20, alias="batchSize", serialization_alias="batchSize")


class EditorialSchedulerRunResponse(BaseModel):
    ran: bool
    reason: str
    planned: int = 0
    generated: int = 0
    reviewed: int = 0
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")


class PublishSchedulerSettings(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=60, serialization_alias="intervalMinutes")
    batch_size: int = Field(default=5, serialization_alias="batchSize")
    last_run_at: Optional[datetime] = Field(default=None, serialization_alias="lastRunAt")
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")
    last_status: str = Field(default="idle", serialization_alias="lastStatus")
    last_error: Optional[str] = Field(default=None, serialization_alias="lastError")
    last_published_count: int = Field(default=0, serialization_alias="lastPublishedCount")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        serialization_alias="updatedAt",
    )


class PublishSchedulerSettingsUpdateRequest(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=5, le=1440, alias="intervalMinutes", serialization_alias="intervalMinutes")
    batch_size: int = Field(default=5, ge=1, le=20, alias="batchSize", serialization_alias="batchSize")


class PublishSchedulerRunResponse(BaseModel):
    ran: bool
    reason: str
    published: int = 0
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")


class EnrichmentRunResponse(BaseModel):
    processed: int
    enriched: int


class PublishRunResponse(BaseModel):
    published: int


class PipelineSchedulerRunResponse(BaseModel):
    mode: str
    ingest: SchedulerRunResponse
    enrichment: EnrichmentSchedulerRunResponse
    editorial: EditorialSchedulerRunResponse
    publish: PublishSchedulerRunResponse
    started_at: datetime = Field(serialization_alias="startedAt")
    finished_at: datetime = Field(serialization_alias="finishedAt")


class MonitoringAlert(BaseModel):
    severity: str
    phase: str
    code: str
    message: str
    error_reason: Optional[str] = Field(default=None, serialization_alias="errorReason")
    observed_value: Optional[int] = Field(default=None, serialization_alias="observedValue")
    threshold_value: Optional[int] = Field(default=None, serialization_alias="thresholdValue")


class MonitoringSchedulerState(BaseModel):
    phase: str
    enabled: bool
    healthy: bool
    last_status: str = Field(serialization_alias="lastStatus")
    last_run_at: Optional[datetime] = Field(default=None, serialization_alias="lastRunAt")
    next_run_at: Optional[datetime] = Field(default=None, serialization_alias="nextRunAt")
    interval_minutes: int = Field(serialization_alias="intervalMinutes")
    queue_count: Optional[int] = Field(default=None, serialization_alias="queueCount")
    alerts: list[MonitoringAlert] = Field(default_factory=list)


class MonitoringQueueSnapshot(BaseModel):
    enrichment: int
    editorial: int
    publish: int


class MonitoringStatusResponse(BaseModel):
    status: str
    generated_at: datetime = Field(serialization_alias="generatedAt")
    queues: MonitoringQueueSnapshot
    schedulers: list[MonitoringSchedulerState]
    alerts: list[MonitoringAlert]


class RecoveryAction(BaseModel):
    phase: str
    previous_status: str = Field(serialization_alias="previousStatus")
    recovered_status: str = Field(serialization_alias="recoveredStatus")
    message: str
    updated_at: Optional[datetime] = Field(default=None, serialization_alias="updatedAt")


class RecoveryStatusResponse(BaseModel):
    recovered: bool
    trigger: str
    checked_at: datetime = Field(serialization_alias="checkedAt")
    actions: list[RecoveryAction]


class IdempotencyCheck(BaseModel):
    code: str
    passed: bool
    message: str
    observed_value: int = Field(serialization_alias="observedValue")
    expected_value: int = Field(serialization_alias="expectedValue")
    severity: str = "warning"


class IdempotencyReportResponse(BaseModel):
    status: str
    checked_at: datetime = Field(serialization_alias="checkedAt")
    checks: list[IdempotencyCheck]


class PromptConfigListResponse(BaseModel):
    items: list[PromptConfig]


class PromptConfigCreateRequest(BaseModel):
    agent_key: str = Field(serialization_alias="agentKey")
    name: str
    system_prompt: str = Field(serialization_alias="systemPrompt")
    user_prompt_template: str = Field(serialization_alias="userPromptTemplate")
    model: str
    notes: str = ""
    activate: bool = True


class PromptStatusUpdateRequest(BaseModel):
    status: str


class DraftArticleListResponse(BaseModel):
    items: list[DraftArticle]


class EditorReviewListResponse(BaseModel):
    items: list[EditorReview]


class ContentPlanListResponse(BaseModel):
    items: list[ContentPlanItem]


class EditorialRunResponse(BaseModel):
    generated: int
    reviewed: int
    drafts: list[DraftArticle]


class ContentPlanRunResponse(BaseModel):
    planned: int
    items: list[ContentPlanItem]


class EditorialStatusResponse(BaseModel):
    openai_enabled: bool = Field(serialization_alias="openaiEnabled")
    openai_model: str = Field(serialization_alias="openaiModel")
    openai_search_model: str = Field(serialization_alias="openaiSearchModel")
    fallback_mode: bool = Field(serialization_alias="fallbackMode")
    provider_label: str = Field(serialization_alias="providerLabel")
    api_style: str = Field(serialization_alias="apiStyle")
    web_search_enabled: bool = Field(serialization_alias="webSearchEnabled")


class ResetResponse(BaseModel):
    cleared: bool
