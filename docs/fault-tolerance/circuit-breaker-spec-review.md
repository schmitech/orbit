# ORBIT Circuit Breaker Spec and Design Review

## Summary

This review covers the circuit breaker design described in `docs/fault-tolerance/circuit-breaker-patterns.md`, the operator cookbook in `docs/cookbook/orbit-fault-tolerance-circuit-breakers.md`, and the event tests in `server/tests/fault_tolerance/test_circuit_breaker_events.py`, checked against the current implementation in `server/services/parallel_adapter_executor.py`.

The implementation has the right basic shape: per-adapter breakers, closed/open/half-open states, timeout accounting, state-transition events, adapter-level overrides, exponential recovery timeout, and capped history. The main risks are around concurrency safety, async event dispatch from synchronous methods, half-open probe control, and documentation that overstates or diverges from runtime behavior.

## Key Findings

### 1. Event callbacks can fail outside a running event loop

`SimpleCircuitBreaker` transition methods call `asyncio.create_task(...)` directly from synchronous methods such as `_open_circuit()`, `_close_circuit()`, `_transition_to_half_open()`, and `reset()`. That is fine in the current async event tests because a running loop exists, but the breaker API itself is synchronous and can be called from sync tests, admin code, shutdown paths, thread-pool callbacks, or future management endpoints.

Impact: calling `record_failure()`, `record_success()`, or `reset()` outside a running event loop can raise `RuntimeError: no running event loop`, turning a monitoring side effect into a circuit-breaker failure path.

Recommendation: centralize event dispatch in a helper that detects whether a running loop exists. Either schedule on the loop when available, run through a configured background dispatcher, or make transition methods async and require callers to await them. Event handler failures should remain isolated from breaker state transitions.

### 2. Thread safety is incomplete

`CircuitBreakerStats` protects `call_history` and `state_transitions` with an internal lock, but the breaker mutates and reads core state without one shared critical section: `state`, `_state_changed_at`, `recovery_attempts`, `current_recovery_timeout`, total counters, consecutive counters, and timestamps.

Impact: concurrent adapter calls can produce lost counter updates, stale state checks, duplicated transitions, inconsistent status snapshots, or multiple opens/closes racing with each other. This matters because the executor runs adapters concurrently and can also execute synchronous adapter work in a thread pool.

Recommendation: add a breaker-level lock and use it around state checks, counter updates, transition decisions, and status snapshots. Keep event dispatch outside the lock after capturing an immutable status snapshot.

### 3. Half-open recovery is not probe-gated

When an open breaker exceeds `current_recovery_timeout`, `is_open()` transitions it to `HALF_OPEN` and returns `False`. There is no limit on how many concurrent requests may pass through while half-open. Under load, many calls can hit a recovering dependency at once.

Impact: a recovering adapter can be flooded exactly when the circuit should be cautiously probing. One failure reopens the circuit, but other in-flight probes may still be running and can distort stats or create load spikes.

Recommendation: add a `max_half_open_calls` setting, defaulting to `1`, and track in-flight half-open probes. Reject or fast-fail additional probes until the current probe succeeds or fails. If multiple probes are desired, make that explicit per adapter.

### 4. Reset behavior does not match the reset API or docs

`ParallelAdapterExecutor.reset_circuit_breaker()` calls the private `_close_circuit()` method instead of `SimpleCircuitBreaker.reset()`. `_close_circuit()` closes the circuit and resets backoff, but it does not clear stats/history and emits a close event rather than a reset event.

Impact: an operator reset may leave old failures, call history, and transition history in place. Monitoring consumers will also see a close event rather than a reset event, which weakens incident auditability.

Recommendation: change executor reset to call `cb.reset()`. Document reset semantics explicitly: state becomes closed, counters/history are cleared, backoff is reset, and a reset event is emitted.

### 5. Execution strategy documentation overstates current behavior

The cookbook documents `all`, `first_success`, and `best_effort` strategies. The executor has helper methods for strategy-specific behavior, but `execute_adapters()` currently filters open circuits, batches available adapters, and always awaits all tasks in each batch with `asyncio.gather(...)`.

Impact: operators may choose `first_success` expecting lower latency and cancellation of slower adapters, but runtime behavior still waits for all adapters in the batch. `best_effort` is similarly documented as a distinct behavior without being used by the main path.

Recommendation: either wire `execution.strategy` into `execute_adapters()` or narrow the docs to the implemented `all` behavior. If strategies are kept, add integration tests that prove cancellation, partial result behavior, and circuit-breaker recording are correct for each strategy.

### 6. Timeout semantics are surprising and under-documented

The cookbook presents `execution.timeout` and adapter `operation_timeout` as operation-level limits. The implementation splits adapter timeout into 30% for adapter lookup/initialization and 70% for query execution.

Impact: a query can time out after 70% of the configured timeout even though operators configured a larger value. Conversely, slow adapter lookup receives only 30% of the configured value. This may be correct, but it is not visible in the docs or config comments.

