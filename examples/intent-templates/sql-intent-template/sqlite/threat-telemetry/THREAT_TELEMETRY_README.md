# Sensor & Threat Telemetry SQLite Adapter

Simulated perimeter/ISR sensor network — radar, perimeter cameras, drones, and
acoustic sensors reporting detections, with alerts raised on high/critical
severity contacts. Built as a real-time threat-analysis demo: natural-language
questions over sensor status, detections, and open alerts, answered via
ORBIT's intent-SQL retriever.

## Generate the database

```bash
cd examples/intent-templates/sql-intent-template/sqlite/threat-telemetry
python3 generate_threat_telemetry_data.py --force
```

This creates `threat_telemetry.db` with 6 sensors, 400 detections spread over
the last 72 hours (skewed toward recent, with a handful of guaranteed
critical detections in the last hour), and alerts raised for the
high/critical-severity ones.

Detection timestamps are anchored to the moment you run the generator, not a
fixed date — **re-run this command shortly before a live demo** so "last
hour" / "today" queries have fresh data to find. Data older than ~72 hours
since generation will make those specific queries return empty.

## Files

- `threat_telemetry_schema.sql` — table DDL (sensors, detections, alerts)
- `generate_threat_telemetry_data.py` — deterministic data generator (seed `7331`)
- `threat-telemetry-domain.yaml` — entity/field/relationship domain definition
- `threat-telemetry-templates.yaml` — 9 intent templates (critical detections,
  sensor status, open alerts, alerts by operator, etc.)
- `threat-telemetry-assistant-prompt.md` — the analyst persona for this
  adapter (direct, severity-first, no chatbot filler)
- `threat-telemetry-intro.md` — welcome/intro message for the API key,
  shown to users of a chat client (e.g. `orbitchat`) on first load

## Registered adapter

`intent-sql-sqlite-threat-telemetry` in `config/adapters/threat-telemetry.yaml`.

## Create an API key

Create a key bound to this adapter and its persona in one call:

```bash
python bin/orbit.py --url http://localhost:3000 key create \
  --adapter intent-sql-sqlite-threat-telemetry \
  --name "Threat Telemetry Demo Key" \
  --prompt-file examples/intent-templates/sql-intent-template/sqlite/threat-telemetry/threat-telemetry-assistant-prompt.md \
  --prompt-name "Threat Telemetry Assistant"
```

Add `--expires-in-days N` for a time-boxed demo key, or `--non-expiring
--justification "..."` for one that should persist through the demo. To
reuse the same persona across multiple keys, create it once with `prompt
create` and pass `--prompt-id` to subsequent `key create` calls instead of
`--prompt-file`.

## Try it

```
"Show critical detections in the last hour"
"How many open alerts are there right now?"
"Which sensors reported detections today?"
"List unresolved alerts by severity"
```

## Related demo pieces

- `examples/threat-telemetry-mq/` — simulates a burst of sensor traffic over
  ORBIT's message-queue surface (see `docs/message-queue-architecture.md`).
- `examples/threat-telemetry-dashboard/` — a static HTML dashboard driving
  this adapter through `/v1/chat/completions`.
