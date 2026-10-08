from __future__ import annotations

from fastapi import Query
from .jobs import JobQueue
from . import runtime


def _enqueue_pipeline(*, force: bool) -> dict[str, object]:
    created, job = JobQueue(runtime.repository).enqueue(force=force)
    return {
        "started": created,
        "reason": "queued" if created else "already_running",
        "message": "Pipeline добавлен в очередь worker." if created else "Pipeline уже ожидает запуска или выполняется worker.",
        "jobId": job["id"], "status": job["status"], "startedAt": job["createdAt"],
    }


def start_pipeline_now() -> dict[str, object]:
    return _enqueue_pipeline(force=True)


def queue_pipeline(force: bool = Query(default=False)) -> dict[str, object]:
    return _enqueue_pipeline(force=force)


def list_worker_jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
    return {"items": JobQueue(runtime.repository).list_jobs(limit), "pool": runtime.repository.pool_stats()}

