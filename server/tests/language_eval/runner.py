"""
Language-detection benchmark runner.

Evaluates the production ``LanguageDetectionStep`` (through ``process()``, with
the canonical ``config/config.yaml`` settings) or a single backend against the
versioned corpus in ``data/``, and emits a machine-readable JSON report. See
README.md in this directory and docs/roadmap/language-detection-accuracy.md
(Phase 0).

Usage (from repo root):
    venv/bin/python server/tests/language_eval/runner.py --output /tmp/report.json
    venv/bin/python server/tests/language_eval/runner.py --modes pipeline --splits heldout
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import resource
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.abspath(os.path.join(HERE, "..", ".."))
REPO_ROOT = os.path.dirname(SERVER_DIR)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps import language_detection as ld

BENCHMARK_VERSION = "v1"
DATASET_PATH = os.path.join(HERE, "data", f"benchmark_{BENCHMARK_VERSION}.jsonl")
CANONICAL_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "config.yaml")
BASELINE_REPORT_PATH = os.path.join(HERE, "reports", f"phase1_baseline_{BENCHMARK_VERSION}.json")

BACKEND_MODES = ("langdetect", "langid", "pycld2")
PIPELINE_MODES = ("pipeline", "pipeline+context")
# Backends run first so each backend's first call measures its own cold start.
ALL_MODES = BACKEND_MODES + PIPELINE_MODES
SPLITS = ("tune", "heldout")

HIGH_CONFIDENCE = 0.9
CALIBRATION_BINS = 10

# Language groups whose members are commonly confused; confusion matrices are
# reported for each.
RELATED_GROUPS = {
    "cyrillic": ["ru", "uk", "bg", "sr", "mk", "be", "kk"],
    "arabic_script": ["ar", "fa", "ur", "ps"],
    "devanagari": ["hi", "mr", "ne"],
    "bengali_script": ["bn", "as"],
    "hebrew_script": ["he", "yi"],
    "han": ["zh", "ja"],
    "scandinavian": ["sv", "no", "da"],
    "iberian": ["es", "pt", "gl", "ca"],
    "malay": ["id", "ms"],
    "west_germanic": ["nl", "af", "de"],
    "west_slavic_south_slavic_latin": ["cs", "sk", "pl", "hr", "sl"],
}

SHARED_SCRIPTS = {"Cyrillic", "Arabic", "Devanagari", "Bengali", "Hebrew", "Han"}
UNSPACED_SCRIPTS = {"Han", "Japanese", "Thai", "Lao", "Khmer", "Myanmar"}
_SCRIPT_NAME_PREFIXES = {
    "LATIN": "Latin", "CYRILLIC": "Cyrillic", "GREEK": "Greek", "ARABIC": "Arabic",
    "HEBREW": "Hebrew", "DEVANAGARI": "Devanagari", "BENGALI": "Bengali", "TAMIL": "Tamil",
    "TELUGU": "Telugu", "THAI": "Thai", "GEORGIAN": "Georgian", "ARMENIAN": "Armenian",
    "HANGUL": "Hangul", "HIRAGANA": "Kana", "KATAKANA": "Kana", "CJK": "Han",
}


# ============================================================================
# Dataset
# ============================================================================

def load_dataset(path: str = DATASET_PATH) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    for record in records:
        record.update(derive_dimensions(record["text"]))
    return records


def dataset_sha256(path: str = DATASET_PATH) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _char_script(ch: str) -> str | None:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    return _SCRIPT_NAME_PREFIXES.get(name.split(" ", 1)[0], "Other")


def derive_dimensions(text: str) -> dict[str, Any]:
    """Stratification dimensions derived from the text so they can't drift from it.

    Length buckets are approximate for unspaced scripts (two letters ≈ one word).
    """
    letters = [c for c in text if unicodedata.category(c).startswith("L")]
    scripts = Counter(s for s in map(_char_script, letters) if s)
    if not scripts:
        script = "none"
    elif scripts.get("Kana"):
        script = "Japanese"
    else:
        script = scripts.most_common(1)[0][0]

    n_letters = len(letters)
    if n_letters == 0:
        length = "no_letters"
    elif n_letters <= 2:
        length = "1-2_chars"
    elif script in UNSPACED_SCRIPTS:
        length = "single_word" if n_letters <= 4 else "short" if n_letters <= 20 else "long"
    else:
        words = [w for w in text.split() if any(unicodedata.category(c).startswith("L") for c in w)]
        length = "single_word" if len(words) <= 1 else "short" if n_letters <= 40 else "long"

    if script != "Latin":
        latin = "non_latin"
    elif all(ord(c) < 128 for c in letters):
        latin = "ascii_only"
    else:
        latin = "latin_diacritics"

    return {
        "script": script,
        "length_bucket": length,
        "latin_form": latin,
        "shared_script": script in SHARED_SCRIPTS,
    }


def secondary_char_labels(record: dict[str, Any]) -> dict[int, str]:
    """Map character index -> language for each labelled secondary span."""
    labels: dict[int, str] = {}
    cursor = 0
    for span in record.get("secondary_spans") or []:
        start = record["text"].index(span["text"], cursor)
        end = start + len(span["text"])
        labels.update({i: span["lang"] for i in range(start, end)})
        cursor = end
    return labels


# ============================================================================
# Detectors under test
# ============================================================================

class _EvalContainer:
    def __init__(self, config: dict[str, Any], services: dict[str, Any] | None = None):
        self._config = config
        self._services = services or {}

    def get(self, key: str) -> Any:
        return self._config if key == "config" else self._services.get(key)

    def get_or_none(self, key: str) -> Any:
        return self.get(key)

    def has(self, key: str) -> bool:
        return key == "config" or key in self._services


class _PriorChatHistory:
    """Chat history that returns one prior user turn tagged with ``context_lang``.

    This is the shape ``_get_chat_history_language_prior()`` reads. Production
    chat history does not currently persist it (see roadmap Phase 2), so the
    ``pipeline+context`` mode measures what the prior *would* do, not what it
    does in production today.
    """

    def __init__(self, languages: dict[str, str]):
        self._languages = languages

    async def get_conversation_history(self, session_id: str, limit: int, include_metadata: bool):
        lang = self._languages.get(session_id)
        if not lang:
            return []
        return [{"role": "user", "content": "", "metadata": {"detected_language": lang}}]


def load_canonical_config(path: str = CANONICAL_CONFIG_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        full = yaml.safe_load(f)
    return {
        "language_detection": dict(full.get("language_detection") or {}, enabled=True),
        "general": {"verbose": False},
    }


def _top2_margin(scores: list[float]) -> float | None:
    if not scores:
        return None
    ordered = sorted(scores, reverse=True)
    return ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)


def _backend_margin(backend: str, text: str) -> float | None:
    """Top-two margin on each backend's own score scale (as the step normalizes it)."""
    try:
        if backend == "langdetect":
            return _top2_margin([c.prob for c in ld.detect_langs(text)])
        if backend == "langid":
            top_k = ld.langid.rank(text)[:5]
            best = max(s for _, s in top_k)
            exps = [math.exp(s - best) for _, s in top_k]
            return _top2_margin([e / sum(exps) for e in exps])
        if backend == "pycld2":
            _, _, details = ld.cld2.detect(text)
            return _top2_margin([d[2] / 100.0 for d in details if d[1] != "un"])
    except Exception:
        return None
    return None


