# `performance.workers` — multi-process support

`config.yaml`'s `performance.workers` now spawns real, independent
OS worker processes via uvicorn's `Multiprocess` supervisor. Previously it
was a no-op — see "History" below for why.

## How it works

`InferenceServer.run()` (`server/inference_server.py`) branches on
`performance.workers`:

- **`workers <= 1`** (default): unchanged single-process path —
  `uvicorn.Config(self.app, ...)` is built from the already-constructed
  `FastAPI` instance and run directly via `uvicorn.Server(config).run()`.
- **`workers > 1`**: the app can no longer be passed as a live instance —
  uvicorn refuses to fork/spawn workers from an object, since open DB
  connections, background tasks, etc. don't survive a fork/spawn safely.
  Instead:
  1. `OIS_CONFIG_PATH` is set to this process's resolved config path, and
     `ORBIT_SUPERVISOR_PID` is set to this process's own PID (both env vars,
     inherited by every forked/spawned worker).
  2. `uvicorn.Config("main:create_app", factory=True, workers=N, ...)` is
     built from the import string, and `uvicorn.supervisors.Multiprocess`
     drives the actual worker pool — each worker independently imports
     `server/main.py` and calls `create_app()`, which builds its own
     `InferenceServer` (reading `OIS_CONFIG_PATH`), its own DB/cache
     connections, its own service instances, etc.
  3. `server/main.py` no longer eagerly builds a module-level `app` at
     import time (that would double-construct `InferenceServer` once via
     the import side effect and once via the `factory=True` call). Instead
     it defines a lazy `__getattr__` so `main:app` (a plain, non-factory
     import string) still works if referenced directly, without ever being
     built twice.

## Known limitations under `workers > 1`

- **`/admin/info` PID**: reports `ORBIT_SUPERVISOR_PID` (the supervisor
  process that all workers descend from) instead of `os.getpid()` (which
  would be whichever worker happened to answer the request). This is what
  `orbit stop`/`orbit status` target, so they correctly signal/inspect the
  supervisor rather than one arbitrary worker.
- **`/admin/restart`**: this endpoint re-execs the *current* process in
  place, which only makes sense for a single process. Under `workers > 1`
  it now returns `501` and points at `orbit restart` instead, which
  already does a full external stop-then-start of the supervisor
  (`bin/orbit/services/server_service.py`) and works correctly regardless
  of worker count.
- **`/admin/jobs` (async admin job tracking)**: `request.app.state.admin_jobs`
  is an in-memory dict, local to whichever worker handled the request that
  created the job. Polling `/admin/jobs/{id}` from a different worker will
  report "not found." This is a pre-existing gap, not introduced by this
  change — not fixed here since none of the current async admin jobs are
  routed to a specific worker deterministically. If this becomes a real
  problem, it needs a shared store (same pattern as
  `server/services/pause_state.py`'s database-backed coordination).
- **Shutdown and force-stop**:
  - `/admin/shutdown` and normal `orbit stop` target the supervisor, which
    terminates and joins every worker.
  - `orbit stop --force` is intentionally more aggressive: detached
    CLI-managed pools are killed by their server-owned process group;
    fallback cases (e.g. a port-discovered worker PID instead of the
    supervisor's) use verified process-tree teardown to avoid killing an
    operator's shell or unrelated processes. See
    `bin/orbit/services/server_service.py`'s `_force_kill`.
- **Pause/resume** (`server/services/pause_state.py`) is already
  cross-process-safe by design (backed by `database_service`, not
  in-memory state), so it needs no changes for multi-worker correctness. A
  read failure on that durable state fails closed — new chat/A2A/voice
  ingress is rejected as "paused" until the state can be read again, rather
  than silently letting traffic through during a database outage. This
  applies to every worker independently, since each reads the same shared
  backend on every request.
- **Rate-limit fallback and thread pools**: already documented in
  `config/config.yaml` as scaling per-worker (e.g. "aggregate fallback
  ceiling can be up to limit * workers"); this was already accurate advice
  even before this fix (in case operators had been running true multi-worker
  via a manual `uvicorn main:app --workers N` invocation outside ORBIT's own
  `run()`), and now applies to ORBIT's own supervised startup too.
