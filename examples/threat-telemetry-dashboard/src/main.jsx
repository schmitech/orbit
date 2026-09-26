import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, ArrowUpRight, Bot, Check, ChevronRight,
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

const sensors = [
  { kind: "sensor", id: "SEN-001", name: "North Perimeter", type: "RADAR", x: 45, y: 18, status: "online", signal: 98 },
  { kind: "sensor", id: "SEN-002", name: "East Gate", type: "OPTICAL", x: 78, y: 43, status: "online", signal: 94 },
  { kind: "sensor", id: "SEN-003", name: "Harbor Watch", type: "ACOUSTIC", x: 67, y: 75, status: "degraded", signal: 62 },
  { kind: "sensor", id: "SEN-004", name: "West Ridge", type: "UAV", x: 21, y: 39, status: "online", signal: 91 },
  { kind: "sensor", id: "SEN-005", name: "South Fence", type: "PERIMETER", x: 38, y: 81, status: "online", signal: 97 },
  { kind: "sensor", id: "SEN-006", name: "Overwatch B", type: "RADAR", x: 64, y: 29, status: "offline", signal: 0 },
];

const initialAlerts = [
  { kind: "alert", id: "ALR-0942", object: "Unknown aircraft", site: "North Perimeter", severity: "critical", confidence: 98, age: "12 sec", status: "OPEN", operator: "Unassigned", x: 47, y: 22 },
  { kind: "alert", id: "ALR-0941", object: "Fast-moving vehicle", site: "East Gate", severity: "high", confidence: 94, age: "48 sec", status: "OPEN", operator: "M. Chen", x: 75, y: 47 },
  { kind: "alert", id: "ALR-0938", object: "Unidentified person", site: "South Fence", severity: "high", confidence: 87, age: "2 min", status: "ACK", operator: "J. Alvarez", x: 40, y: 77 },
  { kind: "alert", id: "ALR-0934", object: "Acoustic anomaly", site: "Harbor Watch", severity: "medium", confidence: 76, age: "5 min", status: "OPEN", operator: "R. Singh", x: 66, y: 71 },
  { kind: "alert", id: "ALR-0929", object: "Low-altitude aircraft", site: "West Ridge", severity: "medium", confidence: 82, age: "11 min", status: "ACK", operator: "K. Novak", x: 25, y: 35 },
];

const prompts = [
  "Show critical detections in the last hour",
  "Which sensors need attention?",
  "Break down detections by object type",
  "List unresolved alerts by severity",
];

const chart = [31, 38, 34, 48, 43, 59, 55, 67, 61, 78, 73, 92, 81, 87, 76, 94, 89, 103, 97, 116, 108, 123, 118, 131];
const cls = (...values) => values.filter(Boolean).join(" ");
const clockTime = () => new Intl.DateTimeFormat("en-CA", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date());

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

function SimulatedBadge() {
  return <span className="simulated-badge" title="Presentation data — not sourced from ORBIT or RabbitMQ">SIMULATED</span>;
}