def _pipeline_margin(raw: dict[str, Any] | None) -> float | None:
    """Vote-share margin, available only on paths that expose the vote table."""
    votes = (raw or {}).get("votes")
    if not votes:
        return None
    total = sum(votes.values())
    return _top2_margin([v / total for v in votes.values()]) if total > 0 else None


async def _predict_pipeline(step, record: dict[str, Any], with_context: bool) -> dict[str, Any]:
    session_id = f"eval-{record['id']}" if with_context and record.get("context_lang") else None
    context = ProcessingContext(message=record["text"], adapter_name="language-eval", session_id=session_id)
    await step.process(context)
    meta = getattr(context, "language_detection_meta", {}) or {}
    return {
        "pred": context.detected_language,
        "confidence": meta.get("confidence"),
        "method": meta.get("method"),
        "margin": _pipeline_margin(meta.get("raw_results")),
        "secondary": meta.get("secondary_language") if meta.get("mixed_language_detected") else None,
        "spans": None,
    }


def _predict_backend(step, backend: str, record: dict[str, Any]) -> dict[str, Any]:
    clean = step._clean_text_for_detection(record["text"])
    result = getattr(step, f"_detect_{backend}")(clean) if clean else None
    return {
        "pred": result.language if result else None,
        "confidence": result.confidence if result else None,
        "method": backend,
        "margin": _backend_margin(backend, clean) if result else None,
        "secondary": None,
        "spans": None,
    }


def _peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is bytes on macOS, kilobytes on Linux.
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


