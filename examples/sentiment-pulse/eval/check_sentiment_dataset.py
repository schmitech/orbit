#!/usr/bin/env python3
"""
Schema and quota checks for the sentiment-analysis eval sets
(examples/sentiment-pulse/eval/*.jsonl).

Run directly to validate the frozen tuning and held-out sets:

    python examples/sentiment-pulse/eval/check_sentiment_dataset.py

Or point it at any other pair of files — e.g. the synthetic dry-run sets — with
--tune/--test (and matching --tune-polarity-each/--tune-min-escalation/etc. if their
quotas differ from the real sets' 60/120-record ones):

    python examples/sentiment-pulse/eval/check_sentiment_dataset.py \
      --tune dry-run/sentiment-tune.sample.jsonl --test dry-run/sentiment-test.sample.jsonl

Or import `check_schema` / `check_quotas` / `check_no_overlap` to validate in a test.
See docs/roadmap/complete/decision-model-sentiment-analysis.md (Phase 0 — Labeled dataset).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).parent.absolute()
REPO_ROOT = EVAL_DIR.parent.parent.parent

POLARITIES = {"positive", "negative", "neutral", "mixed"}
ASPECTS = {"price", "support", "product", "delivery"}
ASPECT_VALUES = {"positive", "negative", "not_mentioned"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with open(path) as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: invalid JSON ({e})") from e
    return records


def check_schema(records: list[dict[str, Any]]) -> list[str]:
    """Every signal must be labeled on every record. Returns a list of error messages."""
    errors = []
    seen_ids: set[str] = set()
    for i, r in enumerate(records):
        where = r.get("id", f"record #{i}")
        if "id" not in r:
            errors.append(f"{where}: missing 'id'")
        elif r["id"] in seen_ids:
            errors.append(f"{where}: duplicate id")
        else:
            seen_ids.add(r["id"])

        if not isinstance(r.get("text"), str) or not r["text"].strip():
            errors.append(f"{where}: missing or empty 'text'")
        if r.get("polarity") not in POLARITIES:
            errors.append(f"{where}: 'polarity' must be one of {sorted(POLARITIES)}, got {r.get('polarity')!r}")
        if not isinstance(r.get("valence"), int) or not 0 <= r.get("valence", -1) <= 4:
            errors.append(f"{where}: 'valence' must be an int in [0, 4], got {r.get('valence')!r}")
        if not isinstance(r.get("sarcasm"), bool):
            errors.append(f"{where}: 'sarcasm' must be a bool")
        if not isinstance(r.get("needs_escalation"), bool):
            errors.append(f"{where}: 'needs_escalation' must be a bool")

        aspects = r.get("aspects")
        if not isinstance(aspects, dict) or set(aspects.keys()) != ASPECTS:
            errors.append(f"{where}: 'aspects' must label exactly {sorted(ASPECTS)}")
        else:
            for name, value in aspects.items():
                if value not in ASPECT_VALUES:
                    errors.append(f"{where}: aspects.{name} must be one of {sorted(ASPECT_VALUES)}, got {value!r}")

        if not isinstance(r.get("lang"), str) or not r["lang"].strip():
            errors.append(f"{where}: missing or empty 'lang'")
    return errors


def check_quotas(records: list[dict[str, Any]], *, polarity_each: int, min_escalation_positives: int) -> list[str]:
    """Composition quotas from the eval plan. `polarity_each` is the required count per polarity."""
    errors = []
    counts = {p: 0 for p in POLARITIES}
    for r in records:
        p = r.get("polarity")
        if p in counts:
            counts[p] += 1
    for p, required in [(p, polarity_each) for p in POLARITIES]:
        if counts[p] < required:
            errors.append(f"polarity '{p}': {counts[p]} records, need >= {required}")

    escalation_positives = sum(1 for r in records if r.get("needs_escalation") is True)
    if escalation_positives < min_escalation_positives:
        errors.append(f"needs_escalation positives: {escalation_positives}, need >= {min_escalation_positives}")

    for aspect in ASPECTS:
        non_not_mentioned = sum(
            1 for r in records
            if isinstance(r.get("aspects"), dict) and r["aspects"].get(aspect) in {"positive", "negative"}
        )
        if non_not_mentioned < 20:
            errors.append(f"aspect '{aspect}': {non_not_mentioned} non-'not_mentioned' records, need >= 20")
    return errors


def check_no_overlap(*datasets: tuple[str, list[dict[str, Any]]]) -> list[str]:
    """No text id may appear in more than one of the given (name, records) datasets."""
    errors = []
    seen: dict[str, str] = {}
    for name, records in datasets:
        for r in records:
            rid = r.get("id")
            if rid is None:
                continue
            if rid in seen:
                errors.append(f"id '{rid}' appears in both '{seen[rid]}' and '{name}'")
            else:
                seen[rid] = name
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--tune", default=None,
        help="Tuning-set JSONL path (default: sentiment-tune.jsonl next to this script). "
             "A relative path is resolved against the current working directory.",
    )
    parser.add_argument(
        "--test", default=None,
        help="Held-out-set JSONL path (default: sentiment-test.jsonl next to this script). "
             "A relative path is resolved against the current working directory.",
    )
    parser.add_argument("--tune-polarity-each", type=int, default=15, help="Required records per polarity in --tune (default: 15, the real tuning set's quota)")
    parser.add_argument("--tune-min-escalation", type=int, default=12, help="Minimum needs_escalation positives in --tune (default: 12)")
    parser.add_argument("--test-polarity-each", type=int, default=30, help="Required records per polarity in --test (default: 30, the real held-out set's quota)")
    parser.add_argument("--test-min-escalation", type=int, default=25, help="Minimum needs_escalation positives in --test (default: 25)")
    return parser.parse_args(argv)


def _resolve(path_arg: str | None, default_name: str) -> Path:
    # No explicit path: default to this script's own directory (the real eval sets
    # live there). An explicit path is resolved the normal way, against the current
    # working directory, so `--tune relative/path.jsonl` behaves as anyone would expect.
    return EVAL_DIR / default_name if path_arg is None else Path(path_arg)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tune_path = _resolve(args.tune, "sentiment-tune.jsonl")
    test_path = _resolve(args.test, "sentiment-test.jsonl")

    missing = [p for p in (tune_path, test_path) if not p.exists()]
    if missing:
        if args.tune is None and args.test is None:
            print("Not yet checkable — these files don't exist yet:")
            for p in missing:
                print(f"  {p.relative_to(REPO_ROOT)}")
            print("\nSee docs/roadmap/complete/decision-model-sentiment-analysis.md, Phase 0 — Labeled dataset.")
            print("To check a different pair of files (e.g. the synthetic dry-run sets), pass --tune/--test.")
        else:
            print("File(s) not found:")
            for p in missing:
                print(f"  {p}")
        return 1

    tune = load_jsonl(tune_path)
    test = load_jsonl(test_path)

    errors = []
    errors += [f"[tune] {e}" for e in check_schema(tune)]
    errors += [f"[test] {e}" for e in check_schema(test)]
    errors += [f"[tune] {e}" for e in check_quotas(tune, polarity_each=args.tune_polarity_each, min_escalation_positives=args.tune_min_escalation)]
    errors += [f"[test] {e}" for e in check_quotas(test, polarity_each=args.test_polarity_each, min_escalation_positives=args.test_min_escalation)]
    errors += check_no_overlap(("tune", tune), ("test", test))

    if errors:
        print(f"{len(errors)} problem(s) found:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"OK: {len(tune)} tuning records, {len(test)} held-out records, schema and quotas pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
