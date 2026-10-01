# Sentiment-analysis labeling guide

For the two annotators labeling `sentiment-tune.jsonl` and `sentiment-test.jsonl`
(see [eval plan](../../../docs/roadmap/complete/decision-model-sentiment-analysis.md)).

**Work independently.** Don't discuss a text with the other annotator before both of you
have labeled it. Disagreements go to the adjudicator, not to a conversation between
the two of you — that's what keeps the agreement numbers (κ) meaningful.

**One definition per signal.** The wording below is the same wording the model is given.
If a text makes you want to add a new rule or exception, don't improvise — flag it and
raise it with whoever owns the eval plan; a changed definition needs a relabel, not a
one-off judgment call.

Label every signal on every record. There's no "skip" — if something is genuinely
ambiguous, pick your best reading and let adjudication catch it; an unlabeled field
fails the schema check (`examples/sentiment-pulse/eval/check_sentiment_dataset.py`).

---

## polarity

*What is the author's overall stance?*

| Label | Meaning |
|---|---|
| `positive` | Satisfied, happy or praising |
| `neutral` | Factual, or no clear stance |
| `negative` | Unhappy, frustrated or complaining |
| `mixed` | Clearly both positive and negative, **about different things** |

**Rules of thumb:**
- `mixed` requires two separate things pulling in different directions — not just a
  positive statement followed by a hedge. "Great product, a bit pricey though" is
  `mixed` (product vs. price). "Pretty good, I guess" is `neutral` or mild `positive`,
  not `mixed` — there's only one thing being evaluated, weakly.
- `neutral` covers both "no opinion stated" (a shipping notification) and "stated
  facts with no evaluative language" ("Arrived Tuesday, box was blue").
