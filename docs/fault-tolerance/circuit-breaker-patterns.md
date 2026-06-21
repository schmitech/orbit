# Circuit Breaker Patterns in ORBIT

This document describes ORBIT's circuit breaker implementation and outlines extension patterns that are not yet implemented. **Read the "Current ORBIT Implementation" section for anything you are deploying or operating. The "Extension Patterns" section contains design ideas for future contributors.**

---

## Current ORBIT Implementation

The circuit breaker lives in `server/services/parallel_adapter_executor.py`. All behavior described in this section reflects the running code.

### Core Components

#### CircuitState

```python
class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation — all calls pass through
    OPEN = "open"           # Fast-failing — calls are rejected immediately
    HALF_OPEN = "half_open" # Cautious probing — limited calls allowed through
```

#### CircuitBreakerStats

Tracks operational metrics used for transition decisions and monitoring. Protected by an internal `threading.Lock`.

```python
@dataclass
class CircuitBreakerStats:
    failure_count: int = 0
    success_count: int = 0
    timeout_calls: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    # Time-series data (capped at max_history_size / max_transitions_size)
    call_history: List[Dict[str, Any]] = ...
    state_transitions: List[Dict[str, Any]] = ...
```

#### SimpleCircuitBreaker

```python
class SimpleCircuitBreaker:
    def __init__(
        self,
        adapter_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 3,
        max_recovery_timeout: float = 300.0,
        enable_exponential_backoff: bool = True,
        cleanup_interval: float = 3600.0,
        retention_period: float = 86400.0,
        max_history_size: int = 10000,
        max_transitions_size: int = 1000,
        event_handler: Optional[CircuitBreakerEventHandler] = None,
        max_half_open_calls: int = 1,
    ): ...
```

Key instance state protected by `self._lock` (a `threading.RLock`):
- `state` — current `CircuitState`
- `recovery_attempts` / `current_recovery_timeout` — exponential backoff tracking
- `_half_open_probes` — number of in-flight HALF_OPEN probes (gated by `max_half_open_calls`)
- `stats` — `CircuitBreakerStats` instance

### State Transition Logic

#### CLOSED → OPEN

The circuit opens when `consecutive_failures >= failure_threshold`. Recovery timeout is calculated using exponential backoff with jitter (up to `max_recovery_timeout`).

#### OPEN → HALF_OPEN

`is_open()` checks `time.time() - _state_changed_at >= current_recovery_timeout`. When elapsed, it calls `_transition_to_half_open()` which resets `_half_open_probes = 0`.

#### HALF_OPEN probe gating

When a request enters `_execute_single_adapter()` while the circuit is HALF_OPEN, it calls `_claim_half_open_slot()`:
- If `_half_open_probes < max_half_open_calls`, the probe is allowed and `_half_open_probes` is incremented.
- If `_half_open_probes >= max_half_open_calls`, the call is fast-failed with *"Circuit is half-open and probe limit reached"*.
- `_half_open_probes` is decremented in both `record_success()` and `record_failure()` when called from HALF_OPEN.

#### HALF_OPEN → CLOSED

After `consecutive_successes >= success_threshold` in HALF_OPEN, `_close_circuit()` is called. Backoff is reset to `base_recovery_timeout`.

#### HALF_OPEN → OPEN

A single failure in HALF_OPEN calls `_open_circuit()` again, incrementing `recovery_attempts` for the next backoff calculation.

### Event Dispatch

Transition methods (`_open_circuit`, `_close_circuit`, `_transition_to_half_open`, `reset`) fire async event callbacks through `_emit_event(coro_factory)`. This helper:
1. Attempts `asyncio.get_running_loop().create_task(coro_factory())`.
2. If no loop is running (sync test, admin code, shutdown path), logs a DEBUG message and returns — it never raises from the breaker state transition.
3. Catches and logs any other dispatch error, again without affecting state.

Available event handler types (configured per adapter via `event_handler.type`):
- `default` — logs events to the ORBIT logger.
- `monitoring` — logs plus calls up to three async callbacks: `alert_callback`, `dashboard_callback`, `metrics_callback`.
- `custom` — loads a class from a dotted import path (restricted to trusted deployments; see monitoring config docs).

### Reset Semantics

`SimpleCircuitBreaker.reset()` (called by `ParallelAdapterExecutor.reset_circuit_breaker()`):
- Sets state to CLOSED.
- Replaces `stats` with a fresh `CircuitBreakerStats` (clears all history and counters).
- Resets `recovery_attempts = 0` and `current_recovery_timeout = base_recovery_timeout`.
- Resets `_half_open_probes = 0`.
- Emits `on_circuit_reset` (not `on_circuit_close`).

### Timeout Allocation

`_execute_single_adapter()` splits `operation_timeout` into two fixed budgets:
- **30%** for adapter lookup/initialization (`asyncio.wait_for(..., timeout=adapter_timeout * 0.3)`).
- **70%** for query execution (`asyncio.wait_for(..., timeout=adapter_timeout * 0.7)`).

