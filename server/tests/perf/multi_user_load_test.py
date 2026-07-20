#!/usr/bin/env python3
"""
Multi-User Load Test for Orbit Inference Server

Drives concurrent virtual users against the server, each authenticating with
a different adapter's API key, to simulate semi-realistic multi-tenant chat
traffic. Reports overall and per-adapter latency/error metrics so you can see
how the server behaves under volume before it's deployed to a given
hardware/environment configuration.

Each virtual user loops: pick a weighted-random adapter -> pick a random
prompt for that adapter -> send a chat request -> pause for a random
"think time" -> repeat. User count can ramp in gradually (--spawn-rate) or
move through explicit stages (--stages) to find the point where the server
starts degrading.

Usage:
    python multi_user_load_test.py --config load_test_config.json --users 20 --duration 120
    python multi_user_load_test.py --config load_test_config.json --stages "10:60,50:120,100:180"
    python multi_user_load_test.py --config load_test_config.json --users 20 --stream
"""

import argparse
import asyncio
import json
import random
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from advanced_performance_test import PerformanceMetrics, TestResult


def safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def load_config(path: Path, host_override: Optional[str], endpoint_override: Optional[str],
                 adapter_subset: Optional[List[str]]) -> Dict[str, Any]:
    with open(path) as f:
        config = json.load(f)

    if host_override:
        config["host"] = host_override
    if endpoint_override:
        config["endpoint"] = endpoint_override

    if adapter_subset:
        config["adapters"] = [a for a in config["adapters"] if a["id"] in adapter_subset]
        missing = set(adapter_subset) - {a["id"] for a in config["adapters"]}
        if missing:
            print(f"Warning: adapters not found in config: {', '.join(sorted(missing))}")

    if not config.get("adapters"):
        raise SystemExit("No adapters to test (check --config / --adapters)")

    config.setdefault("default_prompts", ["Hello, this is a load test message."])
    return config


def parse_stages(stages_str: str) -> List[tuple]:
    stages = []
    for part in stages_str.split(","):
        users_str, seconds_str = part.strip().split(":")
        stages.append((int(users_str), int(seconds_str)))
    return stages


def weighted_choice(adapters: List[Dict[str, Any]]) -> Dict[str, Any]:
    weights = [max(0.0001, float(a.get("weight", 1))) for a in adapters]
    return random.choices(adapters, weights=weights, k=1)[0]


def build_stage_schedule(stages: List[tuple], spawn_rate: float) -> List[tuple]:
    """Turn a (target, hold_duration) stage list into a schedule of
    (ramp_start, ramp_end, hold_end, prev_target, target) tuples.

    Ramp time is added *before* each stage's hold window rather than eaten
    out of it, so a stage's documented duration is always spent fully at
    its target user count.
    """
    schedule = []
    cumulative = 0.0
    prev_target = 0
    for target, duration in stages:
        ramp_time = (target - prev_target) / spawn_rate if target > prev_target and spawn_rate > 0 else 0.0
        ramp_start = cumulative
        ramp_end = ramp_start + ramp_time
        hold_end = ramp_end + duration
        schedule.append((ramp_start, ramp_end, hold_end, prev_target, target))
        cumulative = hold_end
        prev_target = target
    return schedule


def target_at(elapsed: float, schedule: List[tuple], spawn_rate: float) -> int:
    for ramp_start, ramp_end, hold_end, prev_target, target in schedule:
        if elapsed >= hold_end:
            continue
        if elapsed >= ramp_end or ramp_end <= ramp_start:
            return target
        progress = elapsed - ramp_start
        count = prev_target + int(progress * spawn_rate)
        if prev_target == 0:
            count = max(1, count)
        return min(target, count)
    return schedule[-1][4] if schedule else 0