function Header({ mode, setMode, paused, setPaused, openSettings, activeView, setActiveView }) {
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
        <div className="mode-switch"><button className={mode === "demo" ? "active" : ""} onClick={() => setMode("demo")}>DEMO</button><button className={mode === "live" ? "active" : ""} onClick={() => setMode("live")}>LIVE</button></div>
        <button className="icon-button" onClick={() => setPaused(!paused)} title={paused ? "Resume" : "Pause"}>{paused ? <Play size={15} /> : <Pause size={15} />}</button>
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

function Metric({ icon: Icon, label, value, unit, delta, tone = "cyan", values }) {
  const data = values || [14, 17, 15, 22, 19, 27, 25, 31, 28, 34];
  const path = data.map((point, i) => `${i ? "L" : "M"}${i * 12},${38 - point}`).join(" ");
  return <article className={cls("metric", `tone-${tone}`)}>
    <div className="metric-head"><span>{label} <SimulatedBadge /></span><Icon size={16} /></div>
    <div className="metric-main"><strong>{value}<small>{unit}</small></strong><svg viewBox="0 0 108 40" preserveAspectRatio="none"><path className="fill" d={`${path} L108,40 L0,40 Z`} /><path d={path} /></svg></div>
    <div className="metric-foot"><ArrowUpRight size={12} /><span>{delta}</span><small>VS PREVIOUS HOUR</small></div>
  </article>;
}

function PanelHead({ kicker, title, children }) {
  return <div className="panel-head"><div><small>{kicker}</small><h2>{title}</h2></div>{children}</div>;
}

function TacticalMap({ selected, select, paused }) {
  return <section className="panel map-panel">
    <PanelHead kicker="PRESENTATION TOPOLOGY" title={<>Sector overview <SimulatedBadge /></>}><div className="map-tools"><button className="active"><Crosshair size={12} />TRACKS</button><button><Radio size={12} />SENSORS</button></div></PanelHead>
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
          return <g key={sensor.id} className={cls("sensor", sensor.status, selected?.site === sensor.name && "selected")} onClick={() => select({ ...sensor, site: sensor.name, severity: sensor.status === "offline" ? "critical" : "low" })} role="button" tabIndex="0">
            <circle className="range" cx={x} cy={y} r="30"/><circle className="pulse" cx={x} cy={y} r="16"/><circle className="core" cx={x} cy={y} r="5"/><path d={`M${x-9} ${y-9}h5M${x+4} ${y-9}h5M${x-9} ${y+9}h5M${x+4} ${y+9}h5`}/><text className="sensor-label" x={x+17} y={y-10}>{sensor.id}</text><text className="sensor-sub" x={x+17} y={y+5}>{sensor.type} · {sensor.status.toUpperCase()}</text>
          </g>;
        })}
        {initialAlerts.slice(0, 3).map(alert => <g key={alert.id} className={cls("threat", alert.severity)} onClick={() => select(alert)}><circle cx={alert.x*9} cy={alert.y*5.35} r="20"/><path d={`M${alert.x*9} ${alert.y*5.35-8}l8 15h-16Z`}/><text x={alert.x*9+24} y={alert.y*5.35+4}>{alert.id}</text></g>)}
      </svg>
      <div className="coordinates">38° 53' 42.1" N&nbsp; / &nbsp;77° 02' 34.6" W</div>
      <div className="map-legend"><span><i/>ONLINE</span><span><i className="warn"/>DEGRADED</span><span><i className="danger"/>OFFLINE</span></div>
    </div>
  </section>;
}

function Distribution() {
  const parts = [{ name: "Critical", value: 12, color: "#ff5c5f" }, { name: "High", value: 27, color: "#ff9d45" }, { name: "Medium", value: 38, color: "#f4d35e" }, { name: "Low", value: 23, color: "#4de4bd" }];
  let offset = 0;
  return <section className="panel distribution"><PanelHead kicker="LAST 24 HOURS · SIMULATED" title="Threat distribution"><ChevronRight size={16}/></PanelHead><div className="donut-layout"><div className="donut"><svg viewBox="0 0 120 120"><circle className="track" cx="60" cy="60" r="47"/>{parts.map(part => { const start = offset; offset += part.value; return <circle key={part.name} cx="60" cy="60" r="47" fill="none" stroke={part.color} strokeWidth="9" strokeDasharray={`${part.value*2.953} ${295.3-part.value*2.953}`} strokeDashoffset={-start*2.953}/>; })}</svg><div><strong>143</strong><span>CONTACTS</span></div></div><div className="legend-list">{parts.map(part => <div key={part.name}><i style={{background: part.color}}/><span>{part.name}</span><strong>{part.value}%</strong></div>)}</div></div></section>;
}

function Throughput({ rate }) {
  const max = Math.max(...chart);
  const points = chart.map((value, i) => `${i/(chart.length-1)*600},${118-value/max*98}`).join(" ");
  return <section className="panel throughput"><PanelHead kicker="MESSAGE QUEUE · SIMULATED" title="Processing throughput"><div className="rate"><strong>{rate}</strong><span>msg/min</span></div></PanelHead><svg className="line-chart" viewBox="0 0 600 135" preserveAspectRatio="none"><defs><linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#40e3bd" stopOpacity=".25"/><stop offset="1" stopColor="#40e3bd" stopOpacity="0"/></linearGradient></defs>{[28,58,88,118].map(y => <line key={y} x1="0" y1={y} x2="600" y2={y}/>)}<polygon points={`0,135 ${points} 600,135`} fill="url(#chartFill)"/><polyline points={points}/><circle cx="600" cy={118-chart.at(-1)/max*98} r="4"/></svg><div className="chart-labels"><span>-60 MIN</span><span>-45</span><span>-30</span><span>-15</span><span>NOW</span></div></section>;
}

