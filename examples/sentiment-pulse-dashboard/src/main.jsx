import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Pause, Play, Radio, Send, Zap } from "lucide-react";
import { REVIEWS } from "./reviews.js";
import { GATE, showsEscalationLane, showsRoutingLine, isExperimental } from "./gate.js";
import "./styles.css";

// DORMANT DEMO. GATE (./gate.js) is unfilled until the Phase 1 held-out eval actually
// runs — see docs/roadmap/complete/decision-model-sentiment-analysis.md. Every panel below reads
// GATE and shows nothing for a signal that hasn't passed. Nothing here is announced or
// run at a booth until that gate decides. All answers shown come from a real adapter
// call through the bridge; nothing is ever fabricated client-side.

const SETTINGS_KEY = "sentiment-pulse-settings";
const DEFAULT_SETTINGS = {
  bridgeUrl: "http://localhost:8795",
  speed: 2, // items/sec while playing
  pauseAllRequests: false,
};
const FEED_LIMIT = 40;
const MOOD_WINDOW = 20;
const MOOD_SPARK_WINDOW_MS = 60_000;
const SESSION = Math.random().toString(36).slice(2, 8);

const POLARITY_ORDER = ["positive", "neutral", "negative", "mixed"];
const ASPECT_ROWS = ["price", "support", "product", "delivery"];
const VALENCE_LEVELS = ["Very negative", "Negative", "Neutral", "Positive", "Very positive"];

function readStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}
function writeStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