async def send_chat_request(session: aiohttp.ClientSession, host: str, endpoint: str,
                             adapter: Dict[str, Any], prompt: str, stream: bool,
                             timeout: float, session_id: str) -> TestResult:
    url = f"{host.rstrip('/')}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": adapter["api_key"],
        "X-Session-ID": session_id,
    }
    payload = {"messages": [{"role": "user", "content": prompt}], "stream": stream}
    start = time.time()
    first_token_time = None

    try:
        async with session.post(url, json=payload, headers=headers,
                                 timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            status = response.status
            rate_limit = safe_int(response.headers.get("X-RateLimit-Limit"))
            rate_remaining = safe_int(response.headers.get("X-RateLimit-Remaining"))
            error_message = None

            if stream and status == 200:
                saw_done = False
                async for line_bytes in response.content:
                    line = line_bytes.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    if first_token_time is None:
                        first_token_time = time.time() - start
                    if line.startswith("data:") and line[len("data:"):].strip() == "[DONE]":
                        saw_done = True
                        break
                success = saw_done
                if not success:
                    error_message = "Stream closed before [DONE] was received"
            else:
                body = await response.read()
                success = 200 <= status < 400
                if not success:
                    error_message = body.decode("utf-8", errors="ignore")[:500]

            response_time = time.time() - start
            return TestResult(
                endpoint=endpoint,
                method="POST",
                status_code=status,
                response_time=response_time,
                timestamp=start,
                success=success,
                error_message=error_message,
                rate_limited=(status == 429),
                rate_limit=rate_limit,
                rate_remaining=rate_remaining,
                adapter=adapter["id"],
                first_token_time=first_token_time,
            )
    except Exception as e:
        response_time = time.time() - start
        return TestResult(
            endpoint=endpoint,
            method="POST",
            status_code=0,
            response_time=response_time,
            timestamp=start,
            success=False,
            error_message=str(e),
            adapter=adapter["id"],
            first_token_time=first_token_time,
        )


async def user_worker(worker_id: int, config: Dict[str, Any], session: aiohttp.ClientSession,
                       args: argparse.Namespace, target_ref: Dict[str, int],
                       stop_event: asyncio.Event, metrics: PerformanceMetrics):
    session_id_base = f"perf_mu_{int(time.time())}_{worker_id}"
    counter = 0

    while not stop_event.is_set():
        if worker_id >= target_ref["value"]:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
            continue

        counter += 1
        adapter = weighted_choice(config["adapters"])
        prompts = adapter.get("prompts") or config["default_prompts"]
        prompt = random.choice(prompts)

        result = await send_chat_request(
            session, config["host"], config["endpoint"], adapter, prompt,
            args.stream, args.timeout, f"{session_id_base}_{counter}"
        )
        metrics.add_result(result)

        think_time = random.uniform(args.think_time_min, args.think_time_max)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=think_time)
        except asyncio.TimeoutError:
            pass


def per_adapter_summaries(metrics: PerformanceMetrics) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[TestResult]] = {}
    for result in metrics.results:
        groups.setdefault(result.adapter or "unknown", []).append(result)

    summaries = {}
    for adapter_id, results in groups.items():
        pm = PerformanceMetrics()
        pm.start_time = metrics.start_time
        pm.results = results
        summaries[adapter_id] = pm.get_summary()
    return summaries


async def run_load_test(config: Dict[str, Any], args: argparse.Namespace) -> PerformanceMetrics:
    stages = parse_stages(args.stages) if args.stages else [(args.users, args.duration)]
    max_users = max(t for t, _ in stages)
    schedule = build_stage_schedule(stages, args.spawn_rate)
    total_duration = schedule[-1][2] if schedule else 0.0

    metrics = PerformanceMetrics()
    stop_event = asyncio.Event()
    target_ref = {"value": 0}

    connector = aiohttp.TCPConnector(limit=max_users + 10)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [
            asyncio.create_task(user_worker(i, config, session, args, target_ref, stop_event, metrics))
            for i in range(max_users)
        ]

        start = time.time()
        last_status = 0.0
        try:
            while time.time() - start < total_duration:
                elapsed = time.time() - start
                target_ref["value"] = target_at(elapsed, schedule, args.spawn_rate)

                if elapsed - last_status >= args.status_interval:
                    last_status = elapsed
                    total = len(metrics.results)
                    failed = sum(1 for r in metrics.results if not r.success)
                    print(f"  [{elapsed:6.1f}s] active_users={target_ref['value']:<4d} "
                          f"requests={total:<6d} failed={failed}")

                await asyncio.sleep(0.5)
        except KeyboardInterrupt:
            print("\nInterrupted — stopping and generating report from partial results...")
        finally:
            stop_event.set()
            target_ref["value"] = 0
            await asyncio.gather(*workers, return_exceptions=True)

    return metrics