function Alerts({ alerts, selected, select, acknowledge }) {
  const canAcknowledge = selected?.kind === "alert";
  return <section className="panel alerts-panel"><PanelHead kicker="PRIORITY ORDER · SIMULATED" title={<>Active alerts <b>{alerts.length}</b></>}><button className="text-button"><Settings2 size={13}/>FILTER</button></PanelHead><div className="alert-list">{alerts.map(alert => <button key={alert.id} className={cls("alert-row", selected?.id === alert.id && "selected")} onClick={() => select(alert)}><i className={cls("stripe", alert.severity)}/><span className={cls("alert-icon", alert.severity)}><AlertTriangle size={15}/></span><span className="alert-name"><strong>{alert.object}</strong><small>{alert.id} · {alert.site}</small></span><span className="confidence"><strong>{alert.confidence}%</strong><small>CONF</small></span><span className="age">{alert.age}</span><ChevronRight size={14}/></button>)}</div><div className="feed-footer"><button onClick={acknowledge} disabled={!canAcknowledge} title={canAcknowledge ? "Acknowledge selected alert" : "Select an alert before acknowledging"}><Check size={13}/>{canAcknowledge ? "ACKNOWLEDGE SELECTED" : "SELECT AN ALERT TO ACKNOWLEDGE"}</button><span>Sorted by threat score</span></div></section>;
}

function Detail({ item }) {
  if (!item) return null;
  const sensor = item.kind === "sensor";
  return <aside className="detail"><small>{sensor ? "SENSOR DETAIL" : "SELECTED TRACK"}</small><div className="detail-title"><span className={cls("target", item.severity)}><Target size={20}/></span><div><strong>{item.id}</strong><em>{item.object || item.type}</em></div></div><div className="detail-grid"><div><span>LOCATION</span><strong>{item.site || item.name}</strong></div><div><span>STATUS</span><strong>{item.status || item.severity?.toUpperCase()}</strong></div><div><span>{sensor ? "SIGNAL" : "CONFIDENCE"}</span><strong>{item.signal ?? item.confidence}%</strong></div><div><span>{sensor ? "LAST PING" : "DETECTED"}</span><strong>{sensor ? "4 sec ago" : item.age}</strong></div></div>{!sensor && <div className="assignment"><span>ASSIGNED OPERATOR</span><strong><i/>{item.operator}</strong></div>}<button>OPEN FULL RECORD <ArrowUpRight size={13}/></button></aside>;
}

