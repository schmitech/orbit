"""Run artifacts: a JSON record for machines, a markdown scoreboard for humans."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import RESULTS_DIR
from .runner import EvalResult


def to_json(results: list[EvalResult]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summaries": [result.summary() for result in results],
        "runs": [
            {
                "key": result.key(),
                "cases": [
                    {
                        "case_id": case.case_id,
                        "passed": case.passed,
                        "tools_called": case.run.tool_names,
                        "tool_args": [call.args for call in case.run.tool_calls],
                        "latency_s": round(case.run.latency_s, 2),
                        "agent_error": case.run.error,
                        "judge_score": case.judge_score,
                        "judge_comment": case.judge_comment,
                        "checks": [
                            {"type": o.type, "score": o.score, "hard": o.hard, "comment": o.comment}
                            for o in case.outcomes
                        ],
                        "answer": case.run.answer,
                        "ground_truth": case.ground_truth,
                    }
                    for case in result.cases
                ],
            }
            for result in results
        ],
    }


def _delta_table(results: list[EvalResult]) -> list[str]:
    """base vs playbook, per suite and model.

    This is the question the harness exists to answer: does injecting the
    tool-skill playbook actually change rule compliance?
    """
    by_pair: dict[tuple[str, str], dict[str, EvalResult]] = {}
    for result in results:
        by_pair.setdefault((result.suite, result.model_key), {})[result.variant] = result

    comparable = {pair: variants for pair, variants in by_pair.items() if len(variants) > 1}
    if not comparable:
        return []

    lines = ["", "## Playbook effect (checks passed)", "", "| Suite | Model | base | playbook | delta |", "|---|---|---|---|---|"]
    for (suite, model), variants in sorted(comparable.items()):
        base, playbook = variants.get("base"), variants.get("playbook")
        if not (base and playbook):
            continue
        delta = playbook.checks_passed - base.checks_passed
        lines.append(
            f"| {suite} | {model} | {base.checks_passed}/{base.checks_total} | "
            f"{playbook.checks_passed}/{playbook.checks_total} | {delta:+d} |"
        )
    return lines


def to_markdown(results: list[EvalResult]) -> str:
    lines = [
        "# MCP agent evaluation",
        "",
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        "| Suite | Model | Variant | Cases | Checks | Judge | Agent errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        summary = result.summary()
        judge = "-" if summary["judge_mean"] is None else f"{summary['judge_mean']:.2f}"
        lines.append(
            f"| {result.suite} | {result.model_key} | {result.variant} | "
            f"{summary['cases_passed']}/{summary['total']} | "
            f"{summary['checks_passed']}/{summary['checks_total']} | {judge} | {summary['agent_errors']} |"
        )

    lines += _delta_table(results)

    failures = [(result, row) for result in results for row in result.failures]
    lines += ["", "## Failures", ""]
    if not failures:
        lines.append("None.")
    for result, row in failures:
        marker = "" if row["hard"] else " _(soft)_"
        lines.append(f"- **{result.key()}** / `{row['case_id']}` / `{row['check']}`{marker} — {row['comment']}")
        lines.append(f"  - tools called: `{row['tools_called']}`")
    return "\n".join(lines) + "\n"


def write(results: list[EvalResult], label: str = "run") -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = RESULTS_DIR / f"{label}-{stamp}.json"
    md_path = RESULTS_DIR / f"{label}-{stamp}.md"
    json_path.write_text(json.dumps(to_json(results), indent=2, default=str))
    md_path.write_text(to_markdown(results))
    return json_path, md_path
