# Manual/Integration Check: Pause/Resume and Multi-Worker Server Operations

Steps to verify after implementation, in order. Covers `orbit pause`/`orbit resume`,
the ingress gates that enforce them (chat, A2A, voice), and the `performance.workers`
multi-process supervisor (startup, PID reporting, graceful shutdown, and force-kill
safety).

Run from the repo root with the venv active, e.g.:

```bash
source venv/bin/activate   # or use venv/bin/python / venv/bin/orbit directly
```

Several steps assert "no matching processes" via `pgrep`. `pgrep` exits `1`
for "no match" (the expected/passing case here) but exits `2` on a usage or
system error — a bare "no output" reads the same as either, so check the
exit code explicitly rather than just eyeballing empty output. Use this
helper for cmdline-based assertions in this playbook:

```bash
assert_no_match() {
  local pattern="$1"
  local out
  out="$(pgrep -f "$pattern")"
  local status=$?
  if [ "$status" -eq 0 ]; then
    echo "FAIL: matching process(es) still running for '$pattern':"
    echo "$out"
    return 1
  elif [ "$status" -eq 1 ]; then
    echo "OK: no processes matching '$pattern'"
    return 0
  else
    echo "ERROR: pgrep itself failed (exit $status) — result is inconclusive, not a pass"
    return 2
  fi
}
```

`assert_no_match` is only reliable for the **supervisor** process itself —
its command line genuinely contains `server/main.py`. Uvicorn's `Multiprocess`
spawns each worker via `multiprocessing`, whose bootstrap command line does
**not** retain the `main:create_app` import string, so `assert_no_match
"main:create_app"` can report `OK` even while workers are still alive — it
only ever mismatched immediately, never proof of anything. For confirming
"the whole pool is gone," check OS process-group membership instead, which
every worker shares with the supervisor regardless of its own command line:

```bash
assert_group_empty() {
  local pgid="$1"
  local ps_out ps_status

  # Capture ps's own output/status BEFORE piping into awk. A `ps | awk`
  # one-liner hides a ps failure behind awk's exit status (empty stdin ->
  # awk finds no matches -> exit 0 -> reads identical to "group is empty"),
  # which is exactly the false-pass this playbook already fixed for pgrep.
  ps_out="$(ps -e -o pid=,pgid= 2>&1)"
  ps_status=$?
  if [ "$ps_status" -ne 0 ]; then
    echo "ERROR: 'ps' failed (exit $ps_status) — result is inconclusive, not a pass: $ps_out"
    return 2
  fi

  local out
  out="$(printf '%s\n' "$ps_out" | awk -v g="$pgid" '$2==g {print $1}')"
  if [ -n "$out" ]; then
    echo "FAIL: process group $pgid still has member PIDs:"
    echo "$out"
    return 1
  else
    echo "OK: process group $pgid has no remaining members"
    return 0
  fi
}
```

Capture the supervisor's PID *before* stopping it (its process group ID
equals its own PID, since `start()` launches it with
`start_new_session=True`), then call `assert_group_empty` with that captured
value after the stop/force-stop completes.

## Part A — Pause / Resume (single process)

### 1. Start the server and confirm baseline status

```bash
./bin/orbit.sh start
./bin/orbit.sh status
```

**Expected:** `status: running`, a PID, and uptime/metrics.

### 2. Pause via CLI

```bash
./bin/orbit.sh pause
./bin/orbit.sh status
```

**Expected:** `pause` reports success; `status` now shows `paused` (via
`GET /admin/info`), same PID as before — the process never restarted.

### 3. Confirm chat traffic is rejected while paused

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"model":"any","messages":[{"role":"user","content":"hello"}]}'
```

**Expected:** `503`.

### 4. Confirm health checks and non-chat traffic still work while paused

```bash
curl -s http://localhost:3000/health
```

**Expected:** `200`, normal health payload — `/health` must never be gated,
since load balancers/monitoring rely on it to know the process is alive.

### 5. Confirm `/v1/chat/stop` still works while paused

Start a normal (non-paused) streaming request, pause mid-stream, then issue a
stop for that same request/session.

**Expected:** the stop call succeeds — cancellation of an in-flight stream is
intentionally excluded from the pause gate so existing work can still be torn
down cleanly.

### 6. Resume and confirm chat traffic flows again

```bash
./bin/orbit.sh resume
./bin/orbit.sh status
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" -H "X-API-Key: <your-api-key>" \
  -d '{"model":"any","messages":[{"role":"user","content":"hello"}]}'
