from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from .auth import validate_admin_configuration
from .editorial import default_prompt_configs
from .guide_topics import load_guide_topic_seed
from .migrations import check_schema
from . import runtime
from .runtime import logger
from .service_monitoring import _recover_runtime_state


def _initialize_runtime() -> None:
    validate_admin_configuration()
    with runtime.repository.connect() as startup_connection:
        startup_connection.execute("SELECT pg_advisory_xact_lock(%s)", (4815162349,))
        check_schema(startup_connection)
        _recover_runtime_state(trigger="startup")
        runtime.repository.ensure_prompt_defaults(default_prompt_configs())
        runtime.repository.maybe_activate_recommended_prompt("writer", "prompt:writer:v9")
        runtime.repository.maybe_activate_recommended_prompt("editor", "prompt:editor:v11")
        runtime.repository.maybe_activate_recommended_prompt("ai_search", "prompt:ai-search:v1")
        try:
            runtime.repository.ensure_guide_topic_defaults(load_guide_topic_seed())
            runtime.repository.maybe_activate_recommended_prompt("guide_writer", "prompt:guide-writer:v3")
            runtime.repository.maybe_activate_recommended_prompt("guide_editor", "prompt:guide-editor:v2")
        except Exception:
            logger.exception("Guide article startup initialization failed; continuing without guide scheduler setup.")
        runtime.repository.sync_news_ai_review_flags()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        _initialize_runtime()
        yield
    finally:
        runtime.repository.close_pool()

