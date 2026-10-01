#!/usr/bin/env python3
"""
Generates SYNTHETIC tuning/held-out set stand-ins for dry-running Phase 1 steps 2-4
(tune, freeze, test once) before real human labeling happens. These are NOT the real
eval sets — they are machine-templated text with machine-assigned labels, so they
cannot be used to tune wording, pick thresholds, or justify any gate decision. See
../LABELING_GUIDE.md for the real process; this only exists to exercise the pipeline
end to end (eval_decision_adapter.py, check_sentiment_dataset.py, the threshold
freeze/report flow) with something that passes the same schema and quota checks.

Run:
    python examples/sentiment-pulse/eval/dry-run/generate_sample_tuning_set.py

Writes, in this directory:
    sentiment-tune.sample.jsonl  (60 records,  same quotas as the real tuning set)
    sentiment-test.sample.jsonl  (120 records, same quotas as the real held-out set)
"""

import json
import random
from pathlib import Path

OUT_DIR = Path(__file__).parent

VALENCE = {"positive": (3, 4), "negative": (0, 1), "neutral": (2, 2), "mixed": (1, 3)}

ASPECT_CLAUSES = {
    "price": {
        "positive": "The price is great for what you get.",
        "negative": "It's overpriced for what you actually get.",
    },
    "support": {
        "positive": "Support responded fast and sorted it out.",
        "negative": "Support never replied to any of my messages.",
    },
    "product": {
        "positive": "The lamp itself works really well.",
        "negative": "The lamp broke within a week of normal use.",
    },
    "delivery": {
        "positive": "It arrived two days earlier than expected.",
        "negative": "Delivery took almost three weeks longer than promised.",
    },
}

LEAD_INS = {
    "positive": ["Really happy with this purchase.", "Genuinely pleased with how this turned out.", "Can't complain, this was a good buy.", "Pretty glad I ordered this."],
    "negative": ["Pretty unhappy with this.", "Honestly disappointed.", "Not a good experience overall.", "Regretting this purchase."],
    "neutral": ["Just a quick note on the order.", "Logging this for the record.", "Here's an update on the status.", "A factual update on my order."],
    "mixed": ["Mixed feelings about this one.", "Some good, some bad here.", "Half happy, half frustrated.", "Can't decide how I feel about this."],
}

ESCALATION_CLAUSES = [
    "Cancel my subscription, I'm done with this.",
    "This is unacceptable, I want a manager to call me back.",
    "You charged me twice and nobody has fixed it yet.",
    "I've lost access to files I need for work tomorrow.",
    "Switching to a competitor if this isn't resolved today.",
]

SARCASM_WRAPPERS = {
    # Literal wording contradicts the intended (labeled) polarity.
    "negative": lambda body: f"Oh fantastic, {body[0].lower()}{body[1:]} Just what I always wanted.",
    "mixed": lambda body: f"Sure, {body[0].lower()}{body[1:]} Living the dream.",
    "positive": lambda body: f"Color me shocked — {body[0].lower()}{body[1:]} Didn't see that coming.",
}

NEUTRAL_FACTS = [
    "Order #{n} shipped on the 3rd.",
    "Tracking shows it's at the regional hub.",
    "Confirmation email arrived with the receipt attached.",
    "Account was set up without any issues.",
    "The package weighs about two pounds according to the label.",
    "Delivery window is listed as Tuesday to Thursday.",
]


def build_skeletons(id_prefix, per_polarity, escalation_slots, sarcasm_slots):
    """`per_polarity` records per polarity, with escalation/sarcasm flags assigned but
    no aspects yet. `escalation_slots`/`sarcasm_slots` are {polarity: count} maps."""
    escalation_slots = dict(escalation_slots)
    sarcasm_slots = dict(sarcasm_slots)

    records = []
    idx = 1
    for polarity in ["positive", "negative", "neutral", "mixed"]:
        for _ in range(per_polarity):
            escalation = escalation_slots.get(polarity, 0) > 0
            if escalation:
                escalation_slots[polarity] -= 1
            sarcasm = sarcasm_slots.get(polarity, 0) > 0
            if sarcasm:
                sarcasm_slots[polarity] -= 1

            lo, hi = VALENCE[polarity]
            records.append({
                "id": f"{id_prefix}-{idx:03d}",
                "polarity": polarity,
                "valence": random.randint(lo, hi),
                "sarcasm": sarcasm,
                "needs_escalation": escalation,
                "aspects": {a: "not_mentioned" for a in ASPECT_CLAUSES},
                "lang": "en",
                "_text_parts": [],
            })
            idx += 1

    for r in records:
        n = int(r["id"].split("-")[-1])
        if r["polarity"] == "neutral":
            r["_text_parts"].append(NEUTRAL_FACTS[n % len(NEUTRAL_FACTS)].format(n=1000 + n))
        else:
            r["_text_parts"].append(LEAD_INS[r["polarity"]][n % len(LEAD_INS[r["polarity"]])])
            if r["needs_escalation"]:
                r["_text_parts"].append(ESCALATION_CLAUSES[n % len(ESCALATION_CLAUSES)])
    return records


def assign_aspects(records, per_stance=10):
    """`per_stance` positive + `per_stance` negative mentions per aspect, each on a
    distinct record that doesn't already carry that aspect — guaranteed, not left to
    chance, so the quota check always passes regardless of set size."""
    non_neutral = [r for r in records if r["polarity"] != "neutral"]
    for aspect, clauses in ASPECT_CLAUSES.items():
        for stance in ("positive", "negative"):
            candidates = [r for r in non_neutral if r["aspects"][aspect] == "not_mentioned"]
            random.shuffle(candidates)
            for r in candidates[:per_stance]:
                r["aspects"][aspect] = stance
                r["_text_parts"].append(clauses[stance])


def finalize_text(records):
    for r in records:
        body = " ".join(r["_text_parts"])
        if r["sarcasm"]:
            body = SARCASM_WRAPPERS[r["polarity"]](body)
        r["text"] = body
        del r["_text_parts"]
    return records


def build_dataset(id_prefix, per_polarity, escalation_slots, sarcasm_slots, aspect_per_stance):
    records = build_skeletons(id_prefix, per_polarity, escalation_slots, sarcasm_slots)
    assign_aspects(records, per_stance=aspect_per_stance)
    finalize_text(records)
    random.shuffle(records)
    return records


def write_jsonl(path, records):
    with open(path, "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in records)
    print(f"Wrote {len(records)} synthetic records to {path}")


def main():
    random.seed(7)  # deterministic output, so repeated dry runs are comparable

    tune = build_dataset(
        "dryrun-tune", per_polarity=15,
        escalation_slots={"negative": 10, "mixed": 2},  # 12 total, the real minimum
        sarcasm_slots={"negative": 4, "mixed": 3, "positive": 2},  # 9 = 15% of 60
        aspect_per_stance=10,  # 20 per aspect, the real minimum
    )
    write_jsonl(OUT_DIR / "sentiment-tune.sample.jsonl", tune)

    random.seed(13)  # different seed: the held-out set must not overlap the tuning set
    test = build_dataset(
        "dryrun-test", per_polarity=30,
        escalation_slots={"negative": 20, "mixed": 5},  # 25 total, the real minimum
        sarcasm_slots={"negative": 8, "mixed": 6, "positive": 4},  # 18 = 15% of 120
        aspect_per_stance=10,  # 20 per aspect, the real minimum (doesn't scale with set size)
    )
    write_jsonl(OUT_DIR / "sentiment-test.sample.jsonl", test)


if __name__ == "__main__":
    main()