```

**Expected:** `status: running`; chat request returns `200`.

### 7. Admin panel Ops tab

Open the admin panel, go to the **Ops** tab. Click **Pause** (plain confirm,
no typed confirmation, no full-page overlay — the process stays alive).
Confirm the button flips to **Resume** and reflects the current state on
reload. Click **Resume**, confirm it flips back.

### 8. A2A ingress gate

With the server paused (`orbit pause`), send a JSON-RPC `tasks/send` request
to the A2A endpoint:

```bash
curl -s http://localhost:3000/a2a -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0", "id": 1, "method": "tasks/send",
  "params": {"task": {"input": {"message": "hello"}}}
}'
```

**Expected:** a JSON-RPC error response (`code: -32000`, `"Server is paused"`),
not a normal task result. `tasks/get`/`tasks/cancel` for an already-running
task should still work while paused (not gated).

### 9. Voice WebSocket ingress gate

With the server still paused, attempt to open a realtime voice WebSocket
session (via a voice-enabled client, or a raw WebSocket connection to the
voice endpoint with a valid API key).

**Expected:** the connection is rejected pre-accept with an error payload
(`503`, `"Server is paused"`), not a normal session.

### 10. Fail-closed behavior on a database outage (staging only — do not run against production)

This step requires taking down a live backend, so only run it against a
disposable staging/test deployment, never production.

Stop the backing database service that `pause_state.py` reads from — for a
Mongo or Postgres deployment, stop that service (e.g. `docker stop` the
container, or stop the systemd unit). If this deployment uses the SQLite
backend, "stopping" it isn't a meaningful action in the same sense (there's
no separate service to take down); instead simulate the failure by revoking
read permissions on the SQLite file, or by pointing `database.sqlite.path` at
a nonexistent path and restarting — the goal is a genuine query failure, not
just an empty/missing row. Then attempt a chat request.

**Expected:** requests are rejected as if paused (fail closed) — a read
failure on the durable pause flag must never be silently treated as "not
paused." Restore the database (or the SQLite path/permissions) and confirm
normal operation resumes without manual intervention (no need to re-issue
`resume`, since the flag itself was never actually toggled).

## Part B — Multi-worker startup (`performance.workers > 1`)

### 11. Enable multiple workers and start

In `config/config.yaml`:

```yaml
performance:
  workers: 4
```

```bash
./bin/orbit.sh start
```

**Expected in `logs/orbit.log`:** `Started parent process [PID]` followed by
four `Started server process [PID]` lines (one per worker), then
`Application startup complete.` per worker. Occasional one-off gRPC
fork-safety warnings at startup are benign log noise (see
`docs/server.md#benign-grpc-fork-warnings-with-workers--1`), not errors.

### 12. Confirm requests are served by different worker PIDs

Throughput comparisons against `workers: 1` are suggestive but not
conclusive — prefer a deterministic check. Add a temporary debug log line (or
a scratch endpoint) that logs `os.getpid()` per request, e.g. in
`server/routes/health_routes.py`'s health handler:

```python
import os
logger.info("health check served by pid=%s", os.getpid())
```

Restart with `workers: 4`, send several requests, then check the log:

```bash
for i in 1 2 3 4 5 6 7 8; do curl -s http://localhost:3000/health > /dev/null; done
grep "served by pid=" logs/orbit.log | tail -8
```

**Expected:** more than one distinct PID appears across the logged lines.
Remove the temporary log line afterward — it's a debugging aid, not something
to leave in the codebase.

### 13. `/admin/info` reports the supervisor PID, not a worker's

```bash
for i in 1 2 3; do
  curl -s http://localhost:3000/admin/info -H "Authorization: Bearer <token>"
  echo
done
```

**Expected:** the same `pid` every time, regardless of which worker actually
answered the request — this must be the supervisor's PID (visible as
`Started parent process [PID]` in the log), not one of the four worker PIDs.

### 14. `orbit status` / `orbit stop` target the supervisor correctly

```bash
SUPERVISOR_PID="$(curl -s http://localhost:3000/admin/info -H "Authorization: Bearer <token>" | python3 -c 'import sys,json; print(json.load(sys.stdin)["pid"])')"
echo "captured supervisor pid: $SUPERVISOR_PID"
./bin/orbit.sh status
./bin/orbit.sh stop
```

**Expected:** `status` shows the supervisor PID with sane metrics; `stop`
gracefully shuts down — check the log for `Received SIGTERM, exiting.`
followed by `Terminated child process [...]` for *every* worker and
`Stopping parent process [...]`. Confirm no orphaned worker processes remain,
using the PID captured *before* stopping (its process group ID equals its
own PID for a detached supervisor):

