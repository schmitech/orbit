#!/usr/bin/env python
"""
Rate Limiting & Throttling Simulation Script

Simulates API traffic to test rate limiting and throttling behavior with a running ORBIT server.
Supports multiple test modes: burst, sustained, random, and throttle-specific patterns.

Usage:
    python rate_limit_simulation.py [options]

Examples:
    # Burst test - rapid requests to trigger rate limit quickly
    python rate_limit_simulation.py --mode burst --requests 100

    # Sustained test - steady request rate over time
    python rate_limit_simulation.py --mode sustained --duration 120 --rps 2

    # Random test - random delays between requests
    python rate_limit_simulation.py --mode random --requests 50

    # Test with API key (higher limits)
    python rate_limit_simulation.py --mode burst --api-key default-key

    # Throttle test - observe progressive delays as quota increases
    python rate_limit_simulation.py --mode throttle --api-key default-key --requests 200

    # Quota exhaustion test - run until quota is exhausted
    python rate_limit_simulation.py --mode exhaust --api-key default-key

    # Custom endpoint
    python rate_limit_simulation.py --url http://localhost:3000/health --mode burst
"""

import argparse
import json
import random
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)


@dataclass
class RequestResult:
    """Result of a single request."""
    timestamp: float
    status_code: int
    # Rate limit headers
    rate_limit: Optional[int] = None
    rate_remaining: Optional[int] = None
    rate_reset: Optional[int] = None
    retry_after: Optional[int] = None
    # Throttle/quota headers
    throttle_delay_ms: Optional[int] = None
    quota_daily_remaining: Optional[int] = None
    quota_monthly_remaining: Optional[int] = None
    quota_daily_reset: Optional[int] = None
    quota_monthly_reset: Optional[int] = None
    quota_exceeded: Optional[str] = None  # 'daily' or 'monthly' if exceeded
    # Timing
    response_time_ms: float = 0
    error: Optional[str] = None


@dataclass
class SimulationStats:
    """Aggregated statistics for the simulation."""
    total_requests: int = 0
    successful_requests: int = 0
    rate_limited_requests: int = 0
    quota_exceeded_requests: int = 0
    throttled_requests: int = 0  # Requests with delay > 0
    failed_requests: int = 0
    total_response_time_ms: float = 0
    total_throttle_delay_ms: float = 0
    max_throttle_delay_ms: int = 0
    results: List[RequestResult] = field(default_factory=list)

    @property
    def avg_response_time_ms(self) -> float:
        return self.total_response_time_ms / max(1, self.total_requests)

    @property
    def avg_throttle_delay_ms(self) -> float:
        return self.total_throttle_delay_ms / max(1, self.throttled_requests) if self.throttled_requests else 0

    @property
    def rate_limit_percentage(self) -> float:
        return (self.rate_limited_requests / max(1, self.total_requests)) * 100

    @property
    def throttle_percentage(self) -> float:
        return (self.throttled_requests / max(1, self.total_requests)) * 100

    @property
    def quota_exceeded_percentage(self) -> float:
        return (self.quota_exceeded_requests / max(1, self.total_requests)) * 100


