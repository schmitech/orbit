"""
Fit the language-detection calibration on the benchmark tune split.

Writes ``server/inference/pipeline/steps/language_detection_calibration.json``,
which ``LanguageDetectionStep`` loads at startup. Only the ``tune`` split is
read; never fit against ``heldout``. The fit is deterministic, so rerunning it
with the same corpus and backend versions reproduces the file.

There is one fit per non-empty set of backends, because a deployment may
enable only some backends and a request may lose one to a timeout; the step
uses the fit for exactly the backends that answered. For each set, smallest
first (roadmap Phase 3):

1. Take the tune records that reach the statistical stage (enough letters, no
   unique-script or phrase fast path) and on which every backend in the set
   answered, keeping only that set's results.
2. For each floor in ``FLOORS``, fit the pool weights by minimizing the
   negative log-likelihood of the gold language (coordinate descent on log
   weights). A gold language no backend listed gets its share of the
   residual mass, as in ``pool_backend_distributions``. Keep the floor with
   the lowest NLL.
3. Choose the acceptance threshold from ``THRESHOLDS`` that minimizes
   ``WRONG_COST * wrong + unwarranted abstentions`` over the whole tune split,
   running the real pipeline with only that set of backends enabled. Ties go
   to the lower threshold (more coverage).

Usage (from repo root):
    venv/bin/python server/tests/language_eval/calibrate.py            # write the file
    venv/bin/python server/tests/language_eval/calibrate.py --dry-run  # print only
"""

import argparse
import asyncio
import dataclasses
import itertools
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from inference.pipeline.steps import language_detection as ld
from runner import (
    BENCHMARK_VERSION,
    DATASET_PATH,
    REPO_ROOT,
    _EvalContainer,
    _package_versions,
    dataset_sha256,
    load_canonical_config,
    load_dataset,
    score_record,
)

VERSION = "v2"  # v1 was a single all-backend fit whose loss ignored the residual mass
BACKENDS = ("langdetect", "langid", "pycld2")
UNIVERSE_SIZE = 100      # nominal number of languages the backends can name
LANGID_TOP_K = 10
FLOORS = (0.1, 0.03, 0.01, 0.003, 0.001)
THRESHOLDS = tuple(round(0.40 + 0.05 * i, 2) for i in range(11))  # 0.40 .. 0.90
# A wrong language costs twice an unwarranted abstention: an abstention still
# tells the model to reply in the user's language, a wrong detection names
# the wrong one.
WRONG_COST = 2


SUBSETS = tuple(
    frozenset(c) for size in range(1, len(BACKENDS) + 1) for c in itertools.combinations(BACKENDS, size)
)


def _gold(record):
    return ({record["lang"], *record["alternatives"]}) - {"unknown"}


def _placeholder_calibration():
    pool = ld.PoolCalibration(weights=dict.fromkeys(BACKENDS, 1.0), floor=FLOORS[0], accept_confidence=0.5)
    return ld.Calibration(version=VERSION, universe_size=UNIVERSE_SIZE, langid_top_k=LANGID_TOP_K,
                          pools=dict.fromkeys(SUBSETS, pool))


def _reaches_pool(step, text):
    clean = step._clean_text_for_detection(text)
    evidence = step._script_evidence(clean)
    if evidence.letters < step.min_letters:
        return None
    if step._detect_by_script(clean, evidence).confidence > 0.9:
        return None
    return clean


def collect_backend_results(step, records):
    """(record, answering backend results) for tune records that reach the pooling stage."""
    rows = []
    for record in records:
        clean = _reaches_pool(step, record["text"])
        if clean is None or not _gold(record):
            continue
        results = []
        for _name, detect in step.backends:
            result = detect(clean)
            if result and not result.abstained:
                results.append(result)
        if results:
            rows.append((record, results))
    return rows


def rows_for(rows, backends):
    """Rows on which every backend in the set answered, restricted to that set."""
    subset = []
    for record, results in rows:
        kept = [r for r in results if r.backend in backends]
        if {r.backend for r in kept} == backends:
            subset.append((record, kept))
    return subset


def gold_probability(record, probabilities, residual):
    """P(gold) under the pool, including the residual share of an unlisted gold language."""
    unlisted_share = residual / max(UNIVERSE_SIZE - len(probabilities), 1)
    return sum(probabilities.get(lang, unlisted_share) for lang in _gold(record))


def nll(rows, weights, floor):
    pool = ld.PoolCalibration(weights=dict(weights), floor=floor, accept_confidence=0.5)
    total = 0.0
    for record, results in rows:
        probabilities, residual = ld.pool_backend_distributions(results, pool, UNIVERSE_SIZE)
        total -= math.log(gold_probability(record, probabilities, residual))
    return total / len(rows)


