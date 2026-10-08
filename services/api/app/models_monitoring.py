from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


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