def print_report(metrics: PerformanceMetrics, adapter_summaries: Dict[str, Dict[str, Any]], stream: bool):
    summary = metrics.get_summary()

    print("\n" + "=" * 70)
    print("OVERALL RESULTS")
    print("=" * 70)
    print(f"Total Requests:     {summary.get('total_requests', 0)}")
    print(f"Successful:         {summary.get('successful_requests', 0)}")
    print(f"Rate Limited (429): {summary.get('rate_limited_requests', 0)}")
    print(f"Failed (other):     {summary.get('failed_requests', 0)}")
    print(f"Success Rate:       {summary.get('success_rate', 0):.2f}%")
    print(f"Requests/Second:    {summary.get('requests_per_second', 0):.2f}")
    print(f"Test Duration:      {summary.get('test_duration', 0):.2f}s")

    if summary.get("response_time_stats"):
        stats = summary["response_time_stats"]
        print("\nResponse Time (s):  "
              f"min={stats['min']:.3f} mean={stats['mean']:.3f} median={stats['median']:.3f} "
              f"p95={stats['p95']:.3f} p99={stats['p99']:.3f} max={stats['max']:.3f}")

    print("\n" + "=" * 70)
    print("PER-ADAPTER BREAKDOWN")
    print("=" * 70)
    header = f"{'adapter':<30} {'reqs':>6} {'success%':>9} {'p50':>7} {'p95':>7} {'p99':>7} {'rps':>7}"
    print(header)
    print("-" * len(header))
    for adapter_id, s in sorted(adapter_summaries.items(), key=lambda kv: -kv[1].get("total_requests", 0)):
        stats = s.get("response_time_stats", {})
        p50 = stats.get("median", 0)
        p95 = stats.get("p95", 0)
        p99 = stats.get("p99", 0)
        print(f"{adapter_id:<30} {s.get('total_requests', 0):>6} "
              f"{s.get('success_rate', 0):>8.1f}% {p50:>7.3f} {p95:>7.3f} {p99:>7.3f} "
              f"{s.get('requests_per_second', 0):>7.2f}")

    if stream:
        ttft_values = [r.first_token_time for r in metrics.results if r.first_token_time is not None and r.success]
        if ttft_values:
            ttft_sorted = sorted(ttft_values)
            mean_ttft = sum(ttft_values) / len(ttft_values)
            p95_ttft = ttft_sorted[int(0.95 * (len(ttft_sorted) - 1))]
            print(f"\nTime to First Token: mean={mean_ttft:.3f}s p95={p95_ttft:.3f}s "
                  f"(n={len(ttft_values)})")

    errors = [r for r in metrics.results if not r.success and r.error_message]
    if errors:
        print("\nSample errors:")
        for r in errors[:5]:
            print(f"  [{r.adapter}] HTTP {r.status_code}: {r.error_message[:200]}")


