from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
import psycopg
from .ingestion import SUPPORTED_ACTIVE_SOURCE_TYPES
from .models import (
    RawItem,
    SourceItem,
    SourceSyncState,
)

class SourcesRepository:
    def ensure_source_defaults(self, sources: list[SourceItem]) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                for source in sources:
                    cursor.execute(
                        """
                        INSERT INTO source_configs (
                            key,
                            title,
                            url,
                            category,
                            source_type,
                            status,
                            notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (key) DO NOTHING
                        """,
                        (
                            source.key,
                            source.title,
                            source.url,
                            source.category,
                            source.source_type,
                            source.status,
                            source.notes,
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO source_sync_state (
                            source_key,
                            source_title,
                            last_status
                        )
                        VALUES (%s, %s, 'idle')
                        ON CONFLICT (source_key) DO UPDATE SET
                            source_title = EXCLUDED.source_title
                        """,
                        (source.key, source.title),
                    )
            connection.commit()

    def list_source_configs(self) -> list[SourceItem]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT key, title, url, category, source_type, status, notes
                    FROM source_configs
                    ORDER BY created_at ASC, title ASC
                    """
                )
                rows = cursor.fetchall()

        return [
            SourceItem(
                key=str(row[0]),
                title=str(row[1]),
                url=str(row[2]),
                category=str(row[3]),
                source_type=str(row[4]),
                status=str(row[5]),
                notes=str(row[6]),
            )
            for row in rows
        ]

    def list_active_sources(self) -> list[SourceItem]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT key, title, url, category, source_type, status, notes
                    FROM source_configs
                    WHERE status = 'active'
                      AND source_type = ANY(%s)
                    ORDER BY created_at ASC, title ASC
                    """,
                    (list(SUPPORTED_ACTIVE_SOURCE_TYPES),),
                )
                rows = cursor.fetchall()

        return [
            SourceItem(
                key=str(row[0]),
                title=str(row[1]),
                url=str(row[2]),
                category=str(row[3]),
                source_type=str(row[4]),
                status=str(row[5]),
                notes=str(row[6]),
            )
            for row in rows
        ]

    def create_source_config(self, source: SourceItem) -> SourceItem:
        source = self._normalize_source_config(source)
        self._validate_source_config(source)
        self._validate_source_activation_readiness(source)
        try:
            with self.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO source_configs (
                            key,
                            title,
                            url,
                            category,
                            source_type,
                            status,
                            notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            source.key,
                            source.title,
                            source.url,
                            source.category,
                            source.source_type,
                            source.status,
                            source.notes,
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO source_sync_state (source_key, source_title, last_status)
                        VALUES (%s, %s, 'idle')
                        ON CONFLICT (source_key) DO NOTHING
                        """,
                        (source.key, source.title),
                    )
                connection.commit()
        except psycopg.errors.UniqueViolation as exc:
            try:
                existing = self.get_source_config(source.key)
            except LookupError:
                raise ValueError("Источник с таким key уже существует.") from exc

            if existing.status == "draft":
                return self.update_source_config(source)

            raise ValueError(
                "Источник с таким key уже существует. Удалите текущий источник или используйте другой key."
            ) from exc
        return self.get_source_config(source.key)

    def update_source_config(self, source: SourceItem) -> SourceItem:
        source = self._normalize_source_config(source)
        self._validate_source_config(source)
        self._validate_source_activation_readiness(source)
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE source_configs
                    SET title = %s,
                        url = %s,
                        category = %s,
                        source_type = %s,
                        status = %s,
                        notes = %s,
                        updated_at = NOW()
                    WHERE key = %s
                    """,
                    (
                        source.title,
                        source.url,
                        source.category,
                        source.source_type,
                        source.status,
                        source.notes,
                        source.key,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE source_sync_state
                    SET source_title = %s,
                        updated_at = NOW()
                    WHERE source_key = %s
                    """,
                    (source.title, source.key),
                )
            connection.commit()
        return self.get_source_config(source.key)

    def delete_source_config(self, key: str) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM source_sync_state WHERE source_key = %s", (key,))
                cursor.execute("DELETE FROM source_configs WHERE key = %s", (key,))
            connection.commit()

    def get_source_config(self, key: str) -> SourceItem:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT key, title, url, category, source_type, status, notes
                    FROM source_configs
                    WHERE key = %s
                    """,
                    (key,),
                )
                row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Source {key} was not found.")
        return SourceItem(
            key=str(row[0]),
            title=str(row[1]),
            url=str(row[2]),
            category=str(row[3]),
            source_type=str(row[4]),
            status=str(row[5]),
            notes=str(row[6]),
        )

    def list_source_sync_states(self) -> list[SourceSyncState]:
        statement = """
            SELECT
                source_key,
                source_title,
                last_fetched_at,
                last_successful_fetch_at,
                last_successful_parse_at,
                last_published_at,
                last_external_id,
                last_item_count,
                fetch_status,
                parse_status,
                fetch_error_count,
                parse_error_count,
                consecutive_failures,
                retry_count,
                last_probe_at,
                last_probe_count,
                last_probe_readiness,
                preferred_adapter,
                preferred_adapter_url,
                supports_rss,
                supports_news_sitemap,
                supports_sitemap,
                supports_scraping,
                last_probe_full_text_ok,
                last_probe_full_text_method,
                last_probe_lead_ok,
                last_probe_tags_count,
                last_probe_sample_title,
                last_probe_sample_url,
                last_status,
                last_error,
                updated_at
            FROM source_sync_state
            ORDER BY source_title ASC
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement)
                rows = cursor.fetchall()

        return [self._map_source_sync_state_row(row) for row in rows]

    def get_source_sync_state_map(self) -> dict[str, SourceSyncState]:
        return {item.source_key: item for item in self.list_source_sync_states()}

    def get_recent_known_external_ids_by_source(
        self,
        source_keys: list[str],
        *,
        per_source_limit: int = 200,
    ) -> dict[str, set[str]]:
        if not source_keys:
            return {}

        statement = """
            SELECT source_key, external_id
            FROM (
                SELECT
                    source_key,
                    external_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY source_key
                        ORDER BY fetched_at DESC, published_at DESC
                    ) AS rn
                FROM raw_items
                WHERE source_key = ANY(%s)
                  AND external_id <> ''
            ) ranked
            WHERE rn <= %s
        """

        known_by_source: dict[str, set[str]] = {key: set() for key in source_keys}
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (source_keys, per_source_limit))
                rows = cursor.fetchall()

        for row in rows:
            source_key = str(row[0])
            external_id = str(row[1])
            known_by_source.setdefault(source_key, set()).add(external_id)

        return known_by_source

    def get_recent_known_dedupe_keys_by_source(
        self,
        source_keys: list[str],
        *,
        per_source_limit: int = 200,
    ) -> dict[str, set[str]]:
        if not source_keys:
            return {}

        statement = """
            SELECT source_key, dedupe_key
            FROM (
                SELECT
                    source_key,
                    dedupe_key,
                    ROW_NUMBER() OVER (
                        PARTITION BY source_key
                        ORDER BY fetched_at DESC, published_at DESC
                    ) AS rn
                FROM raw_items
                WHERE source_key = ANY(%s)
                  AND dedupe_key <> ''
            ) ranked
            WHERE rn <= %s
        """

        known_by_source: dict[str, set[str]] = {key: set() for key in source_keys}
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (source_keys, per_source_limit))
                rows = cursor.fetchall()

        for row in rows:
            source_key = str(row[0])
            dedupe_key = str(row[1])
            known_by_source.setdefault(source_key, set()).add(dedupe_key)

        return known_by_source

    def update_source_sync_state(
        self,
        source: SourceItem,
        raw_items: list[RawItem],
        *,
        fetch_status: str = "ok",
        parse_status: str = "ok",
        error: str | None = None,
        retry_count: int = 0,
    ) -> None:
        now = datetime.now(timezone.utc)
        last_fetched_at = now
        newest_item = max(raw_items, key=lambda item: (item.published_at, item.external_id), default=None)
        last_published_at = newest_item.published_at if newest_item is not None else None
        last_external_id = newest_item.external_id if newest_item is not None else None
        last_item_count = len(raw_items)
        fetch_ok = fetch_status == "ok"
        parse_ok = parse_status == "ok"
        overall_status = "ok" if (fetch_ok and parse_ok) else ("error" if error else parse_status)

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO source_sync_state (
                        source_key,
                        source_title,
                        last_fetched_at,
                        last_successful_fetch_at,
                        last_successful_parse_at,
                        last_published_at,
                        last_external_id,
                        last_item_count,
                        fetch_status,
                        parse_status,
                        fetch_error_count,
                        parse_error_count,
                        consecutive_failures,
                        retry_count,
                        last_status,
                        last_error
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_key) DO UPDATE SET
                        source_title = EXCLUDED.source_title,
                        last_fetched_at = EXCLUDED.last_fetched_at,
                        last_successful_fetch_at = COALESCE(EXCLUDED.last_successful_fetch_at, source_sync_state.last_successful_fetch_at),
                        last_successful_parse_at = COALESCE(EXCLUDED.last_successful_parse_at, source_sync_state.last_successful_parse_at),
                        last_published_at = COALESCE(EXCLUDED.last_published_at, source_sync_state.last_published_at),
                        last_external_id = COALESCE(EXCLUDED.last_external_id, source_sync_state.last_external_id),
                        last_item_count = EXCLUDED.last_item_count,
                        fetch_status = EXCLUDED.fetch_status,
                        parse_status = EXCLUDED.parse_status,
                        fetch_error_count = CASE
                            WHEN EXCLUDED.fetch_status = 'ok' THEN source_sync_state.fetch_error_count
                            WHEN EXCLUDED.fetch_status = 'error' THEN source_sync_state.fetch_error_count + 1
                            ELSE source_sync_state.fetch_error_count
                        END,
                        parse_error_count = CASE
                            WHEN EXCLUDED.parse_status IN ('ok', 'empty') THEN source_sync_state.parse_error_count
                            WHEN EXCLUDED.parse_status = 'error' THEN source_sync_state.parse_error_count + 1
                            ELSE source_sync_state.parse_error_count
                        END,
                        consecutive_failures = CASE
                            WHEN EXCLUDED.fetch_status = 'ok' AND EXCLUDED.parse_status = 'ok' THEN 0
                            WHEN EXCLUDED.fetch_status = 'ok' AND EXCLUDED.parse_status = 'empty' THEN source_sync_state.consecutive_failures + 1
                            ELSE source_sync_state.consecutive_failures + 1
                        END,
                        retry_count = EXCLUDED.retry_count,
                        last_status = EXCLUDED.last_status,
                        last_error = EXCLUDED.last_error,
                        updated_at = NOW()
                    """,
                    (
                        source.key,
                        source.title,
                        last_fetched_at,
                        now if fetch_ok else None,
                        now if parse_ok else None,
                        last_published_at,
                        last_external_id,
                        last_item_count,
                        fetch_status,
                        parse_status,
                        0,
                        0,
                        0 if (fetch_ok and parse_ok) else 1,
                        retry_count,
                        overall_status,
                        error,
                    ),
                )
            connection.commit()

    def record_source_probe(
        self,
        source: SourceItem,
        *,
        ok: bool,
        item_count: int,
        message: str,
        readiness: str = "unknown",
        preferred_adapter: str | None = None,
        preferred_adapter_url: str | None = None,
        supports_rss: bool = False,
        supports_news_sitemap: bool = False,
        supports_sitemap: bool = False,
        supports_scraping: bool = False,
        full_text_ok: bool = False,
        full_text_method: str | None = None,
        lead_ok: bool = False,
        tags_count: int = 0,
        sample_title: str | None = None,
        sample_url: str | None = None,
    ) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO source_sync_state (
                        source_key,
                        source_title,
                        last_probe_at,
                        last_probe_count,
                        last_probe_readiness,
                        preferred_adapter,
                        preferred_adapter_url,
                        supports_rss,
                        supports_news_sitemap,
                        supports_sitemap,
                        supports_scraping,
                        last_probe_full_text_ok,
                        last_probe_full_text_method,
                        last_probe_lead_ok,
                        last_probe_tags_count,
                        last_probe_sample_title,
                        last_probe_sample_url,
                        last_status,
                        last_error
                    )
                    VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_key) DO UPDATE SET
                        source_title = EXCLUDED.source_title,
                        last_probe_at = EXCLUDED.last_probe_at,
                        last_probe_count = EXCLUDED.last_probe_count,
                        last_probe_readiness = EXCLUDED.last_probe_readiness,
                        preferred_adapter = EXCLUDED.preferred_adapter,
                        preferred_adapter_url = EXCLUDED.preferred_adapter_url,
                        supports_rss = EXCLUDED.supports_rss,
                        supports_news_sitemap = EXCLUDED.supports_news_sitemap,
                        supports_sitemap = EXCLUDED.supports_sitemap,
                        supports_scraping = EXCLUDED.supports_scraping,
                        last_probe_full_text_ok = EXCLUDED.last_probe_full_text_ok,
                        last_probe_full_text_method = EXCLUDED.last_probe_full_text_method,
                        last_probe_lead_ok = EXCLUDED.last_probe_lead_ok,
                        last_probe_tags_count = EXCLUDED.last_probe_tags_count,
                        last_probe_sample_title = EXCLUDED.last_probe_sample_title,
                        last_probe_sample_url = EXCLUDED.last_probe_sample_url,
                        last_status = EXCLUDED.last_status,
                        last_error = EXCLUDED.last_error,
                        updated_at = NOW()
                    """,
                    (
                        source.key,
                        source.title,
                        item_count,
                        readiness,
                        preferred_adapter,
                        preferred_adapter_url,
                        supports_rss,
                        supports_news_sitemap,
                        supports_sitemap,
                        supports_scraping,
                        full_text_ok,
                        full_text_method,
                        lead_ok,
                        tags_count,
                        sample_title,
                        sample_url,
                        "probe_ok" if ok else "probe_error",
                        None if ok else message,
                    ),
                )
            connection.commit()

    @staticmethod
    def _normalize_source_type(value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "ai_search":
            return "ai_research"
        if normalized in {"news-sitemap", "newssitemap"}:
            return "news_sitemap"
        if normalized == "site_map":
            return "sitemap"
        return normalized

    @classmethod
    def _normalize_source_config(cls, source: SourceItem) -> SourceItem:
        normalized_type = cls._normalize_source_type(source.source_type)
        normalized_url = source.url.strip()
        if normalized_type == "ai_research":
            normalized_url = cls._normalize_ai_research_url(normalized_url)
        return SourceItem(
            key=source.key.strip(),
            title=source.title.strip(),
            url=normalized_url,
            category=source.category.strip(),
            source_type=normalized_type,
            status=source.status.strip().lower(),
            notes=source.notes.strip(),
        )

    @staticmethod
    def _validate_source_config(source: SourceItem) -> None:
        key = source.key.strip()
        url = source.url.strip()

        if not key:
            raise ValueError("Source key is required.")
        if not url.startswith(("http://", "https://")):
            raise ValueError("Source URL must start with http:// or https://")
        if source.source_type not in {"rss", "news_sitemap", "sitemap", "scraping", "ai_research"}:
            raise ValueError("Unsupported source type.")
        if source.status not in {"draft", "active", "archived"}:
            raise ValueError("Unsupported source status.")
        if source.status == "active" and source.source_type not in SUPPORTED_ACTIVE_SOURCE_TYPES:
            supported = ", ".join(sorted(SUPPORTED_ACTIVE_SOURCE_TYPES))
            raise ValueError(
                f"Only supported source adapters can be active right now: {supported}."
            )

    def _validate_source_activation_readiness(self, source: SourceItem) -> None:
        if source.status != "active" or source.source_type not in {"scraping", "news_sitemap"}:
            return

        state = self.get_source_sync_state_map().get(source.key)
        if state is None or state.last_probe_at is None:
            raise ValueError("Перед активацией источника сначала запустите Проверить.")
        if state.last_probe_readiness in {"unknown", "empty", "fetch_error"}:
            source_label = {
                "news_sitemap": "News sitemap",
            }.get(source.source_type, "Scraping")
            raise ValueError(
                f"{source_label}-источник можно переводить в active только после успешного preflight, "
                "когда источник действительно возвращает новости."
            )