A 30 s `operation_timeout` means the query must finish within 21 s. Set `operation_timeout` with this split in mind.

### Execution Strategy

`execute_adapters()` currently implements the `all` strategy: all available adapters (those whose circuits are not OPEN) run in parallel batches using `asyncio.gather`. The `execution.strategy` config key is read but has no effect on the current path — see Extension Patterns below.

### Memory Management

`CircuitBreakerStats` caps `call_history` at `max_history_size` (default 10 000) and `state_transitions` at `max_transitions_size` (default 1 000). Periodic cleanup removes records older than `retention_period` (default 24 h) on a `cleanup_interval` timer (default 1 h). `force_cleanup()` runs cleanup immediately.

### Thread Safety

`SimpleCircuitBreaker` uses a `threading.RLock` (`self._lock`) to serialize all state mutations, counter updates, and transition checks. `CircuitBreakerStats` has its own `threading.Lock` protecting `call_history` and `state_transitions`. Event dispatch (`_emit_event`) happens while the breaker lock is held but is non-blocking (`loop.create_task` schedules the coroutine without waiting for it).

### Configuration Reference

```yaml
fault_tolerance:
  circuit_breaker:
    failure_threshold: 5          # Consecutive failures before OPEN
    recovery_timeout: 60.0        # Base recovery wait (seconds); backoff multiplies this
    success_threshold: 3          # Consecutive successes in HALF_OPEN before CLOSED
    max_recovery_timeout: 300.0   # Backoff ceiling
    enable_exponential_backoff: true
    max_half_open_calls: 1        # Max concurrent HALF_OPEN probes per adapter
    cleanup_interval: 3600.0      # How often to prune old records (seconds)
    retention_period: 86400.0     # How long to keep records (seconds)
    max_history_size: 10000       # Cap on call_history list length
    max_transitions_size: 1000    # Cap on state_transitions list length
```

All keys can be overridden per adapter under `adapters[n].fault_tolerance`.

---

## Extension Patterns (not yet implemented)

The patterns in this section have not been built into ORBIT. They are included as design references for contributors. Do not configure or operate ORBIT as if these patterns are active.

### Sliding Window Failure Detection

Rather than counting consecutive failures, open the circuit when the failure *rate* over a recent window exceeds a threshold:

```python
class SlidingWindowCircuitBreaker(SimpleCircuitBreaker):
    def __init__(self, adapter_name: str, window_size: int = 10,
                 failure_rate_threshold: float = 0.5, **kwargs):
        super().__init__(adapter_name, **kwargs)
        self.window_size = window_size
        self.failure_rate_threshold = failure_rate_threshold
        self.recent_calls = deque(maxlen=window_size)

    def should_open_circuit(self) -> bool:
        if len(self.recent_calls) < self.window_size:
            return False
        failure_rate = sum(1 for call in self.recent_calls if not call) / len(self.recent_calls)
        return failure_rate >= self.failure_rate_threshold
```

### Adaptive Timeouts

Adjust per-adapter timeouts based on recent p95 response times:

```python
class AdaptiveTimeoutCircuitBreaker(SimpleCircuitBreaker):
    def __init__(self, adapter_name: str, **kwargs):
        super().__init__(adapter_name, **kwargs)
        self.response_times = deque(maxlen=100)
        self.base_timeout = 30.0

    def get_adaptive_timeout(self) -> float:
        if not self.response_times:
            return self.base_timeout
        p95 = sorted(self.response_times)[int(len(self.response_times) * 0.95)]
        return max(self.base_timeout, p95 * 2)
```

### Bulkhead Pattern

Limit concurrent in-flight calls per adapter independently of circuit state:

```python
class BulkheadCircuitBreaker(SimpleCircuitBreaker):
    def __init__(self, adapter_name: str, max_concurrent_calls: int = 5, **kwargs):
        super().__init__(adapter_name, **kwargs)
        self.semaphore = asyncio.Semaphore(max_concurrent_calls)

    async def execute_with_bulkhead(self, func, *args, **kwargs):
        if self.is_open():
            raise Exception(f"Circuit open for {self.adapter_name}")
        async with self.semaphore:
            try:
                result = await func(*args, **kwargs)
                self.record_success()
                return result
            except Exception:
                self.record_failure()
                raise
```

### first_success and best_effort Strategies

The executor has helper methods `_execute_first_success_strategy` and `_execute_best_effort_strategy` but these are not wired into `execute_adapters()`. To implement:
- `first_success`: dispatch from `execute_adapters()` based on `self.execution_strategy`; cancel remaining tasks on first success; ensure `record_failure` is still called for cancelled tasks if that is the desired semantics.
- `best_effort`: collect completed tasks up to a shorter deadline; cancel pending tasks; return partial results.

### Prometheus Metrics Integration

Extend `MonitoringCircuitBreakerEventHandler` to emit Prometheus counters, gauges, and histograms via the `metrics_callback`. This keeps metrics out of the breaker core and composable with any monitoring backend.