async def run_mode(mode: str, records: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict], dict]:
    services = {}
    if mode == "pipeline+context":
        services["chat_history_service"] = _PriorChatHistory(
            {f"eval-{r['id']}": r["context_lang"] for r in records if r.get("context_lang")}
        )
    step = ld.LanguageDetectionStep(_EvalContainer(config, services))

    async def predict(record):
        if mode in PIPELINE_MODES:
            return await _predict_pipeline(step, record, with_context=mode == "pipeline+context")
        return _predict_backend(step, mode, record)

    start = time.perf_counter()
    await predict({"id": "warmup", "text": "warm up the language detector models", "context_lang": None})
    first_call_ms = (time.perf_counter() - start) * 1000

    predictions, latencies = [], []
    for record in records:
        start = time.perf_counter()
        prediction = await predict(record)
        latencies.append((time.perf_counter() - start) * 1000)
        predictions.append({"id": record["id"], **prediction})

    latencies.sort()
    performance = {
        "first_call_ms": round(first_call_ms, 2),
        "latency_ms": {
            "p50": round(_percentile(latencies, 50), 3),
            "p95": round(_percentile(latencies, 95), 3),
            "mean": round(statistics.fmean(latencies), 3),
            "max": round(latencies[-1], 3),
        },
        "peak_rss_mb_after_mode": round(_peak_rss_mb(), 1),
    }
    return predictions, performance


# ============================================================================
# Scoring
# ============================================================================

def _is_abstention(pred: str | None) -> bool:
    return pred in (None, "", "unknown")