- A sarcastic text is labeled by its **intended** meaning, not its literal wording —
  see [sarcasm](#sarcasm) below. "Great, another update that broke login" is
  `negative`, not `positive`.
- If a text is short and purely descriptive with one mildly loaded word, don't overread
  it. A single adjective isn't enough to leave `neutral` — ask whether a reasonable
  third reader would call it an opinion.

**Worked examples:**
- "Works exactly as described, five stars." → `positive`
- "Order #4471 shipped on the 3rd." → `neutral`
- "Customer service was great, but the product itself broke in a week." → `mixed`
- "Waste of money, returning it." → `negative`

---

## valence

*On a signed scale from very negative to very positive, where does the text sit overall?*

Five ordered levels, lowest first: `Very negative` (0), `Negative` (1), `Neutral` (2),
`Positive` (3), `Very positive` (4).

**This is not intensity on its own** — it's the overall signed tone. A review that is
intensely mixed (strong praise + strong complaint) sits **near the middle** (2, maybe
1 or 3 depending on which side is slightly stronger), not at an extreme. `mixed`
polarity is what carries "this is complicated," not a high-magnitude valence score.

**Calibration anchors** — use these to keep your scale consistent with the other
annotator's:
- `0` (very negative): author is angry, disgusted, or describes real harm/failure with
  no redeeming point. "Charged me twice and support ignored three emails. Never again."
- `1` (negative): clearly unhappy, but milder or partial. "Disappointing — not what
  I expected, but it does technically work."
- `2` (neutral): factual, no stance, or a genuinely even mixed review with no net lean.
- `3` (positive): clearly pleased, without superlatives. "Does what it says, happy
  with it."
- `4` (very positive): enthusiastic, superlative, or explicitly recommends it to others.
  "Best purchase I've made this year, telling everyone I know."

If you're unsure between two adjacent levels, that's expected — weighted κ tolerates
off-by-one disagreement between annotators better than off-by-two, so don't agonize;
just pick one and move on.

---

## sarcasm

*Does the literal wording say the opposite of what the author means?*

A yes/no judgment. Yes only when the **literal** words contradict the **intended**
meaning — not just "this text is critical" or "this text uses strong language."

**Worked examples:**
- "Great, another update that broke login." → `true` (literal "great" is sarcastic; the
  intent is negative)
- "Love how I have to restart it every morning." → `true`
- "This is terrible, I hate waiting on hold for an hour." → `false` (literal and
  intended meaning agree — it's just a direct complaint, not sarcasm)
- "Sure, I'll just rebuy the thing I already bought. No problem." → `true`

If you have to argue yourself into reading a text as sarcastic ("well, maybe they
meant..."), it's probably `false`. Sarcasm should be legible from the text alone,
without outside context about the author.

---

## needs_escalation

*Does the author say they will cancel, leave or switch; report harm such as money
taken wrongly, lost data, a safety issue or being locked out; or explicitly demand a
reply from a person?*

Yes when **any** of these three hold, no otherwise:

1. **Cancellation/switching signal** — says or clearly implies they will cancel, leave,
   or switch to a competitor. ("If this isn't fixed by Friday I'm cancelling my
   subscription.")
2. **Reported harm** — money taken wrongly, lost data, a safety issue, or being locked
   out of something they need. ("Charged me $200 for a plan I never signed up for."
   "Lost six months of my project files after the update." "I can't get back into my
   account and I need it for work tomorrow.")
3. **Explicit demand for a human reply** — asks by name for a person or manager to
   respond, not just "please help" to a general support address. ("I want a manager to
   call me." "Please have an actual person respond, not a bot.")

**What does NOT qualify on its own:**
- Anger or strong language alone. "This is absolutely infuriating" with no cancellation
  threat, harm, or demand for a person → `false`.
- A low valence score alone. A `0` (very negative) review that's just a complaint, with
  none of the three triggers → `false`.
- A generic request for help or a refund that doesn't name a person/manager and
  doesn't describe harm. "Can someone help me set this up?" → `false`.

**Worked examples:**
- "Cancel my account, this is ridiculous." → `true` (trigger 1)
- "Your app deleted three months of photos. This is a disaster." → `true` (trigger 2)
- "I need a manager to call me back today." → `true` (trigger 3)
- "Pretty slow lately, hope they fix it." → `false`
- "I'm so angry I could scream, this app is garbage." → `false` (anger alone)

---

## aspect_price, aspect_support, aspect_product, aspect_delivery

*What is the author's stance on {price/value, customer support, the product itself,
shipping/delivery}?*

Each aspect gets one of `positive`, `negative`, `not_mentioned` independently of the
others and independently of overall `polarity`. A review can be `positive` on
`product` and `negative` on `delivery` in the same breath.

- `not_mentioned` is the default. Use it whenever the aspect isn't discussed, or is
  mentioned with no evaluative stance (e.g., "arrived via FedEx" with no comment on
  whether that was good or bad → `aspect_delivery: not_mentioned`).
- Only label `positive`/`negative` when there's an actual stance about that aspect,
  not just a mention of it.

**Worked example** — "Arrived two days late but support fixed it in minutes. Love it.":
- `price`: `not_mentioned` (price never comes up)
- `support`: `positive` ("support fixed it in minutes")
- `product`: `not_mentioned` ("love it" is about the overall experience/resolution,
  not a stance on the product itself — if it's genuinely ambiguous whether "it" means
  the product or the whole experience, prefer `not_mentioned` over guessing)
- `delivery`: `negative` ("arrived two days late")

---

## lang

The text's language as a short code (`en`, `fr`, `es`, ...). For the multilingual set
(`sentiment-test-multilingual.jsonl`) this should already match the intended language;
otherwise it's almost always `en`.

---

## Workflow

1. Each annotator labels the full tuning set, then the full held-out set, independently,
   writing their raw labels to their own scratch copy (not committed).
2. Compute agreement per signal before adjudicating anything:
   - Cohen's κ for `polarity`, `sarcasm`, `needs_escalation`, and each aspect.
   - Weighted κ for `valence`.
   - A signal with κ < 0.6 is reported as too subjective to gate on — it still gets
     adjudicated and shipped in the dataset, it just won't block or justify the Phase 1
     gate decision for that signal.
3. An adjudicator reviews every disagreement and picks the final label. The adjudicator
   should not simply average or coin-flip — re-read the text against the definition
   above and the worked examples, and write the call down if it's a genuinely close
   case (useful context for Phase 1 if accuracy comes out low).
4. For `polarity` specifically, also record human-vs-human macro-F1 between the two
   annotators' raw (pre-adjudication) labels on the held-out set. This is reported next
   to the model's score as **context only** — it explains a low model score, but the
   gate's cutoffs (Phase 1) never move because of it.
5. Once both files are complete, run the schema/quota checker:
   ```bash
   /Users/remsyschmilinsky/Downloads/orbit/venv/bin/python examples/sentiment-pulse/eval/check_sentiment_dataset.py
   ```
6. Freeze `sentiment-test.jsonl` the moment it's committed. Any later change to
   question wording, criteria, or thresholds needs a **fresh** held-out set — the old
   one becomes extra tuning data, never a second chance at the same held-out numbers.

See `README.md` in this directory for the file schema and how to run the eval script
once labeling is done.
