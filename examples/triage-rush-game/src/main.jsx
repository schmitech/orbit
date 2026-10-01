import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bot, Cpu, Gauge, Hexagon, Layers, Pause, Play, Settings2, Timer, Trophy, User, X, Zap } from "lucide-react";
import { TEAMS, TICKETS, RESOURCE_OPTIONS, RESOURCE_POLICY, RESOURCE_QUESTION, RESOURCE_TICKETS } from "./tickets.js";
import "./styles.css";

const DEFAULT_SETTINGS = {
  bridgeUrl: "http://localhost:8795",
  adapter: "", // "" = no override: ORBIT uses the adapter bound to the bridge's API key
  challenge: "team",
  roundSec: 60,
  speed: 1,
  surgeSize: 25,
  paused: false,
  autoplay: false, // AI plays alone while idle; off so nothing is sent to ORBIT until a round starts
  aiHoldMs: 1500, // how long a decided AI card stays readable before it drops (display only, not scored)
};
const IDLE_ABORT_MS = 20000;
const RESULTS_MS = 30000;
const COUNTDOWN_MS = 3000;
const RESOLVED_LINGER_MS = 900;
// Keep these in sync with styles.css: CARD_H_PX matches the default --card-h,
// and RESOURCE_CARD_H_PX matches .arena-resource's --card-h. The queue spacing
// uses these heights to keep falling cards from overlapping.
const CARD_H_PX = 118;
const RESOURCE_CARD_H_PX = 190;
const CARD_GAP_PX = 10;
// Cards still in the lane's flow; sorted/missed/failed cards are animating away.
const FLOW_STATES = new Set(["falling", "deciding", "decided"]);
const LEADERBOARD_KEY = "triage-rush-leaderboard";
const SETTINGS_KEY = "triage-rush-settings";
// Unique per page load so ids never collide with replies still in flight from a previous load.
const SESSION = Math.random().toString(36).slice(2, 8);

const cls = (...values) => values.filter(Boolean).join(" ");
const lerp = (a, b, t) => a + (b - a) * Math.min(1, Math.max(0, t));
const optionsFor = challenge => challenge === "resource" ? RESOURCE_OPTIONS : TEAMS;
const answerFor = ticket => ticket.answer ?? ticket.team;
const answerLabel = (challenge, id) => optionsFor(challenge).find(option => option.id === id)?.label ?? id;
// The override to send, if the presenter picked one the bridge allows; otherwise none, so the
// bridge's forced --adapter (if any) or the API key's own adapter applies.
const overrideAdapter = (settings, health) =>
  settings.adapter && health.allowed_adapters?.includes(settings.adapter) ? settings.adapter : null;
const adapterLabel = (settings, health) =>
  overrideAdapter(settings, health) || health.adapter || health.key_adapter || "API key's adapter";
const leaderboardFor = (entries, challenge) => entries.filter(entry => (entry.challenge || "team") === challenge);

function readStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
function writeStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable: keep in memory */ }
}

function shuffle(list) {
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function percentile(values, p) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}

const newLaneStats = () => ({ score: 0, correct: 0, wrong: 0, missed: 0, times: [] });

function newEngine() {
  return {
    mode: "attract",
    cards: [],
    seq: 0,
    deck: shuffle(TICKETS),
    deckChallenge: "team",
    challenge: "team",
    deckIdx: 0,
    roundStart: 0,
    roundEnd: 0,
    countdownEnd: 0,
    nextSpawn: 0,
    resultsAt: 0,
    lastInput: 0,
    human: newLaneStats(),
    ai: newLaneStats(),
    latencies: [],
    decidedAt: [],
    model: null,
    binFlash: {},
    pendingDecisions: new Map(),
  };
}

function nextTicket(engine, challenge) {
  if (engine.deckChallenge !== challenge) {
    engine.deckChallenge = challenge;
    engine.deck = shuffle(challenge === "resource" ? RESOURCE_TICKETS : TICKETS);
    engine.deckIdx = 0;
  }
  if (engine.deckIdx >= engine.deck.length) {
    engine.deck = shuffle(challenge === "resource" ? RESOURCE_TICKETS : TICKETS);
    engine.deckIdx = 0;
  }
  return engine.deck[engine.deckIdx++];
}

// ---------------------------------------------------------------------------
// Game component
// ---------------------------------------------------------------------------