```bash
sleep 1
assert_group_empty "$SUPERVISOR_PID"
```

**Expected:** `OK: process group $SUPERVISOR_PID has no remaining members`.

### 15. `orbit pause`/`resume` still work correctly under multiple workers

Repeat steps 2–6 with `workers: 4`. Since `pause_state.py` is backed by the
shared database (not in-memory state), pausing via one worker must be visible
to requests answered by any other worker.

```bash
./bin/orbit.sh pause
# fire several requests in a loop so different workers likely answer them
for i in 1 2 3 4 5 6; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:3000/v1/chat/completions \
    -H "Content-Type: application/json" -H "X-API-Key: <your-api-key>" \
    -d '{"model":"any","messages":[{"role":"user","content":"hi"}]}'
done
```

**Expected:** every single response is `503`, regardless of which worker
handled it.

### 16. `/admin/restart` is disabled under multi-worker mode

```bash
curl -s -X POST http://localhost:3000/admin/restart -H "Authorization: Bearer <token>"
```

**Expected:** `501`, with a message pointing at `orbit restart` instead — an
in-process `execv` restart only makes sense for a single process; under
multiple workers it would replace one worker while leaving the supervisor and
siblings in an inconsistent state.

### 17. `orbit restart` works correctly under multi-worker mode

```bash
./bin/orbit.sh restart
./bin/orbit.sh status
```

