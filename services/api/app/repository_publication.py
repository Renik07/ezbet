from __future__ import annotations

from contextlib import nullcontext
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Optional
from urllib.parse import (
    urlsplit,
    urlunsplit,
)
import psycopg
from .models import (
    Article,
    DraftArticle,
    NewsItem,
    RawItem,
)
from .repository_support import (
    _available_article_slug,
    _build_article_slug,
)

class PublicationRepository:
    def reset_runtime_data(self) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    TRUNCATE TABLE
                        editor_reviews,
                        draft_articles,
                        content_plan_items,
                        news_items,
                        raw_items,
                        source_sync_state
                    RESTART IDENTITY CASCADE
                    """
                )
            connection.commit()

    def list(
        self,
        query: Optional[str] = None,
        ai_only: bool = False,
        *,
        guide_only: bool = False,
        include_hidden: bool = False,
        limit: int | None = None,
        page: int | None = None,
        page_meta: dict | None = None,
    ) -> list[NewsItem]:
        statement = """
            SELECT n.id, n.title, n.description, n.category, n.published_at, n.source, n.link, n.status, n.visibility, n.ai_reviewed, a.slug, a.updated_at
            FROM news_items n
            LEFT JOIN articles a ON a.news_item_id = n.id
        """
        params: list[object] = []
        clauses: list[str] = []

        if not include_hidden:
            clauses.append("COALESCE(n.visibility, 'public') = 'public'")

        if ai_only:
            clauses.append("n.ai_reviewed = TRUE")

        if guide_only:
            clauses.append("a.raw_item_id LIKE %s")
            params.append("guide-topic:%")

        if query:
            clauses.append(
                """
                (
                    n.title ILIKE %s
                    OR n.description ILIKE %s
                    OR n.category ILIKE %s
                    OR n.source ILIKE %s
                )
                """
            )
            search = f"%{query.strip()}%"
            params.extend((search, search, search, search))

        if clauses:
            statement += " WHERE " + " AND ".join(clauses)

        if page is not None:
            statement += " AND a.slug IS NOT NULL" if clauses else " WHERE a.slug IS NOT NULL"
            if not guide_only:
                statement += " AND n.id NOT LIKE %s"
                params.append("guide:%")
            with self.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM (" + statement + ") AS feed", tuple(params))
                    total = cursor.fetchone()[0]
                    page_size = limit or 20
                    current_page = min(page, max(1, (total + page_size - 1) // page_size))
                    cursor.execute(statement + " ORDER BY n.published_at DESC, n.id DESC LIMIT %s OFFSET %s", (*params, page_size, (current_page - 1) * page_size))
                    rows = cursor.fetchall()
            if page_meta is not None:
                page_meta.update(total=total, page=current_page)
            return [self._map_news_row(row) for row in rows]

        statement += " ORDER BY n.published_at DESC"
        if limit is not None:
            statement += " LIMIT %s"
            params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_news_row(row) for row in rows]

    def get_article_by_slug(self, slug: str, *, include_hidden: bool = False) -> Article | None:
        statement = """
            SELECT
                a.id,
                a.slug,
                a.news_item_id,
                a.raw_item_id,
                a.title,
                a.lead,
                a.dek,
                a.body,
                a.category,
                a.source_title,
                a.source_url,
                a.tags,
                a.published_at,
                a.ai_reviewed,
                a.created_at,
                a.updated_at
            FROM articles a
            JOIN news_items n ON n.id = a.news_item_id
            LEFT JOIN article_slug_redirects r ON r.old_slug = %s
            WHERE (a.slug = %s OR a.id = r.article_id)
        """

        if not include_hidden:
            statement += " AND COALESCE(n.visibility, 'public') = 'public'"

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (slug, slug))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_article_row(row)

    def get_news_item(self, news_item_id: str, *, include_hidden: bool = False) -> NewsItem | None:
        statement = """
            SELECT n.id, n.title, n.description, n.category, n.published_at, n.source, n.link, n.status, n.visibility, n.ai_reviewed, a.slug, a.updated_at
            FROM news_items n
            LEFT JOIN articles a ON a.news_item_id = n.id
            WHERE n.id = %s
        """
        params: list[object] = [news_item_id]

        if not include_hidden:
            statement += " AND COALESCE(n.visibility, 'public') = 'public'"

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._map_news_row(row)

    def set_news_visibility(self, news_item_id: str, visibility: str) -> NewsItem | None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE news_items
                    SET visibility = %s
                    WHERE id = %s
                    """,
                    (visibility, news_item_id),
                )
            connection.commit()

        return self.get_news_item(news_item_id, include_hidden=True)

    def list_article_similarity_candidates(
        self,
        *,
        category: str | None,
        published_at: datetime,
        exclude_news_item_id: str | None = None,
        window_hours: int = 24,
        limit: int | None = 20,
    ) -> list[Article]:
        statement = """
            SELECT
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
                ai_reviewed,
                created_at,
                updated_at
            FROM articles
            WHERE published_at >= %s
              AND published_at <= %s
        """
        params: list[object] = [
            published_at - timedelta(hours=window_hours),
            published_at,
        ]

        if category is not None:
            statement += " AND category = %s"
            params.append(category)

        if exclude_news_item_id is not None:
            statement += " AND news_item_id <> %s"
            params.append(exclude_news_item_id)

        statement += " ORDER BY published_at DESC"
        if limit is not None:
            statement += " LIMIT %s"
            params.append(limit)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, tuple(params))
                rows = cursor.fetchall()

        return [self._map_article_row(row) for row in rows]

    def count_ready_to_publish_with_existing_article(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM draft_articles d
            JOIN articles a ON a.raw_item_id = d.raw_item_id
            WHERE d.status = 'ready_for_publish'
              AND d.review_status = 'reviewed'
              AND d.publish_decision = 'publish_auto'
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def count_multiple_articles_per_news_item(self) -> int:
        statement = """
            SELECT COUNT(*)
            FROM (
                SELECT news_item_id
                FROM articles
                GROUP BY news_item_id
                HAVING COUNT(*) > 1
            ) duplicates
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                row = cursor.fetchone()

        return int(row[0] if row and row[0] is not None else 0)

    def ingest_demo_batch(self) -> list[NewsItem]:
        timestamp = int(datetime.now(timezone.utc).timestamp())
        generated = self._default_news_item(
            item_id=str(timestamp),
            title="Scheduler нашел новый инфоповод и отправил его на AI-редактуру",
            description=(
                "Это демонстрационная запись для MVP: ingestion добавляет новость, "
                "после чего она становится доступна для публикации на сайте."
            ),
            category="Система",
            source="scheduler demo",
            link=f"https://example.com/news/system-{timestamp}",
        )
        return self.upsert_many([generated])

    def upsert_many(self, items: list[NewsItem]) -> list[NewsItem]:
        added: list[NewsItem] = []

        with self.connect() as connection:
            with connection.cursor() as cursor:
                for item in items:
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
                            ai_reviewed
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        RETURNING id
                        """,
                        (
                            item.id,
                            item.title,
                            item.description,
                            item.category,
                            item.published_at,
                            item.source,
                            item.link,
                            item.status,
                            item.ai_reviewed,
                        ),
                    )
                    if cursor.fetchone():
                        added.append(item)
            connection.commit()

        return added

    def publish_draft_to_news(self, draft: DraftArticle, raw_item: RawItem) -> NewsItem:
        if draft.generation_mode == "template" or draft.status == "fallback_only":
            raise ValueError("Template fallback drafts must never be published.")

        public_published_at = datetime.now(timezone.utc)
        published_item = NewsItem(
            id=raw_item.external_id,
            title=draft.title,
            description=draft.dek,
            category=draft.category,
            published_at=public_published_at,
            source=raw_item.source_title,
            link=raw_item.url,
            status="published",
            ai_reviewed=True,
            article_slug=None,
            visibility="public",
        )

        with self.connect() as connection:
            article = self.upsert_article(
                draft, raw_item, public_published_at=public_published_at, connection=connection,
            )
            published_item.article_slug = article.slug
            published_item.published_at = article.published_at
            published_item.updated_at = article.updated_at
            with connection.cursor() as cursor:
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
                        ai_reviewed
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        category = EXCLUDED.category,
                        published_at = EXCLUDED.published_at,
                        source = EXCLUDED.source,
                        link = EXCLUDED.link,
                        status = EXCLUDED.status,
                        ai_reviewed = EXCLUDED.ai_reviewed
                    """,
                    (
                        published_item.id,
                        published_item.title,
                        published_item.description,
                        published_item.category,
                        published_item.published_at,
                        published_item.source,
                            published_item.link,
                            published_item.status,
                            published_item.ai_reviewed,
                        ),
                    )
                cursor.execute(
                    """UPDATE draft_articles SET status = 'published', review_status = 'reviewed',
                              publish_decision = 'publish_auto',
                              publish_reason = 'Материал опубликован отдельным publish-этапом.',
                              updated_at = NOW() WHERE id = %s""", (draft.id,),
                )
                cursor.execute(
                    "UPDATE content_plan_items SET status = 'published', updated_at = NOW() WHERE raw_item_id = %s",
                    (raw_item.id,),
                )
            connection.commit()

        return published_item

    def reflow_public_published_at_for_articles(self, *, limit: int = 500) -> int:
        """Compatibility repair endpoint: restore stored creation times, never invent dates."""
        with self.connect() as connection:
            rows = connection.execute("""
                WITH candidates AS (
                    SELECT a.id, a.news_item_id, a.created_at
                    FROM articles a JOIN news_items n ON n.id = a.news_item_id
                    WHERE a.raw_item_id NOT LIKE 'guide-topic:%%'
                      AND (a.published_at IS DISTINCT FROM a.created_at
                           OR n.published_at IS DISTINCT FROM a.created_at)
                    ORDER BY a.created_at DESC LIMIT %s
                ), repaired AS (
                    UPDATE articles a SET published_at = c.created_at
                    FROM candidates c WHERE a.id = c.id
                    RETURNING a.news_item_id, a.published_at
                )
                UPDATE news_items n SET published_at = r.published_at
                FROM repaired r WHERE n.id = r.news_item_id RETURNING n.id
            """, (limit,)).fetchall()
        return len(rows)

    def upsert_article(
        self,
        draft: DraftArticle,
        raw_item: RawItem,
        *,
        public_published_at: datetime | None = None,
        connection: psycopg.Connection | None = None,
    ) -> Article:
        display_published_at = public_published_at or datetime.now(timezone.utc)
        article = Article(
            id=f"article:{raw_item.external_id}",
            slug=_build_article_slug(draft.title),
            news_item_id=raw_item.external_id,
            raw_item_id=raw_item.id,
            title=draft.title,
            lead=raw_item.lead,
            dek=draft.dek,
            body=draft.body,
            category=draft.category,
            source_title=raw_item.source_title,
            source_url=raw_item.url,
            tags=raw_item.tags,
            published_at=display_published_at,
            ai_reviewed=True,
            created_at=display_published_at,
            updated_at=display_published_at,
        )

        owns_connection = connection is None
        with (self.connect() if owns_connection else nullcontext(connection)) as connection:
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
                        ai_reviewed,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        slug = EXCLUDED.slug,
                        news_item_id = EXCLUDED.news_item_id,
                        raw_item_id = EXCLUDED.raw_item_id,
                        title = EXCLUDED.title,
                        lead = EXCLUDED.lead,
                        dek = EXCLUDED.dek,
                        body = EXCLUDED.body,
                        category = EXCLUDED.category,
                        source_title = EXCLUDED.source_title,
                        source_url = EXCLUDED.source_url,
                        tags = EXCLUDED.tags,
                        published_at = articles.published_at,
                        ai_reviewed = EXCLUDED.ai_reviewed,
                        updated_at = CASE WHEN
                            (articles.title, articles.lead, articles.dek, articles.body,
                             articles.category, articles.source_title, articles.source_url,
                             articles.tags, articles.ai_reviewed)
                            IS DISTINCT FROM
                            (EXCLUDED.title, EXCLUDED.lead, EXCLUDED.dek, EXCLUDED.body,
                             EXCLUDED.category, EXCLUDED.source_title, EXCLUDED.source_url,
                             EXCLUDED.tags, EXCLUDED.ai_reviewed)
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
                        article.ai_reviewed,
                        article.created_at,
                        article.updated_at,
                    ),
                )
                cursor.execute(
                    """SELECT id, slug, news_item_id, raw_item_id, title, lead, dek, body,
                              category, source_title, source_url, tags, published_at,
                              ai_reviewed, created_at, updated_at
                       FROM articles WHERE id = %s""", (article.id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LookupError(f"Article {article.slug} was not stored.")
                stored = self._map_article_row(row)
            if owns_connection:
                connection.commit()

        return stored

    def _load_recent_dedup_candidates(
        self,
        cursor: psycopg.Cursor[tuple[object, ...]],
        *,
        window_hours: int,
    ) -> dict[str, list[tuple[str, str, str]]]:
        cursor.execute(
            """
            SELECT id, normalized_category, title, summary, full_text
            FROM raw_items
            WHERE published_at >= %s
              AND is_duplicate = FALSE
            ORDER BY published_at DESC
            """,
            (datetime.now(timezone.utc) - timedelta(hours=window_hours),),
        )
        rows = cursor.fetchall()

        grouped: dict[str, list[tuple[str, str, str]]] = {}
        for row in rows:
            item_id = str(row[0])
            category = str(row[1])
            title = str(row[2])
            summary = str(row[4] or row[3] or "")
            grouped.setdefault(category, []).append(
                (item_id, title, self._normalize_similarity_text(f"{title} {summary}"))
            )
        return grouped

    @staticmethod
    def _normalize_ai_research_url(url: str) -> str:
        parts = urlsplit(url)
        if not parts.scheme or not parts.netloc:
            return url

        path = parts.path or "/"
        article_like = (
            path.endswith(".html")
            or path.endswith(".htm")
            or path.rstrip("/").split("/")[-1].isdigit()
        )

        if article_like:
            if "/" in path.rstrip("/"):
                path = path.rsplit("/", 1)[0] + "/"
            else:
                path = "/"

        return urlunsplit((parts.scheme, parts.netloc, path, "", ""))

    @staticmethod
    def _default_news_item(
        item_id: str,
        title: str,
        description: str,
        category: str,
        source: str,
        link: str,
    ) -> NewsItem:
        return NewsItem(
            id=item_id,
            title=title,
            description=description,
            category=category,
            published_at=datetime.now(timezone.utc),
            source=source,
            link=link,
        )

