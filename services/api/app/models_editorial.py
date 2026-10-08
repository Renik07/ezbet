from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from .models_news import Article


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
    writer_title: Optional[str] = Field(default=None, serialization_alias="writerTitle")
    writer_dek: Optional[str] = Field(default=None, serialization_alias="writerDek")
    writer_body: Optional[str] = Field(default=None, serialization_alias="writerBody")
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
    decision: str = "approve"
    summary: str
    notes: str = ""
    revised_title: Optional[str] = Field(default=None, serialization_alias="revisedTitle")
    revised_dek: Optional[str] = Field(default=None, serialization_alias="revisedDek")
    revised_body: Optional[str] = Field(default=None, serialization_alias="revisedBody")
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


class GuideTopic(BaseModel):
    id: int
    topic_number: int = Field(serialization_alias="topicNumber")
    title: str
    section: str
    category: str
    requires_web_search: bool = Field(default=False, serialization_alias="requiresWebSearch")
    search_context_size: str = Field(default="low", serialization_alias="searchContextSize")
    status: str = "planned"
    article_id: Optional[str] = Field(default=None, serialization_alias="articleId")
    article_slug: Optional[str] = Field(default=None, serialization_alias="articleSlug")
    last_error: Optional[str] = Field(default=None, serialization_alias="lastError")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class GuideTopicListResponse(BaseModel):
    items: list[GuideTopic]


class GuideSchedulerRunResponse(BaseModel):
    ran: bool
    reason: str
    generated: int = 0
    published: int = 0
    topic: Optional[GuideTopic] = None
    article: Optional[Article] = None


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


class PromptCleanupResponse(BaseModel):
    deleted_count: int = Field(serialization_alias="deletedCount")


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