function Intelligence({ mode, config, openSettings, setConnected, forceOpen = false }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState(prompts[0]);
  const [answer, setAnswer] = useState("Critical activity is concentrated at North Perimeter. Five high-confidence tracks were detected inside the last hour; one remains unassigned.");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  async function ask(value) {
    const prompt = value || question.trim();
    if (!prompt) return;
    setQuestion(prompt); setOpen(true); setError(""); setLoading(true);
    if (mode === "demo") {
      setTimeout(() => { setAnswer("ORBIT correlated 143 contacts across six sensor sites. Immediate attention is recommended for ALR-0942 at North Perimeter; confidence is 98% and no operator is assigned. Harbor Watch is degraded and Overwatch B is offline."); setLoading(false); }, 650);
      return;
    }
    if (!config.apiKey) { setError("Add an ORBIT API key to run live intelligence queries."); setLoading(false); openSettings(); return; }
    try { setAnswer(await askOrbit(config.apiUrl, config.apiKey, prompt)); setConnected(true); }
    catch (err) { setError(err.message); setConnected(false); }
    finally { setLoading(false); }
  }
  const expanded = forceOpen || open;
  return <section className={cls("intel", expanded && "open", forceOpen && "standalone-intel")}><div className="intel-head" onClick={() => !forceOpen && setOpen(!open)}><span className="ai-icon"><Sparkles size={16}/></span><div><small>ORBIT INTELLIGENCE</small><strong>Ask the operational picture</strong></div><LivePill>{mode === "live" ? "LIVE ADAPTER" : "DEMO READY"}</LivePill>{!forceOpen && <ChevronRight className="chevron" size={18}/>}</div><div className="intel-body"><div className="prompt-list">{prompts.map(prompt => <button key={prompt} onClick={() => ask(prompt)}>{prompt}</button>)}</div><div className="answer"><span><Bot size={13}/>ORBIT ANALYSIS</span>{loading ? <div className="thinking"><i/><i/><i/> Correlating telemetry</div> : error ? <p className="error">{error}</p> : <Markdown text={answer}/>}</div><form onSubmit={event => { event.preventDefault(); ask(); }}><Command size={15}/><input value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask about detections, sensors, operators…"/><button disabled={loading}><Send size={14}/>ANALYZE</button></form></div></section>;
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
  const active = selected?.kind === "alert" ? selected : alerts[0];
  return <section className="workspace-view">
    <ViewHeading kicker="INCIDENT OPERATIONS · SIMULATED" title="Incident queue" description="Review, prioritize, and acknowledge active threat records."><LivePill>{alerts.filter(item => item.status === "OPEN").length} OPEN</LivePill></ViewHeading>
    <div className="incident-workspace">
      <section className="panel incident-ledger">
        <div className="table-head"><span>INCIDENT</span><span>SEVERITY</span><span>LOCATION</span><span>CONFIDENCE</span><span>STATUS</span><span>ASSIGNEE</span></div>
        {alerts.map(alert => <button key={alert.id} className={cls("incident-row", active.id === alert.id && "selected")} onClick={() => select(alert)}>
          <span className="incident-id"><i className={alert.severity}/><span><strong>{alert.object}</strong><small>{alert.id} · {alert.age} ago</small></span></span>
          <span className={cls("severity-label", alert.severity)}>{alert.severity}</span><span>{alert.site}</span><span>{alert.confidence}%</span><span>{alert.status}</span><span>{alert.operator}</span>
        </button>)}
      </section>
      <aside className="panel record-panel">
        <div className="record-icon"><AlertTriangle size={22}/></div><small>SELECTED INCIDENT</small><h3>{active.id}</h3><p>{active.object}</p>
        <dl><div><dt>THREAT LEVEL</dt><dd className={active.severity}>{active.severity.toUpperCase()}</dd></div><div><dt>CONFIDENCE</dt><dd>{active.confidence}%</dd></div><div><dt>LOCATION</dt><dd>{active.site}</dd></div><div><dt>OPERATOR</dt><dd>{active.operator}</dd></div><div><dt>DETECTED</dt><dd>{active.age} ago</dd></div><div><dt>STATUS</dt><dd>{active.status}</dd></div></dl>
        <button className="record-action" onClick={() => acknowledge(active)} disabled={active.status === "ACK"}><Check size={14}/>{active.status === "ACK" ? "ALREADY ACKNOWLEDGED" : "ACKNOWLEDGE INCIDENT"}</button>
      </aside>
    </div>
  </section>;
}

function SensorView({ selected, select, paused }) {
  const active = selected?.kind === "sensor" ? selected : sensors[0];
  return <section className="workspace-view">
    <ViewHeading kicker="NETWORK OPERATIONS · SIMULATED" title="Sensor network" description="Inspect the presentation topology and current simulated node health."><span className="network-summary"><i/>5 ONLINE <i className="warn"/>1 ATTENTION</span></ViewHeading>
    <div className="sensor-workspace">
      <TacticalMap selected={active} select={select} paused={paused}/>
      <section className="panel sensor-inventory"><PanelHead kicker="NODE INVENTORY · SIMULATED" title="Deployed sensors"/><div className="sensor-list">{sensors.map(sensor => <button key={sensor.id} className={cls("sensor-card", active.id === sensor.id && "selected")} onClick={() => select({...sensor, site: sensor.name, severity: sensor.status === "offline" ? "critical" : "low"})}><span className={cls("node-status", sensor.status)}/><span><strong>{sensor.name}</strong><small>{sensor.id} · {sensor.type}</small></span><span className="signal-value"><strong>{sensor.signal}%</strong><small>SIGNAL</small></span><ChevronRight size={14}/></button>)}</div><div className="sensor-detail-strip"><span>SELECTED NODE</span><strong>{active.id}</strong><em>{active.status.toUpperCase()}</em></div></section>
    </div>
  </section>;
}

