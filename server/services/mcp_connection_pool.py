"""
MCP Connection Pool

Per-server connection pooling and circuit-breaking for MCP client sessions,
split out of mcp_client_service.py so that file can stay focused on tool
discovery/caching and mcp_client_service.py's own settings resolution.

ServerConnectionPool is the single choke point every caller (discovery,
tool calls) goes through via `run()`: circuit-breaker gating, connection
acquisition/release, and success/failure recording all happen in one place,
so no call site can forget a step or apply them inconsistently. Set
`pool_size` to 0 to disable pooling for a server — `run()` then builds and
tears down a one-shot connection per call instead of keeping any idle.
"""

import asyncio
import time
from typing import Any, Optional
from collections.abc import Awaitable, Callable

from services.cache_backends.base import CircuitBreaker


class MCPConnection:
    """A live, initialized MCP session plus the exit stack that tears down
    its transport (subprocess or HTTP client) when closed."""

    def __init__(self, session: Any, stack: Any):
        self.session = session
        self.stack = stack
        now = time.monotonic()
        self.created_at = now
        self.last_used_at = now
        self.in_use = False
        self.closing = False

    async def close(self) -> None:
        await self.stack.aclose()


class ServerConnectionPool:
    """Bounds concurrent live connections to one MCP server, reuses idle ones
    across calls, and gates every attempt on a circuit breaker.

    `max_size` also bounds the number of connections ever created
    concurrently (via the semaphore), not just how many may sit idle.
    """

    def __init__(self, pool_size: int, idle_timeout: int, breaker_recovery_timeout: int):
        self.pool_size = pool_size
        self.idle_timeout = idle_timeout
        self._breaker_recovery_timeout = breaker_recovery_timeout
        self.breaker = CircuitBreaker(max_failures=1, recovery_timeout=breaker_recovery_timeout)
        self._idle: list[MCPConnection] = []
        # Membership set for O(1) discard on release/drain, not iteration order.
        self._all: set = set()
        self._semaphore = asyncio.Semaphore(max(pool_size, 1))
        self._lock = asyncio.Lock()
        # Set by drain(): a caller already waiting on the semaphore when
        # drain() runs can still acquire it afterward and build a brand new
        # connection. Without this flag that connection would be returned to
        # this (already discarded) pool's idle list and never get drained.
        self._draining = False

    def reset_breaker(self) -> None:
        """Start a fresh breaker without disturbing pooled connections —
        used when only discovery/retry state should reset (a config change
        that also invalidates live connections should call drain() instead)."""
        self.breaker = CircuitBreaker(max_failures=1, recovery_timeout=self._breaker_recovery_timeout)

    async def run(
        self,
        build: Callable[[], Awaitable[MCPConnection]],
        op: Callable[[Any], Awaitable[Any]],
        retries: int = 0,
    ) -> Any:
        """Run `op(session)` against a connection from `build()`.

        Gated by the circuit breaker up front (fails fast without attempting
        a connection when open). On failure, retries up to `retries` extra
        times, rebuilding the connection each time — tool calls and discovery
        both pass retries=1 for one transparent retry.
        """
        if self.breaker.is_open:
            raise RuntimeError(
                "MCP server is temporarily unavailable (circuit open after a recent connection failure)"
            )
        last_exc: Optional[Exception] = None
        for _attempt in range(retries + 1):
            try:
                conn = await self._acquire(build)
            except BaseException as exc:
                # Record even a cancelled acquire (e.g. cancelled while
                # waiting on the semaphore) so an outer timeout still marks
                # the server failed instead of silently never tripping the
                # breaker; not swallowed into a retry — see the same
                # reasoning below.
                self.breaker.record_failure()
                if not isinstance(exc, Exception):
                    raise
                last_exc = exc
                continue
            try:
                result = await op(conn.session)
            except BaseException as exc:
                # BaseException (not just Exception) so a cancelled/timed-out
                # call still releases the connection instead of leaking its
                # pool permit, which would exhaust the pool after pool_size
                # timeouts. The breaker is recorded either way — including
                # for cancellation — so an outer wait_for timeout (e.g.
                # discovery_timeout) still throttles retries against a
                # hanging server; only Exception is retried, a cancellation
                # is re-raised immediately rather than swallowed into a
                # retry loop.
                await self._release(conn, healthy=False)
                self.breaker.record_failure()
                if not isinstance(exc, Exception):
                    raise
                last_exc = exc
                continue
            self.breaker.record_success()
            await self._release(conn, healthy=True)
            return result
        raise last_exc

    async def _acquire(self, build: Callable[[], Awaitable[MCPConnection]]) -> MCPConnection:
        if self.pool_size <= 0:
            return await build()

        await self._semaphore.acquire()
        try:
            async with self._lock:
                now = time.monotonic()
                while self._idle:
                    conn = self._idle.pop()
                    if self.idle_timeout and (now - conn.last_used_at) > self.idle_timeout:
                        self._all.discard(conn)
                        await conn.close()
                        continue
                    conn.in_use = True
                    return conn
                conn = await build()
                conn.in_use = True
                if self._draining:
                    # This pool was already drained (e.g. dropped from the
                    # manager by update_server) while this caller was still
                    # waiting on the semaphore. Don't hand out a connection
                    # that looks poolable — flag it so release() closes it
                    # instead of adding it back to a pool nothing will ever
                    # drain again.
                    conn.closing = True
                else:
                    self._all.add(conn)
                return conn
        except BaseException:
            self._semaphore.release()
            raise

    async def _release(self, conn: MCPConnection, healthy: bool) -> None:
        if self.pool_size <= 0:
            await conn.close()
            return
        try:
            async with self._lock:
                conn.in_use = False
                conn.last_used_at = time.monotonic()
                if healthy and not conn.closing:
                    self._idle.append(conn)
                else:
                    self._all.discard(conn)
                    await conn.close()
        finally:
            self._semaphore.release()

    async def drain(self) -> None:
        """Close every idle connection and flag in-flight ones to close on
        release instead of returning to idle. Does not block on in-flight
        callers finishing — they tear their own connection down."""
        async with self._lock:
            self._draining = True
            to_close, self._idle = self._idle, []
            for conn in to_close:
                self._all.discard(conn)
            await asyncio.gather(*(c.close() for c in to_close), return_exceptions=True)
            for conn in self._all:
                conn.closing = True