def fit_weights(rows, floor, backends, tol=1e-3):
    """Coordinate descent on log weights; deterministic."""
    order = [b for b in BACKENDS if b in backends]
    log_w = dict.fromkeys(order, 0.0)

    def loss(lw):
        return nll(rows, {b: math.exp(v) for b, v in lw.items()}, floor)

    best = loss(log_w)
    step = 1.0
    while step >= tol:
        improved = False
        for backend in order:
            for delta in (step, -step):
                trial = dict(log_w, **{backend: log_w[backend] + delta})
                value = loss(trial)
                if value < best - 1e-9:
                    log_w, best, improved = trial, value, True
                    break
        if not improved:
            step /= 2
    return {b: round(math.exp(v), 4) for b, v in log_w.items()}, best


def _memoized(func):
    cache = {}

    def detect(text):
        if text not in cache:
            cache[text] = func(text)
        return cache[text]
    return detect


async def threshold_costs(step, records, backends, all_backends):
    """Cost of each threshold for ``backends``, with only those backends enabled."""
    step.backends = [(name, func) for name, func in all_backends if name in backends]
    base = step.calibration
    costs = {}
    for threshold in THRESHOLDS:
        pools = dict(base.pools)
        pools[backends] = dataclasses.replace(pools[backends], accept_confidence=threshold)
        step.calibration = dataclasses.replace(base, pools=pools)
        wrong = unwarranted = 0
        for record in records:
            result = await step._detect_language_ensemble_async(record["text"])
            score = score_record(record, {"pred": result.language, "confidence": result.confidence})
            if score["abstained"]:
                unwarranted += not score["acceptable"]
            else:
                wrong += not score["correct"]
        costs[threshold] = [wrong, unwarranted, WRONG_COST * wrong + unwarranted]
    step.calibration = base
    step.backends = all_backends
    return costs


async def calibrate():
    records = [r for r in load_dataset() if r["split"] == "tune"]
    ld.load_calibration = _placeholder_calibration  # the file being rewritten may be stale
    step = ld.LanguageDetectionStep(_EvalContainer(load_canonical_config()))
    step.backends = [(name, _memoized(func)) for name, func in step.backends]
    all_backends = list(step.backends)
    rows = collect_backend_results(step, records)

    pools, fits = {}, {}
    for backends in SUBSETS:
        subset_rows = rows_for(rows, backends)
        by_floor = {floor: fit_weights(subset_rows, floor, backends) for floor in FLOORS}
        floor = min(FLOORS, key=lambda f: by_floor[f][1])
        pools[backends] = ld.PoolCalibration(weights=by_floor[floor][0], floor=floor, accept_confidence=0.5)
        fits[backends] = (len(subset_rows), by_floor)

    # Thresholds smallest set first: a request that loses a backend falls back
    # to a smaller set, whose threshold must already be final.
    step.calibration = dataclasses.replace(_placeholder_calibration(), pools=pools)
    report = []
    for backends in SUBSETS:
        costs = await threshold_costs(step, records, backends, all_backends)
        accept = min(THRESHOLDS, key=lambda t: (costs[t][2], t))
        pools[backends] = dataclasses.replace(pools[backends], accept_confidence=accept)
        step.calibration = dataclasses.replace(step.calibration, pools=dict(pools))
        n_rows, by_floor = fits[backends]
        report.append({
            "backends": [b for b in BACKENDS if b in backends],
            "weights": pools[backends].weights,
            "floor": pools[backends].floor,
            "accept_confidence": accept,
            "selection": {
                "pooled_records": n_rows,
                "nll_by_floor": {str(f): round(by_floor[f][1], 4) for f in FLOORS},
                "cost_by_threshold": {str(t): c for t, c in costs.items()},
            },
        })

    return {
        "version": VERSION,
        "method": "weighted log-linear pool of floored backend distributions, one fit per backend set",
        "universe_size": UNIVERSE_SIZE,
        "langid_top_k": LANGID_TOP_K,
        "fitted_on": {
            "benchmark": BENCHMARK_VERSION,
            "dataset": os.path.relpath(DATASET_PATH, REPO_ROOT),
            "sha256": dataset_sha256(DATASET_PATH),
            "split": "tune",
            "packages": _package_versions(),
        },
        "selection_rule": {
            "wrong_cost": WRONG_COST,
            "cost_by_threshold": "[wrong, unwarranted_abstentions, cost]",
        },
        "pools": report,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the calibration without writing it")
    args = parser.parse_args(argv)
    calibration = asyncio.run(calibrate())
    text = json.dumps(calibration, indent=1, ensure_ascii=False) + "\n"
    if args.dry_run:
        print(text)
    else:
        with open(ld.CALIBRATION_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {os.path.relpath(ld.CALIBRATION_PATH, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
