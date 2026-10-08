from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from psycopg_pool import ConnectionPool
from .config import get_database_url
from .repository_support import _reset_pooled_connection

class DatabaseRepository:
    def __init__(self) -> None:
        self.database_url = get_database_url()
        self._pool: ConnectionPool | None = None
        self._pool_lock = threading.Lock()

    def _get_pool(self) -> ConnectionPool:
        with self._pool_lock:
            if self._pool is None:
                maximum = int(os.getenv("EZBET_DB_POOL_MAX", "12"))
                if not 8 <= maximum <= 64:
                    raise ValueError("EZBET_DB_POOL_MAX must be between 8 and 64.")
                self._pool = ConnectionPool(
                    self.database_url, min_size=0, max_size=maximum,
                    open=False, timeout=10, max_waiting=64, max_idle=60,
                    max_lifetime=1800, reconnect_timeout=30,
                    kwargs={"connect_timeout": 10},
                    check=ConnectionPool.check_connection,
                    reset=_reset_pooled_connection,
                )
                self._pool.open()
            return self._pool

    @contextmanager
    def connect(self):
        with self._get_pool().connection() as connection:
            yield connection

    def close_pool(self) -> None:
        with self._pool_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def pool_stats(self) -> dict[str, int]:
        return self._get_pool().get_stats()


    def ensure_schema(self) -> None:
        """Compatibility entry point for explicit setup and isolated tests."""
        from .migrations import migrate
        with self.connect() as connection:
            migrate(connection)
