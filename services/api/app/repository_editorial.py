from __future__ import annotations

from datetime import datetime
from typing import Optional
from .models import (
    ContentPlanItem,
    DraftArticle,
    EditorReview,
)

class EditorialRepository:
    def sync_news_ai_review_flags(self) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE news_items
                    SET ai_reviewed = FALSE
                    """
                )
                cursor.execute(
                    """
                    UPDATE news_items n
                    SET ai_reviewed = TRUE
                    FROM raw_items r
                    JOIN draft_articles d ON d.raw_item_id = r.id
                    WHERE r.external_id = n.id
                      AND d.status = 'published'
                    """
                )
                cursor.execute(
                    """
                    UPDATE news_items n
                    SET ai_reviewed = TRUE
                    FROM articles a
                    WHERE a.news_item_id = n.id
                      AND a.raw_item_id LIKE 'guide-topic:%'
                    """
                )
            connection.commit()

    def list_drafts(
        self,
        limit: int = 20,
        status: Optional[str] = None,
        review_status: Optional[str] = None,
    ) -> list[DraftArticle]:
        statement = """
            SELECT
                id,
                raw_item_id,
                title,
                dek,
                body,
                writer_title,
                writer_dek,
                writer_body,
                category,
                source_title,
                source_url,
                published_at,
                status,
                review_status,
                review_summary,
                publish_decision,
                publish_reason,
                prompt_config_id,
                prompt_name,
                model,
                generation_mode,
                created_at,
                updated_at
            FROM draft_articles
        """
        params: list[object] = []
        clauses: list[str] = []

        if status:
            clauses.append("status = %s")
            params.append(status)
        if review_status:
            clauses.append("review_status = %s")
            params.append(review_status)

        if clauses:
            statement += " WHERE " + " AND ".join(clauses)

        statement += " ORDER BY published_at DESC, updated_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_draft_row(row) for row in rows]

    def list_content_plan(self, limit: int = 20, status: Optional[str] = None) -> list[ContentPlanItem]:
        statement = """
            SELECT
                id,
                raw_item_id,
                title,
                source_title,
                category,
                priority_score,
                priority_label,
                planned_format,
                status,
                reason,
                created_at,
                updated_at
            FROM content_plan_items
        """
        params: list[object] = []

        if status:
            statement += " WHERE status = %s"
            params.append(status)

        statement += " ORDER BY priority_score DESC, updated_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_content_plan_row(row) for row in rows]

    def get_content_plan_item(self, item_id: str) -> ContentPlanItem | None:
        statement = """
            SELECT
                id,
                raw_item_id,
                title,
                source_title,
                category,
                priority_score,
                priority_label,
                planned_format,
                status,
                reason,
                created_at,
                updated_at
            FROM content_plan_items
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (item_id,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_content_plan_row(row)

    def list_reviews(self, limit: int = 20) -> list[EditorReview]:
        statement = """
            SELECT
                id,
                draft_id,
                status,
                decision,
                summary,
                notes,
                revised_title,
                revised_dek,
                revised_body,
                prompt_config_id,
                prompt_name,
                model,
                created_at
            FROM editor_reviews
            ORDER BY created_at DESC
            LIMIT %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (limit,))
                rows = cursor.fetchall()

        return [self._map_review_row(row) for row in rows]

    def list_publishable_drafts(self, limit: int = 5, since: datetime | None = None) -> list[DraftArticle]:
        statement = """
            SELECT
                d.id,
                d.raw_item_id,
                d.title,
                d.dek,
                d.body,
                d.writer_title,
                d.writer_dek,
                d.writer_body,
                d.category,
                d.source_title,
                d.source_url,
                d.published_at,
                d.status,
                d.review_status,
                d.review_summary,
                d.publish_decision,
                d.publish_reason,
                d.prompt_config_id,
                d.prompt_name,
                d.model,
                d.generation_mode,
                d.created_at,
                d.updated_at
            FROM draft_articles d
            JOIN raw_items r ON r.id = d.raw_item_id
            WHERE d.status = 'ready_for_publish'
              AND d.review_status = 'reviewed'
              AND d.publish_decision = 'publish_auto'
              AND r.is_duplicate = FALSE
        """
        params: list[object] = []
        if since is not None:
            statement += " AND r.fetched_at >= %s"
            params.append(since)
        statement += " ORDER BY d.updated_at ASC, d.published_at DESC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_draft_row(row) for row in rows]

    def count_publishable_drafts(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM draft_articles
            WHERE status = 'ready_for_publish'
              AND review_status = 'reviewed'
              AND publish_decision = 'publish_auto'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_articles_missing_published_draft(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM articles a
            LEFT JOIN draft_articles d ON d.raw_item_id = a.raw_item_id
            WHERE d.raw_item_id IS NULL
               OR d.status <> 'published'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_published_drafts_missing_article(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM draft_articles d
            LEFT JOIN articles a ON a.raw_item_id = d.raw_item_id
            WHERE d.status = 'published'
              AND a.raw_item_id IS NULL
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_published_drafts_missing_news_item(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM draft_articles d
            JOIN raw_items r ON r.id = d.raw_item_id
            LEFT JOIN news_items n ON n.id = r.external_id
            WHERE d.status = 'published'
              AND n.id IS NULL
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def get_draft(self, draft_id: str) -> DraftArticle | None:
        statement = """
            SELECT
                id,
                raw_item_id,
                title,
                dek,
                body,
                writer_title,
                writer_dek,
                writer_body,
                category,
                source_title,
                source_url,
                published_at,
                status,
                review_status,
                review_summary,
                publish_decision,
                publish_reason,
                prompt_config_id,
                prompt_name,
                model,
                generation_mode,
                created_at,
                updated_at
            FROM draft_articles
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (draft_id,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_draft_row(row)

    def upsert_draft(self, draft: DraftArticle) -> DraftArticle:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO draft_articles (
                        id,
                        raw_item_id,
                        title,
                        dek,
                        body,
                        writer_title,
                        writer_dek,
                        writer_body,
                        category,
                        source_title,
                        source_url,
                        published_at,
                        status,
                        review_status,
                        review_summary,
                        publish_decision,
                        publish_reason,
                        prompt_config_id,
                        prompt_name,
                        model,
                        generation_mode
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        dek = EXCLUDED.dek,
                        body = EXCLUDED.body,
                        writer_title = COALESCE(draft_articles.writer_title, EXCLUDED.writer_title),
                        writer_dek = COALESCE(draft_articles.writer_dek, EXCLUDED.writer_dek),
                        writer_body = COALESCE(draft_articles.writer_body, EXCLUDED.writer_body),
                        category = EXCLUDED.category,
                        source_title = EXCLUDED.source_title,
                        source_url = EXCLUDED.source_url,
                        published_at = EXCLUDED.published_at,
                        status = EXCLUDED.status,
                        review_status = EXCLUDED.review_status,
                        review_summary = EXCLUDED.review_summary,
                        publish_decision = EXCLUDED.publish_decision,
                        publish_reason = EXCLUDED.publish_reason,
                        prompt_config_id = EXCLUDED.prompt_config_id,
                        prompt_name = EXCLUDED.prompt_name,
                        model = EXCLUDED.model,
                        generation_mode = EXCLUDED.generation_mode,
                        updated_at = NOW()
                    """,
                    (
                        draft.id,
                        draft.raw_item_id,
                        draft.title,
                        draft.dek,
                        draft.body,
                        draft.writer_title,
                        draft.writer_dek,
                        draft.writer_body,
                        draft.category,
                        draft.source_title,
                        draft.source_url,
                        draft.published_at,
                        draft.status,
                        draft.review_status,
                        draft.review_summary,
                        draft.publish_decision,
                        draft.publish_reason,
                        draft.prompt_config_id,
                        draft.prompt_name,
                        draft.model,
                        draft.generation_mode,
                    ),
                )
            connection.commit()

        stored = self.get_draft(draft.id)
        if stored is None:
            raise LookupError(f"Draft {draft.id} was not stored.")
        return stored

    def upsert_review(self, review: EditorReview) -> EditorReview:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO editor_reviews (
                        id,
                        draft_id,
                        status,
                        decision,
                        summary,
                        notes,
                        revised_title,
                        revised_dek,
                        revised_body,
                        prompt_config_id,
                        prompt_name,
                        model
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (draft_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        decision = EXCLUDED.decision,
                        summary = EXCLUDED.summary,
                        notes = EXCLUDED.notes,
                        revised_title = EXCLUDED.revised_title,
                        revised_dek = EXCLUDED.revised_dek,
                        revised_body = EXCLUDED.revised_body,
                        prompt_config_id = EXCLUDED.prompt_config_id,
                        prompt_name = EXCLUDED.prompt_name,
                        model = EXCLUDED.model,
                        created_at = NOW()
                    """,
                    (
                        review.id,
                        review.draft_id,
                        review.status,
                        review.decision,
                        review.summary,
                        review.notes,
                        review.revised_title,
                        review.revised_dek,
                        review.revised_body,
                        review.prompt_config_id,
                        review.prompt_name,
                        review.model,
                    ),
                )
            connection.commit()

        stored = next((item for item in self.list_reviews(limit=100) if item.draft_id == review.draft_id), None)
        if stored is None:
            raise LookupError(f"Review for draft {review.draft_id} was not stored.")
        return stored

    def upsert_content_plan_item(self, item: ContentPlanItem) -> ContentPlanItem:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO content_plan_items (
                        id,
                        raw_item_id,
                        title,
                        source_title,
                        category,
                        priority_score,
                        priority_label,
                        planned_format,
                        status,
                        reason
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        source_title = EXCLUDED.source_title,
                        category = EXCLUDED.category,
                        priority_score = EXCLUDED.priority_score,
                        priority_label = EXCLUDED.priority_label,
                        planned_format = EXCLUDED.planned_format,
                        status = EXCLUDED.status,
                        reason = EXCLUDED.reason,
                        updated_at = NOW()
                    """,
                    (
                        item.id,
                        item.raw_item_id,
                        item.title,
                        item.source_title,
                        item.category,
                        item.priority_score,
                        item.priority_label,
                        item.planned_format,
                        item.status,
                        item.reason,
                    ),
                )
            connection.commit()

        stored = self.get_content_plan_item(item.id)
        if stored is None:
            raise LookupError(f"Content plan item {item.id} was not stored.")
        return stored

    def set_content_plan_status(self, raw_item_id: str, status: str) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE content_plan_items
                    SET status = %s,
                        updated_at = NOW()
                    WHERE raw_item_id = %s
                    """,
                    (status, raw_item_id),
                )
            connection.commit()

    def set_draft_review_status(
        self,
        draft_id: str,
        *,
        review_status: str,
        status: str,
        review_summary: str,
        publish_decision: str | None = None,
        publish_reason: str | None = None,
    ) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE draft_articles
                    SET review_status = %s,
                        status = %s,
                        review_summary = %s,
                        publish_decision = COALESCE(%s, publish_decision),
                        publish_reason = COALESCE(%s, publish_reason),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (review_status, status, review_summary, publish_decision, publish_reason, draft_id),
                )
            connection.commit()

