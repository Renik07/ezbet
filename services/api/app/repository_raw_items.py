from __future__ import annotations

import re
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from .deduplication import fact_tokens
from .models import (
    PipelineRun,
    RawItem,
    RawItemPreview,
)
from .repository_support import (
    InsertRawItemsResult,
    PrefilterRawItemsResult,
)

class RawItemsRepository:
    def list_raw_items(self, limit: int = 50) -> list[RawItem]:
        statement = """
            SELECT
                id,
                source_key,
                source_title,
                source_url,
                category,
                normalized_category,
                external_id,
                dedupe_key,
                title,
                summary,
                lead,
                url,
                published_at,
                fetched_at,
                importance_score,
                triage_label,
                is_duplicate,
                duplicate_of,
                duplicate_stage,
                duplicate_reason,
                full_text,
                full_text_source_url,
                full_text_source_title,
                reference_urls,
                extraction_mode,
                enrichment_status,
                enrichment_error,
                tags,
                payload
            FROM raw_items
            ORDER BY fetched_at DESC, published_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (limit,))
                rows = cursor.fetchall()

        return [self._map_raw_row(row) for row in rows]

    def list_raw_item_previews(self, limit: int = 50) -> list[RawItemPreview]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.category,
                r.normalized_category,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                cp.status,
                cp.reason,
                cp.priority_label,
                r.tags
            FROM raw_items r
            LEFT JOIN content_plan_items cp ON cp.raw_item_id = r.id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            ORDER BY
                r.fetched_at DESC,
                r.published_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (limit,))
                rows = cursor.fetchall()

        return [self._map_raw_preview_row(row) for row in rows]

    def list_raw_item_previews_for_ingest_run(self, run: PipelineRun, limit: int = 50) -> list[RawItemPreview]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.category,
                r.normalized_category,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                cp.status,
                cp.reason,
                cp.priority_label,
                r.tags
            FROM raw_items r
            LEFT JOIN content_plan_items cp ON cp.raw_item_id = r.id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE r.fetched_at >= %s
              AND r.fetched_at <= (%s + INTERVAL '2 minutes')
            ORDER BY
                r.fetched_at DESC,
                r.published_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (run.started_at, run.finished_at, limit))
                rows = cursor.fetchall()

        return [self._map_raw_preview_row(row) for row in rows]

    def list_raw_item_previews_since(self, since: datetime, limit: int = 50) -> list[RawItemPreview]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.category,
                r.normalized_category,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                cp.status,
                cp.reason,
                cp.priority_label,
                r.tags
            FROM raw_items r
            LEFT JOIN content_plan_items cp ON cp.raw_item_id = r.id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE r.fetched_at >= %s
            ORDER BY
                r.fetched_at DESC,
                r.published_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (since, limit))
                rows = cursor.fetchall()

        return [self._map_raw_preview_row(row) for row in rows]

    def list_pending_enrichment_raw_items(self, limit: int = 20, since: datetime | None = None) -> list[RawItem]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.source_url,
                r.category,
                r.normalized_category,
                r.external_id,
                r.dedupe_key,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                r.tags,
                r.payload
            FROM raw_items r
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            LEFT JOIN source_configs s ON s.key = r.source_key
            WHERE r.is_duplicate = FALSE
              AND d.raw_item_id IS NULL
              AND r.url IS NOT NULL
              AND r.fetched_at >= NOW() - INTERVAL '48 hours'
              AND (
                r.full_text IS NULL
                OR BTRIM(r.full_text) = ''
                OR r.lead IS NULL
                OR BTRIM(r.lead) = ''
                OR COALESCE(array_length(r.tags, 1), 0) = 0
              )
        """
        params: list[object] = []
        if since is not None:
            statement += " AND r.fetched_at >= %s"
            params.append(since)
        statement += """
            ORDER BY
              CASE
                WHEN r.full_text IS NULL OR BTRIM(r.full_text) = '' THEN 0
                ELSE 1
              END,
              CASE
                WHEN r.lead IS NULL OR BTRIM(r.lead) = '' THEN 0
                ELSE 1
              END,
              CASE
                WHEN COALESCE(array_length(r.tags, 1), 0) = 0 THEN 0
                ELSE 1
              END,
              CASE r.triage_label
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                ELSE 2
              END,
              CASE COALESCE(s.source_type, '')
                WHEN 'news_sitemap' THEN 0
                WHEN 'rss' THEN 1
                WHEN 'scraping' THEN 2
                WHEN 'ai_research' THEN 3
                ELSE 4
              END,
              r.importance_score DESC,
              r.fetched_at DESC,
              r.published_at DESC
            LIMIT %s
        """
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_raw_row(row) for row in rows]

    def count_pending_enrichment_raw_items(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM raw_items r
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE r.is_duplicate = FALSE
              AND d.raw_item_id IS NULL
              AND r.url IS NOT NULL
              AND r.fetched_at >= NOW() - INTERVAL '48 hours'
              AND (
                r.full_text IS NULL
                OR BTRIM(r.full_text) = ''
                OR r.lead IS NULL
                OR BTRIM(r.lead) = ''
                OR COALESCE(array_length(r.tags, 1), 0) = 0
              )
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def list_raw_candidates_for_plan(
        self,
        limit: int = 6,
        since: datetime | None = None,
        require_full_text: bool = False,
    ) -> list[RawItem]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.source_url,
                r.category,
                r.normalized_category,
                r.external_id,
                r.dedupe_key,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                r.tags,
                r.payload
            FROM raw_items r
            LEFT JOIN content_plan_items cp ON cp.raw_item_id = r.id
            WHERE r.is_duplicate = FALSE
              AND cp.raw_item_id IS NULL
        """
        params: list[object] = []
        if since is not None:
            statement += " AND r.fetched_at >= %s"
            params.append(since)
        if require_full_text:
            statement += " AND r.full_text IS NOT NULL AND LENGTH(BTRIM(r.full_text)) >= 220"
        statement += """
            ORDER BY
                CASE r.triage_label
                    WHEN 'high' THEN 0
                    WHEN 'medium' THEN 1
                    ELSE 2
                END,
                r.importance_score DESC,
                r.fetched_at DESC,
                r.published_at DESC
            LIMIT %s
        """
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_raw_row(row) for row in rows]

    def list_planned_raw_items_for_drafts(self, limit: int = 3, since: datetime | None = None) -> list[RawItem]:
        statement = """
            SELECT
                r.id,
                r.source_key,
                r.source_title,
                r.source_url,
                r.category,
                r.normalized_category,
                r.external_id,
                r.dedupe_key,
                r.title,
                r.summary,
                r.lead,
                r.url,
                r.published_at,
                r.fetched_at,
                r.importance_score,
                r.triage_label,
                r.is_duplicate,
                r.duplicate_of,
                r.duplicate_stage,
                r.duplicate_reason,
                r.full_text,
                r.full_text_source_url,
                r.full_text_source_title,
                r.reference_urls,
                r.extraction_mode,
                r.enrichment_status,
                r.enrichment_error,
                r.tags,
                r.payload
            FROM content_plan_items cp
            JOIN raw_items r ON r.id = cp.raw_item_id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE cp.status = 'planned'
              AND d.raw_item_id IS NULL
        """
        params: list[object] = []
        if since is not None:
            statement += " AND r.fetched_at >= %s"
            params.append(since)
        statement += " ORDER BY cp.priority_score DESC, r.published_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_raw_row(row) for row in rows]

    def count_planned_raw_items_for_drafts(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM content_plan_items cp
            JOIN raw_items r ON r.id = cp.raw_item_id
            LEFT JOIN draft_articles d ON d.raw_item_id = r.id
            WHERE cp.status = 'planned'
              AND d.raw_item_id IS NULL
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def get_raw_item(self, raw_item_id: str) -> RawItem | None:
        statement = """
            SELECT
                id,
                source_key,
                source_title,
                source_url,
                category,
                normalized_category,
                external_id,
                dedupe_key,
                title,
                summary,
                lead,
                url,
                published_at,
                fetched_at,
                importance_score,
                triage_label,
                is_duplicate,
                duplicate_of,
                duplicate_stage,
                duplicate_reason,
                full_text,
                full_text_source_url,
                full_text_source_title,
                reference_urls,
                extraction_mode,
                enrichment_status,
                enrichment_error,
                tags,
                payload
            FROM raw_items
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (raw_item_id,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_raw_row(row)

    def insert_raw_items(self, items: list[RawItem]) -> InsertRawItemsResult:
        inserted = 0
        skipped_items: list[dict[str, str]] = []
        dedupe_keys = sorted({item.dedupe_key for item in items if item.dedupe_key})

        with self.connect() as connection:
            with connection.cursor() as cursor:
                known_dedupe_map: dict[str, tuple[str, str]] = {}
                if dedupe_keys:
                    cursor.execute(
                        """
                        SELECT dedupe_key, id, title
                        FROM raw_items
                        WHERE dedupe_key = ANY(%s)
                        """,
                        (dedupe_keys,),
                    )
                    known_dedupe_map = {
                        str(row[0]): (str(row[1]), str(row[2] or ""))
                        for row in cursor.fetchall()
                    }
                recent_similarity_candidates = self._load_recent_dedup_candidates(cursor, window_hours=24)
                pending_similarity_candidates: dict[str, list[tuple[str, str, str]]] = {}

                for item in items:
                    existing_raw = known_dedupe_map.get(item.dedupe_key)
                    if existing_raw and existing_raw[0] != item.id:
                        item.is_duplicate = True
                        item.duplicate_of = existing_raw[0]
                        item.duplicate_stage = "ingest"
                        item.duplicate_reason = (
                            f"Точный дубль найден при первичной загрузке по dedupe key / URL. "
                            f"Совпало с новостью: «{existing_raw[1] or existing_raw[0]}»."
                        )
                    elif item.is_duplicate and not item.duplicate_of:
                        exact_match = known_dedupe_map.get(item.dedupe_key)
                        item.duplicate_of = exact_match[0] if exact_match is not None else item.id
                        item.duplicate_stage = item.duplicate_stage or "ingest"
                        item.duplicate_reason = item.duplicate_reason or "Новость помечена как дубль при первичной загрузке."
                    else:
                        duplicate_match = self._find_near_duplicate_match(
                            item,
                            recent_similarity_candidates,
                            pending_similarity_candidates,
                        )
                        if duplicate_match is not None and duplicate_match[0] != item.id:
                            item.is_duplicate = True
                            item.duplicate_of = duplicate_match[0]
                            item.duplicate_stage = "ingest"
                            item.duplicate_reason = (
                                "Похожая новость найдена при первичной загрузке среди свежих raw items. "
                                f"Совпало с новостью: «{duplicate_match[1]}» (similarity {duplicate_match[2]:.2f})."
                            )

                    cursor.execute(
                        """
                        INSERT INTO raw_items (
                            id,
                            source_key,
                            source_title,
                            source_url,
                            category,
                            normalized_category,
                            external_id,
                            dedupe_key,
                            title,
                            summary,
                            lead,
                            url,
                            published_at,
                            fetched_at,
                            importance_score,
                            triage_label,
                            is_duplicate,
                            duplicate_of,
                            duplicate_stage,
                            duplicate_reason,
                            full_text,
                            full_text_source_url,
                            full_text_source_title,
                            reference_urls,
                            extraction_mode,
                            enrichment_status,
                            enrichment_error,
                            tags,
                            payload
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        RETURNING id
                        """,
                        (
                            item.id,
                            item.source_key,
                            item.source_title,
                            item.source_url,
                            item.category,
                            item.normalized_category,
                            item.external_id,
                            item.dedupe_key,
                            item.title,
                            item.summary,
                            item.lead,
                            item.url,
                            item.published_at,
                            item.fetched_at,
                            item.importance_score,
                            item.triage_label,
                            item.is_duplicate,
                            item.duplicate_of,
                            item.duplicate_stage,
                            item.duplicate_reason,
                            item.full_text,
                            item.full_text_source_url,
                            item.full_text_source_title,
                            item.reference_urls,
                            item.extraction_mode,
                            item.enrichment_status,
                            item.enrichment_error,
                            item.tags,
                            item.payload,
                        ),
                    )
                    if cursor.fetchone():
                        inserted += 1
                        known_dedupe_map[item.dedupe_key] = (item.id, item.title)
                        if not item.is_duplicate:
                            combined_text = self._build_similarity_text(item)
                            pending_similarity_candidates.setdefault(item.normalized_category, []).append(
                                (item.id, item.title, combined_text)
                            )
                    else:
                        skipped_items.append(
                            {
                                "title": item.title,
                                "reason": item.duplicate_reason
                                or "Новость уже была сохранена ранее и не была добавлена повторно.",
                            }
                        )
            connection.commit()

        return InsertRawItemsResult(inserted_count=inserted, skipped_items=skipped_items)

    def prefilter_known_raw_items(self, items: list[RawItem]) -> PrefilterRawItemsResult:
        if not items:
            return PrefilterRawItemsResult(fresh_items=[], skipped_items=[])

        dedupe_keys = sorted({item.dedupe_key for item in items if item.dedupe_key})
        if not dedupe_keys:
            return PrefilterRawItemsResult(fresh_items=items, skipped_items=[])

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT dedupe_key
                    FROM raw_items
                    WHERE dedupe_key = ANY(%s)
                    """,
                    (dedupe_keys,),
                )
                known_dedupe_keys = {str(row[0]) for row in cursor.fetchall()}

        if not known_dedupe_keys:
            return PrefilterRawItemsResult(fresh_items=items, skipped_items=[])

        fresh_items: list[RawItem] = []
        skipped_items: list[dict[str, str]] = []
        for item in items:
            if item.dedupe_key in known_dedupe_keys:
                skipped_items.append(
                    {
                        "title": item.title,
                        "reason": "Новость уже была загружена ранее и отсечена до повторного сохранения.",
                    }
                )
                continue
            fresh_items.append(item)

        return PrefilterRawItemsResult(fresh_items=fresh_items, skipped_items=skipped_items)

    def update_raw_item_enrichment(
        self,
        raw_item_id: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        full_text: str | None = None,
        lead: str | None = None,
        full_text_source_url: str | None = None,
        full_text_source_title: str | None = None,
        reference_urls: list[str] | None = None,
        extraction_mode: str | None = None,
        enrichment_status: str | None = None,
        enrichment_error: str | None = None,
        tags: list[str] | None = None,
    ) -> RawItem | None:
        cleaned_title = (title or "").strip() or None
        cleaned_summary = (summary or "").strip() or None
        cleaned_full_text = (full_text or "").strip() or None
        cleaned_lead = (lead or "").strip() or None
        cleaned_full_text_source_url = (full_text_source_url or "").strip() or None
        cleaned_full_text_source_title = (full_text_source_title or "").strip() or None
        cleaned_reference_urls = [value.strip() for value in (reference_urls or []) if value.strip()]
        cleaned_extraction_mode = (extraction_mode or "").strip() or None
        cleaned_enrichment_status = (enrichment_status or "").strip() or None
        cleaned_enrichment_error = (enrichment_error or "").strip() or None
        cleaned_tags = [value.strip() for value in (tags or []) if value.strip()]

        if (
            cleaned_title is None
            and cleaned_summary is None
            and cleaned_full_text is None
            and cleaned_lead is None
            and cleaned_full_text_source_url is None
            and cleaned_full_text_source_title is None
            and not cleaned_reference_urls
            and cleaned_extraction_mode is None
            and cleaned_enrichment_status is None
            and cleaned_enrichment_error is None
            and not cleaned_tags
        ):
            return self.get_raw_item(raw_item_id)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE raw_items
                    SET title = COALESCE(%s, title),
                        summary = COALESCE(%s, summary),
                        full_text = COALESCE(%s, full_text),
                        lead = COALESCE(%s, lead),
                        full_text_source_url = COALESCE(%s, full_text_source_url),
                        full_text_source_title = COALESCE(%s, full_text_source_title),
                        reference_urls = CASE WHEN %s::TEXT[] <> ARRAY[]::TEXT[] THEN %s ELSE reference_urls END,
                        extraction_mode = COALESCE(%s, extraction_mode),
                        enrichment_status = COALESCE(%s, enrichment_status),
                        enrichment_error = COALESCE(%s, enrichment_error),
                        tags = CASE WHEN %s::TEXT[] <> ARRAY[]::TEXT[] THEN %s ELSE tags END
                    WHERE id = %s
                    """,
                    (
                        cleaned_title,
                        cleaned_summary,
                        cleaned_full_text,
                        cleaned_lead,
                        cleaned_full_text_source_url,
                        cleaned_full_text_source_title,
                        cleaned_reference_urls,
                        cleaned_reference_urls,
                        cleaned_extraction_mode,
                        cleaned_enrichment_status,
                        cleaned_enrichment_error,
                        cleaned_tags,
                        cleaned_tags,
                        raw_item_id,
                    ),
                )
            connection.commit()

        return self.get_raw_item(raw_item_id)

    def update_raw_item_full_text(self, raw_item_id: str, full_text: str) -> RawItem | None:
        return self.update_raw_item_enrichment(raw_item_id, full_text=full_text)

    def recheck_raw_item_duplicate_after_enrichment(
        self,
        raw_item_id: str,
        *,
        window_hours: int = 24,
    ) -> RawItem | None:
        item = self.get_raw_item(raw_item_id)
        if item is None or item.is_duplicate:
            return item

        candidate_texts: dict[str, list[tuple[str, str, str]]] = {}
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, normalized_category, title, summary, full_text
                    FROM raw_items
                    WHERE id <> %s
                      AND is_duplicate = FALSE
                      AND fetched_at >= %s
                    ORDER BY fetched_at DESC, published_at DESC
                    """,
                    (
                        raw_item_id,
                        datetime.now(timezone.utc) - timedelta(hours=window_hours),
                    ),
                )
                rows = cursor.fetchall()

        for row in rows:
            candidate_id = str(row[0])
            category = str(row[1])
            title = str(row[2] or "")
            summary = str(row[3] or "")
            full_text = str(row[4] or "")
            source_text = full_text or summary
            candidate_texts.setdefault(category, []).append(
                (candidate_id, title, self._normalize_similarity_text(f"{title} {source_text}"))
            )

        duplicate_match = self._find_near_duplicate_match(
            item,
            recent_similarity_candidates=candidate_texts,
            pending_similarity_candidates={},
        )
        if not duplicate_match:
            return item

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE raw_items
                    SET is_duplicate = TRUE,
                        duplicate_of = %s,
                        duplicate_stage = 'after_enrichment',
                        duplicate_reason = %s
                    WHERE id = %s
                    """,
                    (
                        duplicate_match[0],
                        (
                            "Похожая новость найдена после добора full text и нормализации заголовка. "
                            f"Совпало с новостью: «{duplicate_match[1]}» (similarity {duplicate_match[2]:.2f})."
                        ),
                        raw_item_id,
                    ),
                )
            connection.commit()

        return self.get_raw_item(raw_item_id)

    def _find_near_duplicate_match(
        self,
        item: RawItem,
        recent_similarity_candidates: dict[str, list[tuple[str, str, str]]],
        pending_similarity_candidates: dict[str, list[tuple[str, str, str]]],
    ) -> tuple[str, str, float] | None:
        category = item.normalized_category
        target = self._build_similarity_text(item)
        target_tokens = self._tokenize_similarity_text(target)
        if len(target_tokens) < 4:
            return None

        same_category_match = self._best_duplicate_candidate(
            item_id=item.id,
            target_tokens=target_tokens,
            candidates=recent_similarity_candidates.get(category, []) + pending_similarity_candidates.get(category, []),
        )
        if same_category_match is not None and same_category_match[2] >= 0.84:
            return same_category_match

        cross_category_candidates: list[tuple[str, str, str]] = []
        for candidate_category, candidate_items in recent_similarity_candidates.items():
            if candidate_category == category:
                continue
            cross_category_candidates.extend(candidate_items)
        for candidate_category, candidate_items in pending_similarity_candidates.items():
            if candidate_category == category:
                continue
            cross_category_candidates.extend(candidate_items)

        cross_category_match = self._best_duplicate_candidate(
            item_id=item.id,
            target_tokens=target_tokens,
            candidates=cross_category_candidates,
        )
        if cross_category_match is not None and cross_category_match[2] >= 0.9:
            return cross_category_match
        return None

    def _best_duplicate_candidate(
        self,
        *,
        item_id: str,
        target_tokens: set[str],
        candidates: list[tuple[str, str, str]],
    ) -> tuple[str, str, float] | None:
        best_match_id: str | None = None
        best_match_title = ""
        best_score = 0.0
        target_facts = fact_tokens(" ".join(target_tokens))
        negatives = {"ne", "net", "bez", "not", "no", "without"}

        for candidate_id, candidate_title, candidate_text in candidates:
            if candidate_id == item_id:
                continue
            # Normalized ingest text preserves score order below.
            candidate_tokens = self._tokenize_similarity_text(candidate_text)
            if (
                target_facts != fact_tokens(" ".join(candidate_tokens))
                or (target_tokens & negatives) != (candidate_tokens & negatives)
            ):
                continue
            union = target_tokens | candidate_tokens
            similarity = len(target_tokens & candidate_tokens) / len(union) if union else 0.0
            if similarity > best_score:
                best_score = similarity
                best_match_id = candidate_id
                best_match_title = candidate_title

        if best_match_id is None:
            return None
        return (best_match_id, best_match_title, best_score)

    def _build_similarity_text(self, item: RawItem) -> str:
        source_text = item.full_text or item.summary
        return self._normalize_similarity_text(f"{item.title} {source_text}")

    @staticmethod
    def _normalize_similarity_text(value: str) -> str:
        lowered = " ".join(value.lower().split())
        folded = RawItemsRepository._fold_similarity_text(lowered)
        return " ".join(folded.split())

    @staticmethod
    def _fold_similarity_text(value: str) -> str:
        replacements = {
            "а": "a",
            "б": "b",
            "в": "v",
            "г": "g",
            "д": "d",
            "е": "e",
            "ё": "e",
            "ж": "zh",
            "з": "z",
            "и": "i",
            "й": "i",
            "к": "k",
            "л": "l",
            "м": "m",
            "н": "n",
            "о": "o",
            "п": "p",
            "р": "r",
            "с": "s",
            "т": "t",
            "у": "u",
            "ф": "f",
            "х": "kh",
            "ц": "ts",
            "ч": "ch",
            "ш": "sh",
            "щ": "shch",
            "ъ": "",
            "ы": "y",
            "ь": "",
            "э": "e",
            "ю": "yu",
            "я": "ya",
        }
        folded = "".join(replacements.get(char, char) for char in value)
        return re.sub(r"[^a-z0-9:.,]+", " ", folded)

    @staticmethod
    def _tokenize_similarity_text(value: str) -> set[str]:
        normalized = RawItemsRepository._normalize_similarity_text(value)
        tokens = re.findall(r"\d+\s*:\s*\d+|\d+(?:[.,]\d+)?|[a-z]+", normalized)
        return {
            re.sub(r"\s+", "", token)
            for token in tokens
            if len(token) > 2 or token[0].isdigit()
            or token in {"ne", "net", "bez", "not", "no", "without"}
        }

    def _compute_similarity_from_texts(self, left_tokens: set[str], right_text: str) -> float:
        right_tokens = self._tokenize_similarity_text(right_text)
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        if union == 0:
            return 0.0
        return intersection / union

