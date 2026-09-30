# Decision-Model Sentiment Analysis — Implementation Plan

## Summary

Extend the [decision-model adapters](../adapters/decision-models.md) to sentiment analysis, and add a live booth demo that shows it.

Sentiment maps onto the three question types:

| Signal | Question type | Meaning |
|--------|---------------|---------|
| Polarity (positive / neutral / negative / mixed) | `choice` | One label, with a probability for each option |
| Valence (very negative … very positive) | `score` | A signed 5-level scale. The answer is a distribution over levels |
| Sarcasm | `noul` | Does the text say the opposite of what it means? |
| Needs escalation | `noul` | One explicit rule; see [Signals](#signals) |
| Per-aspect sentiment (price, support, product, delivery) | one `choice` per aspect | A fixed set of aspects, each with a `not_mentioned` option |

No server changes are needed. The step, both providers, the MQ path and the typed `decision` output all work as they are.

The evaluation decides what ships and what the demo may claim. Nothing is announced or demoed until the gate passes. The release proceeds in phases:

1. **Phase 0 — Provisional adapters and a labeled set.** Add the adapters disabled, so they can be evaluated without being offered to users. Build and freeze a labeled dataset split into a tuning set and a held-out test set.
2. **Phase 1 — Evaluate and decide.** Tune the question wording and pick every threshold on the tuning set only. Then evaluate once on the held-out set, with everything frozen. The gate decides whether to enable the adapters, which claims are allowed, and whether Phase 2 goes ahead.
3. **Phase 2 — "Sentiment Pulse" dashboard,** if the gate allows it. A live dashboard fed by MQ bursts, built on the existing Triage Rush bridge.
4. **Phase 3 (optional) —** generalize the Triage Rush game so it works with any decision adapter.

## Signals

Every signal has one written definition. The question text sent to the model and the labeling guide for annotators use the same wording.

- **Polarity:** the author's overall stance.
  - `mixed` means clearly both positive and negative, about different things.
  - `neutral` means factual or no stance.
- **Valence:** a signed scale from `Very negative` (0) to `Very positive` (4), with `Neutral` (2) in the middle. It is not intensity on its own. A strongly mixed review sits near the middle, and polarity (`mixed`) carries that information.
- **Sarcasm:** the literal wording contradicts the meaning ("Great, another update that broke login").
- **Needs escalation:** yes when **any** of the following holds, otherwise no.
  - The author says, or clearly implies, that they will cancel, leave or switch.
  - The author reports harm: money taken wrongly, lost data, a safety issue, or being locked out of something they need.
  - The author explicitly demands a reply from a person or a manager.

  Anger alone doesn't count, and neither does a low valence alone.
- **Aspects:** for each of price, support, product and delivery, the answer is `positive`, `negative` or `not_mentioned`. An aspect with no clear stance is `not_mentioned`.

## Phase 0 — Provisional adapters and a labeled set

### Provisional adapters

Add two adapters to `config/adapters/decision.yaml` with `enabled: false`. They validate and can be evaluated, but the server doesn't load them.
- Use the same shape as `ticket-triage`: `type: decision_model`, `datasource: none`, the multimodal passthrough implementation, `state_key: "text"` and `allow_question_override: true`.
- **`sentiment-analysis`:** `decision_provider: typesafe`, `model: jev-latest`.
- **`sentiment-analysis-local`:** `decision_provider: ollama`, `model: tev1:0.8b`.

```yaml
questions:
  polarity:
    type: "choice"
    instructions: "What is the author's overall stance?"
    criteria:
      positive: "Satisfied, happy or praising"
      neutral: "Factual, or no clear stance"
      negative: "Unhappy, frustrated or complaining"
      mixed: "Clearly both positive and negative, about different things"
  valence:
    type: "score"
    instructions: "On a signed scale from very negative to very positive, where does the text sit overall?"
    criteria: ["Very negative", "Negative", "Neutral", "Positive", "Very positive"]
  sarcasm:
    type: "noul"
    instructions: "Does the literal wording say the opposite of what the author means?"
  needs_escalation:
    type: "noul"
    instructions: "Does the author say they will cancel, leave or switch; report harm such as money taken wrongly, lost data, a safety issue or being locked out; or explicitly demand a reply from a person?"
  aspect_price:
    type: "choice"
    instructions: "What is the author's stance on price or value?"
    criteria: { positive: "Good value", negative: "Too expensive or poor value", not_mentioned: "Price has no clear stance or isn't discussed" }
  aspect_support:
    type: "choice"
    instructions: "What is the author's stance on customer support?"
    criteria: { positive: "Helpful support", negative: "Unhelpful or slow support", not_mentioned: "Support has no clear stance or isn't discussed" }
  aspect_product:
    type: "choice"
    instructions: "What is the author's stance on the product itself?"
    criteria: { positive: "Works well, high quality", negative: "Broken or low quality", not_mentioned: "The product has no clear stance or isn't discussed" }
  aspect_delivery:
    type: "choice"
    instructions: "What is the author's stance on shipping or delivery?"
    criteria: { positive: "Fast or on time", negative: "Late, lost or damaged", not_mentioned: "Delivery has no clear stance or isn't discussed" }
```

Update `server/tests/test_decision/test_decision_adapter_config.py` so the expected name set includes both adapters. The test validates every adapter in the file, disabled ones too.

### Labeled dataset

Put the data in `examples/sentiment-pulse/eval/` as two files with the same schema. **Every measured signal is labeled on every record:**

```json
{"id": "rev-001", "text": "Arrived two days late but support fixed it in minutes. Love it.",
 "polarity": "mixed", "valence": 3, "sarcasm": false, "needs_escalation": false,
 "aspects": {"price": "not_mentioned", "support": "positive", "product": "not_mentioned", "delivery": "negative"},
 "lang": "en"}
```

- **`sentiment-tune.jsonl`** (60 texts) is the only set used for decisions: adjusting question wording or criteria, and choosing the polarity routing threshold and the escalation cutoff. Sixty texts rather than fewer, so the thresholds aren't picked from a handful of examples.
- **`sentiment-test.jsonl`** (120 texts) is the held-out set. It's written and labeled **before** any tuning, and frozen once committed. It's evaluated **exactly once** per provider and model version, after the wording and both thresholds are frozen. Nothing is chosen from its results.
- **Any later change** to question wording, criteria or thresholds, after the held-out run, needs a **fresh held-out set**: new texts, labeled the same way. The old set then becomes extra tuning data. Record each held-out run in the Results section, with its set version, so the history shows which numbers came from which frozen set.

**Composition quotas** for the held-out set. The tuning set follows the same proportions (15 per polarity), with at least 12 escalation positives.

| Polarity | Count | Share |
|----------|-------|-------|
| positive | 30 | 25% |
| negative | 30 | 25% |
| neutral | 30 | 25% |
| mixed | 30 | 25% |

- **Sarcasm:** 18 texts (15%), spread across the positive, negative and mixed labels. A sarcastic text's polarity is its intended meaning.
- **Needs escalation:** at least 25 positives, so recall and precision are measurable.
- **Aspects:** each aspect is non-`not_mentioned` in at least 20 texts, split roughly evenly between positive and negative.
- **Length:** a mix of short and long texts, including at least 5 multi-paragraph reviews.
- **Languages:** 10 extra texts in French and Spanish, stored in `sentiment-test-multilingual.jsonl`. They're reported separately and never count toward the gate.

**Labeling.** Two people label every text, in both sets, on their own, following the written rules in [Signals](#signals).
- Measure agreement per signal: Cohen's κ for polarity, sarcasm, escalation and aspects, and weighted κ for valence.
- An adjudicator resolves disagreements into the final label.
- Treat any signal with κ < 0.6 as too subjective to gate on. Report it, but don't let it block or justify shipping.
- For polarity, record human-vs-human macro-F1 on the held-out set as well. It's **context only**: it's reported next to the model's score and explains a low result, but it never moves the gate's cutoffs.

### Evaluation script

`utils/scripts/eval_decision_adapter.py` is generic. It takes an adapter name from `config/adapters/*.yaml` and a JSONL file.
- **Direct mode (default):** reads the adapter's questions straight from the YAML, whether or not the adapter is enabled, then loads the real config and calls `DecisionService.decide()`. This isolates model quality. It's the only mode used for the gate, which is why the adapters can stay disabled until then.
- **`--via-api`:** goes through `POST /v1/chat` with an API key, and includes ORBIT overhead in the latency figures. The adapter registry skips disabled adapters (`server/adapters/registry.py`), so this mode only works after the adapter is enabled. See [Phase 1](#phase-1--evaluate-and-decide), step 5.
- **`--split tune|test`:** is required and printed in the report header, so tuning numbers are never mistaken for gate numbers.
- **`--burst N`:** publishes N texts at once through the MQ bridge and reports the time until all have been answered. It feeds the surge sizing in Phase 2. It goes through ORBIT's worker, so, like `--via-api`, it needs the adapter enabled.
- **Output:** Markdown on stdout, and JSON with `--json`, so runs can be compared in PRs.
- **Providers:** run TypeSafe `jev-latest` and Ollama `tev1:0.8b`, with `nimble` optional where a GPU is available.

**Metrics:**
- **Choice questions** (polarity and each aspect): accuracy, macro-F1 and a confusion matrix.
- **Valence:** mean absolute error of the expected level, exact-level accuracy, and accuracy within one level.
- **Noul questions:** AUROC, and precision and recall at thresholds 0.5 and 0.8.
- **Selective accuracy** (polarity), used for the routing claim.
  - Take `p_top`, the probability the model gives its chosen polarity (the chosen option's entry in `probabilities`).
  - For each threshold t in {0.5, 0.6, 0.7, 0.8, 0.9}, report the **coverage** (the share of items with `p_top ≥ t`) and the **error rate among accepted items**, with 95% Wilson intervals.
  - On the tuning split the table is used to **choose** t. On the held-out split the script only reports the frozen t passed with `--routing-threshold`. That way the held-out set can't be used to pick among candidates.
  - `--routing-threshold none` records that no threshold qualified on the tuning set. The script then reports "no routing threshold" and skips the selective check.
- **Escalation cutoff:** the same idea for `needs_escalation`. The tuning split shows precision, recall and the false-alert share at each cutoff. The held-out split reports only the frozen cutoff passed with `--escalation-threshold`. `--escalation-threshold none` means no cutoff qualified. The script then reports AUROC only, so escalation can at most pass as a ranking.
- **Calibration** (exploratory only): a 5-bin reliability table and ECE on `p_top`, with bootstrap intervals. With 120 texts, the bins are too thin for ECE to be a gate.
- **Provider `confidence`:** ORBIT passes it through unchanged (`TypeSafeDecisionService.decide` returns the SDK's `answers` as they come). It isn't the top probability: in the Triage Rush run, a `team` answer had probabilities 0.55 / 0.45 and `confidence: 0.39`.
  - Before using it for anything, confirm what it means from the TypeSafe docs and the nimble spec.
  - **`p_top` is the routing signal by default.** `confidence` becomes eligible only once it's documented. When it is, both signals are compared **on the tuning split only**, and whichever gives the better coverage at ≤ 5% accepted error is frozen with its threshold (`--routing-signal p_top|confidence`).
  - On the held-out split, the script evaluates only the frozen signal and threshold. It never compares signals there, so the choice can't be made from held-out results.
- **Latency and tokens:** p50 and p95 latency, and mean input and output tokens.

**Script tests** use a fake `DecisionService` with fixed answers. They check:
- macro-F1 on a hand-computed confusion matrix;
- Wilson intervals and selective coverage and error on a known example;
- the reliability bins;
- valence mean absolute error;
- that missing answers and provider errors count as wrong and are also reported separately;
- that the script refuses to run without `--split`;
- that `--split test` requires `--routing-signal`, `--routing-threshold` and `--escalation-threshold`, each set either to a frozen value or to an explicit `none`, and prints no per-candidate threshold table;
- that with `none`, the report says "no threshold" and the corresponding band or lane checks are skipped rather than failing.

## Phase 1 — Evaluate and decide

1. **Tune.** Run on `--split tune` and adjust question wording and criteria. Keep the signals and their definitions fixed; if a definition turns out wrong, change it in [Signals](#signals) and in the labeling guide, and relabel.
2. **Choose the thresholds on the tuning set**, for each provider:
   - **Routing signal and threshold** (`routing_signal`, `t_route`): `p_top`, unless `confidence` is documented and does better on the tuning set. `t_route` is the lowest t with coverage ≥ 60% and accepted error ≤ 5% on the tuning set. If none qualifies, freeze `t_route = none`: that provider has no routing threshold, and the High band isn't reachable.
   - **Escalation cutoff** `t_esc`: the lowest cutoff with precision ≥ 0.8, meaning at most 1 in 5 alerts is a false alarm, and recall ≥ 0.6. If none qualifies, freeze `t_esc = none`: escalation has no default cutoff, and the dashboard lane isn't shown.
3. **Freeze** the wording, `routing_signal`, `t_route` and `t_esc` (a value or `none` for each), and commit them to this doc before the held-out run.
4. **Test once.** Run `--split test` for each provider with the frozen thresholds, and record the results in the Results section: dated, with the held-out set version and the resolved model version, such as `jev-1.13.0`. Apply the gate below **per provider**. It's normal for TypeSafe to pass and `tev1:0.8b` to fall in a lower band.
5. **Enable, then measure the system.** For each provider in the High or Middle band, set `enabled: true`, restart ORBIT, and run `--via-api` and `--burst 100` to get the end-to-end latency and surge drain time. These measure the system, not the model, so they don't count as another held-out evaluation. They can use the tuning texts.

**Polarity gate.** F1 is macro-F1 on the held-out set. The cutoffs are fixed and don't overlap. Human-vs-human agreement is reported next to the score as context only. If humans agree below 0.85, reaching High is unlikely, and the doc says so rather than moving the bar.

| Band | Outcome |
|------|---------|
| **High:** F1 ≥ 0.85, and using the frozen `routing_signal` and `t_route`, the held-out coverage is ≥ 60% and the accepted error ≤ 5% (upper Wilson bound ≤ 10%) | Enable the adapter. Document it as a standalone feature, with a "route to a person below `t_route`" recommendation and the held-out error at that threshold. Phase 2 may show the routing line. |
| **High accuracy, no usable threshold:** F1 ≥ 0.85, but `t_route` is `none` or fails on the held-out set | Enable it. Document the distributions and **no** routing threshold. Phase 2 shows distributions only. |
| **Middle:** 0.75 ≤ F1 < 0.85 | Enable it, labeled **experimental** in the docs and adapter comments. Phase 2 may go ahead only with an "experimental" badge and no routing line. Improving it later means tuning on the tuning set, then testing on a **fresh** held-out set. |
| **Low:** F1 < 0.75 | Leave the adapter `enabled: false`, as an example config only. No Phase 2 for this provider. Revisit when newer models are available. |

**Other signals** are gated one at a time, and only if their κ ≥ 0.6. A signal that fails is dropped from the adapter's questions, or kept and marked experimental, and the dashboard doesn't show a panel for it.
- **Sarcasm:** AUROC ≥ 0.8.
- **Escalation:** AUROC ≥ 0.8, **and** at the frozen `t_esc` the held-out precision is ≥ 0.8 and recall ≥ 0.6. The held-out precision becomes the expected false-alert share the dashboard states, for example "about 1 in 6 alerts is a false alarm". If AUROC passes but the cutoff doesn't, the signal is documented as a ranking only: the dashboard may sort by it, but it shows no alert lane.
- **Aspects:** macro-F1 ≥ 0.75.
- **Valence:** within-one-level accuracy ≥ 0.85.

**Latency.** The measured p50 and p95, and the `--burst 100` drain time, are the only latency figures the docs and dashboard may quote.

**Docs,** after the gate:
- Add a "Sentiment analysis" subsection under "Shipped examples" in `docs/adapters/decision-models.md`. It gives the band, the measured numbers, and how to read valence (expected level vs distribution).
- Document a **triage + sentiment** variant: adding `polarity` and `needs_escalation` to `ticket-triage` returns routing and mood in one call. That's documentation only. Leave `ticket-triage` unchanged, because the Triage Rush game and its tests depend on it.

## Phase 2 — "Sentiment Pulse" live dashboard

Only for a provider in the High or Middle band.

A head-to-head race works poorly for sentiment: the labels are subjective, and visitors argue with the answer key on ambiguous texts. The strength to show is speed at volume, so the demo is a live dashboard in the style of `examples/threat-telemetry-dashboard/`.

### Transport: use the Triage Rush bridge as it is

Keep `examples/triage-rush-mq/game_bridge.py` where it is, and run it for this demo with:

```bash
python examples/triage-rush-mq/game_bridge.py \
  --adapter sentiment-analysis \
  --allowed-adapters sentiment-analysis,sentiment-analysis-local
```

- **Surge:** publish 100 reviews as two `/publish` calls of 50 each, back to back. That stays within the bridge's existing cap of 50 items per call, so the bridge needs no changes.
- **Timeout check:** the bridge times out unanswered items after `--timeout` (30 s). The `--burst 100` result from Phase 1, step 5 (run after enablement) has to show the surge draining inside that window on each provider the dashboard supports. If it doesn't, lower the surge size in the dashboard, or document running the bridge with a larger `--timeout`. The flag already exists.
- **Moving the bridge:** move it to a shared `examples/decision-mq-bridge/` only when a third demo needs it.

### Dashboard: `examples/sentiment-pulse-dashboard/` (Vite + React)

Use the same stack and dark HUD tokens as the Triage Rush game. Pin the port to **5182** with `--strictPort`, since 5173 is orbitchat and 5180 is Triage Rush.

- **Review deck** (`src/reviews.js`): about 150 hand-written reviews and social posts about one fictional product.
  - The deck is **separate from the eval sets**, so the demo can never overfit the gate.
  - Its labels are used only by the optional "reveal" view, never to fake answers.
- **Stream controls:**
  - a **Play/Pause stream** control (items per second, 1–20);
  - a **Surge** button: 100 reviews in two publishes of 50;
  - a **Pause all requests** control, persisted in `localStorage`;
  - **nothing sent on page load**: the stream starts only when the presenter presses Play.
- **Panels** (show only the signals that passed their gate):
  - **Live feed:** each review card fills in with its polarity chip, valence bar, sarcasm flag and latency as its decision arrives. Cards queue without overlapping, with a "+N waiting" badge, as in Triage Rush.
  - **Mood gauge:** a rolling mean of expected valence over the last N answers, with a 60-second sparkline.
  - **Polarity distribution:** live counts and shares.
  - **Aspect heatmap:** rows are price, support, product and delivery; columns are positive and negative; `not_mentioned` is excluded.
  - **Escalation lane:** reviews whose `needs_escalation` probability is at or above the frozen `t_esc`, highest first. It only appears if escalation passed its cutoff gate.
    - The panel states the expected false-alert share measured on the held-out set at `t_esc`, and shows the rule from [Signals](#signals) as a tooltip.
    - The presenter can move the cutoff for the demo. When it differs from `t_esc`, the false-alert figure is replaced with "not measured at this cutoff" rather than extrapolated.
  - **Routing-signal panel:** a histogram of the provider's frozen `routing_signal` (`p_top` or documented `confidence`) for polarity. The "route to a person below t" line, with the share of items it would send to a person, appears **only** if the provider reached the High band. It uses the frozen `t_route` and the accepted error rate from Phase 1.
  - **HUD:** decisions per second, p50/p95 latency, queue depth, worker count, provider, and the gate band ("experimental" when Middle). It uses the bridge's `/health`.
- **"Type your own":** an input where a visitor writes a sentence and sees its full decision, every distribution.
  - The on-screen copy quotes the latency measured in Phase 1, for example "p50 180 ms on TypeSafe", and the card shows the actual round-trip time. There's no hard-coded speed claim.
  - It's capped at 280 characters, never stored, and published only through the bridge.
  - Optionally, the visitor picks a polarity first, then sees ORBIT's distribution next to their pick.
- **No faked answers:** "NO BRIDGE", "NO WORKER" and "NO REPLY STREAM" states work exactly as in Triage Rush. The dashboard never shows made-up answers.

### Docs

- Write `examples/sentiment-pulse-dashboard/README.md`, self-contained and following the Triage Rush README. It covers:
  - the setup steps, including the bridge command above;
  - creating a key with `--adapter sentiment-analysis` and a prompt file;
  - the gate band and the measured numbers;
  - a booth checklist: pause when away, warm up, fullscreen.
- Add a prompt and intro pair in the example folder, as for Triage Rush: `sentiment-pulse-assistant-prompt.md` and `sentiment-pulse-intro.md`. Also add an orbitchat entry in `clients/orbitchat/orbitchat-local.yaml`.

## Phase 3 (optional) — Generalize Triage Rush to any decision adapter

The team-routing and resource-decision challenges each hard-code their bins and read one answer (`team` or `action`). Generalize them:
- Add a per-adapter game profile: which `choice` question sets the bins, the bin labels and keys, the deck file, and whether the text goes plain or as structured state.
- Add a profile for `sentiment-analysis*`, with polarity as the bins. Show a "labels are subjective" note, and give partial credit on `mixed` when the AI's top two polarities include the label.

This phase is low priority. Do it only if the Phase 2 dashboard doesn't cover the booth need. If it adds a third client of the bridge, that's the point to move the bridge to a shared folder.

## Test plan

- **Adapter config:** the two provisional sentiment adapters (disabled) pass `validate_yaml_text`, `validate_structure` and `validate_questions` in the extended `test_decision_adapter_config.py`.
- **Eval script:** the unit tests listed under [Evaluation script](#evaluation-script).
- **Dataset checks:** a small test asserts on both JSONL files:
  - the schema is complete, with every signal labeled on every record;
  - the quotas are met (120 held-out texts, 60 tuning texts, 25% per polarity, and the escalation-positive minimums);
  - no text appears in both the tuning and held-out sets, or in the dashboard deck.
- **Gate procedure:** the Results section records the frozen `routing_signal`, `t_route` and `t_esc` (values or `none`) with a commit that predates the held-out run, and exactly one held-out run per set version, provider and model version.
- **Surge drain:** after enablement (Phase 1, step 5), `--burst 100` through the bridge finishes inside the bridge `--timeout` on each provider. The results go in the Results section.
- **Dashboard:** build check (`npm run build`), then a live run on Chrome in the foreground:
  - nothing is sent on load;
  - Play streams items;
  - Surge publishes two batches of 50, and the queue depth spikes and then drains with no timeouts;
  - Pause stops publishing, checked with the fetch-count method used for Triage Rush;
  - the escalation lane fills;
  - "type your own" returns a decision;
  - the no-bridge and no-worker states work;
  - the band badge, routing line and escalation false-alert figure match the recorded gate result.

## Lessons carried over from Triage Rush

- **CORS headers:** add them in `on_response_prepare`, not in a middleware. Streamed responses send their headers before the handler returns, and curl-based checks won't catch the problem. Test in a real browser from the dashboard's origin.
- **Stream health:** track the SSE stream's own state (`NO REPLY STREAM`), not just `/health`. Otherwise the UI shows LIVE while every answer is blocked.
- **Worker detection:** treat a missing `orbit.requests` queue the same as zero consumers.
- **No requests by default:** don't send anything to a paid provider on page load. Autoplay is opt-in, and Pause persists across reloads.
- **Fixed ports:** pin the dev port with `--strictPort`.
- **Card layout:** cards must queue, never overlap. Size the spacing from the actual card height, and cap each physics step so a hidden tab doesn't dump every card at once.
- **TypeSafe logs:** the SDK's per-request INFO logs are already silenced by the `typesafe_sdk` logger override in `config.yaml`.

## Assumptions

- The TypeSafe and Ollama decision providers are configured as in `config/decision.yaml`, and `TYPESAFE_API_KEY` is set for the hosted adapter.
- RabbitMQ and messaging are set up as for Triage Rush (`messaging.enabled: true`).
- Two annotators and an adjudicator are available to label the held-out set, which is about 120 texts × 8 signals.
- English is the primary demo language. Multilingual behavior is reported from the separate multilingual set and not promised.

## Known gaps

- **Open-ended aspects:** the model can't discover aspects that aren't listed as questions. A hybrid would work: a decision model for the fixed dimensions, with flagged items sent to an LLM adapter that extracts new aspects. It's out of scope here.
- **Long, multi-topic texts:** these get one averaged answer. Splitting per paragraph or per message on the client side is left to the integrator. The dashboard uses short texts.
- **Small sample:** 120 held-out texts give wide intervals. The gate uses Wilson bounds so it doesn't overclaim, but a production rollout should re-evaluate on real traffic labels, such as agent reassignments and review outcomes.
- **Model drift:** results depend on the model version (`jev-latest` moves). Re-run the held-out evaluation when the resolved model version changes, and update the Results section.
