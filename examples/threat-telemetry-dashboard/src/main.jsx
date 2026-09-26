import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, Bot, Check, ChevronRight,
  CircleDot, Clock3, CloudCog, Command, Crosshair, Database, Download,
  Gauge, Hexagon, ListChecks, Pause, Play, Radio, Send, Server, Settings2,
  Shield, ShieldAlert, Signal, Sparkles, Target, Wifi, X, Zap,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./styles.css";

function Markdown({ text }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div>;
}

const prompts = [
  "Show critical detections in the last hour",
  "Which sensors need attention?",
  "Break down detections by object type",
  "List unresolved alerts by severity",
];

const SEVERITY_COLOR = { critical: "#ff5c5f", high: "#ff9d45", medium: "#f4d35e", low: "#4de4bd" };

const cls = (...values) => values.filter(Boolean).join(" ");
const clockTime = () => new Intl.DateTimeFormat("en-CA", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date());

// Backend timestamps are naive UTC strings ("YYYY-MM-DD HH:MM:SS.ffffff");
// treat them as UTC explicitly rather than letting the browser assume local time.
function parseUtc(value) {
  if (!value) return null;
  const iso = value.replace(" ", "T") + (value.endsWith("Z") ? "" : "Z");
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

function relativeTimeFromDate(date) {
  if (!date) return "—";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function toAlertRecord(a) {
  const raised = parseUtc(a.raised_at);
  return {
    kind: "alert",
    id: a.alert_id,
    object: `${a.object_type[0].toUpperCase()}${a.object_type.slice(1)} contact`,
    site: a.location_name,
    severity: a.severity,
    confidence: Math.round((a.confidence ?? 0) * 100),
    age: relativeTimeFromDate(raised),
    status: a.status === "open" ? "OPEN" : "ACK",
    operator: a.assigned_to || "Unassigned",
    x: a.x,
    y: a.y,
  };
}

function toSensorRecord(s) {
  return {
    kind: "sensor",
    id: s.label,
    sensor_id: s.sensor_id,
    name: s.name,
    type: s.type.toUpperCase(),
    location_name: s.location_name,
    x: s.x,
    y: s.y,
    status: s.status,
  };
}

function useLiveStats(statsUrl, { intervalMs = 3000 } = {}) {
  const [stats, setStats] = useState(null);
  const [reachable, setReachable] = useState(false);
  const [latencyMs, setLatencyMs] = useState(null);
  const [rateHistory, setRateHistory] = useState([]);

  useEffect(() => {
    if (intervalMs <= 0) return; // paused — freeze whatever was last fetched
    let active = true;
    const poll = async () => {
      const started = performance.now();
      try {
        const res = await fetch(statsUrl, { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const body = await res.json();
        if (!active) return;
        setStats(body);
        setReachable(true);
        setLatencyMs(Math.round(performance.now() - started));
        const perMin = Math.round((body.queue?.deliver_rate_per_sec ?? 0) * 60);
        setRateHistory(prev => [...prev.slice(-59), perMin]);
      } catch {
        if (active) { setReachable(false); setLatencyMs(null); }
      }
    };
    poll();
    const id = setInterval(poll, intervalMs);
    return () => { active = false; clearInterval(id); };
  }, [statsUrl, intervalMs]);

  return { stats, reachable, latencyMs, rateHistory };
}

async function acknowledgeAlert(statsUrl, alertId) {
  const base = statsUrl.replace(/\/stats\/?$/, "");
  const res = await fetch(`${base}/alerts/${encodeURIComponent(alertId)}/acknowledge`, { method: "POST" });
  if (!res.ok) throw new Error(`Acknowledge failed (${res.status})`);
  return res.json();
}

function sessionId() {
  let value = sessionStorage.getItem("orbit-threat-session");
  if (!value) {
    value = crypto.randomUUID?.() || String(Date.now());
    sessionStorage.setItem("orbit-threat-session", value);
  }
  return value;
}

async function askOrbit(apiUrl, apiKey, message) {
  const response = await fetch(`${apiUrl.replace(/\/$/, "")}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
      "X-Session-ID": sessionId(),
    },
    body: JSON.stringify({ model: "intent-sql-sqlite-threat-telemetry", messages: [{ role: "user", content: message }] }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.error?.message ?? body?.detail;
    let message = `Request failed (${response.status})`;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) {
      message = detail.map(item => {
        if (typeof item === "string") return item;
        const location = Array.isArray(item?.loc) ? `${item.loc.join(".")}: ` : "";
        return `${location}${item?.msg || JSON.stringify(item)}`;
      }).join("; ");
    } else if (detail && typeof detail === "object") message = JSON.stringify(detail);
    throw new Error(message);
  }
  return body?.choices?.[0]?.message?.content || "No response content returned.";
}

function Brand() {
  return <span className="brand-mark"><Hexagon size={31} strokeWidth={1.35} /><CircleDot className="brand-core" size={14} /></span>;
}

function LivePill({ children, live = true }) {
  return <span className={cls("status-pill", live && "is-live")}><i />{children}</span>;
}

function Header({ paused, setPaused, openSettings, activeView, setActiveView }) {
  const [time, setTime] = useState(clockTime());
  useEffect(() => {
    const id = setInterval(() => setTime(clockTime()), 1000);
    return () => clearInterval(id);
  }, []);
  return <>
    <header className="topbar">
      <div className="brand-block"><Brand /><div><small>ORBIT SYSTEMS</small><strong>THREAT COMMAND</strong></div></div>
      <div className="topbar-center"><LivePill live={!paused}>{paused ? "FEED PAUSED" : "SYSTEM OPERATIONAL"}</LivePill><span className="divider" /><span><Server size={13} /> NODE 04 / EASTERN GRID</span></div>
      <div className="top-actions">
        <button className="icon-button" onClick={() => setPaused(!paused)} title={paused ? "Resume live updates" : "Pause live updates"}>{paused ? <Play size={15} /> : <Pause size={15} />}</button>
        <button className="icon-button" onClick={openSettings} title="Connection settings"><Settings2 size={15} /></button>
        <span className="clock"><Clock3 size={13} />{time}<small>UTC-4</small></span>
      </div>
    </header>
    <nav className="subnav" aria-label="Primary dashboard views">
      <div>
        <button className={activeView === "overview" ? "active" : ""} onClick={() => setActiveView("overview")} aria-current={activeView === "overview" ? "page" : undefined}><Gauge size={14} /> COMMAND OVERVIEW</button>
        <button className={activeView === "incidents" ? "active" : ""} onClick={() => setActiveView("incidents")} aria-current={activeView === "incidents" ? "page" : undefined}><ShieldAlert size={14} /> INCIDENTS</button>
        <button className={activeView === "sensors" ? "active" : ""} onClick={() => setActiveView("sensors")} aria-current={activeView === "sensors" ? "page" : undefined}><Radio size={14} /> SENSOR NETWORK</button>
        <button className={activeView === "intelligence" ? "active" : ""} onClick={() => setActiveView("intelligence")} aria-current={activeView === "intelligence" ? "page" : undefined}><Database size={14} /> INTELLIGENCE</button>
      </div>
    </nav>
  </>;
}

function Metric({ icon: Icon, label, value, unit, tone = "cyan", live = true }) {
  return <article className={cls("metric", `tone-${tone}`)}>
    <div className="metric-head"><span>{label}</span><Icon size={16} /></div>
    <div className="metric-main"><strong>{live ? value : "—"}<small>{unit}</small></strong></div>
    <div className="metric-foot"><span>{live ? "LIVE" : "NO DATA"}</span></div>
  </article>;
}

function PanelHead({ kicker, title, children }) {
  return <div className="panel-head"><div><small>{kicker}</small><h2>{title}</h2></div>{children}</div>;
}

function TacticalMap({ sensors, alerts, selected, select, paused }) {
  return <section className="panel map-panel">
    <PanelHead kicker="SENSOR NETWORK" title="Sector overview"><div className="map-tools"><button className="active"><Crosshair size={12} />TRACKS</button><button><Radio size={12} />SENSORS</button></div></PanelHead>
    <div className="map-canvas">
      <svg viewBox="0 0 900 535" aria-label="Tactical sensor network map">
        <defs>
          <pattern id="smallGrid" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="rgba(120,190,176,.075)" /></pattern>
          <pattern id="grid" width="150" height="150" patternUnits="userSpaceOnUse"><rect width="150" height="150" fill="url(#smallGrid)" /><path d="M150 0H0V150" fill="none" stroke="rgba(120,190,176,.13)" /></pattern>
          <radialGradient id="glow"><stop stopColor="#2ce9bf" stopOpacity=".12"/><stop offset="1" stopColor="#2ce9bf" stopOpacity="0"/></radialGradient>
          <linearGradient id="sweep"><stop stopColor="#4cf2cb" stopOpacity="0"/><stop offset="1" stopColor="#4cf2cb" stopOpacity=".18"/></linearGradient>
        </defs>
        <rect width="900" height="535" fill="url(#grid)"/><circle cx="450" cy="268" r="260" fill="url(#glow)"/>
        <g className="terrain"><path d="M-40 395C95 318 160 362 257 298S443 214 548 257 742 384 950 242"/><path d="M-20 429C126 350 201 409 301 335S491 248 584 295 768 410 932 305"/><path d="M77 0C86 94 154 113 146 196S87 333 121 535"/><path d="M810 0C756 102 799 159 757 235S673 362 698 535"/></g>
        <g className="sector"><circle cx="450" cy="268" r="92"/><circle cx="450" cy="268" r="182"/><circle cx="450" cy="268" r="255"/><path d="M450 12V524M194 268H706M269 87L631 449M269 449L631 87"/></g>
        {!paused && <path className="radar-sweep" d="M450 268V14A254 254 0 0 1 630 88Z"/>}
        <g className="connections">{sensors.slice(1).map(s => <line key={s.id} x1="450" y1="268" x2={s.x * 9} y2={s.y * 5.35}/>)}</g>
        {sensors.map(sensor => {
          const x = sensor.x * 9, y = sensor.y * 5.35;
          return <g key={sensor.id} className={cls("sensor", sensor.status, selected?.id === sensor.id && "selected")} onClick={() => select(sensor)} role="button" tabIndex="0">
            <circle className="range" cx={x} cy={y} r="30"/><circle className="pulse" cx={x} cy={y} r="16"/><circle className="core" cx={x} cy={y} r="5"/><path d={`M${x-9} ${y-9}h5M${x+4} ${y-9}h5M${x-9} ${y+9}h5M${x+4} ${y+9}h5`}/><text className="sensor-label" x={x+17} y={y-10}>{sensor.id}</text><text className="sensor-sub" x={x+17} y={y+5}>{sensor.type} · {sensor.status.toUpperCase()}</text>
          </g>;
        })}
        {alerts.slice(0, 6).map(alert => <g key={alert.id} className={cls("threat", alert.severity)} onClick={() => select(alert)}><circle cx={alert.x*9} cy={alert.y*5.35} r="20"/><path d={`M${alert.x*9} ${alert.y*5.35-8}l8 15h-16Z`}/><text x={alert.x*9+24} y={alert.y*5.35+4}>{alert.id}</text></g>)}
      </svg>
      <div className="coordinates">38° 53' 42.1" N&nbsp; / &nbsp;77° 02' 34.6" W</div>
      <div className="map-legend"><span><i/>ONLINE</span><span><i className="warn"/>DEGRADED</span><span><i className="danger"/>OFFLINE</span></div>
    </div>
  </section>;
}

function Distribution({ distribution, total }) {
  const parts = ["critical", "high", "medium", "low"].map(sev => ({
    name: sev[0].toUpperCase() + sev.slice(1),
    value: distribution?.[sev]?.percent ?? 0,
    color: SEVERITY_COLOR[sev],
  }));
  let offset = 0;
  return <section className="panel distribution"><PanelHead kicker="LAST 24 HOURS" title="Threat distribution"/><div className="donut-layout"><div className="donut"><svg viewBox="0 0 120 120"><circle className="track" cx="60" cy="60" r="47"/>{parts.map(part => { const start = offset; offset += part.value; return <circle key={part.name} cx="60" cy="60" r="47" fill="none" stroke={part.color} strokeWidth="9" strokeDasharray={`${part.value*2.953} ${295.3-part.value*2.953}`} strokeDashoffset={-start*2.953}/>; })}</svg><div><strong>{total ?? 0}</strong><span>CONTACTS</span></div></div><div className="legend-list">{parts.map(part => <div key={part.name}><i style={{background: part.color}}/><span>{part.name}</span><strong>{part.value}%</strong></div>)}</div></div></section>;
}

function Throughput({ rate, history }) {
  const samples = history && history.length > 1 ? history : [0, 0];
  const max = Math.max(1, ...samples);
  const points = samples.map((value, i) => `${i/(samples.length-1)*600},${118-value/max*98}`).join(" ");
  return <section className="panel throughput"><PanelHead kicker="MESSAGE QUEUE · LIVE" title="Processing throughput"><div className="rate"><strong>{rate}</strong><span>msg/min</span></div></PanelHead><svg className="line-chart" viewBox="0 0 600 135" preserveAspectRatio="none"><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#40e3bd" stopOpacity=".25"/><stop offset="1" stopColor="#40e3bd" stopOpacity="0"/></linearGradient></defs>{[28,58,88,118].map(y => <line key={y} x1="0" y1={y} x2="600" y2={y}/>)}<polygon points={`0,135 ${points} 600,135`} fill="url(#chartFill)"/><polyline points={points}/><circle cx="600" cy={118-samples.at(-1)/max*98} r="4"/></svg><div className="chart-labels"><span>OLDEST SAMPLE</span><span>NOW</span></div></section>;
}

function Alerts({ alerts, selected, select, acknowledge }) {
  const canAcknowledge = selected?.kind === "alert" && selected.status === "OPEN";
  return <section className="panel alerts-panel"><PanelHead kicker="PRIORITY ORDER · LIVE" title={<>Active alerts <b>{alerts.length}</b></>}/><div className="alert-list">{alerts.length === 0 && <div className="burst-empty"><p>No open or acknowledged alerts.</p></div>}{alerts.map(alert => <button key={alert.id} className={cls("alert-row", selected?.id === alert.id && "selected")} onClick={() => select(alert)}><i className={cls("stripe", alert.severity)}/><span className={cls("alert-icon", alert.severity)}><AlertTriangle size={15}/></span><span className="alert-name"><strong>{alert.object}</strong><small>{alert.id} · {alert.site}</small></span><span className="confidence"><strong>{alert.confidence}%</strong><small>CONF</small></span><span className="age">{alert.age}</span><ChevronRight size={14}/></button>)}</div><div className="feed-footer"><button onClick={acknowledge} disabled={!canAcknowledge} title={canAcknowledge ? "Acknowledge selected alert" : "Select an open alert before acknowledging"}><Check size={13}/>{canAcknowledge ? "ACKNOWLEDGE SELECTED" : "SELECT AN OPEN ALERT"}</button><span>Sorted by severity</span></div></section>;
}

function Detail({ item }) {
  if (!item) return null;
  const sensor = item.kind === "sensor";
  return <aside className="detail"><small>{sensor ? "SENSOR DETAIL" : "SELECTED TRACK"}</small><div className="detail-title"><span className={cls("target", sensor ? item.status : item.severity)}><Target size={20}/></span><div><strong>{item.id}</strong><em>{item.object || item.type}</em></div></div><div className="detail-grid">
    <div><span>LOCATION</span><strong>{sensor ? item.location_name : item.site}</strong></div>
    <div><span>STATUS</span><strong>{sensor ? item.status?.toUpperCase() : item.status}</strong></div>
    {sensor
      ? <div><span>TYPE</span><strong>{item.type}</strong></div>
      : <div><span>CONFIDENCE</span><strong>{item.confidence}%</strong></div>}
    {!sensor && <div><span>DETECTED</span><strong>{item.age}</strong></div>}
  </div>{!sensor && <div className="assignment"><span>ASSIGNED OPERATOR</span><strong><i/>{item.operator}</strong></div>}</aside>;
}

function Intelligence({ config, openSettings, setConnected, forceOpen = false }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState(prompts[0]);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function ask(value) {
    const prompt = value || question.trim();
    if (!prompt) return;
    setQuestion(prompt); setOpen(true); setError(""); setLoading(true);
    if (!config.apiKey) { setError("Add an ORBIT API key to run intelligence queries."); setLoading(false); openSettings(); return; }
    try { setAnswer(await askOrbit(config.apiUrl, config.apiKey, prompt)); setConnected(true); }
    catch (err) { setError(err.message); setConnected(false); }
    finally { setLoading(false); }
  }
  const expanded = forceOpen || open;
  return <section className={cls("intel", expanded && "open", forceOpen && "standalone-intel")}><div className="intel-head" onClick={() => !forceOpen && setOpen(!open)}><span className="ai-icon"><Sparkles size={16}/></span><div><small>ORBIT INTELLIGENCE</small><strong>Ask the operational picture</strong></div><LivePill live={!!config.apiKey}>{config.apiKey ? "API CONFIGURED" : "NO API KEY"}</LivePill>{!forceOpen && <ChevronRight className="chevron" size={18}/>}</div><div className="intel-body"><div className="prompt-list">{prompts.map(prompt => <button key={prompt} onClick={() => ask(prompt)}>{prompt}</button>)}</div><div className="answer"><span><Bot size={13}/>ORBIT ANALYSIS</span>{loading ? <div className="thinking"><i/><i/><i/> Correlating telemetry</div> : error ? <p className="error">{error}</p> : answer ? <Markdown text={answer}/> : <p className="hint">Ask a question or click a suggestion above.</p>}</div><form onSubmit={event => { event.preventDefault(); ask(); }}><Command size={15}/><input value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask about detections, sensors, operators…"/><button disabled={loading}><Send size={14}/>ANALYZE</button></form></div></section>;
}

function relativeTime(ts) {
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.round(seconds / 60)}m ago`;
}

function QueryBurst({ statusUrl, setStatusUrl }) {
  const [monitoring, setMonitoringValue] = useState(() => localStorage.getItem("orbit-threat-burst-monitor") === "1");
  const [state, setState] = useState(null);
  const [reachable, setReachable] = useState(false);

  const setMonitoring = value => {
    setMonitoringValue(value);
    localStorage.setItem("orbit-threat-burst-monitor", value ? "1" : "0");
    if (!value) { setState(null); setReachable(false); }
  };

  useEffect(() => {
    if (!monitoring) return;
    let active = true;
    const poll = async () => {
      try {
        const res = await fetch(statusUrl, { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const body = await res.json();
        if (active) { setState(body); setReachable(true); }
      } catch {
        if (active) setReachable(false);
      }
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => { active = false; clearInterval(id); };
  }, [statusUrl, monitoring]);

  const results = state?.results ? state.results.slice().reverse() : [];
  const running = reachable && state && state.outstanding > 0;

  return <section className="panel query-burst">
    <PanelHead kicker="MESSAGE QUEUE · LIVE" title={<>Query burst monitor</>}>
      <div className="burst-controls">
        <LivePill live={running}>{!monitoring ? "MONITORING OFF" : !reachable ? "NO PRODUCER DETECTED" : running ? "IN PROGRESS" : "IDLE"}</LivePill>
        <button className="text-button" onClick={() => setMonitoring(!monitoring)}>{monitoring ? "STOP MONITORING" : "START MONITORING"}</button>
      </div>
    </PanelHead>
    <div className="burst-source">
      <span>STATUS SOURCE</span>
      <input value={statusUrl} onChange={e => setStatusUrl(e.target.value)} spellCheck={false} />
    </div>
    {!monitoring && <div className="burst-empty">
      <ListChecks size={20} />
      <p>Monitoring is off, so this panel isn't polling anything. Click <strong>START MONITORING</strong> before running <code>sensor_burst_producer.py</code> to watch replies arrive live.</p>
    </div>}
    {monitoring && !reachable && <div className="burst-empty">
      <ListChecks size={20} />
      <p>Waiting for <code>sensor_burst_producer.py</code>. Run it from a terminal to see each reply appear here as it arrives.</p>
    </div>}
    {monitoring && reachable && state && <>
      <div className="burst-tally">
        <span>PUBLISHED<strong>{state.burst_size}</strong></span>
        <span>COMPLETED<strong className="ok">{state.completed}</strong></span>
        <span>FAILED<strong className={state.failed ? "bad" : ""}>{state.failed}</strong></span>
        <span>OUTSTANDING<strong>{state.outstanding}</strong></span>
      </div>
      <div className="burst-list">
        {results.length === 0 && <div className="burst-empty"><p>Burst published — waiting on the first reply…</p></div>}
        {results.map((r, i) => <div key={`${r.question}-${r.received_at}-${i}`} className={cls("burst-row", r.status)}>
          <span className={cls("burst-status", r.status)}>{r.status === "completed" ? "OK" : "ERR"}</span>
          <div className="burst-body">
            <strong>{r.question}</strong>
            {r.response ? <Markdown text={r.response}/> : <p className="error">{r.error}</p>}
          </div>
          <small>{relativeTime(r.received_at)}</small>
        </div>)}
      </div>
    </>}
  </section>;
}

function ViewHeading({ kicker, title, description, children }) {
  return <div className="view-heading"><div><small>{kicker}</small><h2>{title}</h2><p>{description}</p></div>{children}</div>;
}

function IncidentView({ alerts, selected, select, acknowledge }) {
  const active = (selected?.kind === "alert" ? selected : alerts[0]) ?? null;
  return <section className="workspace-view">
    <ViewHeading kicker="INCIDENT OPERATIONS · LIVE" title="Incident queue" description="Review, prioritize, and acknowledge active threat records."><LivePill>{alerts.filter(item => item.status === "OPEN").length} OPEN</LivePill></ViewHeading>
    <div className="incident-workspace">
      <section className="panel incident-ledger">
        <div className="table-head"><span>INCIDENT</span><span>SEVERITY</span><span>LOCATION</span><span>CONFIDENCE</span><span>STATUS</span><span>ASSIGNEE</span></div>
        {alerts.length === 0 && <div className="burst-empty"><p>No open or acknowledged alerts.</p></div>}
        {alerts.map(alert => <button key={alert.id} className={cls("incident-row", active?.id === alert.id && "selected")} onClick={() => select(alert)}>
          <span className="incident-id"><i className={alert.severity}/><span><strong>{alert.object}</strong><small>{alert.id} · {alert.age}</small></span></span>
          <span className={cls("severity-label", alert.severity)}>{alert.severity}</span><span>{alert.site}</span><span>{alert.confidence}%</span><span>{alert.status}</span><span>{alert.operator}</span>
        </button>)}
      </section>
      {active && <aside className="panel record-panel">
        <div className="record-icon"><AlertTriangle size={22}/></div><small>SELECTED INCIDENT</small><h3>{active.id}</h3><p>{active.object}</p>
        <dl><div><dt>THREAT LEVEL</dt><dd className={active.severity}>{active.severity.toUpperCase()}</dd></div><div><dt>CONFIDENCE</dt><dd>{active.confidence}%</dd></div><div><dt>LOCATION</dt><dd>{active.site}</dd></div><div><dt>OPERATOR</dt><dd>{active.operator}</dd></div><div><dt>DETECTED</dt><dd>{active.age}</dd></div><div><dt>STATUS</dt><dd>{active.status}</dd></div></dl>
        <button className="record-action" onClick={() => acknowledge(active)} disabled={active.status === "ACK"}><Check size={14}/>{active.status === "ACK" ? "ALREADY ACKNOWLEDGED" : "ACKNOWLEDGE INCIDENT"}</button>
      </aside>}
    </div>
  </section>;
}

function SensorView({ sensors, selected, select, paused, alerts }) {
  const active = (selected?.kind === "sensor" ? selected : sensors[0]) ?? null;
  const online = sensors.filter(s => s.status === "online").length;
  const attention = sensors.length - online;
  return <section className="workspace-view">
    <ViewHeading kicker="NETWORK OPERATIONS · LIVE" title="Sensor network" description="Real sensor status and detection topology from the threat telemetry adapter's database."><span className="network-summary"><i/>{online} ONLINE {attention > 0 && <><i className="warn"/>{attention} ATTENTION</>}</span></ViewHeading>
    <div className="sensor-workspace">
      <TacticalMap sensors={sensors} alerts={alerts} selected={active} select={select} paused={paused}/>
      <section className="panel sensor-inventory"><PanelHead kicker="NODE INVENTORY · LIVE" title="Deployed sensors"/><div className="sensor-list">{sensors.map(sensor => <button key={sensor.id} className={cls("sensor-card", active?.id === sensor.id && "selected")} onClick={() => select(sensor)}><span className={cls("node-status", sensor.status)}/><span><strong>{sensor.name}</strong><small>{sensor.id} · {sensor.type}</small></span><span className="signal-value"><strong>{sensor.location_name}</strong><small>LOCATION</small></span><ChevronRight size={14}/></button>)}</div>{active && <div className="sensor-detail-strip"><span>SELECTED NODE</span><strong>{active.id}</strong><em>{active.status.toUpperCase()}</em></div>}</section>
    </div>
  </section>;
}

function IntelligenceView({ config, openSettings, setConnected, connected, burstStatusUrl, setBurstStatusUrl }) {
  return <section className="workspace-view intelligence-view">
    <ViewHeading kicker="NATURAL-LANGUAGE ANALYSIS" title="ORBIT intelligence" description="Query the threat telemetry adapter through the real ORBIT inference pipeline."><LivePill live={connected}>{connected ? "API CONNECTED" : "API DISCONNECTED"}</LivePill></ViewHeading>
    <div className="intelligence-workspace">
      <Intelligence config={config} openSettings={openSettings} setConnected={setConnected} forceOpen/>
      <aside className="panel intel-context"><PanelHead kicker="CONTEXT" title="Data boundary"/><div className="context-body"><Shield size={22}/><h3>{config.apiKey ? "Live inference enabled" : "No API key configured"}</h3><p>{config.apiKey ? "Questions in this workspace are sent to the configured ORBIT API and answered from the real intent-to-SQL pipeline." : "Add an ORBIT API key to send questions through the intent-to-SQL telemetry adapter."}</p><div><span>ADAPTER</span><strong>intent-sql-sqlite-threat-telemetry</strong></div><div><span>TRANSPORT</span><strong>HTTP(S) / Bearer</strong></div><button onClick={openSettings}><Settings2 size={14}/>CONNECTION SETTINGS</button></div></aside>
    </div>
    <QueryBurst statusUrl={burstStatusUrl} setStatusUrl={setBurstStatusUrl}/>
  </section>;
}

function Settings({ config, close, save }) {
  const [draft, setDraft] = useState(config);
  const [validation, setValidation] = useState("");
  const submit = () => {
    if (!/^https?:\/\//i.test(draft.apiUrl.trim())) {
      setValidation("Enter an HTTP or HTTPS ORBIT URL, including the scheme.");
      return;
    }
    setValidation("");
    save(draft);
  };
  return <div className="backdrop" onMouseDown={event => event.target === event.currentTarget && close()}><section className="modal"><div className="modal-head"><div><small>LIVE CONNECTION</small><h2>Connect to ORBIT</h2></div><button className="icon-button" onClick={close}><X size={17}/></button></div><p>The API key is kept only for this browser tab. Use a key scoped to <code>intent-sql-sqlite-threat-telemetry</code>.</p><label><span>ORBIT API URL</span><input value={draft.apiUrl} onChange={e => setDraft({...draft, apiUrl: e.target.value})}/></label><label><span>API KEY</span><input type="password" value={draft.apiKey} onChange={e => setDraft({...draft, apiKey: e.target.value})} placeholder="orbit_…"/></label>{validation && <div className="validation-error">{validation}</div>}<div className="note"><Shield size={15}/><span>The dashboard calls ORBIT over HTTP(S). RabbitMQ stays isolated behind the worker.</span></div><div className="modal-actions"><button onClick={close}>CANCEL</button><button className="primary" onClick={submit}><Wifi size={14}/>SAVE & CONNECT</button></div></section></div>;
}

function App() {
  const [activeView, setActiveView] = useState("overview");
  const [paused, setPaused] = useState(false);
  const [settings, setSettings] = useState(false);
  const [connected, setConnected] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [statsUrl, setStatsUrlValue] = useState(() => localStorage.getItem("orbit-threat-stats-url") || "http://localhost:8790/stats");
  const [burstStatusUrl, setBurstStatusUrl] = useState(() => localStorage.getItem("orbit-threat-burst-url") || "http://localhost:8787/status");
  const [config, setConfig] = useState(() => {
    // Remove credentials persisted by dashboard versions prior to session-only storage.
    localStorage.removeItem("orbit-threat-key");
    return {
      apiUrl: localStorage.getItem("orbit-threat-url") || "http://localhost:3000",
      apiKey: sessionStorage.getItem("orbit-threat-key") || "",
    };
  });

  const { stats, reachable: statsReachable, latencyMs, rateHistory } = useLiveStats(statsUrl, { intervalMs: paused ? 0 : 3000 });

  const sensors = (stats?.sensors ?? []).map(toSensorRecord);
  const alerts = (stats?.unresolved_alerts ?? []).map(toAlertRecord);
  const selectedItem = alerts.find(a => a.id === selectedId) ?? sensors.find(s => s.id === selectedId) ?? null;
  const select = item => setSelectedId(item?.id ?? null);

  useEffect(() => {
    if (selectedId === null && alerts.length > 0) setSelectedId(alerts[0].id);
  }, [selectedId, alerts.length]);

  useEffect(() => {
    if (paused || !config.apiKey) return;
    let active = true;
    const sync = async () => { try { await askOrbit(config.apiUrl, config.apiKey, "How many open alerts are there right now?"); if (active) setConnected(true); } catch { if (active) setConnected(false); } };
    sync(); const id = setInterval(sync, 30000); return () => { active = false; clearInterval(id); };
  }, [paused, config]);

  const save = draft => { const next = { apiUrl: draft.apiUrl.trim().replace(/\/$/, ""), apiKey: draft.apiKey.trim() }; setConfig(next); localStorage.setItem("orbit-threat-url", next.apiUrl); sessionStorage.setItem("orbit-threat-key", next.apiKey); setSettings(false); };
  const acknowledge = async target => {
    const incident = target?.kind === "alert" ? target : selectedItem;
    if (incident?.kind !== "alert" || incident.status !== "OPEN") return;
    try { await acknowledgeAlert(statsUrl, incident.id); } catch { /* next poll will reflect the current server state either way */ }
  };
  const exportData = () => { const url = URL.createObjectURL(new Blob([JSON.stringify({ generatedAt: new Date().toISOString(), stats }, null, 2)], {type: "application/json"})); const link = document.createElement("a"); link.href = url; link.download = `orbit-threat-snapshot-${Date.now()}.json`; link.click(); URL.revokeObjectURL(url); };
  const setStatsUrl = value => { setStatsUrlValue(value); localStorage.setItem("orbit-threat-stats-url", value); };
  const setBurstUrl = value => { setBurstStatusUrl(value); localStorage.setItem("orbit-threat-burst-url", value); };

  const lastDetection = parseUtc(stats?.last_detection_at);
  const queueDepth = statsReachable && stats?.queue?.available ? stats.queue.messages_ready + stats.queue.messages_unacknowledged : null;
  const throughputPerMin = statsReachable && stats?.queue?.available ? Math.round(stats.queue.deliver_rate_per_sec * 60) : null;

  return <div className="app-shell"><Header paused={paused} setPaused={setPaused} openSettings={() => setSettings(true)} activeView={activeView} setActiveView={setActiveView}/><main>
    <div className={cls("provenance-banner", statsReachable && "live-context")}><Shield size={13}/><strong>{statsReachable ? "LIVE OPERATIONAL DATA" : "STATS SERVER UNREACHABLE"}</strong><span>{statsReachable ? "Sensor status, detections, alerts, and queue depth are read live from threat_telemetry.db and RabbitMQ. Only the map's node layout is illustrative." : `Start live_stats_server.py and confirm the URL below (${statsUrl}).`}</span><input className="stats-source" value={statsUrl} onChange={e => setStatsUrl(e.target.value)} spellCheck={false}/></div>
    <section className="mission"><div><small>MISSION STATUS</small><h1>Eastern Grid <span>/</span> Perimeter Watch</h1></div><div className="mission-meta"><span><Activity size={13}/>LAST DETECTION <strong>{lastDetection ? relativeTimeFromDate(lastDetection) : "—"}</strong></span><span><CloudCog size={13}/>MQ DEPTH <strong>{queueDepth ?? "—"}</strong></span><span><Signal size={13}/>STATS LATENCY <strong>{latencyMs != null ? `${latencyMs}ms` : "—"}</strong></span><button onClick={exportData}><Download size={13}/>EXPORT</button></div></section>
    {activeView === "overview" && <>
      <section className="metrics">
        <Metric icon={ShieldAlert} label="ACTIVE THREATS" value={stats?.open_alerts} tone="red" live={statsReachable}/>
        <Metric icon={Radio} label="SENSORS ONLINE" value={stats?.sensors_online} unit={stats ? `/ ${stats.sensors_total}` : ""} live={statsReachable}/>
        <Metric icon={Crosshair} label="DETECTIONS / HR" value={stats?.detections_last_hour} tone="amber" live={statsReachable}/>
        <Metric icon={Zap} label="MQ THROUGHPUT" value={throughputPerMin} unit="/m" tone="violet" live={statsReachable && !!stats?.queue?.available}/>
      </section>
      <section className="dashboard-grid"><TacticalMap sensors={sensors} alerts={alerts} selected={selectedItem} select={select} paused={paused}/><div className="right-stack"><Distribution distribution={stats?.distribution_24h} total={stats?.distribution_total_24h}/><Throughput rate={throughputPerMin ?? 0} history={rateHistory}/></div><Alerts alerts={alerts} selected={selectedItem} select={select} acknowledge={acknowledge}/><Detail item={selectedItem}/></section>
      <Intelligence config={config} openSettings={() => setSettings(true)} setConnected={setConnected}/>
      <QueryBurst statusUrl={burstStatusUrl} setStatusUrl={setBurstUrl}/>
    </>}
    {activeView === "incidents" && <IncidentView alerts={alerts} selected={selectedItem} select={select} acknowledge={acknowledge}/>}
    {activeView === "sensors" && <SensorView sensors={sensors} alerts={alerts} selected={selectedItem} select={select} paused={paused}/>}
    {activeView === "intelligence" && <IntelligenceView config={config} openSettings={() => setSettings(true)} setConnected={setConnected} connected={connected} burstStatusUrl={burstStatusUrl} setBurstStatusUrl={setBurstUrl}/>}
  </main><footer><span><Brand/>ORBIT THREAT TELEMETRY</span><span>LIVE STATS <i className={statsReachable ? "good" : ""}/>{statsReachable ? "CONNECTED" : "DISCONNECTED"}</span><span>ORBIT API <i className={connected ? "good" : ""}/>{connected ? "CONNECTED" : "DISCONNECTED"}</span><span>CLASSIFICATION // DEMONSTRATION</span></footer>{settings && <Settings config={config} close={() => setSettings(false)} save={save}/>}</div>;
}

createRoot(document.getElementById("root")).render(<App/>);
