"""Evaluators — one per rule the playbooks state.

Every check function has the same shape, `(ctx, check) -> CheckOutcome`, and
the family-level wrappers at the bottom expose the same results to LangSmith's
`(inputs, outputs, reference_outputs) -> dict` convention. The two runners
therefore share one implementation rather than drifting apart.

Scores are 0.0-1.0. `hard` marks a check that must score 1.0 for the case to
pass; partial-credit checks are reported but kept out of the pass/fail gate.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from .agent import AgentRun
from .schema import Case, Check, resolve_templates


@dataclass
class CheckOutcome:
    type: str
    score: float
    comment: str
    hard: bool = True

    @property
    def passed(self) -> bool:
        return self.score >= 1.0


@dataclass
class CheckContext:
    case: Case
    run: AgentRun
    ground_truth: dict[str, Any]

    def resolve(self, value: Any) -> Any:
        return resolve_templates(value, self.ground_truth)


# ---------------------------------------------------------------- normalizing

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


# Markdown emphasis, stripped before matching. Models write "does **not**
# exist", which a plain substring search for "does not exist" misses — a false
# failure about formatting, not behaviour. Underscores are deliberately kept:
# they carry meaning in ids like cus_0025.
_EMPHASIS_RE = re.compile(r"[*`]+")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", _EMPHASIS_RE.sub("", text.lower()))


def _numbers_in(text: str) -> set[float]:
    out = set()
    for match in _NUM_RE.finditer(text):
        try:
            out.add(float(match.group().replace(",", "")))
        except ValueError:
            continue
    return out


def answer_mentions(answer: str, value: Any) -> bool:
    """Does the answer state this value?

    Money and percentages arrive pre-formatted from the server ("$1,007,966",
    "42%"), while a model may restate them as "1,007,966", "1007966" or
    "$1.0M". Compare numbers numerically and everything else as normalized
    substrings.
    """
    text = normalize_text(answer)
    if isinstance(value, bool):
        return str(value).lower() in text
    if isinstance(value, (int, float)):
        return float(value) in _numbers_in(answer)
    literal = str(value).strip()
    if not literal:
        return False
    numeric = literal.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(numeric) in _numbers_in(answer)
    except ValueError:
        return normalize_text(literal) in text


# -------------------------------------------------------------- check bodies


def _calls_of(ctx: CheckContext, tool: str):
    return [call for call in ctx.run.tool_calls if call.name == tool]


def check_required_tools(ctx, check) -> CheckOutcome:
    expected = list(check.get("tools", []))
    called = set(ctx.run.tool_names)
    missing = [tool for tool in expected if tool not in called]
    score = (len(expected) - len(missing)) / len(expected) if expected else 1.0
    return CheckOutcome(
        check.type, score, "all required tools called" if not missing else f"never called: {', '.join(missing)}"
    )


def check_forbidden_tools(ctx, check) -> CheckOutcome:
    forbidden = set(check.get("tools", []))
    hit = sorted(forbidden.intersection(ctx.run.tool_names))
    return CheckOutcome(
        check.type, 0.0 if hit else 1.0, f"called forbidden tool(s): {', '.join(hit)}" if hit else "no forbidden tools"
    )


def check_tool_order(ctx, check) -> CheckOutcome:
    before, after = check.get("before"), check.get("after")
    names = ctx.run.tool_names
    if after not in names:
        # The ordering rule only binds when the later tool was actually used.
        return CheckOutcome(check.type, 1.0, f"{after} not called; ordering rule not engaged")
    if before not in names:
        return CheckOutcome(check.type, 0.0, f"called {after} without ever calling {before}")
    ok = names.index(before) < names.index(after)
    return CheckOutcome(check.type, 1.0 if ok else 0.0, f"order {' -> '.join(names)}")


def check_tool_sequence(ctx, check) -> CheckOutcome:
    """An ordered subsequence over the WHOLE trajectory.

    tool_order relates a single pair by first occurrence, which checks the wrong
    call as soon as a tool repeats: given A, C, B, C the rule "A before C"
    passes on the first C and never examines the second. This walks the
    trajectory once instead, requiring each expected tool to appear after the
    previous match — the check a multi-step workflow actually needs.

    Other calls may appear in between; the agent is allowed to do more than the
    minimum, just not in the wrong order.
    """
    expected = list(check.get("tools", []))
    if not expected:
        raise ValueError("tool_sequence needs a non-empty 'tools' list")
    names = ctx.run.tool_names
    position = 0
    for name in names:
        if position < len(expected) and name == expected[position]:
            position += 1
    if position == len(expected):
        return CheckOutcome(check.type, 1.0, f"sequence held: {' -> '.join(expected)}")
    return CheckOutcome(
        check.type,
        0.0,
        f"sequence broke at step {position + 1} ({expected[position]}); "
        f"matched {position}/{len(expected)}, actual order {' -> '.join(names) or '(no tool calls)'}",
    )


# How many of a repeated tool's calls must carry the expected argument.
ARG_SELECTORS = {
    "any": lambda flags: any(flags),
    "all": lambda flags: all(flags),
    "first": lambda flags: flags[0],
    "last": lambda flags: flags[-1],
}


def check_arg_matches(ctx, check) -> CheckOutcome:
    tool, arg = check.get("tool"), check.get("arg")
    expected = ctx.resolve(check.get("equals"))
    # Default "any" preserves the original semantics. In a multi-step workflow
    # that calls one tool several times, "any" lets a single correct call mask
    # several wrong ones — use "all" there.
    which = check.get("which", "any")
    selector = ARG_SELECTORS.get(which)
    if selector is None:
        raise ValueError(f"arg_matches: unknown which={which!r}, expected one of {sorted(ARG_SELECTORS)}")
    calls = _calls_of(ctx, tool)
    if not calls:
        return CheckOutcome(check.type, 0.0, f"{tool} was never called")
    seen = [call.args.get(arg) for call in calls]
    flags = [str(value) == str(expected) for value in seen]
    ok = selector(flags)
    return CheckOutcome(
        check.type,
        1.0 if ok else 0.0,
        f"{tool}.{arg} expected {expected!r} ({which} of {len(seen)} call(s)), saw {seen!r}",
    )


def check_arg_bound(ctx, check) -> CheckOutcome:
    tool, arg = check.get("tool"), check.get("arg")
    maximum = check.get("max")
    offenders = [
        call.args[arg] for call in _calls_of(ctx, tool) if isinstance(call.args.get(arg), (int, float)) and call.args[arg] > maximum
    ]
    return CheckOutcome(
        check.type,
        0.0 if offenders else 1.0,
        f"{tool}.{arg} exceeded {maximum}: {offenders}" if offenders else f"{tool}.{arg} within {maximum}",
    )


def check_tool_choice(ctx, check) -> CheckOutcome:
    """Exactly one of a mutually-exclusive pair should be used."""
    prefer, instead_of = check.get("prefer"), check.get("instead_of")
    names = set(ctx.run.tool_names)
    used_right, used_wrong = prefer in names, instead_of in names
    if used_right and not used_wrong:
        return CheckOutcome(check.type, 1.0, f"used {prefer}")
    if used_wrong and not used_right:
        return CheckOutcome(check.type, 0.0, f"used {instead_of} instead of {prefer}")
    if not used_right and not used_wrong:
        return CheckOutcome(check.type, 0.0, f"used neither {prefer} nor {instead_of}")
    return CheckOutcome(check.type, 0.5, f"used both {prefer} and {instead_of}", hard=False)


def check_answer_contains(ctx, check) -> CheckOutcome:
    values = [ctx.resolve(value) for value in check.get("values", [])]
    missing = [value for value in values if not answer_mentions(ctx.run.answer, value)]
    score = (len(values) - len(missing)) / len(values) if values else 1.0
    return CheckOutcome(
        check.type, score, "all facts present" if not missing else f"absent from answer: {missing!r}"
    )


def check_answer_not_contains(ctx, check) -> CheckOutcome:
    values = [ctx.resolve(value) for value in check.get("values", [])]
    present = [value for value in values if answer_mentions(ctx.run.answer, value)]
    return CheckOutcome(
        check.type, 0.0 if present else 1.0, f"should not have stated: {present!r}" if present else "clean"
    )


def check_answer_ordering(ctx, check) -> CheckOutcome:
    """Values must appear in the answer in the given order (e.g. a ranking)."""
    values = [str(ctx.resolve(value)) for value in check.get("values", [])]
    text = normalize_text(ctx.run.answer)
    positions = [text.find(normalize_text(value)) for value in values]
    if any(position < 0 for position in positions):
        missing = [value for value, position in zip(values, positions) if position < 0]
        return CheckOutcome(check.type, 0.0, f"not all ranked items present, missing {missing!r}")
    ok = positions == sorted(positions)
    return CheckOutcome(check.type, 1.0 if ok else 0.0, f"expected order {values!r}, positions {positions}")


def check_no_tool_calls(ctx, check) -> CheckOutcome:
    count = len(ctx.run.tool_calls)
    substantive = len(ctx.run.answer.strip()) > 40
    if count:
        return CheckOutcome(check.type, 0.0, f"called {count} tool(s) for a question needing none: {ctx.run.tool_names}")
    return CheckOutcome(check.type, 1.0 if substantive else 0.0, "answered without tools" if substantive else "no tools, but no real answer either")


def check_tool_error_handled(ctx, check) -> CheckOutcome:
    """A failed tool call must be reported, not papered over with invented data."""
    errored = [call for call in ctx.run.tool_calls if call.is_error]
    if not errored:
        return CheckOutcome(check.type, 0.0, "expected a tool error but none occurred")
    text = normalize_text(ctx.run.answer)
    acknowledged = any(
        phrase in text for phrase in ("not found", "no such", "does not exist", "doesn't exist", "unable to find", "could not find", "couldn't find", "no record")
    )
    if not acknowledged:
        return CheckOutcome(check.type, 0.0, "tool errored but the answer never says the record was not found")
    fabricated = [value for value in check.get("must_not_contain", []) if answer_mentions(ctx.run.answer, ctx.resolve(value))]
    if fabricated:
        return CheckOutcome(check.type, 0.0, f"answer invented data after an error: {fabricated!r}")
    return CheckOutcome(check.type, 1.0, "error surfaced honestly")


def check_recovers_after_error(ctx, check) -> CheckOutcome:
    """A failed step mid-workflow must not end the workflow.

    tool_error_handled covers the terminal case: the tool failed and the answer
    says so instead of inventing the value. This covers the other half — the
    agent hit the error, kept going, and finished the job. Without it a run
    that gave up at step two and a run that recovered and completed score
    identically, which is the wrong signal for anything multi-step.
    """
    calls = ctx.run.tool_calls
    first_error = next((i for i, call in enumerate(calls) if call.is_error), None)
    if first_error is None:
        return CheckOutcome(check.type, 0.0, "expected a tool error but none occurred")

    after = calls[first_error + 1 :]
    succeeded = [call for call in after if not call.is_error]
    failed_name = calls[first_error].name
    if not succeeded:
        return CheckOutcome(check.type, 0.0, f"gave up: no tool call succeeded after {failed_name} errored")

    required = list(check.get("then_tools", []))
    recovered_names = [call.name for call in succeeded]
    missing = [tool for tool in required if tool not in recovered_names]
    if missing:
        return CheckOutcome(
            check.type, 0.0, f"recovered but never completed: {', '.join(missing)} did not succeed after the error"
        )
    if not ctx.run.answer.strip():
        return CheckOutcome(check.type, 0.0, "recovered but produced no answer")
    return CheckOutcome(
        check.type,
        1.0,
        f"{failed_name} errored, then {' -> '.join(recovered_names)} succeeded",
    )


def check_no_id_enumeration(ctx, check) -> CheckOutcome:
    """Catches the 'guess ids by iterating cus_0001, cus_0002, ...' failure."""
    prefix = check.get("prefix", "cus_")
    ids = [
        value
        for call in ctx.run.tool_calls
        for value in call.args.values()
        if isinstance(value, str) and value.startswith(prefix)
    ]
    numbers = sorted({int(value.split("_")[1]) for value in ids if value.split("_")[-1].isdigit()})
    consecutive = sum(1 for a, b in pairwise(numbers) if b - a == 1)
    return CheckOutcome(
        check.type,
        0.0 if consecutive >= 2 else 1.0,
        f"looks like id enumeration: {ids}" if consecutive >= 2 else f"no enumeration ({len(ids)} id arg(s))",
    )


def check_max_tool_calls(ctx, check) -> CheckOutcome:
    limit = check.get("max", ctx.case.max_tool_calls)
    count = len(ctx.run.tool_calls)
    return CheckOutcome(check.type, 1.0 if count <= limit else 0.0, f"{count} tool call(s), limit {limit}")


CHECKS: dict[str, Callable[[CheckContext, Check], CheckOutcome]] = {
    "required_tools": check_required_tools,
    "forbidden_tools": check_forbidden_tools,
    "tool_order": check_tool_order,
    "tool_sequence": check_tool_sequence,
    "arg_matches": check_arg_matches,
    "arg_bound": check_arg_bound,
    "tool_choice": check_tool_choice,
    "answer_contains": check_answer_contains,
    "answer_not_contains": check_answer_not_contains,
    "answer_ordering": check_answer_ordering,
    "no_tool_calls": check_no_tool_calls,
    "tool_error_handled": check_tool_error_handled,
    "recovers_after_error": check_recovers_after_error,
    "no_id_enumeration": check_no_id_enumeration,
    "max_tool_calls": check_max_tool_calls,
}

# Partial-credit checks are informative but too noisy to gate on.
SOFT_CHECK_TYPES = {"answer_contains"}


def run_checks(ctx: CheckContext) -> list[CheckOutcome]:
    if ctx.run.error:
        return [CheckOutcome("agent_error", 0.0, ctx.run.error)]
    outcomes: list[CheckOutcome] = []
    for check in ctx.case.checks:
        if check.type == "groundedness":
            continue  # judged separately in judge.py
        fn = CHECKS.get(check.type)
        if fn is None:
            raise ValueError(f"case {ctx.case.id}: unknown check type {check.type!r}")
        outcome = fn(ctx, check)
        if check.type in SOFT_CHECK_TYPES:
            outcome.hard = False
        outcomes.append(outcome)
    return outcomes
