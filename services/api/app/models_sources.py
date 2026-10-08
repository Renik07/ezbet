from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


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
    full_text_method: Optional[str] = Field(default=None, alias="fullTextMethod", serialization_alias="fullTextMethod")
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
    last_probe_full_text_method: Optional[str] = Field(default=None, serialization_alias="lastProbeFullTextMethod")
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
    full_text_method: Optional[str] = Field(default=None, serialization_alias="fullTextMethod")
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

