from __future__ import annotations

from .models import (
    SourceCreateRequest,
    SourceCapabilityListResponse,
    SourceListResponse,
    SourceProbeResponse,
    SourceUpdateRequest,
    SourceSyncStateListResponse,
)
from fastapi import APIRouter
from . import service_sources

router = APIRouter()


@router.get("/api/v1/sources", response_model=SourceListResponse)
def list_sources() -> SourceListResponse:
    return service_sources.list_sources()


@router.post("/api/v1/sources", response_model=SourceListResponse)
def create_source(payload: SourceCreateRequest) -> SourceListResponse:
    return service_sources.create_source(payload=payload)


@router.post("/api/v1/sources/{source_key}", response_model=SourceListResponse)
def update_source(source_key: str, payload: SourceUpdateRequest) -> SourceListResponse:
    return service_sources.update_source(source_key=source_key, payload=payload)


@router.post("/api/v1/sources/{source_key}/delete", response_model=SourceListResponse)
def delete_source(source_key: str) -> SourceListResponse:
    return service_sources.delete_source(source_key=source_key)


@router.post("/api/v1/source-probe", response_model=SourceProbeResponse)
def probe_source_draft(payload: SourceCreateRequest) -> SourceProbeResponse:
    return service_sources.probe_source_draft(payload=payload)


@router.post("/api/v1/sources/{source_key}/probe", response_model=SourceProbeResponse)
def probe_source_config(source_key: str) -> SourceProbeResponse:
    return service_sources.probe_source_config(source_key=source_key)


@router.get("/api/v1/source-states", response_model=SourceSyncStateListResponse)
def list_source_states() -> SourceSyncStateListResponse:
    return service_sources.list_source_states()


@router.get("/api/v1/source-capabilities", response_model=SourceCapabilityListResponse)
def list_source_capabilities() -> SourceCapabilityListResponse:
    return service_sources.list_source_capabilities()