def generate_html_report(summary: Dict[str, Any], adapter_summaries: Dict[str, Dict[str, Any]],
                          args: argparse.Namespace, timestamp: str) -> str:
    rows = ""
    for adapter_id, s in sorted(adapter_summaries.items(), key=lambda kv: -kv[1].get("total_requests", 0)):
        stats = s.get("response_time_stats", {})
        rows += f"""
        <tr>
            <td>{adapter_id}</td>
            <td>{s.get('total_requests', 0)}</td>
            <td>{s.get('success_rate', 0):.1f}%</td>
            <td>{stats.get('median', 0):.3f}s</td>
            <td>{stats.get('p95', 0):.3f}s</td>
            <td>{stats.get('p99', 0):.3f}s</td>
            <td>{s.get('requests_per_second', 0):.2f}</td>
        </tr>"""

    stats = summary.get("response_time_stats", {})
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Orbit Multi-User Load Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        .metric {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #007bff; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-align: center; }}
        .stat-value {{ font-size: 1.8em; font-weight: bold; color: #007bff; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #eee; }}
        th {{ background: #f0f4f8; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Orbit Multi-User Load Test Report</h1>
        <div class="metric">
            <h3>Configuration</h3>
            <p><strong>Users:</strong> {args.users} &nbsp; <strong>Spawn Rate:</strong> {args.spawn_rate}/s
               &nbsp; <strong>Stages:</strong> {args.stages or 'n/a'}</p>
            <p><strong>Streaming:</strong> {args.stream} &nbsp; <strong>Timestamp:</strong> {timestamp}</p>
        </div>
        <div class="metric">
            <h3>Overall Results</h3>
            <div class="stats-grid">
                <div class="stat-card"><div class="stat-value">{summary.get('total_requests', 0)}</div><div class="stat-label">Total Requests</div></div>
                <div class="stat-card"><div class="stat-value">{summary.get('success_rate', 0):.1f}%</div><div class="stat-label">Success Rate</div></div>
                <div class="stat-card"><div class="stat-value">{summary.get('requests_per_second', 0):.2f}</div><div class="stat-label">Requests/Second</div></div>
                <div class="stat-card"><div class="stat-value">{stats.get('p95', 0):.3f}s</div><div class="stat-label">p95 Latency</div></div>
                <div class="stat-card"><div class="stat-value">{stats.get('p99', 0):.3f}s</div><div class="stat-label">p99 Latency</div></div>
            </div>
        </div>
        <div class="metric">
            <h3>Per-Adapter Breakdown</h3>
            <table>
                <tr><th>Adapter</th><th>Requests</th><th>Success</th><th>p50</th><th>p95</th><th>p99</th><th>RPS</th></tr>
                {rows}
            </table>
        </div>
    </div>
</body>
</html>
"""


async def main_async():
    parser = argparse.ArgumentParser(description="Multi-user load test for Orbit Inference Server")
    parser.add_argument("--config", default="load_test_config.json", help="Path to load test config JSON")
    parser.add_argument("--host", help="Override host from config")
    parser.add_argument("--endpoint", help="Override chat endpoint from config")
    parser.add_argument("--adapters", help="Comma-separated adapter ids to restrict to")
    parser.add_argument("--users", type=int, default=10, help="Concurrent virtual users (ignored if --stages given)")
    parser.add_argument("--spawn-rate", type=float, default=1.0, help="Users/second ramp-up rate")
    parser.add_argument("--duration", type=int, default=60,
                        help="Seconds to hold at --users, once ramped up (ignored if --stages given)")
    parser.add_argument("--stages",
                        help='Staged ramp as "users:seconds,users:seconds,...", e.g. "10:60,50:120,100:180". '
                             "Each stage's seconds is time held at its target user count; ramp time between "
                             "stages is added on top, so total run time exceeds the sum of stage durations.")
    parser.add_argument("--stream", action="store_true", help="Use SSE streaming and record time-to-first-token")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds")
    parser.add_argument("--think-time-min", type=float, default=0.5, help="Minimum think time between a user's requests")
    parser.add_argument("--think-time-max", type=float, default=3.0, help="Maximum think time between a user's requests")
    parser.add_argument("--status-interval", type=float, default=5.0, help="Console status print interval in seconds")
    parser.add_argument("--output", default="results", help="Output directory for CSV/HTML reports")
    args = parser.parse_args()

    adapter_subset = [a.strip() for a in args.adapters.split(",")] if args.adapters else None
    config = load_config(Path(args.config), args.host, args.endpoint, adapter_subset)

    print("Starting multi-user load test")
    print(f"Target: {config['host']}{config['endpoint']}")
    print(f"Adapters: {', '.join(a['id'] for a in config['adapters'])}")
    if args.stages:
        print(f"Stages: {args.stages}")
    else:
        print(f"Users: {args.users}  Spawn rate: {args.spawn_rate}/s  Duration: {args.duration}s")
    print(f"Streaming: {args.stream}\n")

    metrics = await run_load_test(config, args)
    adapter_summaries = per_adapter_summaries(metrics)
    print_report(metrics, adapter_summaries, args.stream)

    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True, parents=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    csv_file = output_dir / f"multi_user_load_{timestamp}.csv"
    html_file = output_dir / f"multi_user_load_{timestamp}.html"

    metrics.export_csv(str(csv_file))
    with open(html_file, "w") as f:
        f.write(generate_html_report(metrics.get_summary(), adapter_summaries, args, timestamp))

    print(f"\nResults exported to:\n  CSV:  {csv_file}\n  HTML: {html_file}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