class RateLimitSimulator:
    """Simulates API traffic to test rate limiting."""

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        api_key: Optional[str] = None,
        verbose: bool = True
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.verbose = verbose
        self.stats = SimulationStats()
        self.session_id = str(uuid.uuid4())

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
            "X-Session-ID": self.session_id,
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _make_request(self, endpoint: str = "/v1/chat", method: str = "POST") -> RequestResult:
        """Make a single request and capture rate limit headers."""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        # Simple payload for chat endpoint
        payload = {
            "messages": [{"role": "user", "content": "test"}],
            "stream": False
        }

        start_time = time.time()
        result = RequestResult(timestamp=start_time, status_code=0)

        try:
            if method.upper() == "POST":
                response = requests.post(url, json=payload, headers=headers, timeout=30)
            else:
                response = requests.get(url, headers=headers, timeout=30)

            end_time = time.time()
            result.response_time_ms = (end_time - start_time) * 1000
            result.status_code = response.status_code

            # Extract rate limit headers
            result.rate_limit = self._safe_int(response.headers.get("X-RateLimit-Limit"))
            result.rate_remaining = self._safe_int(response.headers.get("X-RateLimit-Remaining"))
            result.rate_reset = self._safe_int(response.headers.get("X-RateLimit-Reset"))
            result.retry_after = self._safe_int(response.headers.get("Retry-After"))

            # Extract throttle/quota headers
            result.throttle_delay_ms = self._safe_int(response.headers.get("X-Throttle-Delay"))
            result.quota_daily_remaining = self._safe_int(response.headers.get("X-Quota-Daily-Remaining"))
            result.quota_monthly_remaining = self._safe_int(response.headers.get("X-Quota-Monthly-Remaining"))
            result.quota_daily_reset = self._safe_int(response.headers.get("X-Quota-Daily-Reset"))
            result.quota_monthly_reset = self._safe_int(response.headers.get("X-Quota-Monthly-Reset"))

            # Check for quota exceeded in response body
            if response.status_code == 429:
                try:
                    body = response.json()
                    result.quota_exceeded = body.get("quota_exceeded")
                except Exception:
                    pass

        except requests.exceptions.Timeout:
            result.error = "Request timeout"
            result.status_code = 0
        except requests.exceptions.ConnectionError as e:
            result.error = f"Connection error: {e}"
            result.status_code = 0
        except Exception as e:
            result.error = f"Error: {e}"
            result.status_code = 0

        return result

    def _safe_int(self, value: Optional[str]) -> Optional[int]:
        """Safely convert string to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _log(self, message: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] {message}")

    def _log_result(self, result: RequestResult, request_num: int, show_throttle: bool = False) -> None:
        """Log a single request result."""
        if not self.verbose:
            return

        status_icon = {
            200: "\033[92m✓\033[0m",  # Green check
            429: "\033[93m⚠\033[0m",  # Yellow warning
        }.get(result.status_code, "\033[91m✗\033[0m")  # Red X for errors

        # Rate limit info
        rate_info = ""
        if result.rate_remaining is not None:
            rate_info = f" | Remaining: {result.rate_remaining}/{result.rate_limit}"
        if result.retry_after:
            rate_info += f" | Retry-After: {result.retry_after}s"

        # Throttle info
        throttle_info = ""
        if show_throttle or result.throttle_delay_ms:
            if result.throttle_delay_ms is not None:
                delay_color = "\033[92m" if result.throttle_delay_ms == 0 else (
                    "\033[93m" if result.throttle_delay_ms < 1000 else "\033[91m"
                )
                throttle_info = f" | Delay: {delay_color}{result.throttle_delay_ms}ms\033[0m"
            if result.quota_daily_remaining is not None:
                throttle_info += f" | Daily: {result.quota_daily_remaining}"
            if result.quota_monthly_remaining is not None:
                throttle_info += f" | Monthly: {result.quota_monthly_remaining}"
            if result.quota_exceeded:
                throttle_info += f" | \033[91mQUOTA EXCEEDED ({result.quota_exceeded})\033[0m"

        self._log(
            f"{status_icon} Request #{request_num:3d} | "
            f"Status: {result.status_code} | "
            f"Time: {result.response_time_ms:6.1f}ms{rate_info}{throttle_info}"
        )

    def _update_stats(self, result: RequestResult) -> None:
        """Update simulation statistics."""
        self.stats.total_requests += 1
        self.stats.total_response_time_ms += result.response_time_ms
        self.stats.results.append(result)

        if result.status_code == 200:
            self.stats.successful_requests += 1
        elif result.status_code == 429:
            if result.quota_exceeded:
                self.stats.quota_exceeded_requests += 1
            else:
                self.stats.rate_limited_requests += 1
        else:
            self.stats.failed_requests += 1

        # Track throttle stats
        if result.throttle_delay_ms is not None and result.throttle_delay_ms > 0:
            self.stats.throttled_requests += 1
            self.stats.total_throttle_delay_ms += result.throttle_delay_ms
            if result.throttle_delay_ms > self.stats.max_throttle_delay_ms:
                self.stats.max_throttle_delay_ms = result.throttle_delay_ms

    def run_burst_test(
        self,
        num_requests: int = 100,
        endpoint: str = "/v1/chat",
        method: str = "POST"
    ) -> SimulationStats:
        """
        Burst test: Send requests as fast as possible to trigger rate limiting.

        Args:
            num_requests: Number of requests to send
            endpoint: API endpoint to test
            method: HTTP method (GET or POST)
        """
        self._log(f"Starting BURST test: {num_requests} requests to {endpoint}")
        self._log(f"API Key: {'Yes' if self.api_key else 'No'}")
        self._log("-" * 60)

        for i in range(num_requests):
            result = self._make_request(endpoint, method)
            self._update_stats(result)
            self._log_result(result, i + 1)

            # Stop if we hit too many errors (not rate limits)
            if self.stats.failed_requests > 10:
                self._log("Too many failures, stopping test")
                break

        return self.stats

    def run_sustained_test(
        self,
        duration_seconds: int = 60,
        requests_per_second: float = 1.0,
        endpoint: str = "/v1/chat",
        method: str = "POST"
    ) -> SimulationStats:
        """
        Sustained test: Send requests at a steady rate over time.

        Args:
            duration_seconds: How long to run the test
            requests_per_second: Target request rate
            endpoint: API endpoint to test
            method: HTTP method (GET or POST)
        """
        delay = 1.0 / requests_per_second
        self._log(f"Starting SUSTAINED test: {requests_per_second} RPS for {duration_seconds}s")
        self._log(f"API Key: {'Yes' if self.api_key else 'No'}")
        self._log("-" * 60)

        start_time = time.time()
        request_num = 0

        while (time.time() - start_time) < duration_seconds:
            request_num += 1
            result = self._make_request(endpoint, method)
            self._update_stats(result)
            self._log_result(result, request_num)

            # Sleep to maintain target RPS
            elapsed = time.time() - start_time
            expected_requests = elapsed * requests_per_second
            if request_num > expected_requests:
                sleep_time = (request_num - expected_requests) / requests_per_second
                time.sleep(sleep_time)

        return self.stats

    def run_random_test(
        self,
        num_requests: int = 50,
        min_delay_ms: int = 0,
        max_delay_ms: int = 500,
        endpoint: str = "/v1/chat",
        method: str = "POST"
    ) -> SimulationStats:
        """
        Random test: Send requests with random delays between them.

        Args:
            num_requests: Number of requests to send
            min_delay_ms: Minimum delay between requests in milliseconds
            max_delay_ms: Maximum delay between requests in milliseconds
            endpoint: API endpoint to test
            method: HTTP method (GET or POST)
        """
        self._log(f"Starting RANDOM test: {num_requests} requests with {min_delay_ms}-{max_delay_ms}ms delays")
        self._log(f"API Key: {'Yes' if self.api_key else 'No'}")
        self._log("-" * 60)

        for i in range(num_requests):
            result = self._make_request(endpoint, method)
            self._update_stats(result)
            self._log_result(result, i + 1)

            # Random delay before next request
            if i < num_requests - 1:
                delay_ms = random.randint(min_delay_ms, max_delay_ms)
                time.sleep(delay_ms / 1000.0)

        return self.stats

    def run_throttle_test(
        self,
        num_requests: int = 200,
        endpoint: str = "/v1/chat",
        method: str = "POST"
    ) -> SimulationStats:
        """
        Throttle test: Send requests to observe progressive throttle delays.

        Requires an API key to trigger throttle middleware.
        Shows how delays increase as quota usage grows.

        Args:
            num_requests: Number of requests to send
            endpoint: API endpoint to test
            method: HTTP method (GET or POST)
        """
        if not self.api_key:
            self._log("\033[93mWARNING: Throttle test requires --api-key to observe throttling behavior\033[0m")

        self._log(f"Starting THROTTLE test: {num_requests} requests to observe progressive delays")
        self._log(f"API Key: {'Yes' if self.api_key else 'No'}")
        self._log("-" * 60)

        for i in range(num_requests):
            result = self._make_request(endpoint, method)
            self._update_stats(result)
            self._log_result(result, i + 1, show_throttle=True)

            # Stop if quota exceeded
            if result.quota_exceeded:
                self._log(f"\n\033[91mQuota exceeded ({result.quota_exceeded}), stopping test\033[0m")
                break

            # Stop if too many failures
            if self.stats.failed_requests > 10:
                self._log("Too many failures, stopping test")
                break

        return self.stats

    def run_exhaust_test(
        self,
        endpoint: str = "/v1/chat",
        method: str = "POST",
        max_requests: int = 50000
    ) -> SimulationStats:
        """
        Quota exhaustion test: Send requests until quota is exhausted.

        Requires an API key. Will continue until daily or monthly quota
        is exceeded (429 with quota_exceeded in response).

        Args:
            endpoint: API endpoint to test
            method: HTTP method (GET or POST)
            max_requests: Safety limit to prevent infinite loops
        """
        if not self.api_key:
            self._log("\033[91mERROR: Exhaust test requires --api-key\033[0m")
            return self.stats

        self._log(f"Starting EXHAUST test: Run until quota is exhausted (max {max_requests} requests)")
        self._log(f"API Key: Yes ({self.api_key[:8]}...)")
        self._log("-" * 60)

        request_num = 0
        quota_exhausted = False

        while not quota_exhausted and request_num < max_requests:
            request_num += 1
            result = self._make_request(endpoint, method)
            self._update_stats(result)

            # Log every 10th request or when throttling/quota exceeded
            if request_num % 10 == 0 or result.throttle_delay_ms or result.quota_exceeded:
                self._log_result(result, request_num, show_throttle=True)

            # Check for quota exceeded
            if result.quota_exceeded:
                quota_exhausted = True
                self._log(f"\n\033[91mQuota exhausted ({result.quota_exceeded}) at request #{request_num}\033[0m")
                break

            # Stop if too many non-quota failures
            if self.stats.failed_requests > 10:
                self._log("Too many failures, stopping test")
                break

        if not quota_exhausted:
            self._log(f"\nReached max requests ({max_requests}) without exhausting quota")

        return self.stats

    def print_summary(self) -> None:
        """Print summary statistics."""
        print("\n" + "=" * 60)
        print("SIMULATION SUMMARY")
        print("=" * 60)
        print(f"Total Requests:      {self.stats.total_requests}")
        print(f"Successful (200):    {self.stats.successful_requests}")
        print(f"Rate Limited (429):  {self.stats.rate_limited_requests} ({self.stats.rate_limit_percentage:.1f}%)")
        print(f"Quota Exceeded:      {self.stats.quota_exceeded_requests} ({self.stats.quota_exceeded_percentage:.1f}%)")
        print(f"Failed (other):      {self.stats.failed_requests}")
        print(f"Avg Response Time:   {self.stats.avg_response_time_ms:.1f}ms")

        # Throttle statistics
        if self.stats.throttled_requests > 0:
            print("\n" + "-" * 40)
            print("THROTTLE STATISTICS")
            print("-" * 40)
            print(f"Throttled Requests:  {self.stats.throttled_requests} ({self.stats.throttle_percentage:.1f}%)")
            print(f"Avg Throttle Delay:  {self.stats.avg_throttle_delay_ms:.1f}ms")
            print(f"Max Throttle Delay:  {self.stats.max_throttle_delay_ms}ms")

            # Find when throttling started
            for i, result in enumerate(self.stats.results):
                if result.throttle_delay_ms and result.throttle_delay_ms > 0:
                    print(f"Throttling started:  Request #{i + 1}")
                    break

        # Show when rate limiting kicked in
        for i, result in enumerate(self.stats.results):
            if result.status_code == 429:
                if result.quota_exceeded:
                    print(f"\nQuota exceeded ({result.quota_exceeded}) at request #{i + 1}")
                else:
                    print(f"\nRate limiting triggered at request #{i + 1}")
                break
        else:
            if self.stats.rate_limited_requests == 0 and self.stats.quota_exceeded_requests == 0:
                print("\nNo rate limiting or quota exceeded during this test")

        # Show final quota status if available
        if self.stats.results:
            last_result = self.stats.results[-1]
            if last_result.quota_daily_remaining is not None or last_result.quota_monthly_remaining is not None:
                print("\n" + "-" * 40)
                print("FINAL QUOTA STATUS")
                print("-" * 40)
                if last_result.quota_daily_remaining is not None:
                    print(f"Daily Remaining:     {last_result.quota_daily_remaining}")
                if last_result.quota_monthly_remaining is not None:
                    print(f"Monthly Remaining:   {last_result.quota_monthly_remaining}")

        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Rate Limiting & Throttling Simulation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Burst test to quickly trigger rate limits
  python rate_limit_simulation.py --mode burst --requests 100

  # Sustained load at 2 requests/second for 2 minutes
  python rate_limit_simulation.py --mode sustained --duration 120 --rps 2

  # Random delays between requests
  python rate_limit_simulation.py --mode random --requests 50

  # Test with API key (gets higher rate limits)
  python rate_limit_simulation.py --mode burst --api-key default-key

  # Throttle test - observe progressive delays as quota increases
  python rate_limit_simulation.py --mode throttle --api-key default-key --requests 200

  # Quota exhaustion test - run until quota is exceeded
  python rate_limit_simulation.py --mode exhaust --api-key default-key

  # Test health endpoint (GET request, usually excluded from rate limiting)
  python rate_limit_simulation.py --endpoint /health --method GET --mode burst
        """
    )

    parser.add_argument(
        "--url",
        default="http://localhost:3000",
        help="Base URL of the ORBIT server (default: http://localhost:3000)"
    )
    parser.add_argument(
        "--endpoint",
        default="/v1/chat",
        help="API endpoint to test (default: /v1/chat)"
    )
    parser.add_argument(
        "--method",
        choices=["GET", "POST"],
        default="POST",
        help="HTTP method (default: POST)"
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (uses higher rate limits)"
    )
    parser.add_argument(
        "--mode",
        choices=["burst", "sustained", "random", "throttle", "exhaust"],
        default="burst",
        help="Test mode: burst, sustained, random, throttle, or exhaust (default: burst)"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Number of requests for burst/random/throttle mode (default: 100)"
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=50000,
        help="Maximum requests for exhaust mode safety limit (default: 50000)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration in seconds for sustained mode (default: 60)"
    )
    parser.add_argument(
        "--rps",
        type=float,
        default=2.0,
        help="Requests per second for sustained mode (default: 2.0)"
    )
    parser.add_argument(
        "--min-delay",
        type=int,
        default=0,
        help="Min delay in ms for random mode (default: 0)"
    )
    parser.add_argument(
        "--max-delay",
        type=int,
        default=500,
        help="Max delay in ms for random mode (default: 500)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-request output, show only summary"
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("ORBIT Rate Limiting & Throttling Simulation")
    print("=" * 60)
    print(f"Server:    {args.url}")
    print(f"Endpoint:  {args.endpoint}")
    print(f"Method:    {args.method}")
    print(f"API Key:   {'Yes (' + args.api_key[:8] + '...)' if args.api_key else 'No'}")
    print(f"Mode:      {args.mode.upper()}")
    print("=" * 60 + "\n")

    # Create simulator
    simulator = RateLimitSimulator(
        base_url=args.url,
        api_key=args.api_key,
        verbose=not args.quiet
    )

    # Run appropriate test mode
    try:
        if args.mode == "burst":
            simulator.run_burst_test(
                num_requests=args.requests,
                endpoint=args.endpoint,
                method=args.method
            )
        elif args.mode == "sustained":
            simulator.run_sustained_test(
                duration_seconds=args.duration,
                requests_per_second=args.rps,
                endpoint=args.endpoint,
                method=args.method
            )
        elif args.mode == "random":
            simulator.run_random_test(
                num_requests=args.requests,
                min_delay_ms=args.min_delay,
                max_delay_ms=args.max_delay,
                endpoint=args.endpoint,
                method=args.method
            )
        elif args.mode == "throttle":
            simulator.run_throttle_test(
                num_requests=args.requests,
                endpoint=args.endpoint,
                method=args.method
            )
        elif args.mode == "exhaust":
            simulator.run_exhaust_test(
                endpoint=args.endpoint,
                method=args.method,
                max_requests=args.max_requests
            )
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")

    # Print summary
    simulator.print_summary()


if __name__ == "__main__":
    main()
