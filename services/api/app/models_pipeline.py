from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from .models_news import NewsItem


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
    score_breakdown: list[str] = Field(default_factory=list, serialization_alias="scoreBreakdown")
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
    score_breakdown: list[str] = Field(default_factory=list, serialization_alias="scoreBreakdown")
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
    parsed_count: int = Field(default=0, serialization_alias="parsedCount")
    fresh_count: int = Field(default=0, serialization_alias="freshCount")
    filtered_count: int = Field(default=0, serialization_alias="filteredCount")
    filter_reasons: dict[str, int] = Field(default_factory=dict, serialization_alias="filterReasons")


class RawItemListResponse(BaseModel):
    items: list[RawItem]


class RawItemPreviewListResponse(BaseModel):
    items: list[RawItemPreview]


class PipelineRunListResponse(BaseModel):
    items: list[PipelineRun]


class AiUsageSummaryRow(BaseModel):
    usage_date: str = Field(serialization_alias="usageDate")
    usage_group: str = Field(serialization_alias="usageGroup")
    operation: str
    model: str
    request_count: int = Field(serialization_alias="requestCount")
    input_tokens: int = Field(serialization_alias="inputTokens")
    output_tokens: int = Field(serialization_alias="outputTokens")
    cached_input_tokens: int = Field(serialization_alias="cachedInputTokens")
    total_tokens: int = Field(serialization_alias="totalTokens")
    web_search_calls: int = Field(serialization_alias="webSearchCalls")
    estimated_cost_usd: float = Field(serialization_alias="estimatedCostUsd")


class AiUsageSummaryTotals(BaseModel):
    request_count: int = Field(serialization_alias="requestCount")
    input_tokens: int = Field(serialization_alias="inputTokens")
    output_tokens: int = Field(serialization_alias="outputTokens")
    cached_input_tokens: int = Field(serialization_alias="cachedInputTokens")
    total_tokens: int = Field(serialization_alias="totalTokens")
    web_search_calls: int = Field(serialization_alias="webSearchCalls")
    estimated_cost_usd: float = Field(serialization_alias="estimatedCostUsd")


class AiUsageSummaryResponse(BaseModel):
    items: list[AiUsageSummaryRow]
    totals: AiUsageSummaryTotals
    days: int
    timezone: str = "Europe/Moscow"


class IngestResponse(BaseModel):
    ingested: int
    published: int
    items: list[NewsItem]
    raw_items: int = Field(serialization_alias="rawItems")


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


class ResetResponse(BaseModel):
    cleared: bool


# Resolve the forward references inside the pipeline history model.
PipelineRun.model_rebuild()