def score_record(record: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    gold = record["lang"]
    accept = ({gold} | set(record.get("alternatives") or [])) - {"unknown"}
    pred = prediction["pred"]
    abstained = _is_abstention(pred)
    correct = (pred in accept) if not abstained else gold == "unknown"
    acceptable = correct or (abstained and record.get("abstain_ok", False))
    confidence = prediction.get("confidence")
    return {
        "abstained": abstained,
        "correct": correct,
        "acceptable": acceptable,
        "high_conf_error": (not abstained and not correct and confidence is not None
                            and confidence >= HIGH_CONFIDENCE),
    }


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    k = (len(sorted_values) - 1) * pct / 100
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def _distribution(values: list[float]) -> dict[str, Any]:
    values = sorted(values)
    if not values:
        return {"n": 0}
    return {"n": len(values), **{f"p{p}": round(_percentile(values, p), 4) for p in (0, 10, 25, 50, 75, 90, 100)}}


def _slice(rows: list[tuple[dict, dict, dict]]) -> dict[str, int]:
    return {
        "n": len(rows),
        "correct": sum(s["correct"] for _, _, s in rows),
        "acceptable": sum(s["acceptable"] for _, _, s in rows),
        "abstained": sum(s["abstained"] for _, _, s in rows),
    }


def _macro_f1(rows: list[tuple[dict, dict, dict]]) -> float:
    labels = sorted({r["lang"] for r, _, _ in rows if r["lang"] != "unknown"})
    f1s = []
    for label in labels:
        tp = sum(1 for r, _, s in rows if r["lang"] == label and s["correct"])
        fn = sum(1 for r, _, s in rows if r["lang"] == label and not s["correct"])
        fp = sum(1 for r, p, s in rows if p["pred"] == label and r["lang"] != label and not s["correct"])
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return statistics.fmean(f1s) if f1s else float("nan")


def _calibration(rows: list[tuple[dict, dict, dict]]) -> dict[str, Any]:
    points = [(p["confidence"], 1.0 if s["correct"] else 0.0)
              for _, p, s in rows if not s["abstained"] and p.get("confidence") is not None]
    if not points:
        return {"n": 0}
    bins = []
    ece = 0.0
    for b in range(CALIBRATION_BINS):
        lo, hi = b / CALIBRATION_BINS, (b + 1) / CALIBRATION_BINS
        members = [(c, y) for c, y in points if lo <= c < hi or (b == CALIBRATION_BINS - 1 and c == 1.0)]
        if not members:
            continue
        mean_conf = statistics.fmean(c for c, _ in members)
        accuracy = statistics.fmean(y for _, y in members)
        ece += len(members) / len(points) * abs(mean_conf - accuracy)
        bins.append({"range": [lo, hi], "n": len(members),
                     "mean_confidence": round(mean_conf, 4), "accuracy": round(accuracy, 4)})
    return {
        "n": len(points),
        "brier": round(statistics.fmean((c - y) ** 2 for c, y in points), 4),
        "ece": round(ece, 4),
        "bins": bins,
    }


def _mixed_metrics(rows: list[tuple[dict, dict, dict]]) -> dict[str, Any]:
    gold_mixed = [bool(r.get("secondary_spans")) for r, _, _ in rows]
    pred_mixed = [bool(p.get("secondary")) or bool(p.get("spans")) for _, p, _ in rows]
    tp = sum(g and p for g, p in zip(gold_mixed, pred_mixed))
    fp = sum(p and not g for g, p in zip(gold_mixed, pred_mixed))
    fn = sum(g and not p for g, p in zip(gold_mixed, pred_mixed))
    secondary_hits = sum(
        1 for (r, p, _), g in zip(rows, gold_mixed)
        if g and p.get("secondary") in {s["lang"] for s in r["secondary_spans"]}
    )

    # Character-level secondary-span precision/recall; needs a detector that
    # emits spans as [{"start", "end", "lang"}] — none does yet (roadmap Phase 4).
    span_tp = span_fp = span_fn = 0
    spans_emitted = any(p.get("spans") is not None for _, p, _ in rows)
    if spans_emitted:
        for r, p, _ in rows:
            gold = secondary_char_labels(r)
            pred = {i: s["lang"] for s in p.get("spans") or [] if s["lang"] != p["pred"]
                    for i in range(s["start"], s["end"])}
            span_tp += sum(1 for i, lang in pred.items() if gold.get(i) == lang)
            span_fp += sum(1 for i, lang in pred.items() if gold.get(i) != lang)
            span_fn += sum(1 for i, lang in gold.items() if pred.get(i) != lang)

    return {
        "gold_mixed": sum(gold_mixed),
        "predicted_mixed": sum(pred_mixed),
        "flag_precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "flag_recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "monolingual_false_positive_rate": (
            round(fp / (len(rows) - sum(gold_mixed)), 4) if len(rows) > sum(gold_mixed) else None
        ),
        "secondary_language_recall": round(secondary_hits / sum(gold_mixed), 4) if any(gold_mixed) else None,
        "span_char_precision": round(span_tp / (span_tp + span_fp), 4) if span_tp + span_fp else None,
        "span_char_recall": round(span_tp / (span_tp + span_fn), 4) if span_tp + span_fn else None,
        "spans_emitted": spans_emitted,
    }


def compute_metrics(records: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {p["id"]: p for p in predictions}
    rows = [(r, by_id[r["id"]], score_record(r, by_id[r["id"]])) for r in records]
    labelled = [row for row in rows if row[0]["lang"] != "unknown"]
    accepted = [row for row in rows if not row[2]["abstained"]]

    def grouped(key):
        groups = defaultdict(list)
        for row in rows:
            groups[row[0][key]].append(row)
        return {k: _slice(v) for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}

    errors = Counter(f"{r['lang']}->{p['pred'] or 'none'}" for r, p, s in rows if not s["correct"])
    confusion = {}
    for group, langs in RELATED_GROUPS.items():
        matrix = defaultdict(Counter)
        for r, p, _ in rows:
            if r["lang"] in langs:
                matrix[r["lang"]][p["pred"] or "none"] += 1
        if matrix:
            confusion[group] = {gold: dict(preds) for gold, preds in sorted(matrix.items())}

    margins_correct = [p["margin"] for _, p, s in accepted if s["correct"] and p["margin"] is not None]
    margins_wrong = [p["margin"] for _, p, s in accepted if not s["correct"] and p["margin"] is not None]
    counts = {
        "n": len(rows),
        "labelled": len(labelled),
        "correct": sum(s["correct"] for _, _, s in rows),
        "labelled_correct": sum(s["correct"] for _, _, s in labelled),
        "acceptable": sum(s["acceptable"] for _, _, s in rows),
        "abstained": sum(s["abstained"] for _, _, s in rows),
        "accepted": len(accepted),
        "accepted_correct": sum(s["correct"] for _, _, s in accepted),
        "high_conf_errors": sum(s["high_conf_error"] for _, _, s in rows),
    }
    return {
        "counts": counts,
        "top1_accuracy": round(counts["labelled_correct"] / counts["labelled"], 4) if labelled else None,
        "macro_f1": round(_macro_f1(labelled), 4) if labelled else None,
        "acceptable_rate": round(counts["acceptable"] / counts["n"], 4),
        "coverage": round(counts["accepted"] / counts["n"], 4),
        "selective_accuracy": round(counts["accepted_correct"] / counts["accepted"], 4) if accepted else None,
        "calibration": _calibration(rows),
        "margin": {"correct": _distribution(margins_correct), "incorrect": _distribution(margins_wrong)},
        "mixed_language": _mixed_metrics(rows),
        "by_language": grouped("lang"),
        "by_script": grouped("script"),
        "by_length": grouped("length_bucket"),
        "by_latin_form": grouped("latin_form"),
        "by_category": grouped("category"),
        "by_shared_script": grouped("shared_script"),
        "methods": dict(Counter(p["method"] for _, p, _ in rows).most_common()),
        "top_errors": dict(errors.most_common(25)),
        "related_confusion": confusion,
    }


# ============================================================================
# Report
# ============================================================================

def _package_versions() -> dict[str, str | None]:
    versions = {}
    for package in ("langdetect", "langid", "pycld2", "pycountry", "regex"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def _mode_available(mode: str) -> bool:
    return {
        "langdetect": ld.LANGDETECT_AVAILABLE,
        "langid": ld.LANGID_AVAILABLE,
        "pycld2": ld.PYCLD2_AVAILABLE,
    }.get(mode, any([ld.LANGDETECT_AVAILABLE, ld.LANGID_AVAILABLE, ld.PYCLD2_AVAILABLE]))


async def run_benchmark(
    modes: tuple[str, ...] = ALL_MODES,
    splits: tuple[str, ...] = SPLITS,
    dataset_path: str = DATASET_PATH,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    records = [r for r in load_dataset(dataset_path) if r["split"] in splits]
    config = config or load_canonical_config()
    report: dict[str, Any] = {
        "benchmark": {
            "version": BENCHMARK_VERSION,
            "dataset": os.path.relpath(dataset_path, REPO_ROOT),
            "sha256": dataset_sha256(dataset_path),
            "records": len(records),
        },
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": _package_versions(),
        },
        "config": config["language_detection"],
        "modes": {},
        "skipped_modes": [],
        "predictions": {},
    }
    for mode in modes:
        if not _mode_available(mode):
            report["skipped_modes"].append(mode)
            continue
        predictions, performance = await run_mode(mode, records, config)
        report["modes"][mode] = {
            "performance": performance,
            "splits": {
                split: compute_metrics([r for r in records if r["split"] == split], predictions)
                for split in splits
            },
        }
        if mode in PIPELINE_MODES:
            report["predictions"][mode] = {
                p["id"]: [p["pred"], None if p["confidence"] is None else round(p["confidence"], 4), p["method"]]
                for p in predictions
            }
    return report


def format_summary(report: dict[str, Any], split: str = "heldout") -> str:
    header = ("| Mode | Top-1 acc | Macro F1 | Acceptable | Coverage | Selective acc | "
              "High-conf errors | Brier | ECE | p50 ms | p95 ms |")
    lines = [header, "|" + "---|" * (header.count("|") - 1)]
    for mode, data in report["modes"].items():
        m = data["splits"].get(split)
        if not m:
            continue
        c, cal, lat = m["counts"], m["calibration"], data["performance"]["latency_ms"]
        lines.append(
            f"| {mode} | {m['top1_accuracy']:.3f} | {m['macro_f1']:.3f} | "
            f"{m['acceptable_rate']:.3f} ({c['acceptable']}/{c['n']}) | {m['coverage']:.3f} | "
            f"{m['selective_accuracy']:.3f} | {c['high_conf_errors']} | "
            f"{cal.get('brier', float('nan')):.3f} | {cal.get('ece', float('nan')):.3f} | "
            f"{lat['p50']:.2f} | {lat['p95']:.2f} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modes", default=",".join(ALL_MODES),
                        help=f"comma-separated subset of: {', '.join(ALL_MODES)}")
    parser.add_argument("--splits", default=",".join(SPLITS), help="comma-separated subset of: tune, heldout")
    parser.add_argument("--output", help="write the JSON report to this path")
    args = parser.parse_args(argv)

    modes = tuple(m for m in args.modes.split(",") if m)
    unknown = set(modes) - set(ALL_MODES)
    if unknown:
        parser.error(f"unknown modes: {', '.join(sorted(unknown))}")
    splits = tuple(s for s in args.splits.split(",") if s)

    report = asyncio.run(run_benchmark(modes=modes, splits=splits))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write("\n")
    for split in splits:
        print(f"\n## {split}\n")
        print(format_summary(report, split))
    if report["skipped_modes"]:
        print(f"\nSkipped (backend not installed): {', '.join(report['skipped_modes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