Recommendation: document the split if it is intentional, or enforce one deadline across the full adapter operation and let adapter lookup consume part of that same budget dynamically.

### 7. Spec docs mix implemented behavior with future patterns

`circuit-breaker-patterns.md` shows a simplified `SimpleCircuitBreaker` that omits implemented behavior such as event handlers, memory retention, history caps, exponential backoff, and actual status shape. It also includes sliding-window, adaptive-timeout, bulkhead, and Prometheus examples without clearly separating implemented features from suggested patterns.

Impact: engineers and operators can misread the examples as current ORBIT behavior. This is especially risky for monitoring fields, config keys, and recovery behavior.

Recommendation: split the document into two sections: "Current ORBIT behavior" and "Potential extensions". Keep the current behavior examples generated from or aligned with `parallel_adapter_executor.py`.

### 8. Monitoring callback configuration is under-specified

The implementation can create `MonitoringCircuitBreakerEventHandler` from callback objects in config, and can import custom event handler classes from a dotted path. The cookbook does not describe how callback objects are provided safely through YAML or how custom handler imports should be constrained.

Impact: config examples may imply YAML can directly supply callables. The custom import path also needs operational guidance because arbitrary import strings are sensitive in production configuration.

Recommendation: document supported handler types precisely. Prefer named built-in integrations or a small registry over arbitrary callback objects in YAML. If custom imports remain supported, restrict them to trusted deployments and document that they are code-loading behavior.

## Recommended Design Changes

1. Add a breaker-level synchronization model:
   - use one lock for state, counters, backoff fields, and transition checks;
   - capture event payloads inside the lock;
   - dispatch events after releasing the lock.

2. Make event dispatch safe:
   - introduce `_emit_event(coro_factory)` or similar;
   - schedule on the running loop when present;
   - avoid raising from breaker state transitions if event dispatch cannot run;
   - log dispatch failures clearly.

3. Gate half-open probes:
   - add `max_half_open_calls`, default `1`;
   - track in-flight probes;
   - decrement on success/failure completion;
   - fail fast with a clear `Circuit is half-open and probe limit reached` error when saturated.

4. Align reset semantics:
   - make executor reset call `SimpleCircuitBreaker.reset()`;
   - expose reset behavior consistently through health/admin APIs;
   - verify reset emits `on_circuit_reset`.

5. Either implement or remove strategy claims:
   - if implementing, dispatch from `execute_adapters()` based on `self.execution_strategy`;
   - ensure `first_success` cancels pending tasks and handles cancellation accounting deliberately;
   - ensure `best_effort` returns completed work without leaving pending tasks running.

6. Clarify timeout policy:
   - prefer a single operation deadline unless there is a strong reason for fixed 30/70 allocation;
   - document lookup timeout and query timeout separately if the split remains.

7. Update the docs:
   - make the cookbook match actual config and behavior;
   - add `cleanup_interval`, `retention_period`, `max_history_size`, `max_transitions_size`, event handler options, and exponential backoff details where operators need them;
   - label sliding windows, adaptive timeouts, bulkheads, and Prometheus examples as extension patterns unless implemented.

## Test Improvements

Add focused tests before changing runtime behavior:

- Event dispatch from synchronous code does not raise when no event loop is running.
- Handler exceptions do not break `record_failure()`, `record_success()`, or `reset()`.
- Concurrent failures open the circuit exactly once and produce consistent counters.
- Half-open mode allows only `max_half_open_calls` probes and fast-fails extra calls.
- Executor reset clears stats/history/backoff and emits a reset event.
- `execution.strategy=first_success` returns after first success and cancels pending work, if strategy support is implemented.
- `execution.strategy=best_effort` returns completed results and cancels pending work, if strategy support is implemented.
- Adapter timeout tests cover initialization budget, query budget, and the full operation deadline.

## Priority

High priority:

- Safe event dispatch.
- Half-open probe gating.
- Reset semantics.
- Strategy documentation/runtime alignment.

Medium priority:

- Breaker-level locking.
- Timeout policy clarification.
- Monitoring handler configuration docs.

Lower priority:

- Sliding-window failure rate, adaptive timeouts, and bulkhead implementation. These are useful patterns, but they should remain clearly labeled as future extensions until ORBIT implements and tests them.

## Source Notes

- `server/services/parallel_adapter_executor.py` defines the current `SimpleCircuitBreaker`, event handlers, executor strategy config, timeout split, and reset behavior.
- `docs/fault-tolerance/circuit-breaker-patterns.md` documents a simplified breaker and advanced patterns that are not clearly marked as implemented versus optional.
- `docs/cookbook/orbit-fault-tolerance-circuit-breakers.md` documents operator configuration and strategies.
- `server/tests/fault_tolerance/test_circuit_breaker_events.py` verifies async event callbacks but does not cover synchronous/no-loop dispatch or concurrency.
