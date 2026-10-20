// Decision Car Simulation — a tiny booth arcade demo for ORBIT's decision-model adapters.
//
// The car drives continuously; hazards scroll toward it in real time, and the lane
// the car steers toward is updated every time a fresh decision arrives. Every lane
// recommendation, probability, and collision-risk flag shown here comes from a real
// `lane-choice` (or `lane-choice-openai`) adapter call made through
// examples/triage-rush-mq/game_bridge.py — nothing is simulated client-side. Because
// the car never waits for a reply, a decision is advisory: on a slow reply, the car
// can reach a hazard before the model's recommendation for it has arrived. The
// client-side physics (hazard positions, collisions, scoring) are not ORBIT's concern
// and are generated/judged locally, same as the hazard layout itself.

const SETTINGS_KEY = "decision-car-simulation-settings";
const BEST_SCORE_KEY = "decision-car-simulation-best-score";
const DEFAULT_SETTINGS = { bridgeUrl: "http://localhost:8795" };
const LANES = ["lane_1", "lane_2", "lane_3"];
const LANE_X = [53, 160, 266]; // lane centers for a 320px-wide canvas
const CAR_Y = 340;
const CAR_W = 34, CAR_H = 54;
const HAZARD_W = 64, HAZARD_H = 24;
const UNSAFE_DISTANCE = CAR_H / 2 + HAZARD_H / 2; // collision threshold, in px of remaining distance

const START_LIVES = 3;
const START_SPEED = 95; // px/s
const MAX_SPEED = 400;
const SPEED_RAMP_PER_SEC = 3.2; // how fast the road speeds up the longer you survive
const STEER_SPEED = 480; // px/s the car can move laterally toward its recommended lane
const SPAWN_INTERVAL_START_MS = 1100;
const SPAWN_INTERVAL_MIN_MS = 520;
const DECISION_INTERVAL_MS = 350; // how often a fresh lane-choice request is fired, at minimum
const DECISION_LOOKAHEAD_PX = 480; // only hazards this close (or closer) are described to ORBIT
const MAX_INFLIGHT_DECISIONS = 6;
const PENDING_DECISION_TIMEOUT_MS = 6000; // drop a stale pending slot so new requests aren't starved
const SESSION = Math.random().toString(36).slice(2, 8);

function readSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : { ...DEFAULT_SETTINGS };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}
function writeSettings(settings) {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch { /* storage unavailable */ }
}
function readBestScore() {
  try { return Number(localStorage.getItem(BEST_SCORE_KEY)) || 0; } catch { return 0; }
}
function writeBestScore(value) {
  try { localStorage.setItem(BEST_SCORE_KEY, String(value)); } catch { /* storage unavailable */ }
}

const settings = readSettings();

// ---------------------------------------------------------------------------
// DOM references

const el = {
  bridgePill: document.getElementById("bridge-pill"),
  btnStart: document.getElementById("btn-start"),
  btnPanel: document.getElementById("btn-panel"),
  road: document.getElementById("road"),
  overlay: document.getElementById("overlay"),
  overlayLabel: document.getElementById("overlay-label"),
  overlayDetail: document.getElementById("overlay-detail"),
  btnOverlayAction: document.getElementById("btn-overlay-action"),
  laneBars: document.getElementById("lane-bars"),
  deciding: document.getElementById("deciding"),
  risk: document.getElementById("risk"),
  sceneText: document.getElementById("scene-text"),
  statScore: document.getElementById("stat-score"),
  statBest: document.getElementById("stat-best"),
  statLives: document.getElementById("stat-lives"),
  statLatency: document.getElementById("stat-latency"),
  statProvider: document.getElementById("stat-provider"),
  panel: document.getElementById("panel"),
  panelClose: document.getElementById("panel-close"),
  inputBridgeUrl: document.getElementById("input-bridge-url"),
  selectAdapter: document.getElementById("select-adapter"),
  healthBroker: document.getElementById("health-broker"),
  healthWorker: document.getElementById("health-worker"),
  healthKeyAdapter: document.getElementById("health-key-adapter"),
  btnResetScore: document.getElementById("btn-reset-score"),
};
const ctx = el.road.getContext("2d");

