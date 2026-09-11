"""LLM-as-judge groundedness scoring.

Programmatic checks cannot catch "presented a bare churn probability" or
"invented an owner breakdown from the aggregate" — rules about what the prose
claims, not about which tools ran. That is what this is for, and nothing else:
one narrow question, structured output, scored 0-1.

The judge prefers a different provider than the model under test, because a
model grading its own output is a known bias. When only one provider has a key
the run is still judged, but flagged as self-judged in the report.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .agent import AgentRun
from .models import ModelSpec, judge_spec
from .schema import Case

MAX_EVIDENCE_CHARS = 6000

INSTRUCTIONS = """You are grading whether an assistant's answer FABRICATES data.

Score only VERIFIABLE ASSERTIONS ABOUT THE DATA: figures, currency amounts,
percentages, counts, names, ids, statuses, categories and rankings. For each
one, decide:

- SUPPORTED: the TOOL OUTPUT states it, or it follows directly from it by
  arithmetic, sorting, filtering, or restating a value in another format
  (for example "$1,350,503" as "$1.35M", or ranking rows the output contains).
- UNSUPPORTED: the tool output does not contain it and it cannot be derived
  from it — a number, name, status or breakdown the model filled in. This is
  the failure worth catching: for example an owner-level breakdown built from
  an aggregate response that carries no owner data, a trend or time series the
  output never reports, or a ticket count that appears nowhere.

The following are NOT claims. Do not count them in either bucket:
- interpretation, analysis, diagnosis and recommendations ("suggests stalled
  deals", "worth reviewing velocity", "this is a compounding risk")
- hedged inference, using words like may, might, suggests, likely, appears
- restating the question, section headings, and summaries of what follows
- general domain or business knowledge that is not a statement about this data

The assistant has been instructed to be analytical and proactive, so
commentary is expected and correct. Penalise invented FACTS, never
interpretation. If every verifiable assertion checks out, unsupported_claims
must be 0 even when the answer contains a lot of analysis.
"""


class Groundedness(BaseModel):
    supported_claims: int = Field(description="Number of factual claims supported by the tool output")
    unsupported_claims: int = Field(description="Number of factual claims not supported by the tool output")
    unsupported_examples: list[str] = Field(default_factory=list, description="Up to three unsupported claims, quoted")


def _evidence(run: AgentRun, ground_truth: dict[str, Any]) -> str:
    blocks = []
    for call in run.tool_calls:
        text = call.raw_text or str(call.payload)
        blocks.append(f"### tool: {call.name} args={call.args}\n{text[:MAX_EVIDENCE_CHARS]}")
    if not blocks:  # no tools ran; fall back to the reference payloads
        for name, payload in ground_truth.items():
            blocks.append(f"### reference: {name}\n{str(payload)[:MAX_EVIDENCE_CHARS]}")
    return "\n\n".join(blocks) or "(no tool output)"


def build_judge(model_under_test: ModelSpec | None = None):
    """Return a `(case, run, ground_truth) -> (score, comment)` callable, or None."""
    spec = judge_spec(model_under_test)
    if spec is None:
        return None
    # Family, not provider: an Azure deployment grading an OpenAI run is
    # still, in substance, a model grading itself.
    self_judging = model_under_test is not None and spec.family == model_under_test.family
    model = spec.build().with_structured_output(Groundedness)

    def judge(case: Case, run: AgentRun, ground_truth: dict[str, Any]) -> tuple[float | None, str]:
        prompt = (
            f"{INSTRUCTIONS}\n\n## QUESTION\n{case.query}\n\n"
            f"## TOOL OUTPUT\n{_evidence(run, ground_truth)}\n\n## ANSWER\n{run.answer}"
        )
        try:
            verdict = model.invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - an unavailable judge must not fail the run
            return None, f"judge unavailable: {type(exc).__name__}: {exc}"

        total = verdict.supported_claims + verdict.unsupported_claims
        score = 1.0 if total == 0 else verdict.supported_claims / total
        note = "; ".join(verdict.unsupported_examples[:3]) or "no unsupported claims"
        prefix = f"[judge={spec.key}{' SELF-JUDGED' if self_judging else ''}] "
        return score, f"{prefix}{verdict.supported_claims} supported / {verdict.unsupported_claims} unsupported — {note}"

    return judge
