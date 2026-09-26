# ORBIT Threat Telemetry Dashboard

A command-center UI for the threat telemetry example. Every operational panel
is backed by a real data source — nothing on this screen is a canned demo
value:

| Panel | Real source |
| :--- | :--- |
| Sensor status, sector map, threat distribution, active alerts, acknowledge action | `threat_telemetry.db` (SQLite), via `live_stats_server.py` |
| MQ depth, MQ throughput | RabbitMQ's management API, via `live_stats_server.py` |
| Stats latency | Measured client-side round-trip to `live_stats_server.py` |
| Query Burst Monitor | `sensor_burst_producer.py`'s own status server |
| ORBIT Intelligence (chat) | ORBIT's real `/v1/chat/completions`, via the `intent-sql-sqlite-threat-telemetry` adapter |

The only non-real element is the sector map's node **layout** (x/y screen
position) — sensor identity, status, and detections plotted on it are all
real; the map just doesn't project real lat/lon onto a real terrain image.
The provenance banner at the top of the dashboard says this plainly.

It pairs with ORBIT's `intent-sql-sqlite-threat-telemetry` adapter and the two
bridge scripts in [`../threat-telemetry-mq`](../threat-telemetry-mq/).

## 1. Generate the database (if you haven't already)

```bash
cd examples/intent-templates/sql-intent-template/sqlite/threat-telemetry
python3 generate_threat_telemetry_data.py --force
```

## 2. Start the live stats server

This is what makes the dashboard "live" — a small read/write bridge between
the dashboard (a browser, which can't open a SQLite file or call RabbitMQ's
management API directly) and the real data:

```bash
python examples/threat-telemetry-mq/live_stats_server.py
```

By default it serves `http://localhost:8790/stats` and expects RabbitMQ's
management API at `http://localhost:15672` (guest/guest, the default for the
`rabbitmq:3-management` Docker image). Pass `--rabbitmq-user`/
`--rabbitmq-password`/`--rabbitmq-api` if yours differ, and `--port` to serve
on somewhere other than 8790.

RabbitMQ doesn't need to be running for sensor/alert data to work — only the
MQ depth/throughput tile and the Throughput chart need it; without it they
show "NO DATA" rather than a fabricated number.

## 3. Run the dashboard

```bash
cd examples/threat-telemetry-dashboard
npm install
npm run dev
```

Open the URL printed by Vite (normally <http://localhost:5173>). The
provenance banner at the top shows whether it found the stats server; if not,
double check the URL in the banner's input field against step 2's `--port`.

For a production-style preview:

```bash
npm run build
npm run preview
```

## 4. Connect ORBIT intelligence (optional, for the chat panel)

The sensor/alert/map/metrics panels work without this — only the
**Intelligence** chat panel needs an ORBIT API key:

```bash
./bin/orbit.sh start

python bin/orbit.py --url http://localhost:3000 key create \
  --adapter intent-sql-sqlite-threat-telemetry \
  --name "Threat Telemetry Dashboard" \
  --prompt-file examples/intent-templates/sql-intent-template/sqlite/threat-telemetry/threat-telemetry-assistant-prompt.md \
  --prompt-name "Threat Telemetry Assistant"
```

Enter the resulting key via the settings icon (top right). The key is kept in
session storage only and is discarded when the browser tab closes.

## 5. Run the message-queue demos alongside it (optional)

Follow [`../threat-telemetry-mq/README.md`](../threat-telemetry-mq/README.md)
for the full setup. Two independent things you can layer on top:

- **Live sensor ingestion** (`sensor_event_producer.py` +
  `telemetry_ingest_consumer.py`) — publishes new synthetic detections that
  actually get written to the database. Once ingested, they show up on the
  dashboard on its next poll (every 3s) — new alerts, updated counts, all of
  it, with no dashboard changes needed.
- **Query burst** (`sensor_burst_producer.py`) — the **Query Burst Monitor**
  panel (Command Overview and Intelligence tabs) polls that script's own
  status server (default `http://localhost:8787/status`, click **START
  MONITORING** first) and shows each reply live as it arrives.

## Controls

- The top navigation opens dedicated Command Overview, Incidents, Sensor
  Network, and Intelligence workspaces — all reading the same live data.
- The pause button (top right) freezes live polling everywhere (stats,
  intelligence keepalive) so the screen holds still, e.g. for a photo or a
  moment of audience Q&A. Click it again to resume.
- Select map sensors or alert rows to inspect them.
- **Acknowledge selected** / **Acknowledge incident** sends a real
  `POST /alerts/<id>/acknowledge` to `live_stats_server.py`, which updates
  `threat_telemetry.db` directly — this is a genuine write, not a local-only
  UI state change.
- **Export** downloads the current live stats snapshot as JSON.
- Expand **ORBIT Intelligence** to run preset or free-form questions through
  the real inference pipeline.

The layout targets large 16:9 displays and also collapses cleanly for tablets
and phones. Reduced-motion preferences are respected.

## Troubleshooting

- **Provenance banner says "STATS SERVER UNREACHABLE"** — `live_stats_server.py`
  isn't running, or the URL in the banner's input field doesn't match its
  `--port`.
- **MQ DEPTH / MQ THROUGHPUT show "NO DATA"** — RabbitMQ isn't running, or
  `live_stats_server.py`'s `--rabbitmq-api`/`--rabbitmq-user`/
  `--rabbitmq-password` don't match your broker. Sensor/alert data is
  unaffected either way.
- **Acknowledge doesn't seem to do anything** — it takes up to one poll
  interval (3s) to reflect; confirm directly with
  `sqlite3 .../threat_telemetry.db "SELECT status FROM alerts WHERE alert_id='...'"`
  if in doubt.
