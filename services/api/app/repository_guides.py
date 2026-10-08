from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from .models import (
    Article,
    GuideTopic,
    PromptConfig,
)
from .repository_support import (
    _available_article_slug,
    _build_article_slug,
)

class GuidesRepository:
    def ensure_guide_topic_defaults(self, topics: list[dict[str, object]]) -> None:
        if not topics:
            return

        with self.connect() as connection:
            with connection.cursor() as cursor:
                for topic in topics:
                    cursor.execute(
                        """
                        INSERT INTO guide_topics (
                            topic_number,
                            title,
                            section,
                            category,
                            requires_web_search,
                            search_context_size
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (topic_number) DO UPDATE SET
                            title = CASE
                                WHEN guide_topics.status = 'planned' THEN EXCLUDED.title
                                ELSE guide_topics.title
                            END,
                            section = CASE
                                WHEN guide_topics.status = 'planned' THEN EXCLUDED.section
                                ELSE guide_topics.section
                            END,
                            category = CASE
                                WHEN guide_topics.status = 'planned' THEN EXCLUDED.category
                                ELSE guide_topics.category
                            END,
                            requires_web_search = CASE
                                WHEN guide_topics.status = 'planned' THEN EXCLUDED.requires_web_search
                                ELSE guide_topics.requires_web_search
                            END,
                            search_context_size = CASE
                                WHEN guide_topics.status = 'planned' THEN EXCLUDED.search_context_size
                                ELSE guide_topics.search_context_size
                            END,
                            updated_at = CASE
                                WHEN guide_topics.status = 'planned' THEN NOW()
                                ELSE guide_topics.updated_at
                            END
                        """,
                        (
                            topic["topic_number"],
                            topic["title"],
                            topic["section"],
                            topic["category"],
                            bool(topic.get("requires_web_search", False)),
                            str(topic.get("search_context_size") or "low"),
                        ),
                    )
            connection.commit()

    def list_guide_topics(self, limit: int = 50, status: str | None = None) -> list[GuideTopic]:
        statement = """
            SELECT
                id,
                topic_number,
                title,
                section,
                category,
                requires_web_search,
                search_context_size,
                status,
                article_id,
                article_slug,
                last_error,
                created_at,
                updated_at
            FROM guide_topics
        """
        params: list[object] = []
        if status:
            statement += " WHERE status = %s"
            params.append(status)
        statement += " ORDER BY topic_number ASC LIMIT %s"
        params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_guide_topic_row(row) for row in rows]

    def claim_next_guide_topic(self) -> GuideTopic | None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE guide_topics
                    SET status = 'planned',
                        last_error = COALESCE(last_error, 'Recovered stale in_progress topic.'),
                        updated_at = NOW()
                    WHERE status = 'in_progress'
                      AND updated_at < NOW() - INTERVAL '12 hours'
                    """
                )
                cursor.execute(
                    """
                    SELECT section
                    FROM guide_topics
                    WHERE status = 'published'
                    ORDER BY updated_at DESC
                    LIMIT 3
                    """
                )
                recent_sections = [str(row[0]) for row in cursor.fetchall()]

                cursor.execute(
                    """
                    SELECT id
                    FROM guide_topics
                    WHERE status = 'planned'
                      AND topic_number BETWEEN 1 AND 40
                    ORDER BY topic_number ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
                row = cursor.fetchone()

                if row is None and recent_sections:
                    cursor.execute(
                        """
                        SELECT id
                        FROM guide_topics
                        WHERE status = 'planned'
                          AND topic_number > 40
                          AND section <> ALL(%s)
                        ORDER BY MD5(topic_number::TEXT || ':ezbet-guide-shuffle-v1') ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                        """,
                        (recent_sections,),
                    )
                    row = cursor.fetchone()

                if row is None:
                    cursor.execute(
                        """
                        SELECT id
                        FROM guide_topics
                        WHERE status = 'planned'
                          AND topic_number > 40
                        ORDER BY MD5(topic_number::TEXT || ':ezbet-guide-shuffle-v1') ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                        """
                    )
                    row = cursor.fetchone()

                if row is None:
                    connection.commit()
                    return None

                topic_id = int(row[0])
                cursor.execute(
                    """
                    UPDATE guide_topics
                    SET status = 'in_progress',
                        last_error = NULL,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (topic_id,),
                )
            connection.commit()

        return self.get_guide_topic(topic_id)

    def get_guide_topic(self, topic_id: int) -> GuideTopic | None:
        statement = """
            SELECT
                id,
                topic_number,
                title,
                section,
                category,
                requires_web_search,
                search_context_size,
                status,
                article_id,
                article_slug,
                last_error,
                created_at,
                updated_at
            FROM guide_topics
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (topic_id,))
                row = cursor.fetchone()

        return self._map_guide_topic_row(row) if row else None

    def mark_guide_topic_error(self, topic_id: int, error: str) -> GuideTopic | None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE guide_topics
                    SET status = 'planned',
                        last_error = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (error[:1000], topic_id),
                )
            connection.commit()

        return self.get_guide_topic(topic_id)

    def publish_guide_article(
        self,
        *,
        topic: GuideTopic,
        title: str,
        dek: str,
        body: str,
        model: str,
        generation_mode: str,
        prompt: PromptConfig,
    ) -> Article:
        published_at = datetime.now(timezone.utc)
        news_item_id = f"guide:{topic.topic_number}"
        raw_item_id = f"guide-topic:{topic.topic_number}"
        article_id = f"article:{news_item_id}"
        tags = [topic.category, topic.section, "Аналитика", "Гайд"]
        article = Article(
            id=article_id,
            slug=_build_article_slug(title),
            news_item_id=news_item_id,
            raw_item_id=raw_item_id,
            title=title,
            lead=dek,
            dek=dek,
            body=body,
            category=topic.category,
            source_title="ezbet.ru",
            source_url=None,
            tags=tags,
            published_at=published_at,
            ai_reviewed=True,
            created_at=published_at,
            updated_at=published_at,
        )

        with self.connect() as connection:
            with connection.cursor() as cursor:
                article = article.model_copy(
                    update={"slug": _available_article_slug(cursor, article.slug, article.id)}
                )
                cursor.execute(
                    """
                    INSERT INTO articles (
                        id,
                        slug,
                        news_item_id,
                        raw_item_id,
                        title,
                        lead,
                        dek,
                        body,
                        category,
                        source_title,
                        source_url,
                        tags,
                        published_at,
                        ai_reviewed
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (id) DO UPDATE SET
                        slug = EXCLUDED.slug,
                        title = EXCLUDED.title,
                        lead = EXCLUDED.lead,
                        dek = EXCLUDED.dek,
                        body = EXCLUDED.body,
                        category = EXCLUDED.category,
                        source_title = EXCLUDED.source_title,
                        source_url = EXCLUDED.source_url,
                        tags = EXCLUDED.tags,
                        published_at = articles.published_at,
                        ai_reviewed = TRUE,
                        updated_at = CASE WHEN
                            (articles.title, articles.lead, articles.dek, articles.body,
                             articles.category, articles.source_title, articles.source_url, articles.tags)
                            IS DISTINCT FROM
                            (EXCLUDED.title, EXCLUDED.lead, EXCLUDED.dek, EXCLUDED.body,
                             EXCLUDED.category, EXCLUDED.source_title, EXCLUDED.source_url, EXCLUDED.tags)
                            THEN NOW() ELSE articles.updated_at END
                    """,
                    (
                        article.id,
                        article.slug,
                        article.news_item_id,
                        article.raw_item_id,
                        article.title,
                        article.lead,
                        article.dek,
                        article.body,
                        article.category,
                        article.source_title,
                        article.source_url,
                        article.tags,
                        article.published_at,
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO news_items (
                        id,
                        title,
                        description,
                        category,
                        published_at,
                        source,
                        link,
                        status,
                        visibility,
                        ai_reviewed
                    )
                    VALUES (%s, %s, %s, %s, %s, 'ezbet.ru', NULL, 'published', 'public', TRUE)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        category = EXCLUDED.category,
                        published_at = news_items.published_at,
                        source = EXCLUDED.source,
                        link = EXCLUDED.link,
                        status = EXCLUDED.status,
                        visibility = EXCLUDED.visibility,
                        ai_reviewed = TRUE
                    """,
                    (
                        news_item_id,
                        title,
                        dek,
                        topic.category,
                        published_at,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE guide_topics
                    SET status = 'published',
                        article_id = %s,
                        article_slug = %s,
                        last_error = NULL,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (article.id, article.slug, topic.id),
                )
            connection.commit()

        stored = self.get_article_by_slug(article.slug)
        if stored is None:
            raise LookupError(f"Guide article {article.slug} was not stored.")
        return stored

