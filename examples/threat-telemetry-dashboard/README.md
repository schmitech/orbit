# ORBIT Threat Telemetry Dashboard

A demo-ready command-center UI for the threat telemetry example. It pairs
with ORBIT's `intent-sql-sqlite-threat-telemetry` adapter and the burst producer
in [`../threat-telemetry-mq`](../threat-telemetry-mq/).

## Run the dashboard

```bash
cd examples/threat-telemetry-dashboard
npm install
npm run dev
```

Open the URL printed by Vite (normally <http://localhost:5173>). The dashboard
starts in **Demo** mode, so it is presentation-safe even when the backend is not
available. Click **Live** or the settings icon to add the ORBIT URL and API key.
The URL is stored locally, while the API key is kept in session storage and is
discarded when the browser tab closes.

For a production-style preview:

```bash
npm run build
npm run preview
```

## Connect live ORBIT intelligence

Start ORBIT and create a key scoped to the telemetry adapter:

```bash
./bin/orbit.sh start

python bin/orbit.py --url http://localhost:3000 key create \
  --adapter intent-sql-sqlite-threat-telemetry \
  --name "Threat Telemetry Dashboard" \
  --prompt-file examples/intent-templates/sql-intent-template/sqlite/threat-telemetry/threat-telemetry-assistant-prompt.md \
  --prompt-name "Threat Telemetry Assistant"
```

Enter the resulting key in the dashboard connection dialog. Live mode calls
ORBIT's OpenAI-compatible `/v1/chat/completions` endpoint, polls backend health,
and sends operator questions through the real intent-to-SQL pipeline.

## Run the message-queue demo alongside it

Follow [`../threat-telemetry-mq/README.md`](../threat-telemetry-mq/README.md) to
start RabbitMQ and the standalone worker, then run:

```bash
python examples/threat-telemetry-mq/sensor_burst_producer.py --burst-size 20
```

The dashboard's map, alert feed, sensor state, latency, and queue throughput
chart are clearly labeled simulated presentation data—even in Live mode.
Browsers do not connect directly to AMQP, so those stay presentation-only.

The **Query Burst Monitor** panel (Command Overview and Intelligence tabs) is
the one exception: it's labeled "MESSAGE QUEUE · LIVE" because it genuinely
is. The burst producer runs a small local HTTP status server (default
`http://localhost:8787/status`) that the dashboard polls once a second; each
question and its real ORBIT-generated answer appears there as the reply
arrives, with a live published/completed/failed/outstanding tally. This is a
demo-only bridge (not part of ORBIT itself) — see
`../threat-telemetry-mq/README.md`'s "Watch it live in the dashboard" section
for details, including how the panel keeps showing the final tally for a
while after the burst finishes.

For a deployment that needs literal broker counters instead of this bridge,
put a server-side endpoint in front of RabbitMQ's management API rather than
exposing broker credentials in the browser.

## demo controls

- The top navigation opens dedicated Command Overview, Incidents, Sensor
  Network, and Intelligence workspaces.
- **Demo / Live** toggles presentation-safe data and the real ORBIT adapter.
- The pause button freezes changing throughput and timestamps.
- Select map sensors or alert rows to inspect them.
- **Acknowledge selected** updates an alert during the demo.
- **Export** downloads the current dashboard snapshot as JSON.
- Expand **ORBIT Intelligence** to run preset or free-form questions.

The layout targets large 16:9 displays and also collapses cleanly for tablets
and phones. Reduced-motion preferences are respected.