function IntelligenceView({ mode, config, openSettings, setConnected, connected, burstStatusUrl, setBurstStatusUrl }) {
  return <section className="workspace-view intelligence-view">
    <ViewHeading kicker="NATURAL-LANGUAGE ANALYSIS" title="ORBIT intelligence" description="Query the threat telemetry adapter through the real ORBIT inference pipeline."><LivePill live={mode === "demo" || connected}>{mode === "demo" ? "DEMO RESPONSES" : connected ? "API CONNECTED" : "API DISCONNECTED"}</LivePill></ViewHeading>
    <div className="intelligence-workspace">
      <Intelligence mode={mode} config={config} openSettings={openSettings} setConnected={setConnected} forceOpen/>
      <aside className="panel intel-context"><PanelHead kicker="CONTEXT" title="Data boundary"/><div className="context-body"><Shield size={22}/><h3>{mode === "live" ? "Live inference enabled" : "Demonstration responses"}</h3><p>{mode === "live" ? "Questions in this workspace are sent to the configured ORBIT API. The operational map and counters remain simulated." : "Switch to Live mode to send questions through the intent-to-SQL telemetry adapter."}</p><div><span>ADAPTER</span><strong>intent-sql-sqlite-threat-telemetry</strong></div><div><span>TRANSPORT</span><strong>{mode === "live" ? "HTTP(S) / Bearer" : "Local simulation"}</strong></div><button onClick={openSettings}><Settings2 size={14}/>CONNECTION SETTINGS</button></div></aside>
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
  const [mode, setModeValue] = useState("demo");
  const [paused, setPaused] = useState(false);
  const [settings, setSettings] = useState(false);
  const [connected, setConnected] = useState(false);
  const [alerts, setAlerts] = useState(initialAlerts);
  const [selected, setSelected] = useState(initialAlerts[0]);
  const [throughput, setThroughput] = useState(128);
  const [queue, setQueue] = useState(8);
  const [lastEvent, setLastEvent] = useState(clockTime());
  const [burstStatusUrl, setBurstStatusUrl] = useState(() => localStorage.getItem("orbit-threat-burst-url") || "http://localhost:8787/status");
  const [config, setConfig] = useState(() => {
    // Remove credentials persisted by dashboard versions prior to session-only storage.
    localStorage.removeItem("orbit-threat-key");
    return {
      apiUrl: localStorage.getItem("orbit-threat-url") || "http://localhost:3000",
      apiKey: sessionStorage.getItem("orbit-threat-key") || "",
    };
  });

  const setMode = value => { setModeValue(value); if (value === "live" && !config.apiKey) setSettings(true); };
  useEffect(() => {
    if (paused) return;
    const id = setInterval(() => { setThroughput(value => Math.max(112, Math.min(148, value + Math.floor(Math.random()*9)-4))); setQueue(Math.floor(Math.random()*12)+2); setLastEvent(clockTime()); }, 2200);
    return () => clearInterval(id);
  }, [paused]);
  useEffect(() => {
    if (mode !== "live" || paused || !config.apiKey) return;
    let active = true;
    const sync = async () => { try { await askOrbit(config.apiUrl, config.apiKey, "How many open alerts are there right now?"); if (active) { setConnected(true); setLastEvent(clockTime()); } } catch { if (active) setConnected(false); } };
    sync(); const id = setInterval(sync, 30000); return () => { active = false; clearInterval(id); };
  }, [mode, paused, config]);
  const save = draft => { const next = { apiUrl: draft.apiUrl.trim().replace(/\/$/, ""), apiKey: draft.apiKey.trim() }; setConfig(next); localStorage.setItem("orbit-threat-url", next.apiUrl); sessionStorage.setItem("orbit-threat-key", next.apiKey); setModeValue("live"); setSettings(false); };
  const acknowledge = target => { const incident = target?.kind === "alert" ? target : selected; if (incident?.kind !== "alert") return; const update = item => item.id === incident.id ? {...item, status: "ACK", operator: item.operator === "Unassigned" ? "Demo Operator" : item.operator} : item; setAlerts(value => value.map(update)); setSelected(update(incident)); };
  const exportData = () => { const url = URL.createObjectURL(new Blob([JSON.stringify({ generatedAt: new Date().toISOString(), mode, alerts, sensors }, null, 2)], {type: "application/json"})); const link = document.createElement("a"); link.href = url; link.download = `orbit-threat-snapshot-${Date.now()}.json`; link.click(); URL.revokeObjectURL(url); };
  const healthy = mode === "demo" || connected;
  const setBurstUrl = value => { setBurstStatusUrl(value); localStorage.setItem("orbit-threat-burst-url", value); };

  return <div className="app-shell"><Header mode={mode} setMode={setMode} paused={paused} setPaused={setPaused} openSettings={() => setSettings(true)} activeView={activeView} setActiveView={setActiveView}/><main>
    <div className={cls("provenance-banner", mode === "live" && "live-context")}><Shield size={13}/><strong>{mode === "live" ? "LIVE ORBIT INTELLIGENCE" : "DEMONSTRATION MODE"}</strong><span>{mode === "live" ? "Chat and connection status are live. Map, alerts, sensors, latency, and MQ metrics remain simulated presentation data." : "All operational data on this screen is simulated."}</span></div>
    <section className="mission"><div><small>MISSION STATUS</small><h1>Eastern Grid <span>/</span> Perimeter Watch</h1></div><div className="mission-meta"><span><Activity size={13}/>LAST EVENT <strong>{lastEvent}</strong></span><span><CloudCog size={13}/>MQ DEPTH <strong>{queue}</strong></span><span><Signal size={13}/>UPLINK <strong>24ms</strong></span><button onClick={exportData}><Download size={13}/>EXPORT</button></div></section>
    {activeView === "overview" && <>
      <section className="metrics"><Metric icon={ShieldAlert} label="ACTIVE THREATS" value="12" delta="8.4%" tone="red" values={[9,11,8,14,12,17,15,21,18,24]}/><Metric icon={Radio} label="SENSORS ONLINE" value="5" unit="/ 6" delta="Stable"/><Metric icon={Crosshair} label="DETECTIONS / HR" value="143" delta="18.2%" tone="amber"/><Metric icon={Zap} label="MQ THROUGHPUT" value={throughput} unit="/m" delta="12.7%" tone="violet"/></section>
      <section className="dashboard-grid"><TacticalMap selected={selected} select={setSelected} paused={paused}/><div className="right-stack"><Distribution/><Throughput rate={throughput}/></div><Alerts alerts={alerts} selected={selected} select={setSelected} acknowledge={acknowledge}/><Detail item={selected}/></section>
      <Intelligence mode={mode} config={config} openSettings={() => setSettings(true)} setConnected={setConnected}/>
      <QueryBurst statusUrl={burstStatusUrl} setStatusUrl={setBurstUrl}/>
    </>}
    {activeView === "incidents" && <IncidentView alerts={alerts} selected={selected} select={setSelected} acknowledge={acknowledge}/>}
    {activeView === "sensors" && <SensorView selected={selected} select={setSelected} paused={paused}/>}
    {activeView === "intelligence" && <IntelligenceView mode={mode} config={config} openSettings={() => setSettings(true)} setConnected={setConnected} connected={connected} burstStatusUrl={burstStatusUrl} setBurstStatusUrl={setBurstUrl}/>}
  </main><footer><span><Brand/>ORBIT THREAT TELEMETRY</span><span>{mode === "demo" ? "DEMO FEED" : "ORBIT API"} <i className={healthy ? "good" : ""}/>{mode === "demo" ? "ACTIVE" : healthy ? "CONNECTED" : "DISCONNECTED"}</span><span>CLASSIFICATION // DEMONSTRATION</span></footer>{settings && <Settings config={config} close={() => setSettings(false)} save={save}/>}</div>;
}

createRoot(document.getElementById("root")).render(<App/>);