function shuffle(list) {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function expectedValence(answer) {
  // `score` answers report the expected level on a 0..N-1 scale (see decision-models.md).
  return typeof answer?.score === "number" ? answer.score : null;
}

function topProbability(answer) {
  if (!answer?.choice || !answer?.probabilities) return null;
  return answer.probabilities[answer.choice] ?? null;
}

function percentile(values, p) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

// ---------------------------------------------------------------------------

function useBridgeHealth(bridgeUrl) {
  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState("connecting"); // connecting | ok | no-bridge | no-worker

  useEffect(() => {
    let cancelled = false;
    let timer;

    async function poll() {
      try {
        const response = await fetch(`${bridgeUrl.replace(/\/$/, "")}/health`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (cancelled) return;
        setHealth(data);
        if (!data.broker) setStatus("no-bridge");
        else if (!data.queue?.available || data.queue?.consumers === 0) setStatus("no-worker");
        else setStatus("ok");
      } catch {
        if (!cancelled) { setHealth(null); setStatus("no-bridge"); }
      } finally {
        if (!cancelled) timer = setTimeout(poll, 2000);
      }
    }
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [bridgeUrl]);

  return { health, status };
}

function useReplyStream(bridgeUrl, enabled) {
  const [decisions, setDecisions] = useState([]); // most-recent-first
  const [connected, setConnected] = useState(false);
  const [streamStale, setStreamStale] = useState(false);
  // Refs, not state: the staleness interval below must keep running on its own 2s
  // cadence without being torn down and recreated on every single incoming message
  // (continuous fast streaming would otherwise reset it before its check ever fires,
  // and a staleness flag set true during a gap would then get stuck true forever).
  const connectedRef = useRef(false);
  const connectedAtRef = useRef(null);
  const lastEventAtRef = useRef(null);

  useEffect(() => {
    if (!enabled) {
      connectedRef.current = false;
      connectedAtRef.current = null;
      lastEventAtRef.current = null;
      setConnected(false);
      setStreamStale(false);
      return;
    }
    const source = new EventSource(`${bridgeUrl.replace(/\/$/, "")}/events`);
    source.onopen = () => {
      connectedRef.current = true;
      connectedAtRef.current = Date.now();
      setConnected(true);
    };
    source.onerror = () => { connectedRef.current = false; setConnected(false); };
    source.onmessage = (event) => {
      lastEventAtRef.current = Date.now();
      try {
        const payload = JSON.parse(event.data);
        if (payload.type !== "decision") return;
        // The bridge doesn't stamp a wall-clock time on the event (only latency_ms,
        // measured from when the bridge itself published it) — "at" here is this
        // browser's receipt time, used only for the mood sparkline/dps windows.
        setDecisions((prev) => [{ ...payload, at: Date.now() }, ...prev].slice(0, 500));
      } catch { /* ignore unparseable events */ }
    };
    return () => source.close();
  }, [bridgeUrl, enabled]);

  // The stream can report "connected" while every reply is actually blocked — including
  // the case where it's been connected the whole time and has NEVER received a single
  // event. Track staleness against whichever happened more recently: the last event,
  // or the connection itself opening. Runs on its own fixed cadence for `enabled`'s
  // whole lifetime, independent of message traffic.
  useEffect(() => {
    if (!enabled) return;
    const timer = setInterval(() => {
      if (!connectedRef.current) { setStreamStale(false); return; }
      const since = lastEventAtRef.current ?? connectedAtRef.current;
      setStreamStale(since !== null && Date.now() - since > 15_000);
    }, 2000);
    return () => clearInterval(timer);
  }, [enabled]);

  return { decisions, connected, streamStale };
}

async function publishBatch(bridgeUrl, items) {
  const response = await fetch(`${bridgeUrl.replace(/\/$/, "")}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

// ---------------------------------------------------------------------------

function Dashboard() {
  const [settings, setSettingsState] = useState(() => readStorage(SETTINGS_KEY, DEFAULT_SETTINGS));
  const setSettings = useCallback((patch) => {
    setSettingsState((prev) => {
      const next = { ...prev, ...(typeof patch === "function" ? patch(prev) : patch) };
      writeStorage(SETTINGS_KEY, next);
      return next;
    });
  }, []);

  const [playing, setPlaying] = useState(false); // never true on load
  const { health, status } = useBridgeHealth(settings.bridgeUrl);
  const { decisions, connected, streamStale } = useReplyStream(settings.bridgeUrl, status === "ok");

  const deckRef = useRef(shuffle(REVIEWS));
  const deckIdxRef = useRef(0);
  const seqRef = useRef(0);
  // The bridge's reply events carry id/answers/latency, not the original text — track
  // it client-side by id so the feed can show what was asked. Capped so it can't grow
  // unbounded over a long-running demo.
  const textByIdRef = useRef(new Map());
  const rememberText = useCallback((id, text) => {
    textByIdRef.current.set(id, text);
    if (textByIdRef.current.size > 1000) {
      const oldest = textByIdRef.current.keys().next().value;
      textByIdRef.current.delete(oldest);
    }
  }, []);
  const [ownResult, setOwnResult] = useState(null);
  const [ownText, setOwnText] = useState("");
  const [ownPublishing, setOwnPublishing] = useState(false);

  const nextReview = useCallback(() => {
    if (deckIdxRef.current >= deckRef.current.length) {
      deckRef.current = shuffle(REVIEWS);
      deckIdxRef.current = 0;
    }
    return deckRef.current[deckIdxRef.current++];
  }, []);

  const canPublish = status === "ok" && !settings.pauseAllRequests;

  // Play loop: publishes one review every 1000/speed ms, stops on pause or unmount.
  useEffect(() => {
    if (!playing || !canPublish) return;
    const interval = setInterval(() => {
      const review = nextReview();
      const id = `${SESSION}-${seqRef.current++}`;
      rememberText(id, review.text);
      publishBatch(settings.bridgeUrl, [{ id, text: review.text }]).catch(() => { /* surfaces via /health */ });
    }, Math.max(50, 1000 / settings.speed));
    return () => clearInterval(interval);
  }, [playing, canPublish, settings.bridgeUrl, settings.speed, nextReview, rememberText]);

  const surge = useCallback(async () => {
    if (!canPublish) return;
    for (const size of [50, 50]) {
      const items = Array.from({ length: size }, () => {
        const review = nextReview();
        const id = `${SESSION}-${seqRef.current++}`;
        rememberText(id, review.text);
        return { id, text: review.text };
      });
      await publishBatch(settings.bridgeUrl, items).catch(() => { /* surfaces via /health */ });
    }
  }, [canPublish, settings.bridgeUrl, nextReview, rememberText]);

  const submitOwn = useCallback(async (event) => {
    event.preventDefault();
    const text = ownText.trim().slice(0, 280);
    if (!text || !canPublish || ownPublishing) return;
    setOwnPublishing(true);
    setOwnResult(null);
    const id = `${SESSION}-own-${seqRef.current++}`;
    try {
      rememberText(id, text);
      await publishBatch(settings.bridgeUrl, [{ id, text }]);
      setOwnResult({ id, text, status: "pending", publishedAt: Date.now() });
      setOwnText("");
    } catch (e) {
      setOwnResult({ id, text, status: "error", error: String(e) });
    } finally {
      setOwnPublishing(false);
    }
  }, [ownText, canPublish, ownPublishing, settings.bridgeUrl]);

  // Resolve the "type your own" card once its decision arrives in the stream.
  useEffect(() => {
    if (!ownResult || ownResult.status !== "pending") return;
    const match = decisions.find((d) => d.id === ownResult.id);
    if (match) {
      setOwnResult((prev) => ({
        ...prev, status: match.status, answers: match.answers, error: match.error,
        latency_ms: match.latency_ms, resolvedAt: Date.now(),
      }));
    }
  }, [decisions, ownResult]);

  // Enrich each event with its originating text (tracked client-side, see rememberText).
  const enriched = useMemo(
    () => decisions.map((d) => ({ ...d, text: textByIdRef.current.get(d.id) })),
    [decisions],
  );
  const recent = enriched.slice(0, FEED_LIMIT);
  // The bridge's reply envelope reports "completed" on success (server/services/
  // messaging/message_consumer.py), not "ok" — and "failed" on error, or "timeout"
  // synthesized by the bridge itself when nothing comes back in time.
  const resolved = enriched.filter((d) => d.status === "completed" && d.answers);

  const polarityCounts = useMemo(() => {
    const counts = Object.fromEntries(POLARITY_ORDER.map((p) => [p, 0]));
    for (const d of resolved) {
      const choice = d.answers?.polarity?.choice;
      if (choice in counts) counts[choice] += 1;
    }
    return counts;
  }, [resolved]);
  const polarityTotal = Object.values(polarityCounts).reduce((a, b) => a + b, 0);

  const moodSeries = useMemo(() => {
    const now = Date.now();
    return resolved
      .map((d) => ({ at: d.at || now, valence: expectedValence(d.answers?.valence) }))
      .filter((p) => p.valence !== null && now - p.at <= MOOD_SPARK_WINDOW_MS)
      .reverse();
  }, [resolved]);
  const moodRolling = useMemo(() => {
    const window = resolved.slice(0, MOOD_WINDOW).map((d) => expectedValence(d.answers?.valence)).filter((v) => v !== null);
    if (!window.length) return null;
    return window.reduce((a, b) => a + b, 0) / window.length;
  }, [resolved]);

  const aspectCounts = useMemo(() => {
    const table = Object.fromEntries(ASPECT_ROWS.map((a) => [a, { positive: 0, negative: 0 }]));
    for (const d of resolved) {
      for (const aspect of ASPECT_ROWS) {
        const choice = d.answers?.[`aspect_${aspect}`]?.choice;
        if (choice === "positive" || choice === "negative") table[aspect][choice] += 1;
      }
    }
    return table;
  }, [resolved]);

  const latencies = useMemo(() => decisions.filter((d) => d.latency_ms != null).map((d) => d.latency_ms), [decisions]);
  const dps = useMemo(() => {
    const now = Date.now();
    return resolved.filter((d) => d.at && now - d.at <= 1000).length;
  }, [resolved]);

  // Plot whichever signal Phase 1 actually froze (p_top by default, or the provider's
  // own `confidence` if that was frozen instead) — not always p_top, or the panel's
  // header and its chart would disagree about which signal the gate claims.
  const routingSeries = useMemo(() => {
    const pick = GATE.polarity.routing.signal === "confidence"
      ? (d) => d.answers?.polarity?.confidence
      : (d) => topProbability(d.answers?.polarity);
    return resolved.map(pick).filter((v) => typeof v === "number");
  }, [resolved]);

  const statusLabel = { connecting: "CONNECTING", "no-bridge": "NO BRIDGE", "no-worker": "NO WORKER", ok: streamStale ? "NO REPLY STREAM" : "LIVE" }[status];
  const statusClass = { connecting: "warn", "no-bridge": "bad", "no-worker": "bad", ok: streamStale ? "bad" : "ok" }[status];

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark"><Radio size={18} /></div>
          <div>
            <small>ORBIT</small>
            <strong>Sentiment Pulse</strong>
          </div>
        </div>
        {!GATE.evaluated && <span className="badge dormant">DORMANT — gate not yet run</span>}
        {isExperimental() && <span className="badge experimental">EXPERIMENTAL</span>}
        <span className={`bridge-pill ${statusClass}`}><i />{statusLabel}</span>
        <div className="controls">
          <button
            className={`btn ${playing ? "paused" : ""}`}
            disabled={!canPublish}
            onClick={() => setPlaying((p) => !p)}
          >
            {playing ? <Pause size={15} /> : <Play size={15} />} {playing ? "Pause stream" : "Play"}
          </button>
          <button className="btn secondary" disabled={!canPublish} onClick={surge}>
            <Zap size={15} /> Surge (100)
          </button>
          <label className="range">
            items/sec
            <input
              type="range" min={1} max={20} value={settings.speed}
              onChange={(e) => setSettings({ speed: Number(e.target.value) })}
            />
            {settings.speed}
          </label>
          <button
            className={`btn secondary ${settings.pauseAllRequests ? "paused" : ""}`}
            onClick={() => { setPlaying(false); setSettings({ pauseAllRequests: !settings.pauseAllRequests }); }}
          >
            {settings.pauseAllRequests ? "Requests paused" : "Pause all requests"}
          </button>
        </div>
      </div>

      {/* No banner here by design — the dormant/gate-not-run explanation lives in
          examples/sentiment-pulse-dashboard/README.md instead, so the live view stays
          clean. The small "DORMANT" badge above is the only on-screen indicator. */}

      {status !== "ok" ? (
        <div className="no-state">
          <strong>{statusLabel}</strong>
          <p>
            {status === "no-bridge"
              ? `Can't reach the bridge at ${settings.bridgeUrl}. Run examples/triage-rush-mq/game_bridge.py --adapter sentiment-analysis --allowed-adapters sentiment-analysis,sentiment-analysis-local`
              : "The bridge is up but no worker is consuming orbit.requests — start an ORBIT worker."}
          </p>
        </div>
      ) : (
        <div className="grid">
          <section className="panel span-2 feed">
            <h2>Live feed {decisions.length > recent.length && <span className="queue-badge">+{decisions.length - recent.length} older</span>}</h2>
            {recent.length === 0 ? (
              <p className="empty">Press Play, or Surge, to start streaming reviews.</p>
            ) : (
              <div className="feed-list">
                {recent.map((d) => (
                  <FeedCard key={d.id} decision={d} />
                ))}
              </div>
            )}
          </section>

          {GATE.valence.passed && (
            <section className="panel">
              <h2>Mood gauge</h2>
              {moodRolling === null ? (
                <p className="empty">No answers yet.</p>
              ) : (
                <>
                  <div className="gauge-value">{VALENCE_LEVELS[Math.round(moodRolling)]}</div>
                  <Sparkline series={moodSeries} />
                </>
              )}
            </section>
          )}

          <section className="panel">
            <h2>Polarity distribution</h2>
            {polarityTotal === 0 ? (
              <p className="empty">No answers yet.</p>
            ) : (
              POLARITY_ORDER.map((p) => (
                <div className="bar-row" key={p}>
                  <span className="label">{p}</span>
                  <span className="bar-track"><span className="bar-fill" style={{ width: `${(100 * polarityCounts[p]) / polarityTotal}%` }} /></span>
                  <span className="count">{polarityCounts[p]}</span>
                </div>
              ))
            )}
          </section>

          {GATE.aspects.passed && (
          <section className="panel">
            <h2>Aspect heatmap</h2>
            <div className="heatmap">
              <span />
              <span className="hlabel" style={{ textAlign: "center" }}>positive</span>
              <span className="hlabel" style={{ textAlign: "center" }}>negative</span>
              {ASPECT_ROWS.map((aspect) => (
                <React.Fragment key={aspect}>
                  <span className="hlabel">{aspect}</span>
                  <span className="hcell">{aspectCounts[aspect].positive}</span>
                  <span className="hcell">{aspectCounts[aspect].negative}</span>
                </React.Fragment>
              ))}
            </div>
          </section>
          )}

          {showsEscalationLane() && (
            <section className="panel">
              <h2>Escalation lane</h2>
              <p className="empty">
                Expected false-alert share at t={GATE.escalation.threshold}: {GATE.escalation.falseAlertShare}
              </p>
              {resolved
                .filter((d) => (d.answers?.needs_escalation?.noul ?? 0) >= GATE.escalation.threshold)
                .sort((a, b) => (b.answers?.needs_escalation?.noul ?? 0) - (a.answers?.needs_escalation?.noul ?? 0))
                .slice(0, 8)
                .map((d) => <FeedCard key={d.id} decision={d} />)}
            </section>
          )}

          {showsRoutingLine() && (
            <section className="panel">
              <h2>Routing signal ({GATE.polarity.routing.signal})</h2>
              <p className="empty">
                Route to a person below t={GATE.polarity.routing.threshold} — held-out accepted error{" "}
                {GATE.polarity.routing.acceptedError}
              </p>
              <Sparkline series={routingSeries.map((v, i) => ({ at: i, valence: v * 4 }))} />
            </section>
          )}

          <section className="panel span-2">
            <h2>HUD</h2>
            <dl className="hud-row">
              <div className="hud-stat"><dt>Decisions/sec</dt><dd>{dps}</dd></div>
              <div className="hud-stat"><dt>p50 latency</dt><dd>{percentile(latencies, 50) ?? "—"} ms</dd></div>
              <div className="hud-stat"><dt>p95 latency</dt><dd>{percentile(latencies, 95) ?? "—"} ms</dd></div>
              <div className="hud-stat"><dt>Queue depth</dt><dd>{health?.in_flight ?? "—"}</dd></div>
              <div className="hud-stat"><dt>Workers</dt><dd>{health?.queue?.consumers ?? "—"}</dd></div>
            </dl>
            <p className="empty">
              Provider: {health?.key_adapter || health?.adapter || "—"} · Band:{" "}
              {GATE.evaluated ? GATE.polarity.band : "not evaluated"}
            </p>
          </section>

          <section className="panel span-2">
            <h2>Type your own</h2>
            <form className="own-form" onSubmit={submitOwn}>
              <input
                value={ownText}
                maxLength={280}
                placeholder="Write a sentence and see its full decision…"
                disabled={!canPublish || ownPublishing}
                onChange={(e) => setOwnText(e.target.value)}
              />
              <button className="btn" type="submit" disabled={!canPublish || ownPublishing || !ownText.trim()}>
                <Send size={15} /> Send
              </button>
            </form>
            {ownResult && (
              <div className="own-result">
                {ownResult.status === "pending" && <span className="empty">Waiting for a reply…</span>}
                {ownResult.status === "error" && <span className="chip error">{ownResult.error}</span>}
                {ownResult.status === "completed" && <FeedCard decision={{ ...ownResult, text: ownResult.text }} showText={false} />}
                {ownResult.status === "failed" && <span className="chip error">{ownResult.error || "Decision failed"}</span>}
                {ownResult.status === "timeout" && <span className="chip error">Timed out — no reply within the bridge's window.</span>}
              </div>
            )}
            <p className="empty">Never stored. Capped at 280 characters. Published only through the bridge — never fabricated.</p>
          </section>
        </div>
      )}

      <footer>
        <span>Session {SESSION}</span>
        <span>{connected ? "events stream connected" : "events stream idle"}</span>
      </footer>
    </div>
  );
}

function FeedCard({ decision, showText = true }) {
  const answers = decision.answers || {};
  const polarity = answers.polarity?.choice;
  const sarcasm = answers.sarcasm?.noul;
  return (
    <div className="feed-card">
      {showText && <div className="text">{decision.text}</div>}
      <div className="chips">
        {decision.status && decision.status !== "completed" && <span className="chip error">{decision.status}</span>}
        {polarity && <span className={`chip ${polarity}`}>{polarity}</span>}
        {GATE.valence.passed && typeof answers.valence?.score === "number" && (
          <span className="chip">{VALENCE_LEVELS[Math.round(answers.valence.score)]}</span>
        )}
        {GATE.sarcasm.passed && sarcasm > 0.5 && <span className="chip sarcasm">sarcasm</span>}
        {decision.latency_ms != null && <span className="chip">{decision.latency_ms} ms</span>}
      </div>
    </div>
  );
}

function Sparkline({ series }) {
  if (!series.length) return <svg className="sparkline" />;
  const values = series.map((p) => p.valence);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 4);
  const points = series
    .map((p, i) => {
      const x = (i / Math.max(1, series.length - 1)) * 100;
      const y = 100 - ((p.valence - min) / Math.max(1e-6, max - min)) * 100;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg className="sparkline" viewBox="0 0 100 100" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke="var(--cyan)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

createRoot(document.getElementById("root")).render(<Dashboard />);
