#!/usr/bin/env python
"""CLI entry point for ad-hoc evaluation runs.

    .venv/bin/python run_suite.py                        # every suite, every available model, playbook variant
    .venv/bin/python run_suite.py --suite crm_pipeline --variant base playbook
    .venv/bin/python run_suite.py --case rank_reps_by_attainment --no-judge

The pytest gate in tests/test_regression.py runs the same code path; this is
for iterating on cases and reading the report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcpeval import report
from mcpeval.agent import load_tools
from mcpeval.config import CASES_DIR, Settings
from mcpeval.judge import build_judge
from mcpeval.models import available
from mcpeval.protocol import RawMcpClient, server_healthy
from mcpeval.runner import VARIANTS, run_eval
from mcpeval.sandbox import TicketSandbox
from mcpeval.schema import load_suites


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", action="append", help="suite name; repeatable (default: all)")
    parser.add_argument("--case", action="append", help="case id; repeatable (default: all)")
    parser.add_argument("--model", action="append", help="model key substring; repeatable (default: all available)")
    parser.add_argument("--variant", nargs="+", choices=VARIANTS, default=["playbook"])
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM groundedness judge")
    parser.add_argument("--label", default="run", help="filename prefix for the report")
    parser.add_argument("--skip-mutating", action="store_true", help="skip the support-ticket CRUD cases")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not server_healthy(settings):
        print(f"MCP server is not reachable at {settings.health_url}.", file=sys.stderr)
        print("Start it with: cd ../mcp-server && MCP_TOKEN=test-secret npm start", file=sys.stderr)
        return 2

    specs = available()
    if args.model:
        specs = [spec for spec in specs if any(fragment in spec.key for fragment in args.model)]
    if not specs:
        print("No provider API keys found — set OPENAI_API_KEY and/or ANTHROPIC_API_KEY.", file=sys.stderr)
        return 2

    suites = [suite for suite in load_suites(CASES_DIR) if not args.suite or suite.name in args.suite]
    only = set(args.case) if args.case else None
    if only:
        suites = [suite for suite in suites if any(case.id in only for case in suite.cases)]
    if not suites:
        print("No suites matched.", file=sys.stderr)
        return 2

    tools = await load_tools(settings)
    results = []
    with RawMcpClient(settings) as raw_client:
        # Snapshot the ticket table up front; restore it however the run ends,
        # so an interrupted run never leaves the server's data skewed for the
        # next one.
        sandbox = None if args.skip_mutating else TicketSandbox.capture(raw_client)
        for spec in specs:
            judge = None if args.no_judge else build_judge(spec)
            for suite in suites:
                # A suite with no playbook has nothing to inject, so it always
                # runs as "base" rather than being skipped.
                variants = sorted({("base" if not suite.playbook else v) for v in args.variant})
                for variant in variants:
                    print(f"-> {suite.name} / {spec.key} / {variant}", file=sys.stderr)
                    results.append(
                        await run_eval(
                            suite, spec, variant,
                            tools=tools, raw_client=raw_client, judge=judge, only=only,
                            sandbox=sandbox, include_mutating=not args.skip_mutating,
                        )
                    )
        if sandbox is not None:
            repaired = sandbox.restore()
            if any(repaired.values()):
                print(f"sandbox restored: {repaired}", file=sys.stderr)
            drift = sandbox.drifted()
            if drift:
                print(f"WARNING: ticket state still drifted after restore: {drift}", file=sys.stderr)

    json_path, md_path = report.write(results, label=args.label)
    for result in results:
        print(json.dumps(result.summary()))
    print(f"\nreports: {json_path}\n         {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
