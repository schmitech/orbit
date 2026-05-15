#!/usr/bin/env python3
"""
Run the Orbit server under memray and drive an existing perf workload.

This script profiles the server process, not the load-generator process. It
starts ``server/main.py`` through memray, waits for ``/health``, runs one of the
advanced performance scenarios, then stops the server and writes memray reports.
"""

import argparse
import asyncio
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import urlopen

from advanced_performance_test import LoadGenerator


SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_DIR = SCRIPT_DIR.parents[1]
PROJECT_ROOT = SERVER_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Orbit under memray and generate leak reports.",
        epilog=(
            "If /health is already reachable at --base-url, stop the existing "
            "server with ./bin/orbit.sh stop or use a config with a different "
            "port and pass the matching --base-url, for example: "
            "--config ../../../config/config-memray.yaml "
            "--base-url http://127.0.0.1:3001"
        ),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:3000",
        help="Base URL for workload requests. Must match the server config.",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "config.yaml"),
        help="Config file passed to server/main.py.",
    )
    parser.add_argument("--api-key", help="API key for authenticated workloads")
    parser.add_argument(
        "--scenario",
        choices=["health", "chat", "mixed", "burst", "ramp"],
        default="mixed",
        help="Workload scenario from advanced_performance_test.py.",
    )
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds")
    parser.add_argument("--rps", type=int, default=5, help="Requests per second")
    parser.add_argument("--burst-size", type=int, default=50, help="Burst scenario size")
    parser.add_argument("--burst-count", type=int, default=5, help="Burst count")
    parser.add_argument("--start-rps", type=int, default=1, help="Ramp starting RPS")
    parser.add_argument("--end-rps", type=int, default=20, help="Ramp ending RPS")
    parser.add_argument(
        "--output",
        default=str(SCRIPT_DIR / "results" / "memray"),
        help="Directory for memray output and generated reports.",
    )
    parser.add_argument(
        "--native",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Capture native frames. Disable with --no-native.",
    )
    parser.add_argument(
        "--follow-fork",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Capture child processes. Usually keep false and configure one worker.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=int,
        default=90,
        help="Seconds to wait for /health before failing.",
    )
    return parser.parse_args()


def wait_for_health(base_url: str, timeout: int, proc: subprocess.Popen) -> None:
    deadline = time.time() + timeout
    health_url = f"{base_url.rstrip('/')}/health"

    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Server exited before becoming healthy: {proc.returncode}")

        try:
            with urlopen(health_url, timeout=2) as response:
                if 200 <= response.status < 500:
                    if proc.poll() is not None:
                        raise RuntimeError(
                            "Server exited after health check responded. "
                            f"Exit code: {proc.returncode}"
                        )
                    return
        except URLError:
            pass
        except TimeoutError:
            pass

        time.sleep(1)

    raise TimeoutError(f"Timed out waiting for {health_url}")


def health_is_reachable(base_url: str) -> bool:
    try:
        with urlopen(f"{base_url.rstrip('/')}/health", timeout=2) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


async def run_workload(args: argparse.Namespace, base_url: str) -> dict:
    async with LoadGenerator(base_url, args.api_key) as loader:
        if args.scenario == "health":
            await loader.health_check_load(args.duration, args.rps)
        elif args.scenario == "chat":
            await loader.chat_load(args.duration, args.rps)
        elif args.scenario == "mixed":
            await loader.mixed_load(args.duration, args.rps)
        elif args.scenario == "burst":
            await loader.burst_load(args.burst_size, args.burst_count, 2.0)
        elif args.scenario == "ramp":
            await loader.ramp_load(args.start_rps, args.end_rps, args.duration)
        return loader.metrics.get_summary()


def stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return

    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=10)


def run_report_command(command: list[str], output_file: Optional[Path] = None) -> None:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if output_file is not None:
        output_file.write_text(result.stdout + result.stderr)

    if result.returncode != 0:
        joined = " ".join(command)
        raise RuntimeError(f"Report command failed ({result.returncode}): {joined}")


def generate_reports(output_bin: Path, run_dir: Path) -> None:
    summary_txt = run_dir / "memray_summary.txt"
    stats_txt = run_dir / "memray_stats.txt"
    peak_flamegraph = run_dir / "memray_peak_flamegraph.html"
    leak_flamegraph = run_dir / "memray_leaks_flamegraph.html"
    leak_table = run_dir / "memray_leaks_table.html"

    run_report_command(
        [sys.executable, "-m", "memray", "summary", str(output_bin)], summary_txt
    )
    run_report_command(
        [sys.executable, "-m", "memray", "stats", str(output_bin)], stats_txt
    )
    run_report_command(
        [
            sys.executable,
            "-m",
            "memray",
            "flamegraph",
            "-f",
            "-o",
            str(peak_flamegraph),
            str(output_bin),
        ]
    )
    run_report_command(
        [
            sys.executable,
            "-m",
            "memray",
            "flamegraph",
            "--leaks",
            "-f",
            "-o",
            str(leak_flamegraph),
            str(output_bin),
        ]
    )
    run_report_command(
        [
            sys.executable,
            "-m",
            "memray",
            "table",
            "--leaks",
            "-f",
            "-o",
            str(leak_table),
            str(output_bin),
        ]
    )


def main() -> int:
    args = parse_args()
    base_url = args.base_url
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output) / f"{args.scenario}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    output_bin = run_dir / "orbit_memray.bin"
    server_log = run_dir / "server.log"
    workload_summary = run_dir / "workload_summary.txt"

    if health_is_reachable(base_url):
        print(
            f"{base_url}/health is already reachable. Stop the existing server "
            "or choose a config/base URL with a free port before profiling.",
            file=sys.stderr,
        )
        return 2

    command = [
        sys.executable,
        "-m",
        "memray",
        "run",
        "-o",
        str(output_bin),
    ]
    if args.native:
        command.append("--native")
    if args.follow_fork:
        command.append("--follow-fork")

    command.extend(["server/main.py", "--config", str(Path(args.config).resolve())])

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with server_log.open("w") as log:
        proc = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )

        try:
            wait_for_health(base_url, args.startup_timeout, proc)
            summary = asyncio.run(run_workload(args, base_url))
        finally:
            stop_process(proc)

    workload_summary.write_text(
        "\n".join(
            [
                f"Base URL: {base_url}",
                f"Scenario: {args.scenario}",
                f"Duration: {args.duration}s",
                f"RPS: {args.rps}",
                f"Total requests: {summary.get('total_requests', 0)}",
                f"Successful requests: {summary.get('successful_requests', 0)}",
                f"Failed requests: {summary.get('failed_requests', 0)}",
                f"Success rate: {summary.get('success_rate', 0):.2f}%",
                f"Requests/second: {summary.get('requests_per_second', 0):.2f}",
                "",
            ]
        )
    )

    generate_reports(output_bin, run_dir)

    print(f"Memray binary: {output_bin}")
    print(f"Server log: {server_log}")
    print(f"Workload summary: {workload_summary}")
    print(f"Text summary: {run_dir / 'memray_summary.txt'}")
    print(f"Stats: {run_dir / 'memray_stats.txt'}")
    print(f"Peak flamegraph: {run_dir / 'memray_peak_flamegraph.html'}")
    print(f"Leak flamegraph: {run_dir / 'memray_leaks_flamegraph.html'}")
    print(f"Leak table: {run_dir / 'memray_leaks_table.html'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