el.inputBridgeUrl.value = settings.bridgeUrl;
el.statBest.textContent = readBestScore();

// ---------------------------------------------------------------------------
// Connectivity state (GET /health, GET /events SSE, POST /publish — same contract
// as the Triage Rush / Sentiment Pulse bridge clients)

let status = "connecting"; // connecting | no-bridge | no-worker | ok
let allowedAdapters = [];
let eventSource = null;
let streamOpen = false; // the SSE connection is actually open, not just requested

function bridgeUrl() {
  return settings.bridgeUrl.replace(/\/$/, "");
}

async function pollHealth() {
  try {
    const response = await fetch(`${bridgeUrl()}/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data.broker) status = "no-bridge";
    else if (!data.queue?.available || data.queue?.consumers === 0) status = "no-worker";
    else status = "ok";
    allowedAdapters = data.allowed_adapters || [];
    renderAdapterOptions();
    el.healthBroker.textContent = data.broker ? "up" : "down";
    el.healthWorker.textContent = data.queue?.available ? `${data.queue.consumers} worker(s)` : "unavailable";
    el.healthKeyAdapter.textContent = data.key_adapter || "—";
  } catch {
    status = "no-bridge";
  }
  renderStatus();
  // The SSE connection is intentionally not tied to worker/broker health: closing it
  // on every transient health hiccup would risk dropping a reply for a request that's
  // still in flight (the bridge discards a reply it can't broadcast to anyone), and
  // the browser's EventSource already retries on its own when the connection drops.
  if (!eventSource) connectEvents();
  setTimeout(pollHealth, 2000);
}

function connectEvents() {
  streamOpen = false;
  eventSource = new EventSource(`${bridgeUrl()}/events`);
  eventSource.onopen = () => { streamOpen = true; renderStatus(); };
  eventSource.onmessage = (event) => {
    let payload;
    try { payload = JSON.parse(event.data); } catch { return; }
    if (payload.type !== "decision") return;
    onDecision(payload);
  };
  eventSource.onerror = () => { streamOpen = false; renderStatus(); };
}

async function publishScene(id, text) {
  const adapter = el.selectAdapter.value || undefined;
  const response = await fetch(`${bridgeUrl()}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items: [{ id, text }], adapter }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
}

function canRunGame() {
  return status === "ok" && streamOpen;
}

// ---------------------------------------------------------------------------
// Game state

let gameOn = false; // the player pressed Start and hasn't paused/game-overed
let gameOver = false;
let score = 0;
let lives = START_LIVES;
let speed = START_SPEED;
let elapsedMs = 0;
let spawnAccumulatorMs = 0;
let decisionAccumulatorMs = 0;
let hazardSeq = 0;
let hazards = []; // { id, laneIndex, distance } — distance counts down to 0 at the car
let carX = LANE_X[1];
let recommendedLaneIndex = 1;
let lastAppliedSeq = -1; // guards against a stale (out-of-order) reply overwriting the panel or steering
let decisionSeq = 0;
const pendingDecisions = new Map(); // id -> { seq, timeoutId }
let lastFrameAt = null;
let rafId = null; // the single pending requestAnimationFrame handle, so pause/resume can't create a second chain
let crashFlashUntil = 0;
let invulnerableUntilMs = 0; // brief grace period after a crash so the same hazard can't hit twice

function resetGame() {
  score = 0;
  lives = START_LIVES;
  speed = START_SPEED;
  elapsedMs = 0;
  spawnAccumulatorMs = 0;
  decisionAccumulatorMs = 0;
  hazards = [];
  carX = LANE_X[1];
  recommendedLaneIndex = 1;
  lastAppliedSeq = -1;
  invulnerableUntilMs = 0;
  for (const entry of pendingDecisions.values()) clearTimeout(entry.timeoutId);
  pendingDecisions.clear();
  resetBars();
  el.risk.textContent = "";
  el.sceneText.textContent = "—";
  updateStats();
}

function startGame() {
  if (gameOver) resetGame();
  gameOver = false;
  gameOn = true;
  lastFrameAt = null;
  renderStatus();
  // Only ever one frame in flight: if a frame from before a pause/resume cycle is
  // still pending when we get here, cancel it instead of letting it fire later and
  // start a second, parallel tick() chain (tick() itself also guards this, but a
  // pending frame scheduled before gameOn flipped back to true would otherwise see
  // gameOn===true and keep rescheduling itself alongside this new chain).
  if (rafId !== null) cancelAnimationFrame(rafId);
  rafId = requestAnimationFrame(tick);
}

function pauseGame() {
  gameOn = false;
  if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
  renderStatus();
}

function endGame() {
  gameOn = false;
  gameOver = true;
  const best = Math.max(readBestScore(), Math.round(score));
  writeBestScore(best);
  el.statBest.textContent = best;
  renderStatus();
}

// ---------------------------------------------------------------------------
// Scene description + decision requests

function laneLabel(i) { return `Lane ${i + 1}`; }

function nearestHazardDistance(laneIndex) {
  let nearest = null;
  for (const hazard of hazards) {
    if (hazard.laneIndex !== laneIndex || hazard.distance > DECISION_LOOKAHEAD_PX) continue;
    if (nearest === null || hazard.distance < nearest) nearest = hazard.distance;
  }
  return nearest;
}

function sceneText() {
  const currentLaneIndex = Math.round((carX - LANE_X[0]) / (LANE_X[1] - LANE_X[0]));
  const lines = LANES.map((_, i) => {
    const distance = nearestHazardDistance(i);
    return `${laneLabel(i)}: ${distance === null ? "clear" : `hazard ${Math.round(distance)}px ahead`}.`;
  });
  return [`The car is currently in ${laneLabel(currentLaneIndex).toLowerCase()} at ${Math.round(speed)} px/s.`, ...lines].join("\n");
}

function maybeRequestDecision(dt) {
  if (!canRunGame()) return;
  decisionAccumulatorMs += dt;
  if (decisionAccumulatorMs < DECISION_INTERVAL_MS) return;
  if (pendingDecisions.size >= MAX_INFLIGHT_DECISIONS) return; // back off until some resolve or time out
  decisionAccumulatorMs = 0;

  const seq = ++decisionSeq;
  const id = `${SESSION}-${seq}`;
  const text = sceneText();
  el.sceneText.textContent = text;
  el.deciding.hidden = false;

  const timeoutId = setTimeout(() => {
    pendingDecisions.delete(id);
    if (pendingDecisions.size === 0) el.deciding.hidden = true;
  }, PENDING_DECISION_TIMEOUT_MS);
  pendingDecisions.set(id, { seq, timeoutId });

  publishScene(id, text).catch(() => {
    const entry = pendingDecisions.get(id);
    if (entry) { clearTimeout(entry.timeoutId); pendingDecisions.delete(id); }
    if (pendingDecisions.size === 0) el.deciding.hidden = true;
  });
}

function onDecision(payload) {
  const entry = pendingDecisions.get(payload.id);
  if (!entry) return; // not ours, or already timed out client-side
  clearTimeout(entry.timeoutId);
  pendingDecisions.delete(payload.id);
  if (pendingDecisions.size === 0) el.deciding.hidden = true;

  const latency = payload.latency_ms;
  el.statLatency.textContent = latency != null ? `${latency} ms` : "—";
  el.statProvider.textContent = payload.adapter || payload.model || "—";

  // Everything below — the panel and the steering — only ever moves forward in
  // request order: a reply from an older request that arrives after a newer one's
  // reply must not overwrite the panel with a stale lane, or steer the car back
  // toward it, even if it completed while the newer one failed or is still pending.
  if (entry.seq <= lastAppliedSeq) return;
  lastAppliedSeq = entry.seq;

  if (payload.status !== "completed" || !payload.answers) {
    el.risk.textContent = payload.error || `Decision ${payload.status}`;
    return;
  }

  const laneAnswer = payload.answers.lane || {};
  const probabilities = laneAnswer.probabilities || {};
  const choice = laneAnswer.choice;
  for (const lane of LANES) {
    const row = el.laneBars.querySelector(`.bar-row[data-lane="${lane}"]`);
    const p = probabilities[lane] ?? 0;
    row.querySelector(".bar-fill").style.width = `${Math.round(p * 100)}%`;
    row.querySelector(".count").textContent = p.toFixed(2);
    row.classList.toggle("winner", lane === choice);
  }

  const risk = payload.answers.collision_risk?.noul;
  el.risk.textContent = typeof risk === "number"
    ? `Collision risk: ${(risk * 100).toFixed(0)}%${risk > 0.5 ? " — HIGH" : ""}`
    : "";

  const choiceIndex = LANES.indexOf(choice);
  if (choiceIndex !== -1) recommendedLaneIndex = choiceIndex;
}

function resetBars() {
  for (const row of el.laneBars.querySelectorAll(".bar-row")) {
    row.classList.remove("winner");
    row.querySelector(".bar-fill").style.width = "0%";
    row.querySelector(".count").textContent = "—";
  }
}

// ---------------------------------------------------------------------------
// Hazard spawning + physics

function spawnWave(dt) {
  // Only one wave of hazards is ever in flight: waiting for the road to clear before
  // starting the next wave's countdown keeps it a single line the car can read and
  // dodge, instead of several waves' hazards stacking up in the same lane because a
  // new one spawned on a timer before the last one had moved on.
  if (hazards.length > 0) return;
  spawnAccumulatorMs += dt;
  const interval = Math.max(SPAWN_INTERVAL_MIN_MS, SPAWN_INTERVAL_START_MS - speed * 2.2);
  if (spawnAccumulatorMs < interval) return;
  spawnAccumulatorMs = 0;

  // Each lane independently gets a hazard ~50% of the time. Re-roll an "every lane
  // blocked at once" result most of the time, so the game mostly stays winnable.
  let lanesToSpawn;
  do {
    lanesToSpawn = LANES.map(() => Math.random() < 0.5);
  } while (lanesToSpawn.every(Boolean) && Math.random() < 0.8);

  // A new wave is the moment that matters most: force the next tick's decision
  // check to fire immediately instead of waiting out the rest of the periodic
  // interval, so ORBIT gets as much lead time as possible to react to it.
  decisionAccumulatorMs = DECISION_INTERVAL_MS;

  const startDistance = CAR_Y + 60; // just above the visible canvas
  lanesToSpawn.forEach((spawn, laneIndex) => {
    if (!spawn) return;
    hazards.push({ id: ++hazardSeq, laneIndex, distance: startDistance });
  });
}

function updatePhysics(dt) {
  const dtSec = dt / 1000;
  speed = Math.min(MAX_SPEED, speed + SPEED_RAMP_PER_SEC * dtSec);
  elapsedMs += dt;
  score += speed * dtSec * 0.05;

  spawnWave(dt);

  const targetX = LANE_X[recommendedLaneIndex];
  const maxStep = STEER_SPEED * dtSec;
  const dx = targetX - carX;
  carX += Math.abs(dx) <= maxStep ? dx : Math.sign(dx) * maxStep;

  // UNSAFE_DISTANCE is half the car's height plus half the hazard's: the car and a
  // same-lane hazard can only actually overlap vertically while the hazard's distance
  // is within +/-UNSAFE_DISTANCE of the car. A hazard must not be removed (and scored
  // as passed) before it clears that window, or a late lane change could pass clean
  // through a hazard that's still visually overlapping the car with no collision check.
  const survivors = [];
  for (const hazard of hazards) {
    hazard.distance -= speed * dtSec;
    if (hazard.distance <= -UNSAFE_DISTANCE) {
      score += 10; // passed safely
      continue;
    }
    survivors.push(hazard);
  }
  hazards = survivors;

  if (elapsedMs >= invulnerableUntilMs) {
    for (const hazard of hazards) {
      if (Math.abs(hazard.distance) > UNSAFE_DISTANCE) continue;
      const hazardX = LANE_X[hazard.laneIndex];
      if (Math.abs(hazardX - carX) > (CAR_W + HAZARD_W) / 2 - 10) continue; // lane overlap tolerance
      onCrash(hazard);
      break; // one collision per frame is plenty
    }
  }

  el.statScore.textContent = Math.floor(score);
}

function onCrash(hazard) {
  hazards = hazards.filter((h) => h.id !== hazard.id);
  lives -= 1;
  invulnerableUntilMs = elapsedMs + 900;
  crashFlashUntil = performance.now() + 500;
  updateStats();
  if (lives <= 0) endGame();
}

function updateStats() {
  el.statScore.textContent = Math.floor(score);
  el.statLives.textContent = Math.max(0, lives);
}

// ---------------------------------------------------------------------------
// Main loop

function tick(now) {
  rafId = null;
  if (!gameOn) return;
  if (lastFrameAt === null) lastFrameAt = now;
  const dt = Math.min(100, now - lastFrameAt); // clamp so a dropped/backgrounded tab can't jump physics
  lastFrameAt = now;

  if (canRunGame()) {
    updatePhysics(dt);
    maybeRequestDecision(dt);
  }
  drawScene();
  if (gameOn) rafId = requestAnimationFrame(tick); // updatePhysics may have ended the game this frame
}

// ---------------------------------------------------------------------------
// Rendering

function drawScene() {
  const { width, height } = el.road;
  ctx.clearRect(0, 0, width, height);

  const asphalt = ctx.createLinearGradient(0, 0, 0, height);
  asphalt.addColorStop(0, "#111f1d");
  asphalt.addColorStop(1, "#060e0d");
  ctx.fillStyle = asphalt;
  ctx.fillRect(0, 0, width, height);

  // Road edges, so the lanes read as a track rather than empty canvas.
  ctx.strokeStyle = "rgba(72,229,192,.25)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(1, 0); ctx.lineTo(1, height);
  ctx.moveTo(width - 1, 0); ctx.lineTo(width - 1, height);
  ctx.stroke();

  // Lane dividers scroll with road speed, so the car visibly reads as moving
  // forward even though it's the hazards (and these dashes) that actually animate.
  const dashOffset = -((elapsedMs / 1000) * speed) % 40;
  ctx.strokeStyle = "rgba(230,241,238,.3)";
  ctx.setLineDash([18, 18]);
  ctx.lineDashOffset = dashOffset;
  ctx.lineWidth = 2;
  for (const x of [107, 213]) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  ctx.fillStyle = "rgba(154,175,169,.55)";
  ctx.font = "11px ui-monospace, monospace";
  ctx.textAlign = "center";
  LANES.forEach((_, i) => ctx.fillText(String(i + 1), LANE_X[i], 16));

  for (const hazard of hazards) {
    const y = CAR_Y - hazard.distance;
    if (y < -HAZARD_H || y > height + HAZARD_H) continue;
    drawHazard(LANE_X[hazard.laneIndex], y);
  }

  drawCar(carX, CAR_Y);

  if (performance.now() < crashFlashUntil) {
    ctx.fillStyle = "rgba(255,92,95,.25)";
    ctx.fillRect(0, 0, width, height);
  }
}

function roundRectPath(x, y, w, h, r) {
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
}

function drawHazard(cx, cy) {
  const w = HAZARD_W, h = HAZARD_H;
  ctx.save();
  ctx.translate(cx - w / 2, cy - h / 2);

  ctx.fillStyle = "rgba(0,0,0,.35)";
  roundRectPath(2, 3, w, h, 5);
  ctx.fill();

  // Diagonal hazard stripes as filled bands (not thin strokes) so the barricade
  // reads clearly as "danger" at a glance, even moving at speed.
  ctx.save();
  roundRectPath(0, 0, w, h, 5);
  ctx.clip();
  ctx.fillStyle = "#1c1b18";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#f5b85a";
  const stripeW = 11;
  for (let x = -h; x < w + h; x += stripeW * 2) {
    ctx.beginPath();
    ctx.moveTo(x, h);
    ctx.lineTo(x + h, 0);
    ctx.lineTo(x + h + stripeW, 0);
    ctx.lineTo(x + stripeW, h);
    ctx.closePath();
    ctx.fill();
  }
  ctx.restore();

  ctx.strokeStyle = "#2a1a08";
  ctx.lineWidth = 2;
  roundRectPath(0, 0, w, h, 5);
  ctx.stroke();
  ctx.restore();
}

function drawCar(cx, cy) {
  const w = CAR_W, h = CAR_H;
  ctx.save();
  ctx.translate(cx, cy);

  // Shadow, slightly offset, so the car reads as sitting on the road.
  ctx.save();
  ctx.translate(0, 3);
  ctx.fillStyle = "rgba(0,0,0,.4)";
  roundRectPath(-w / 2, -h / 2, w, h, [10, 10, 5, 5]);
  ctx.fill();
  ctx.restore();

  // Wheels peek out past the body on both sides, front and rear, like a real
  // top-down car sprite rather than a plain rounded box.
  ctx.fillStyle = "#12201e";
  const wheelW = 5, wheelH = 14;
  ctx.fillRect(-w / 2 - 2, -h / 2 + 7, wheelW, wheelH);
  ctx.fillRect(w / 2 - wheelW + 2, -h / 2 + 7, wheelW, wheelH);
  ctx.fillRect(-w / 2 - 2, h / 2 - 7 - wheelH, wheelW, wheelH);
  ctx.fillRect(w / 2 - wheelW + 2, h / 2 - 7 - wheelH, wheelW, wheelH);

  // Body: a vertical gradient gives it a glossy, lit-from-above look. The front
  // (toward the approaching hazards, i.e. up) gets rounder corners than the rear.
  const bodyGrad = ctx.createLinearGradient(0, -h / 2, 0, h / 2);
  bodyGrad.addColorStop(0, "#6fb4ff");
  bodyGrad.addColorStop(0.5, "#2f7de0");
  bodyGrad.addColorStop(1, "#1c4f9c");
  ctx.fillStyle = bodyGrad;
  roundRectPath(-w / 2, -h / 2, w, h, [11, 11, 4, 4]);
  ctx.fill();
  ctx.strokeStyle = "#0d2c57";
  ctx.lineWidth = 1.5;
  roundRectPath(-w / 2, -h / 2, w, h, [11, 11, 4, 4]);
  ctx.stroke();

  // Roof / cabin.
  ctx.fillStyle = "rgba(8,18,17,.55)";
  const roofW = w * 0.62, roofH = h * 0.42;
  roundRectPath(-roofW / 2, -h * 0.08 - roofH / 2, roofW, roofH, 6);
  ctx.fill();

  // Windshield, toward the front.
  ctx.fillStyle = "rgba(214,236,255,.9)";
  const wsW = w * 0.56, wsH = h * 0.15;
  roundRectPath(-wsW / 2, -h * 0.32, wsW, wsH, 4);
  ctx.fill();

  // Headlights (front) and taillights (rear).
  ctx.fillStyle = "#ffe9a8";
  ctx.beginPath();
  ctx.ellipse(-w * 0.3, -h / 2 + 5, 2.6, 3.4, 0, 0, Math.PI * 2);
  ctx.ellipse(w * 0.3, -h / 2 + 5, 2.6, 3.4, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#ff5c5f";
  ctx.beginPath();
  ctx.ellipse(-w * 0.3, h / 2 - 5, 2.2, 2.8, 0, 0, Math.PI * 2);
  ctx.ellipse(w * 0.3, h / 2 - 5, 2.2, 2.8, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

// ---------------------------------------------------------------------------
// Status / overlay / panel wiring

function renderStatus() {
  // ok-but-not-streaming is its own label: health can report a healthy broker/worker
  // while the SSE reply stream is still (re)connecting, and running the game before
  // it's open means no decision reply could ever reach this browser.
  const effective = status === "ok" && !streamOpen ? "no-stream" : status;
  const labels = {
    connecting: "CONNECTING", "no-bridge": "NO BRIDGE", "no-worker": "NO WORKER",
    "no-stream": "CONNECTING REPLY STREAM", ok: "LIVE",
  };
  const classes = {
    connecting: "warn", "no-bridge": "bad", "no-worker": "bad", "no-stream": "warn", ok: "ok",
  };
  el.bridgePill.className = `bridge-pill ${classes[effective]}`;
  el.bridgePill.innerHTML = `<i></i>${labels[effective]}`;

  if (effective !== "ok") {
    el.btnStart.disabled = true;
    showOverlay(labels[effective], status === "no-bridge"
      ? `Can't reach the bridge at ${settings.bridgeUrl}. Run examples/triage-rush-mq/game_bridge.py --allowed-adapters lane-choice,lane-choice-openai`
      : status === "no-worker"
      ? "The bridge is up but no worker is consuming orbit.requests — start an ORBIT worker."
      : "Waiting for the bridge's reply stream (/events) to open.");
    return;
  }

  el.btnStart.disabled = false;
  if (gameOver) {
    el.btnStart.textContent = "Start (space)";
    showOverlay("GAME OVER", `Score: ${Math.floor(score)} · Best: ${readBestScore()}`, "Play again", startGame);
  } else if (!gameOn) {
    el.btnStart.textContent = "Start (space)";
    showOverlay("PAUSED", "Press Start, or Space, to drive.", elapsedMs > 0 ? "Resume" : "Start", startGame);
  } else {
    el.btnStart.textContent = "Pause (space)";
    hideOverlay();
  }
}

function showOverlay(label, detail, actionLabel, actionFn) {
  el.overlay.hidden = false;
  el.overlayLabel.textContent = label;
  el.overlayDetail.textContent = detail;
  if (actionLabel) {
    el.btnOverlayAction.hidden = false;
    el.btnOverlayAction.textContent = actionLabel;
    el.btnOverlayAction.onclick = actionFn;
  } else {
    el.btnOverlayAction.hidden = true;
    el.btnOverlayAction.onclick = null;
  }
}
function hideOverlay() { el.overlay.hidden = true; }

function renderAdapterOptions() {
  const current = el.selectAdapter.value;
  el.selectAdapter.innerHTML = '<option value="">(use API key\'s adapter)</option>';
  for (const adapter of allowedAdapters) {
    const option = document.createElement("option");
    option.value = adapter;
    option.textContent = adapter;
    el.selectAdapter.appendChild(option);
  }
  if (allowedAdapters.includes(current)) el.selectAdapter.value = current;
}

function toggleStart() {
  if (el.btnStart.disabled) return;
  if (!gameOn) startGame(); else pauseGame();
}

el.btnStart.addEventListener("click", toggleStart);
el.btnPanel.addEventListener("click", () => { el.panel.hidden = !el.panel.hidden; });
el.panelClose.addEventListener("click", () => { el.panel.hidden = true; });
el.inputBridgeUrl.addEventListener("change", () => {
  settings.bridgeUrl = el.inputBridgeUrl.value.trim() || DEFAULT_SETTINGS.bridgeUrl;
  writeSettings(settings);
  if (eventSource) { eventSource.close(); eventSource = null; }
  streamOpen = false;
  pauseGame();
  status = "connecting";
  renderStatus();
});
el.btnResetScore.addEventListener("click", () => {
  writeBestScore(0);
  el.statBest.textContent = "0";
});

document.addEventListener("keydown", (event) => {
  if (event.target.tagName === "INPUT" || event.target.tagName === "SELECT") return;
  if (event.code === "Space") { event.preventDefault(); toggleStart(); }
  else if (event.key === "p" || event.key === "P") { el.panel.hidden = !el.panel.hidden; }
  else if (event.key === "Escape") { el.panel.hidden = true; }
});

resetGame();
drawScene();
renderStatus();
pollHealth();
