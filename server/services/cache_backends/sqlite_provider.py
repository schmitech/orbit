"""
SQLite Cache Provider
======================

SQLite-backed implementation of CacheProvider. Requires no external service - it's
the zero-config default for self-hosted deployments that haven't set up Redis or
Memcached. Persists across restarts (unlike the in-memory fallbacks scattered across
individual consumers) at the cost of disk-backed writes instead of an in-memory
round trip.

Uses its own connection/file, separate from the SQLite backend database
(internal_services.backend.sqlite) so cache write volume doesn't contend with
application data (users, audit logs, etc.).

Known limitations vs. Redis:
- Slower under high write throughput (e.g. per-request rate limiting/quota counters)
  since every write is a disk-backed transaction, even with WAL mode.
- No TTL introspection beyond what's stored - ttl() computes remaining time from the
  stored expiry, same precision as Redis.
- Multi-process safety (multiple `performance.workers`) relies on SQLite's own file
  locking; set_if_not_exists()/increment_with_ttl() use BEGIN IMMEDIATE transactions
  to make the read-then-write atomic across processes, not just threads.
"""

import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import CacheProvider, CircuitBreaker, is_cache_master_enabled

logger = logging.getLogger(__name__)


class SqliteCacheProvider(CacheProvider):
    """Cache provider backed by a dedicated SQLite database file."""

    _instances: Dict[str, 'SqliteCacheProvider'] = {}
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any]):
        cache_key = cls._create_cache_key(config)

        with cls._lock:
            if cache_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
                logger.debug(f"Created new SQLite cache provider instance for: {cache_key}")
            return cls._instances[cache_key]

    @classmethod
    def _create_cache_key(cls, config: Dict[str, Any]) -> str:
        sqlite_config = config.get('internal_services', {}).get('sqlite_cache', {})
        return f"sqlite_cache:{sqlite_config.get('database_path', 'orbit_cache.db')}"

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached SqliteCacheProvider instances (mainly for testing)"""
        with cls._lock:
            cls._instances.clear()

    def __init__(self, config: Dict[str, Any]):
        if hasattr(self, '_singleton_initialized'):
            return

        self.config = config
        self.sqlite_config = config.get('internal_services', {}).get('sqlite_cache', {})
        # Zero-config default backend - no external service to opt into, so it's
        # enabled whenever selected via cache.provider and the master switch is on.
        self.enabled = is_cache_master_enabled(config)
        self.database_path = self.sqlite_config.get('database_path', 'orbit_cache.db')
        self.default_ttl = int(self.sqlite_config.get('ttl', 3600))

        self.connection: Optional[sqlite3.Connection] = None
        self.initialized = False
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='sqlite_cache_')
        self._db_lock = threading.Lock()

        max_failures = self.sqlite_config.get('max_consecutive_failures', 5)
        recovery_timeout = self.sqlite_config.get('circuit_recovery_timeout', 30)
        self._circuit_breaker = CircuitBreaker(
            max_failures=max_failures,
            recovery_timeout=recovery_timeout
        )

        self._singleton_initialized = True

    def _is_available(self) -> bool:
        return self.enabled and self.connection is not None and not self._circuit_breaker.is_open

    def _handle_error(self, operation: str, error: Exception) -> None:
        self._circuit_breaker.record_failure()
        if self._circuit_breaker.is_open:
            logger.warning(f"SQLite cache circuit breaker open after {operation} error: {error}")
        else:
            logger.debug(f"SQLite cache error during {operation}: {error}")

    async def initialize(self) -> bool:
        if self.initialized:
            return True

        if not self.enabled:
            logger.warning(
                "Caching is disabled (internal_services.cache.enabled=false) - SQLite cache will not initialize"
            )
            return False

        try:
            loop = self._loop()
            await loop.run_in_executor(self.executor, self._connect_and_create_schema)
            logger.info(f"Successfully connected to SQLite cache at {self.database_path}")

            cache_config = self.config.get("internal_services", {}).get("cache", {})
            if cache_config.get("clear_cache_on_startup", True):
                await self.clear_all_application_cache()
            else:
                logger.debug("Cache clearing on startup is disabled")

            self.initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize SQLite cache: {str(e)}")
            self.enabled = False
            self.connection = None
            self.initialized = False
            return False

    def _connect_and_create_schema(self) -> None:
        """Connect to the cache database and create its schema (runs in executor thread)."""
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.database_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_kv_expires_at ON cache_kv(expires_at)")
        conn.commit()
        self.connection = conn

    def _loop(self):
        import asyncio
        return asyncio.get_running_loop()

    async def _run(self, func, *args):
        loop = self._loop()
        return await loop.run_in_executor(self.executor, func, *args)

    # -- synchronous helpers, always called via self._run() from an async method --

    def _get_sync(self, key: str) -> Optional[str]:
        now = time.time()
        with self._db_lock:
            cur = self.connection.cursor()
            cur.execute("SELECT value, expires_at FROM cache_kv WHERE key = ?", (key,))
            row = cur.fetchone()
            if row is None:
                return None
            value, expires_at = row
            if expires_at is not None and expires_at <= now:
                cur.execute("DELETE FROM cache_kv WHERE key = ?", (key,))
                self.connection.commit()
                return None
            return value

    def _set_sync(self, key: str, value: str, ttl: Optional[int]) -> bool:
        ttl_to_use = ttl if ttl is not None else self.default_ttl
        expires_at = time.time() + ttl_to_use if ttl_to_use else None
        with self._db_lock:
            self.connection.execute(
                "INSERT OR REPLACE INTO cache_kv (key, value, expires_at) VALUES (?, ?, ?)",
                (key, value, expires_at)
            )
            self.connection.commit()
        return True

    def _delete_sync(self, keys: tuple) -> int:
        with self._db_lock:
            placeholders = ','.join(['?'] * len(keys))
            cur = self.connection.execute(
                f"DELETE FROM cache_kv WHERE key IN ({placeholders})", keys
            )
            self.connection.commit()
            return cur.rowcount

    def _ttl_sync(self, key: str) -> int:
        now = time.time()
        with self._db_lock:
            cur = self.connection.cursor()
            cur.execute("SELECT expires_at FROM cache_kv WHERE key = ?", (key,))
            row = cur.fetchone()
            if row is None:
                return -2
            expires_at = row[0]
            if expires_at is None:
                return -1
            remaining = int(expires_at - now)
            if remaining <= 0:
                cur.execute("DELETE FROM cache_kv WHERE key = ?", (key,))
                self.connection.commit()
                return -2
            return remaining

    def _expire_sync(self, key: str, seconds: int) -> bool:
        with self._db_lock:
            cur = self.connection.execute(
                "UPDATE cache_kv SET expires_at = ? WHERE key = ?",
                (time.time() + seconds, key)
            )
            self.connection.commit()
            return cur.rowcount > 0

    def _mget_sync(self, keys: tuple) -> List[Optional[str]]:
        now = time.time()
        with self._db_lock:
            placeholders = ','.join(['?'] * len(keys))
            cur = self.connection.execute(
                f"SELECT key, value, expires_at FROM cache_kv WHERE key IN ({placeholders})", keys
            )
            rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        result = []
        for key in keys:
            entry = rows.get(key)
            if entry is None:
                result.append(None)
            else:
                value, expires_at = entry
                result.append(None if (expires_at is not None and expires_at <= now) else value)
        return result

    def _mset_sync(self, mapping: Dict[str, str]) -> bool:
        expires_at = time.time() + self.default_ttl if self.default_ttl else None
        with self._db_lock:
            self.connection.executemany(
                "INSERT OR REPLACE INTO cache_kv (key, value, expires_at) VALUES (?, ?, ?)",
                [(k, v, expires_at) for k, v in mapping.items()]
            )
            self.connection.commit()
        return True

    def _set_if_not_exists_sync(self, key: str, value: str, ttl: int) -> bool:
        now = time.time()
        expires_at = now + ttl if ttl else None
        with self._db_lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                cur = self.connection.execute(
                    "SELECT expires_at FROM cache_kv WHERE key = ?", (key,)
                )
                row = cur.fetchone()
                if row is not None and (row[0] is None or row[0] > now):
                    self.connection.rollback()
                    return False

                self.connection.execute(
                    "INSERT OR REPLACE INTO cache_kv (key, value, expires_at) VALUES (?, ?, ?)",
                    (key, value, expires_at)
                )
                self.connection.commit()
                return True
            except Exception:
                self.connection.rollback()
                raise

    def _increment_with_ttl_sync(self, key: str, ttl: int, amount: int) -> int:
        now = time.time()
        with self._db_lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                cur = self.connection.execute(
                    "SELECT value, expires_at FROM cache_kv WHERE key = ?", (key,)
                )
                row = cur.fetchone()

                if row is not None and (row[1] is None or row[1] > now):
                    try:
                        count = int(row[0]) + amount
                    except (TypeError, ValueError):
                        count = amount
                    self.connection.execute(
                        "UPDATE cache_kv SET value = ? WHERE key = ?", (str(count), key)
                    )
                else:
                    count = amount
                    self.connection.execute(
                        "INSERT OR REPLACE INTO cache_kv (key, value, expires_at) VALUES (?, ?, ?)",
                        (key, str(count), now + ttl)
                    )

                self.connection.commit()
                return count
            except Exception:
                self.connection.rollback()
                raise

    def _check_and_increment_sync(
        self,
        checks: List[Tuple[str, str, int, Optional[int]]],
        amount: int,
    ) -> Tuple[Dict[str, int], Optional[str]]:
        """Check all counters against their limits and increment all of them (or
        none) in a single BEGIN IMMEDIATE transaction - atomic across processes."""
        now = time.time()
        with self._db_lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                current_counts: Dict[str, int] = {}
                is_fresh: Dict[str, bool] = {}
                exceeded_name: Optional[str] = None
                for name, key, _ttl, limit in checks:
                    cur = self.connection.execute(
                        "SELECT value, expires_at FROM cache_kv WHERE key = ?", (key,)
                    )
                    row = cur.fetchone()
                    valid_row = row is not None and (row[1] is None or row[1] > now)
                    if valid_row:
                        try:
                            current = int(row[0])
                        except (TypeError, ValueError):
                            current = 0
                    else:
                        current = 0
                    current_counts[name] = current
                    is_fresh[name] = not valid_row  # missing, or expired -> needs a fresh row + new TTL
                    if exceeded_name is None and limit is not None and current + amount > limit:
                        exceeded_name = name

                if exceeded_name is not None:
                    self.connection.rollback()
                    return current_counts, exceeded_name

                new_counts: Dict[str, int] = {}
                for name, key, ttl, _limit in checks:
                    new_count = current_counts[name] + amount
                    if is_fresh[name]:
                        self.connection.execute(
                            "INSERT OR REPLACE INTO cache_kv (key, value, expires_at) VALUES (?, ?, ?)",
                            (key, str(new_count), now + ttl)
                        )
                    else:
                        self.connection.execute(
                            "UPDATE cache_kv SET value = ? WHERE key = ?", (str(new_count), key)
                        )
                    new_counts[name] = new_count

                self.connection.commit()
                return new_counts, None
            except Exception:
                self.connection.rollback()
                raise

    def _clear_by_pattern_sync(self, like_pattern: str) -> int:
        with self._db_lock:
            cur = self.connection.execute(
                "DELETE FROM cache_kv WHERE key LIKE ? ESCAPE '\\'", (like_pattern,)
            )
            self.connection.commit()
            return cur.rowcount

    @staticmethod
    def _to_like_pattern(pattern: str) -> str:
        """Translate a 'prefix:*' glob pattern into a SQL LIKE pattern."""
        escaped = pattern.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        return escaped.replace('*', '%')

    # -- CacheProvider interface --

    async def get(self, key: str) -> Optional[str]:
        if not self._is_available():
            return None
        try:
            result = await self._run(self._get_sync, key)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error getting key {key} from SQLite cache: {str(e)}")
            self._handle_error("get", e)
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        if not self._is_available():
            return False
        try:
            result = await self._run(self._set_sync, key, value, ttl)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error setting key {key} in SQLite cache: {str(e)}")
            self._handle_error("set", e)
            return False

    async def delete(self, *keys: str) -> int:
        if not self._is_available() or not keys:
            return 0
        try:
            result = await self._run(self._delete_sync, tuple(keys))
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error deleting keys {keys} from SQLite cache: {str(e)}")
            self._handle_error("delete", e)
            return 0

    async def exists(self, key: str) -> bool:
        if not self._is_available():
            return False
        try:
            result = await self._run(self._get_sync, key)
            self._circuit_breaker.record_success()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking if key {key} exists in SQLite cache: {str(e)}")
            self._handle_error("exists", e)
            return False

    async def ttl(self, key: str) -> int:
        if not self._is_available():
            return -2
        try:
            result = await self._run(self._ttl_sync, key)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error getting TTL for key {key} in SQLite cache: {str(e)}")
            self._handle_error("ttl", e)
            return -2

    async def expire(self, key: str, seconds: int) -> bool:
        if not self._is_available():
            return False
        try:
            result = await self._run(self._expire_sync, key, seconds)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error setting expiration for key {key} in SQLite cache: {str(e)}")
            self._handle_error("expire", e)
            return False

    async def mget(self, *keys: str) -> List[Optional[str]]:
        if not self._is_available() or not keys:
            return [None] * len(keys)
        try:
            result = await self._run(self._mget_sync, tuple(keys))
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error in mget for {len(keys)} keys: {str(e)}")
            self._handle_error("mget", e)
            return [None] * len(keys)

    async def mset(self, mapping: Dict[str, str]) -> bool:
        if not self._is_available() or not mapping:
            return False
        try:
            result = await self._run(self._mset_sync, mapping)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error in mset for {len(mapping)} keys: {str(e)}")
            self._handle_error("mset", e)
            return False

    async def set_if_not_exists(self, key: str, value: str, ttl: int) -> bool:
        if not self._is_available():
            return False
        try:
            result = await self._run(self._set_if_not_exists_sync, key, value, ttl)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error in set_if_not_exists for key {key} in SQLite cache: {str(e)}")
            self._handle_error("set_if_not_exists", e)
            return False

    async def increment_with_ttl(self, key: str, ttl: int, amount: int = 1) -> int:
        if not self._is_available():
            return 0
        try:
            result = await self._run(self._increment_with_ttl_sync, key, ttl, amount)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error in increment_with_ttl for key {key} in SQLite cache: {str(e)}")
            self._handle_error("increment_with_ttl", e)
            return 0

    async def check_and_increment(
        self,
        checks: List[Tuple[str, str, int, Optional[int]]],
        amount: int = 1,
    ) -> Tuple[Dict[str, int], Optional[str]]:
        if not checks:
            return {}, None
        if not self._is_available():
            return await super().check_and_increment(checks, amount)
        try:
            result = await self._run(self._check_and_increment_sync, checks, amount)
            self._circuit_breaker.record_success()
            return result
        except Exception as e:
            logger.error(f"Error in check_and_increment in SQLite cache: {str(e)}")
            self._handle_error("check_and_increment", e)
            return await super().check_and_increment(checks, amount)

    async def clear_by_pattern(self, pattern: str, description: str = "") -> int:
        if not self._is_available():
            return 0
        try:
            like_pattern = self._to_like_pattern(pattern)
            result = await self._run(self._clear_by_pattern_sync, like_pattern)
            self._circuit_breaker.record_success()
            if result:
                logger.debug(f"Cleared {result} {description or pattern} entries from SQLite cache")
            return result
        except Exception as e:
            logger.warning(f"Failed to clear {description or pattern} from SQLite cache: {str(e)}")
            self._handle_error("clear_by_pattern", e)
            return 0

    def get_health_stats(self) -> Dict[str, Any]:
        return {
            "provider": "sqlite",
            "enabled": self.enabled,
            "initialized": self.initialized,
            "circuit_breaker": {
                "state": self._circuit_breaker.state,
                "failure_count": self._circuit_breaker.failure_count,
                "max_failures": self._circuit_breaker.max_failures,
            },
            "database_path": self.database_path,
        }

    async def close(self) -> None:
        if self.connection:
            def _close():
                with self._db_lock:
                    self.connection.close()
            await self._run(_close)
            self.connection = None
            self.initialized = False
