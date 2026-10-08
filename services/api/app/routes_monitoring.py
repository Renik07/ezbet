from __future__ import annotations

from .models import (
    IdempotencyReportResponse,
    MonitoringStatusResponse,
    RecoveryStatusResponse,
)
from fastapi import APIRouter
from . import service_monitoring

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return service_monitoring.healthcheck()


@router.get("/api/v1/monitoring/status", response_model=MonitoringStatusResponse)
def monitoring_status() -> MonitoringStatusResponse:
    return service_monitoring.monitoring_status()


@router.post("/api/v1/recovery/run", response_model=RecoveryStatusResponse)
def run_recovery() -> RecoveryStatusResponse:
    return service_monitoring.run_recovery()


@router.get("/api/v1/monitoring/idempotency", response_model=IdempotencyReportResponse)
def monitoring_idempotency() -> IdempotencyReportResponse:
    return service_monitoring.monitoring_idempotency()


