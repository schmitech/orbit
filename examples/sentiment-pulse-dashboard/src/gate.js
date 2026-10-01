// The Phase 1 gate result for the provider this dashboard instance is pointed at.
//
// DORMANT BY DEFAULT. Every field below is `null`/`false` until the held-out eval in
// docs/roadmap/complete/decision-model-sentiment-analysis.md (Phase 1) actually runs and the gate
// decides. Do not fill this in from a tuning-split run, a hunch, or "it looked fine in
// the demo" — only from a frozen, single, held-out run recorded in that doc's Results
// section. Panels below read this object to decide what they're allowed to show; a
// panel with no passing signal shows nothing, per the eval plan's "no faked answers"
// rule — there is no placeholder band or sample number to fall back on.

export const GATE = {
  // Set after the Results section records a dated held-out run for this provider.
  evaluated: false,
  provider: null, // "typesafe" | "ollama"
  modelVersion: null, // e.g. "jev-1.13.0"
  heldOutSetVersion: null,

  polarity: {
    band: null, // "high" | "high_no_threshold" | "middle" | "low"
    macroF1: null,
    routing: {
      // Only meaningful when band === "high".
      signal: null, // "p_top" | "confidence"
      threshold: null, // number, or "none"
      coverage: null,
      acceptedError: null,
    },
  },

  // Each gated one at a time; only shown if `passed`.
  sarcasm: { passed: false, auroc: null },
  escalation: {
    passed: false, // AUROC >= 0.8
    auroc: null,
    cutoffUsable: false, // AND precision/recall thresholds met at the frozen cutoff
    threshold: null,
    precision: null,
    recall: null,
    falseAlertShare: null,
  },
  aspects: { passed: false, macroF1: null },
  valence: { passed: false, withinOneAccuracy: null },

  latency: { p50Ms: null, p95Ms: null, burst100DrainS: null },
};

export const isExperimental = () => GATE.polarity.band === "middle";
export const showsRoutingLine = () => GATE.polarity.band === "high";
export const showsEscalationLane = () => GATE.escalation.passed && GATE.escalation.cutoffUsable;