**Expected:** clean stop (per step 14's checks) followed by a fresh start with
a new supervisor PID and all four workers back up.

## Part C — Force-stop safety under multi-worker mode

These are the scenarios from the review cycle that motivated the `_force_kill`
design in `bin/orbit/services/server_service.py` — they're about *not* taking
down more than the server, so run them deliberately and watch process state
closely.

### 18. Force-stop the detached supervisor (the normal case)

```bash
./bin/orbit.sh start   # workers: 4
SUPERVISOR_PID="$(curl -s http://localhost:3000/admin/info -H "Authorization: Bearer <token>" | python3 -c 'import sys,json; print(json.load(sys.stdin)["pid"])')"
echo "captured supervisor pid: $SUPERVISOR_PID"
./bin/orbit.sh stop --force
```

**Expected:** all 5 processes (supervisor + 4 workers) are gone.

```bash
sleep 1
assert_group_empty "$SUPERVISOR_PID"
```

**Expected:** `OK: process group $SUPERVISOR_PID has no remaining members` —
no orphaned workers survive the force-kill.

### 19. Force-stop when `/admin/info` is unreachable (port-discovery fallback)

Before breaking `/admin/info`, capture the supervisor's PID independently —
via its actual command line, which *does* reliably identify the supervisor
(unlike a worker):

```bash
SUPERVISOR_PID="$(pgrep -f 'server/main\.py')"
echo "captured supervisor pid: $SUPERVISOR_PID"
```

Then simulate `/admin/info` being unavailable — for example, temporarily
block the admin route or revoke the CLI's auth token — so `stop --force`
must fall back to `_find_process_by_port()`, which under multi-worker mode
may return a *worker's* PID rather than the supervisor's.

**Expected:** the CLI still resolves the actual supervisor (by process
ancestry + command-line verification, matching `server/main.py`/`main:app`/
`main:create_app`) and kills the whole verified tree — not just the one
worker it happened to discover. Confirm with the PID captured above (not a
fresh `pgrep -f "main:create_app"`, which would never have matched a worker
in the first place):

```bash
sleep 1
assert_group_empty "$SUPERVISOR_PID"
```

**Expected:** `OK: process group $SUPERVISOR_PID has no remaining members`.

### 20. Force-stop does not touch unrelated foreground processes

This has to actually reproduce the unsafe precondition — both processes
genuinely sharing one OS process group — or it doesn't test anything. An
interactive shell's job control assigns each backgrounded job its own
process group by default, so simply running `sleep 600 &` followed by
`python3 server/main.py &` at an interactive prompt will usually **not**
share a group, and the test would silently pass without ever exercising the
unsafe case. Run this as a single non-interactive script instead, with job
control explicitly disabled (`set +m`), so both children inherit the
script's own group — and assert that precondition before proceeding, rather
than assuming it:

```bash
cat > /tmp/force_kill_group_test.sh <<'SCRIPT'
#!/bin/bash
set +m   # disable job control so backgrounded children share this shell's group, not their own

sleep 600 &                  # a stand-in for an unrelated process in the same shell session
SLEEP_PID=$!
python3 server/main.py &     # foreground-style launch, no start_new_session
ORBIT_PID=$!
sleep 2

sleep_pgid="$(ps -o pgid= -p "$SLEEP_PID" | tr -d ' ')"
orbit_pgid="$(ps -o pgid= -p "$ORBIT_PID" | tr -d ' ')"
echo "sleep pgid=$sleep_pgid orbit pgid=$orbit_pgid"

if [ "$sleep_pgid" != "$orbit_pgid" ]; then
  echo "ABORT: precondition not met -- sleep and orbit ended up in different groups ($sleep_pgid vs $orbit_pgid)."
  echo "This harness must reproduce the shared-group case before the force-kill is meaningful; investigate why set +m didn't prevent group separation on this shell/OS before trusting any result below."
  kill "$SLEEP_PID" "$ORBIT_PID" 2>/dev/null
  exit 1
fi
echo "OK: precondition confirmed -- both processes share pgid=$orbit_pgid"

python3 - "$ORBIT_PID" <<PYEOF
import sys
sys.path.insert(0, "bin")
from orbit.services.server_service import ServerService
ServerService._force_kill(int(sys.argv[1]))
PYEOF

sleep 1
echo "--- post-kill check ---"
pgrep -f "sleep 600"
echo "sleep 600 pgrep exit status: $?"
kill "$SLEEP_PID" 2>/dev/null
SCRIPT
bash /tmp/force_kill_group_test.sh
```

**Expected output, in order:**

1. `OK: precondition confirmed -- both processes share pgid=<N>` — if this
   instead prints `ABORT: precondition not met`, stop: the harness didn't
   reproduce the unsafe case on this shell/OS, and nothing below is a valid
   result.
2. The `sleep 600` PID printed by `pgrep`, with `sleep 600 pgrep exit status:
   0` — a match, not empty output. This is the critical safety property: a
   `killpg` on the shared group here would have taken the whole terminal
   session down, `sleep 600` included, and printed exit status `1` (no
   match) instead.

### 21. No orphaned respawn during verified-tree teardown

This exercises the supervisor-freeze fix — that killing a worker doesn't race
against the supervisor's own respawn logic.

Start with `workers: 4`, then force-stop via the port-discovery path (as in
step 19) while watching worker PIDs closely:

```bash
./bin/orbit.sh start
SUPERVISOR_PID="$(pgrep -f 'server/main\.py')"
echo "captured supervisor pid: $SUPERVISOR_PID"
# trigger a force-stop via the worker-PID fallback path (see step 19 setup)
./bin/orbit.sh stop --force
sleep 2
assert_group_empty "$SUPERVISOR_PID"
```

**Expected:** `OK: process group $SUPERVISOR_PID has no remaining members`.
If the supervisor were still able to react between the child-kill loop and
the final supervisor kill, a freshly spawned replacement worker would appear
as a new member of this same group — that's the exact race this step is
designed to catch, and it's why the assertion checks the whole group rather
than a fixed list of PIDs snapshotted beforehand.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `orbit status` shows `running` right after `orbit pause` | Check `GET /admin/info` directly — if it also says `running`, the pause write likely failed (`503` from `/admin/pause` would confirm this); check the database backend used by `pause_state.py` is reachable. |
| Chat requests succeed while paused | Confirm the request actually hit `/v1/chat` or `/v1/chat/completions` (not `/v1/chat/stop`, which is intentionally excluded) and that the adapter/route wiring wasn't bypassed by a custom route. |
| `/admin/info` PID changes between requests under `workers > 1` | `ORBIT_SUPERVISOR_PID` isn't being set/inherited — confirm `InferenceServer.run()` sets it before calling `Multiprocess(...).run()`, and that workers were actually spawned via the `main:create_app` factory path, not the single-process fallback. |
| Workers don't start at all with `workers > 1` | Check `cwd`/`PYTHONPATH` — the `main:create_app` import string must resolve from wherever the server process's cwd is; confirm `OIS_CONFIG_PATH` is set and points at a valid config. |
| Orphaned worker process survives `stop --force` | This is the exact bug class fixed by `_force_kill`'s ancestry+cmdline verification and supervisor-freeze — if reproduced, check whether `psutil.Process.suspend()`/`.children(recursive=True)` behaved as expected on this OS/psutil version. |
| `stop --force` kills unrelated shell jobs | Regression in the `os.getpgid(pid) == pid` guard in `_force_kill` — this must gate `killpg`, and any non-supervisor PID must go through the verified-tree path instead, never a raw group signal. |