function Game() {
  const [settings, setSettingsState] = useState(() => ({ ...DEFAULT_SETTINGS, ...readStorage(SETTINGS_KEY, {}) }));
  const [leaderboard, setLeaderboard] = useState(() => readStorage(LEADERBOARD_KEY, []));
  const [health, setHealth] = useState({ status: "offline" });
  const streamOpenRef = useRef(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [initials, setInitials] = useState("");
  const [saved, setSaved] = useState(false);
  const [, setFrame] = useState(0);

  const engineRef = useRef(newEngine());
  const playfieldRef = useRef(null);
  const settingsRef = useRef(settings);
  const healthRef = useRef(health);
  const leaderboardRef = useRef(leaderboard);
  const panelRef = useRef(panelOpen);
  const savedRef = useRef(saved);
  settingsRef.current = settings;
  healthRef.current = health;
  leaderboardRef.current = leaderboard;
  panelRef.current = panelOpen;
  savedRef.current = saved;

  const setSettings = patch => setSettingsState(prev => {
    const next = { ...prev, ...patch };
    writeStorage(SETTINGS_KEY, next);
    return next;
  });

  // --- bridge: health polling -------------------------------------------------
  useEffect(() => {
    let active = true;
    const base = settings.bridgeUrl.replace(/\/$/, "");
    const poll = async () => {
      try {
        const res = await fetch(`${base}/health`, { cache: "no-store", signal: AbortSignal.timeout(1500) });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        if (!active) return;
        // A missing orbit.requests queue (no worker has declared it yet) is as unready as zero consumers:
        // publishing to it via the default exchange would silently drop the tickets.
        const hasWorker = body.queue?.available && body.queue.consumers > 0;
        // Without the reply stream, published tickets would be answered but never shown.
        const status = !body.broker ? "no-broker" : !hasWorker ? "no-worker" : streamOpenRef.current ? "ready" : "no-stream";
        setHealth({ status, ...body });
      } catch {
        if (active) setHealth({ status: "offline" });
      }
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => { active = false; clearInterval(id); };
  }, [settings.bridgeUrl]);

  // --- bridge: decision stream ------------------------------------------------
  useEffect(() => {
    const source = new EventSource(`${settings.bridgeUrl.replace(/\/$/, "")}/events`);
    streamOpenRef.current = false;
    source.onopen = () => { streamOpenRef.current = true; };
    source.onerror = () => { streamOpenRef.current = source.readyState === EventSource.OPEN; };
    source.onmessage = message => {
      let event;
      try { event = JSON.parse(message.data); } catch { return; }
      if (event.type !== "decision") return;
      const engine = engineRef.current;
      const card = engine.cards.find(c => c.bridgeId === event.id);
      if (!card || card.state !== "deciding") return;
      card.reply = event; // applied in the frame loop once the card is on screen
    };
    return () => { source.close(); streamOpenRef.current = false; };
  }, [settings.bridgeUrl]);

  // --- publishing ---------------------------------------------------------------
  const publish = async cards => {
    const { bridgeUrl } = settingsRef.current;
    const adapter = overrideAdapter(settingsRef.current, healthRef.current);
    const items = cards.map(c => c.challenge === "resource" ? {
      id: c.bridgeId,
      text: c.ticket.text,
      state: { ticket: c.ticket.text, resources: c.ticket.resource, policy: RESOURCE_POLICY },
      questions: RESOURCE_QUESTION,
    } : { id: c.bridgeId, text: c.ticket.text });
    let error = null;
    try {
      const res = await fetch(`${bridgeUrl.replace(/\/$/, "")}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(adapter ? { items, adapter } : { items }),
      });
      if (!res.ok) error = (await res.json().catch(() => ({}))).error || `bridge HTTP ${res.status}`;
    } catch (e) {
      error = `bridge unreachable: ${e.message}`;
    }
    if (error) cards.forEach(c => { if (c.state === "deciding") c.reply = { status: "failed", error }; });
  };

  // --- engine actions -------------------------------------------------------------
  const spawn = (now, count = 1) => {
    const engine = engineRef.current;
    const { speed } = settingsRef.current;
    const playing = engine.mode === "playing";
    const challenge = playing ? engine.challenge : settingsRef.current.challenge;
    const progress = playing ? (now - engine.roundStart) / (engine.roundEnd - engine.roundStart) : 0;
    const fallMs = (playing ? lerp(9000, 6000, progress) : 8000) / speed;
    const aiCards = [];
    for (let i = 0; i < count; i++) {
      const ticket = nextTicket(engine, challenge);
      const uid = ++engine.seq;
      const x = Math.round((Math.random() - 0.5) * 16);
      const spawnedAt = now + i * 220; // surge tickets stream in one after another
      const base = { num: uid, ticket, challenge, x, spawnedAt, fallMs, state: "falling", resolvedAt: 0 };
      if (playing) engine.cards.push({ ...base, uid: `h${uid}`, lane: "human" });
      const ai = { ...base, uid: `a${uid}`, lane: "ai", state: "deciding", bridgeId: `${SESSION}-${uid}` };
      engine.cards.push(ai);
      aiCards.push(ai);
    }
    publish(aiCards);
  };

  const flashBin = (lane, bin, good, now) => { engineRef.current.binFlash[lane] = { bin, good, at: now }; };

  const score = (lane, correct, decisionMs, fallMs) => {
    const stats = engineRef.current[lane];
    if (correct) {
      stats.correct += 1;
      stats.score += 100 + Math.round(100 * Math.max(0, 1 - decisionMs / fallMs));
    } else {
      stats.wrong += 1;
      stats.score -= 50;
    }
    stats.times.push(decisionMs);
  };

  const humanSort = binId => {
    const engine = engineRef.current;
    if (engine.mode !== "playing") return;
    const now = performance.now();
    engine.lastInput = now;
    const active = activeHumanCard(engine, now);
    if (!active) return;
    const correct = binId === answerFor(active.ticket);
    active.state = "sorted";
    active.bin = binId;
    active.correct = correct;
    active.resolvedAt = now;
    score("human", correct, now - Math.max(active.spawnedAt, active.visibleAt ?? active.spawnedAt), active.fallMs);
    flashBin("human", binId, correct, now);
  };

  const startCountdown = () => {
    const engine = engineRef.current;
    if (healthRef.current.status !== "ready" || settingsRef.current.paused) return;
    const now = performance.now();
    engine.cards = [];
    engine.challenge = settingsRef.current.challenge;
    engine.mode = "countdown";
    engine.countdownEnd = now + COUNTDOWN_MS;
    engine.lastInput = now;
    setInitials("");
    setSaved(false);
  };

  const surge = () => {
    const engine = engineRef.current;
    if (engine.mode !== "playing" && engine.mode !== "attract") return;
    if (healthRef.current.status !== "ready" || settingsRef.current.paused) return;
    spawn(performance.now(), settingsRef.current.surgeSize);
  };

  // Pausing stops every new request to ORBIT: it ends any round, clears the lanes and stops
  // attract-mode autoplay. It is saved, so a page reload stays paused.
  const togglePause = () => {
    const paused = !settingsRef.current.paused;
    if (paused) enterAttract(engineRef.current);
    setSettings({ paused });
  };

  const saveScore = () => {
    const engine = engineRef.current;
    const name = initials.trim().toUpperCase() || "???";
    const entry = { initials: name, score: engine.human.score, accuracy: accuracy(engine.human), at: Date.now(), challenge: engine.challenge };
    const next = [
      ...leaderboardFor(leaderboardRef.current, engine.challenge).concat(entry).sort((a, b) => b.score - a.score).slice(0, 10),
      ...leaderboardRef.current.filter(item => (item.challenge || "team") !== engine.challenge),
    ];
    setLeaderboard(next);
    writeStorage(LEADERBOARD_KEY, next);
    setSaved(true);
    engine.resultsAt = performance.now(); // give them time to see their rank
  };

  const resetLeaderboard = () => {
    const challenge = settingsRef.current.challenge;
    const next = leaderboardRef.current.filter(entry => (entry.challenge || "team") !== challenge);
    setLeaderboard(next);
    writeStorage(LEADERBOARD_KEY, next);
  };
  const changeChallenge = challenge => {
    if (engineRef.current.mode === "attract") enterAttract(engineRef.current);
    setSettings({ challenge });
  };

  // --- frame loop -----------------------------------------------------------------
  useEffect(() => {
    let raf;
    const tick = () => {
      step(performance.now());
      setFrame(n => (n + 1) % 1_000_000);
      raf = requestAnimationFrame(tick);
    };
    const step = now => {
      const engine = engineRef.current;
      const ready = healthRef.current.status === "ready" && !settingsRef.current.paused;

      if (engine.mode === "countdown" && now >= engine.countdownEnd) {
        Object.assign(engine, {
          mode: "playing", human: newLaneStats(), ai: newLaneStats(), latencies: [], decidedAt: [],
          roundStart: now, roundEnd: now + settingsRef.current.roundSec * 1000, nextSpawn: now, lastInput: now,
        });
      }
      if (engine.mode === "playing") {
        if (now >= engine.roundEnd) {
          engine.mode = "results";
          engine.resultsAt = now;
          engine.cards = [];
        } else if (now - engine.lastInput > IDLE_ABORT_MS) {
          enterAttract(engine);
        }
      }
      if (engine.mode === "results" && now - engine.resultsAt > RESULTS_MS) enterAttract(engine);

      // Spawning
      const autoplay = engine.mode === "attract" && settingsRef.current.autoplay;
      if ((engine.mode === "playing" || autoplay) && ready && now >= engine.nextSpawn) {
        spawn(now);
        const progress = engine.mode === "playing" ? (now - engine.roundStart) / (engine.roundEnd - engine.roundStart) : 0;
        const interval = (engine.mode === "playing" ? lerp(2400, 1000, progress) : 1800) / settingsRef.current.speed;
        engine.nextSpawn = now + interval;
      }

      // Card physics: each lane is a queue. A card falls at its own speed but never closer than
      // one card height to the card below it, so tickets stack up (and wait above the lane,
      // shown as "+N waiting") instead of overlapping.
      const challenge = engine.mode === "attract" ? settingsRef.current.challenge : engine.challenge;
      const cardHeight = challenge === "resource" ? RESOURCE_CARD_H_PX : CARD_H_PX;
      const span = Math.max(1, (playfieldRef.current?.clientHeight || 500) - cardHeight);
      const spacing = (cardHeight + CARD_GAP_PX) / span;
      for (const lane of ["human", "ai"]) {
        const flow = engine.cards
          .filter(c => c.lane === lane && FLOW_STATES.has(c.state) && now >= c.spawnedAt)
          .sort((a, b) => a.spawnedAt - b.spawnedAt); // oldest is lowest
        let limit = Infinity;
        for (const card of flow) {
          // Capped so a briefly hidden tab doesn't drop every card to the floor at once.
          const dt = Math.min(100, now - (card.lastStepAt ?? card.spawnedAt));
          card.lastStepAt = now;
          card.y = Math.min((card.y ?? 0) + dt / card.fallMs, limit);
          limit = card.y - spacing;
        }
      }

      // AI decisions and misses
      for (const card of engine.cards) {
        if (now < card.spawnedAt) continue;
        if (card.y >= 0 && card.visibleAt == null) card.visibleAt = now;
        const falling = card.state === "falling" || card.state === "deciding";
        if (falling && card.reply && card.y >= 0) applyReply(engine, card, now);
        if (card.state === "decided" && now >= card.dropAt) {
          card.state = "sorted";
          card.resolvedAt = now;
          flashBin("ai", card.bin, card.correct, now);
        }
        if (falling && card.y >= 1) {
          card.state = "missed";
          card.resolvedAt = now;
          engine[card.lane].missed += 1;
          engine[card.lane].score -= 100;
        }
      }
      engine.cards = engine.cards.filter(c => !c.resolvedAt || now - c.resolvedAt < RESOLVED_LINGER_MS);
      engine.decidedAt = engine.decidedAt.filter(t => now - t < 5000);
    };
    const applyReply = (engine, card, now) => {
      const { reply } = card;
      const answer = reply.answers?.[card.challenge === "resource" ? "action" : "team"];
      card.decision = reply;
      if (reply.status === "completed" && optionsFor(card.challenge).some(option => option.id === answer?.choice)) {
        const correct = answer.choice === answerFor(card.ticket);
        // Scored on the real round-trip latency now; the card just stays readable, falling
        // beside its twin in the human lane, for aiHoldMs before it drops into the bin.
        card.state = "decided";
        card.dropAt = now + settingsRef.current.aiHoldMs;
        card.bin = answer.choice;
        card.correct = correct;
        score("ai", correct, reply.latency_ms ?? card.fallMs, card.fallMs);
        if (reply.latency_ms != null) engine.latencies = [...engine.latencies.slice(-199), reply.latency_ms];
        engine.decidedAt.push(now);
        engine.model = reply.model || engine.model;
      } else {
        card.state = "failed";
        card.resolvedAt = now + 1500; // keep the error readable a little longer
        engine.ai.missed += 1;
        engine.ai.score -= 100;
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  // --- keyboard -------------------------------------------------------------------
  useEffect(() => {
    const onKey = event => {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) {
        if (event.key === "Escape") event.target.blur();
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "p") { setPanelOpen(open => !open); return; }
      if (key === "escape") { setPanelOpen(false); return; }
      if (panelRef.current) return;
      if (key === "s") { surge(); return; }
      const engine = engineRef.current;
      if (engine.mode === "playing") {
        const option = optionsFor(engine.challenge).find(choice => choice.key === key);
        if (option) humanSort(option.id);
      } else if (engine.mode === "attract") {
        startCountdown();
      } else if (engine.mode === "results" && (savedRef.current || !qualifiesFor(engine, leaderboardFor(leaderboardRef.current, engine.challenge))) &&
        performance.now() - engine.resultsAt > 1500) {
        startCountdown();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // --- render ---------------------------------------------------------------------
  const engine = engineRef.current;
  const now = performance.now();
  const timeLeft = engine.mode === "playing" ? Math.max(0, Math.ceil((engine.roundEnd - now) / 1000)) : null;
  const qualifies = engine.mode === "results" && qualifiesFor(engine, leaderboardFor(leaderboard, engine.challenge));

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><Hexagon size={22} /></span>
          <div><small>ORBIT decision models</small><strong>TRIAGE RUSH</strong></div>
        </div>
        <div className="topbar-center">
          {engine.mode === "playing" && <span className="timer"><Timer size={18} />{timeLeft}s</span>}
          {engine.mode === "attract" && (settings.paused
            ? <span className="mode-pill paused">PAUSED · NO REQUESTS TO ORBIT</span>
            : settings.autoplay
              ? <span className="mode-pill">ATTRACT MODE · AI PLAYING</span>
              : <span className="mode-pill">READY · PRESS ANY KEY</span>)}
          {engine.mode === "countdown" && <span className="mode-pill">GET READY</span>}
          {engine.mode === "results" && <span className="mode-pill">ROUND OVER</span>}
        </div>
        <div className="topbar-right">
          <BridgePill health={health} />
          <button
            className={cls("pause-button", settings.paused && "paused")} onClick={togglePause}
            title={settings.paused ? "Resume sending tickets to ORBIT" : "Stop sending tickets to ORBIT"}
          >
            {settings.paused ? <><Play size={16} /> Resume</> : <><Pause size={16} /> Pause</>}
          </button>
          <button className="icon-button" onClick={() => setPanelOpen(open => !open)} aria-label="Presenter panel (P)">
            <Settings2 size={18} />
          </button>
        </div>
      </header>

      <main className={cls("arena", (engine.mode === "attract" ? settings.challenge : engine.challenge) === "resource" && "arena-resource")}>
        {(engine.mode === "attract" ? settings.challenge : engine.challenge) === "resource" &&
          <div className="resource-policy"><strong>RESOURCE POLICY</strong><span>{RESOURCE_POLICY}</span></div>}
        <Lane
          lane="human" title="YOU" icon={User} engine={engine} challenge={engine.mode === "attract" ? settings.challenge : engine.challenge} now={now} onSort={humanSort} playfieldRef={playfieldRef}
          overlay={engine.mode === "attract" ? (
            <AttractOverlay health={health} paused={settings.paused} leaderboard={leaderboardFor(leaderboard, settings.challenge)} challenge={settings.challenge} onStart={startCountdown} />
          ) : null}
        />
        <Lane
          lane="ai" title="ORBIT AI" icon={Bot} engine={engine} challenge={engine.mode === "attract" ? settings.challenge : engine.challenge} now={now}
          subtitle={`${adapterLabel(settings, health)}${engine.model ? ` · ${engine.model}` : ""}`}
          overlay={settings.paused ? <PausedOverlay onResume={togglePause} />
            : health.status !== "ready" && engine.mode !== "results" ? <BridgeOverlay health={health} />
            : engine.mode === "attract" && !settings.autoplay && engine.cards.length === 0 ? <IdleOverlay /> : null}
        />
        {engine.mode === "countdown" && (
          <div className="countdown">{Math.max(1, Math.ceil((engine.countdownEnd - now) / 1000))}</div>
        )}
        {engine.mode === "results" && (
          <Results
            engine={engine} qualifies={qualifies} saved={saved} initials={initials}
            setInitials={setInitials} saveScore={saveScore} leaderboard={leaderboardFor(leaderboard, engine.challenge)} onAgain={startCountdown}
          />
        )}
      </main>

      <HudStrip engine={engine} health={health} settings={settings} />

      {panelOpen && (
        <PresenterPanel
          settings={settings} setSettings={setSettings} onChallengeChange={changeChallenge} health={health} mode={engine.mode} close={() => setPanelOpen(false)}
          surge={surge} togglePause={togglePause} resetLeaderboard={resetLeaderboard}
        />
      )}
    </div>
  );
}

function enterAttract(engine) {
  Object.assign(engine, { mode: "attract", cards: [], ai: newLaneStats(), human: newLaneStats(), latencies: [], decidedAt: [] });
}

function qualifiesFor(engine, leaderboard) {
  return engine.human.score > 0 &&
    (leaderboard.length < 10 || engine.human.score > leaderboard[leaderboard.length - 1].score);
}

function activeHumanCard(engine, now) {
  let active = null;
  for (const card of engine.cards) {
    if (card.lane !== "human" || card.state !== "falling" || now < card.spawnedAt) continue;
    if (!active || card.y > active.y) active = card;
  }
  return active;
}

function accuracy(stats) {
  const total = stats.correct + stats.wrong + stats.missed;
  return total ? Math.round((stats.correct / total) * 100) : 0;
}

function avgMs(stats) {
  return stats.times.length ? Math.round(stats.times.reduce((a, b) => a + b, 0) / stats.times.length) : null;
}

function formatMs(ms) {
  if (ms == null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

// ---------------------------------------------------------------------------
// Lanes and cards
// ---------------------------------------------------------------------------

function Lane({ lane, title, icon: Icon, subtitle, engine, challenge, now, onSort, overlay, playfieldRef }) {
  const options = optionsFor(challenge);
  const stats = engine[lane];
  const cards = engine.cards.filter(c => c.lane === lane && now >= c.spawnedAt);
  const waiting = engine.cards.filter(c => c.lane === lane && FLOW_STATES.has(c.state) && (now < c.spawnedAt || c.y < 0)).length;
  const active = lane === "human" ? activeHumanCard(engine, now) : null;
  const flash = engine.binFlash[lane];
  const flashing = flash && now - flash.at < 450 ? flash : null;
  return (
    <section className={cls("lane", `lane-${lane}`)}>
      <div className="lane-head">
        <div className="lane-title"><Icon size={22} /><div><strong>{title}</strong>{subtitle && <small>{subtitle}</small>}</div></div>
        <dl className="lane-stats">
          <div><dt>Score</dt><dd>{stats.score.toLocaleString()}</dd></div>
          <div><dt>Accuracy</dt><dd>{accuracy(stats)}%</dd></div>
          <div><dt>Avg decision</dt><dd>{formatMs(avgMs(stats))}</dd></div>
        </dl>
      </div>
      <div className="playfield" ref={playfieldRef}>
        {waiting > 0 && <span className="waiting">+{waiting} waiting</span>}
        {cards.map(card => (
          <Card key={card.uid} card={card} active={card === active} />
        ))}
        {overlay}
      </div>
      <div className="bins">
        {options.map(option => (
          <button
            key={option.id}
            className={cls("bin", flashing?.bin === option.id && (flashing.good ? "flash-good" : "flash-bad"))}
            onClick={onSort ? () => onSort(option.id) : undefined}
            disabled={!onSort}
            tabIndex={onSort ? 0 : -1}
          >
            {onSort && <kbd>{option.key}</kbd>}
            <span>{option.label}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function Card({ card, active }) {
  const y = Math.min(1, card.y ?? 0); // negative while waiting above the lane
  const resolved = card.state === "sorted";
  const binIdx = resolved ? optionsFor(card.challenge).findIndex(option => option.id === card.bin) : -1;
  const style = resolved
    ? { left: `calc(${12.5 + 25 * binIdx}% - var(--card-w) / 2)`, top: "calc(100% - var(--card-h))" }
    : { left: `calc(${50 + card.x}% - var(--card-w) / 2)`, top: `calc((100% - var(--card-h)) * ${y})` };
  const answers = card.decision?.answers;
  return (
    <article
      className={cls("card", card.challenge === "resource" && "resource-card", `state-${card.state}`, active && "active", resolved && (card.correct ? "good" : "bad"))}
      style={style}
    >
      <span className="card-num">#{card.num}</span>
      <p>{card.ticket.text}</p>
      {card.ticket.resource && <span className="resource-context">{card.ticket.resource}</span>}
      {card.lane === "ai" && card.state === "deciding" && <span className="deciding"><Cpu size={13} /> deciding…</span>}
      {card.lane === "ai" && answers && <Decision answers={answers} challenge={card.challenge} latency={card.decision.latency_ms} />}
      {card.state === "failed" && <span className="card-error">{card.decision?.error || "decision failed"}</span>}
      {card.state === "missed" && <span className="card-error">MISSED · {answerLabel(card.challenge, answerFor(card.ticket))}</span>}
      {resolved && !card.correct && <span className="card-truth">was {answerLabel(card.challenge, answerFor(card.ticket))}</span>}
    </article>
  );
}

function Decision({ answers, challenge, latency }) {
  const answer = answers[challenge === "resource" ? "action" : "team"];
  const probability = answer?.probabilities?.[answer.choice];
  const urgency = answers.urgency;
  const urgencyLabel = urgency?.legend?.[String(Math.round(urgency.score))];
  const refund = answers.refund_requested?.noul;
  return (
    <div className="decision">
      <div className="decision-row">
        <strong>→ {answerLabel(challenge, answer?.choice)}</strong>
        {probability != null && <span className="prob"><i style={{ width: `${Math.round(probability * 100)}%` }} />{Math.round(probability * 100)}%</span>}
        <span className="latency">{formatMs(latency)}</span>
      </div>
      <div className="chips">
        {challenge === "team" && urgencyLabel && <span className={cls("chip", `urgency-${urgencyLabel.toLowerCase()}`)}>{urgencyLabel}</span>}
        {challenge === "team" && refund != null && refund >= 0.5 && <span className="chip refund">refund {Math.round(refund * 100)}%</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overlays
// ---------------------------------------------------------------------------

const BRIDGE_MESSAGES = {
  offline: ["NO BRIDGE", "Start examples/triage-rush-mq/game_bridge.py, or press P to set its URL."],
  "no-broker": ["NO BROKER", "The bridge lost its RabbitMQ connection."],
  "no-worker": ["NO WORKER", "Nothing is consuming orbit.requests. Start ORBIT with messaging enabled."],
  "no-stream": ["NO REPLY STREAM", "The bridge is up but its /events stream isn't connected. Restart game_bridge.py and reload."],
};

function BridgeOverlay({ health }) {
  const [title, hint] = BRIDGE_MESSAGES[health.status] || BRIDGE_MESSAGES.offline;
  return (
    <div className="overlay bridge-overlay">
      <strong>{title}</strong>
      <p>{hint}</p>
      <small>The AI lane only shows real decisions from ORBIT. Nothing is simulated.</small>
    </div>
  );
}

function IdleOverlay() {
  return (
    <div className="overlay idle-overlay">
      <strong>STANDING BY</strong>
      <p>ORBIT is ready. No tickets are sent until a round starts.</p>
    </div>
  );
}

function PausedOverlay({ onResume }) {
  return (
    <div className="overlay paused-overlay">
      <strong>PAUSED</strong>
      <p>No tickets are being sent to ORBIT.</p>
      <button className="again" onClick={onResume}><Play size={16} /> Resume</button>
      <small>Tickets already published still get answered, then the lane stays empty.</small>
    </div>
  );
}

function AttractOverlay({ health, paused, leaderboard, challenge, onStart }) {
  const ready = health.status === "ready" && !paused;
  const cta = paused ? "PAUSED" : ready ? "PRESS ANY KEY OR TAP TO CHALLENGE ORBIT" : "WAITING FOR ORBIT…";
  return (
    <div className="overlay attract-overlay" onClick={ready ? onStart : undefined} role="button" tabIndex={-1}>
      <strong className="cta">{cta}</strong>
      <p>{challenge === "resource" ? "Choose the next action using the resource policy." : "Sort each support ticket into the right team before it hits the floor."}<br />Keys <kbd>1</kbd>–<kbd>4</kbd> or tap a bin.</p>
      <Leaderboard entries={leaderboard} />
    </div>
  );
}

function Leaderboard({ entries, highlight }) {
  return (
    <div className="leaderboard">
      <h3><Trophy size={16} /> Top humans</h3>
      {entries.length === 0 ? <p className="empty">No scores yet. Be the first.</p> : (
        <ol>
          {entries.map((e, i) => (
            <li key={`${e.at}-${i}`} className={e.at === highlight ? "highlight" : undefined}>
              <span>{e.initials}</span><span>{e.score.toLocaleString()}</span><span>{e.accuracy}%</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Results({ engine, qualifies, saved, initials, setInitials, saveScore, leaderboard, onAgain }) {
  const human = engine.human;
  const ai = engine.ai;
  const humanWins = human.score > ai.score;
  const humanAvg = avgMs(human);
  const aiAvg = avgMs(ai);
  const speedup = humanAvg && aiAvg ? Math.round(humanAvg / aiAvg) : null;
  const lastSaved = saved ? Math.max(...leaderboard.map(e => e.at)) : null;
  return (
    <div className="results">
      <h2>{humanWins ? "YOU BEAT ORBIT!" : "ORBIT WINS"}</h2>
      <div className="versus">
        <ResultColumn title="YOU" stats={human} winner={humanWins} />
        <span className="vs">VS</span>
        <ResultColumn title="ORBIT AI" stats={ai} winner={!humanWins} />
      </div>
      {speedup > 1 && <p className="speedup">ORBIT decided <strong>{speedup}×</strong> faster than you, and returned a probability with every call.</p>}
      {qualifies && !saved && (
        <form className="initials" onSubmit={e => { e.preventDefault(); saveScore(); }}>
          <label htmlFor="initials">New high score! Your initials</label>
          <input
            id="initials" autoFocus maxLength={3} value={initials}
            onChange={e => {
              engine.resultsAt = performance.now(); // typing keeps the results screen up
              setInitials(e.target.value.replace(/[^a-z]/gi, "").toUpperCase());
            }}
          />
          <button type="submit">Save</button>
        </form>
      )}
      {(saved || !qualifies) && (
        <>
          {saved && <Leaderboard entries={leaderboard} highlight={lastSaved} />}
          <button className="again" onClick={onAgain}>Play again</button>
        </>
      )}
      {!qualifies && <small className="hint">Press any key to play again</small>}
    </div>
  );
}

function ResultColumn({ title, stats, winner }) {
  return (
    <div className={cls("result-col", winner && "winner")}>
      <small>{title}</small>
      <strong>{stats.score.toLocaleString()}</strong>
      <dl>
        <div><dt>Accuracy</dt><dd>{accuracy(stats)}%</dd></div>
        <div><dt>Avg decision</dt><dd>{formatMs(avgMs(stats))}</dd></div>
        <div><dt>Correct / wrong / missed</dt><dd>{stats.correct} / {stats.wrong} / {stats.missed}</dd></div>
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// HUD, bridge pill, presenter panel
// ---------------------------------------------------------------------------

function BridgePill({ health }) {
  const label = { ready: "LIVE", offline: "NO BRIDGE", "no-broker": "NO BROKER", "no-worker": "NO WORKER", "no-stream": "NO STREAM" }[health.status];
  return <span className={cls("bridge-pill", health.status === "ready" ? "ok" : "bad")}><i />{label}</span>;
}

function HudStrip({ engine, health, settings }) {
  const p50 = percentile(engine.latencies, 50);
  const p95 = percentile(engine.latencies, 95);
  const rate = engine.decidedAt.length / 5;
  const queue = health.queue?.available ? health.queue : null;
  return (
    <footer className="hud">
      <HudItem icon={Zap} label="Decisions / s" value={rate.toFixed(1)} />
      <HudItem icon={Gauge} label="Latency p50" value={formatMs(p50)} />
      <HudItem icon={Gauge} label="Latency p95" value={formatMs(p95)} />
      <HudItem icon={Layers} label="Queue depth" value={queue ? queue.messages : "—"} hot={queue?.messages > 5} />
      <HudItem icon={Cpu} label="Workers" value={queue ? queue.consumers : "—"} />
      <HudItem icon={Bot} label="In flight" value={health.in_flight ?? "—"} />
      <div className="hud-note">
        <span>via RabbitMQ <code>{health.requests_queue || "orbit.requests"}</code> → <code>{adapterLabel(settings, health)}</code></span>
        <span className="keys"><kbd>S</kbd> surge · <kbd>P</kbd> presenter</span>
      </div>
    </footer>
  );
}

function HudItem({ icon: Icon, label, value, hot }) {
  return (
    <div className={cls("hud-item", hot && "hot")}>
      <small><Icon size={13} />{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function PresenterPanel({ settings, setSettings, onChallengeChange, health, mode, close, surge, togglePause, resetLeaderboard }) {
  const [bridgeDraft, setBridgeDraft] = useState(settings.bridgeUrl);
  const [confirmReset, setConfirmReset] = useState(null);
  const overrides = health.allowed_adapters || [];
  const keyLabel = health.adapter
    ? `Bridge default (${health.adapter})`
    : `API key's adapter${health.key_adapter ? ` (${health.key_adapter})` : ""}`;
  return (
    <aside className="panel">
      <div className="panel-head">
        <strong>Presenter</strong>
        <button className="icon-button" onClick={close} aria-label="Close"><X size={16} /></button>
      </div>
      <label>
        Bridge URL
        <input
          value={bridgeDraft}
          onChange={e => setBridgeDraft(e.target.value)}
          onBlur={() => setSettings({ bridgeUrl: bridgeDraft.trim() || DEFAULT_SETTINGS.bridgeUrl })}
        />
      </label>
      <label>
        Decision adapter
        <select value={overrideAdapter(settings, health) || ""} onChange={e => setSettings({ adapter: e.target.value })}
          disabled={overrides.length === 0} title={overrides.length === 0 ? "Start the bridge with --allowed-adapters to enable overrides" : undefined}>
          <option value="">{keyLabel}</option>
          {overrides.filter(a => a !== health.adapter).map(a => <option key={a} value={a}>Override: {a}</option>)}
        </select>
      </label>
      <label>
        Challenge
        <select value={settings.challenge} disabled={mode === "playing" || mode === "countdown"}
          onChange={e => onChallengeChange(e.target.value)}>
          <option value="team">Team routing</option>
          <option value="resource">Resource decisions</option>
        </select>
      </label>
      <label>
        Round length: {settings.roundSec}s
        <input type="range" min="30" max="120" step="15" value={settings.roundSec}
          onChange={e => setSettings({ roundSec: Number(e.target.value) })} />
      </label>
      <label>
        Speed: {settings.speed.toFixed(2)}×
        <input type="range" min="0.5" max="2" step="0.25" value={settings.speed}
          onChange={e => setSettings({ speed: Number(e.target.value) })} />
      </label>
      <label>
        AI answer display: {(settings.aiHoldMs / 1000).toFixed(2)}s
        <input type="range" min="0" max="4000" step="250" value={settings.aiHoldMs}
          onChange={e => setSettings({ aiHoldMs: Number(e.target.value) })} />
      </label>
      <label>
        Surge size: {settings.surgeSize} tickets
        <input type="range" min="10" max="50" step="5" value={settings.surgeSize}
          onChange={e => setSettings({ surgeSize: Number(e.target.value) })} />
      </label>
      <label className="toggle">
        <input type="checkbox" checked={settings.autoplay} onChange={e => setSettings({ autoplay: e.target.checked })} />
        AI autoplay when idle (sends a ticket to ORBIT every ~2s)
      </label>
      <button className="surge" onClick={surge} disabled={health.status !== "ready" || settings.paused}><Zap size={16} /> Surge now</button>
      <button className={cls("pause-button", "wide", settings.paused && "paused")} onClick={togglePause}>
        {settings.paused ? <><Play size={16} /> Resume requests to ORBIT</> : <><Pause size={16} /> Pause all requests to ORBIT</>}
      </button>
      <dl className="health">
        <div><dt>Bridge</dt><dd>{health.status}</dd></div>
        <div><dt>Queue</dt><dd>{health.queue?.available ? `${health.queue.messages} ready · ${health.queue.consumers} consumers` : "—"}</dd></div>
        <div><dt>API key</dt><dd>{health.api_key_configured == null ? "—" : health.api_key_configured ? "configured" : "missing"}</dd></div>
      </dl>
      <button className="reset" onClick={() => (confirmReset === settings.challenge
        ? (resetLeaderboard(), setConfirmReset(null)) : setConfirmReset(settings.challenge))}>
        {confirmReset === settings.challenge
          ? `Click again to clear ${settings.challenge === "resource" ? "Resource" : "Team"} scores`
          : `Reset ${settings.challenge === "resource" ? "Resource" : "Team"} leaderboard`}
      </button>
    </aside>
  );
}

createRoot(document.getElementById("root")).render(<Game />);
