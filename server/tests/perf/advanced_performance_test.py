#!/usr/bin/env python3
"""
Advanced Performance Test Script for Orbit Inference Server

This script provides more sophisticated performance testing capabilities including:
- Custom test scenarios
- Detailed metrics collection
- Performance regression testing
- Load pattern simulation
- Resource monitoring

Usage:
    python advanced_performance_test.py --scenario stress --users 100 --duration 10m
"""

import argparse
import asyncio
import aiohttp
import time
import json
import statistics
import csv
import os
from datetime import datetime, timedelta, UTC
from typing import Dict, List, Any, Optional
import concurrent.futures
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    """Data class for storing test results."""
    endpoint: str
    method: str
    status_code: int
    response_time: float
    timestamp: float
    success: bool
    error_message: Optional[str] = None
    rate_limited: bool = False
    rate_limit: Optional[int] = None
    rate_remaining: Optional[int] = None


class PerformanceMetrics:
    """Collects and analyzes performance metrics."""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.start_time = time.time()
        self.lock = threading.Lock()
    
    def add_result(self, result: TestResult):
        """Add a test result to the metrics."""
        with self.lock:
            self.results.append(result)
    
    def get_summary(self) -> Dict[str, Any]:
        """Generate a summary of all test results."""
        if not self.results:
            return {}

        successful_results = [r for r in self.results if r.success]
        failed_results = [r for r in self.results if not r.success]
        rate_limited_results = [r for r in self.results if r.rate_limited]

        if successful_results:
            response_times = [r.response_time for r in successful_results]
            summary = {
                "total_requests": len(self.results),
                "successful_requests": len(successful_results),
                "failed_requests": len(failed_results),
                "rate_limited_requests": len(rate_limited_results),
                "success_rate": len(successful_results) / len(self.results) * 100,
                "rate_limit_rate": len(rate_limited_results) / len(self.results) * 100,
                "response_time_stats": {
                    "min": min(response_times),
                    "max": max(response_times),
                    "mean": statistics.mean(response_times),
                    "median": statistics.median(response_times),
                    "p95": self._percentile(response_times, 95),
                    "p99": self._percentile(response_times, 99)
                },
                "requests_per_second": len(self.results) / (time.time() - self.start_time),
                "test_duration": time.time() - self.start_time
            }
        else:
            summary = {
                "total_requests": len(self.results),
                "successful_requests": 0,
                "failed_requests": len(failed_results),
                "rate_limited_requests": len(rate_limited_results),
                "success_rate": 0.0,
                "rate_limit_rate": len(rate_limited_results) / max(1, len(self.results)) * 100,
                "response_time_stats": {},
                "requests_per_second": 0.0,
                "test_duration": time.time() - self.start_time
            }

        return summary
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate the nth percentile of a dataset."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    def export_csv(self, filename: str):
        """Export results to CSV file."""
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = ['timestamp', 'endpoint', 'method', 'status_code', 'response_time',
                         'success', 'rate_limited', 'rate_limit', 'rate_remaining', 'error_message']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for result in self.results:
                writer.writerow({
                    'timestamp': datetime.fromtimestamp(result.timestamp).isoformat(),
                    'endpoint': result.endpoint,
                    'method': result.method,
                    'status_code': result.status_code,
                    'response_time': result.response_time,
                    'success': result.success,
                    'rate_limited': result.rate_limited,
                    'rate_limit': result.rate_limit or '',
                    'rate_remaining': result.rate_remaining or '',
                    'error_message': result.error_message or ''
                })


class LoadGenerator:
    """Generates different types of load patterns."""

    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.metrics = PerformanceMetrics()
        self.session_id = f"perf_test_{int(time.time())}"
        self._request_counter = 0
    
    async def __aenter__(self):
        """Async context manager entry."""
        timeout = aiohttp.ClientTimeout(total=60)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def make_request(self, method: str, endpoint: str, **kwargs) -> TestResult:
        """Make a single HTTP request and record metrics."""
        if not self.session:
            raise RuntimeError("Session not initialized")

        self._request_counter += 1
        url = f"{self.base_url}{endpoint}"
        headers = kwargs.pop('headers', {}).copy()

        # Add API key if configured
        if self.api_key:
            headers['X-API-Key'] = self.api_key

        # Add session ID for endpoints that require it
        if 'X-Session-ID' not in headers:
            headers['X-Session-ID'] = f"{self.session_id}_{self._request_counter}"

        kwargs['headers'] = headers
        start_time = time.time()

        try:
            async with self.session.request(method, url, **kwargs) as response:
                response_time = time.time() - start_time

                # Check for rate limiting
                is_rate_limited = response.status == 429
                rate_limit = self._safe_int(response.headers.get('X-RateLimit-Limit'))
                rate_remaining = self._safe_int(response.headers.get('X-RateLimit-Remaining'))

                result = TestResult(
                    endpoint=endpoint,
                    method=method,
                    status_code=response.status,
                    response_time=response_time,
                    timestamp=start_time,
                    success=200 <= response.status < 400,
                    rate_limited=is_rate_limited,
                    rate_limit=rate_limit,
                    rate_remaining=rate_remaining
                )

                if not result.success:
                    try:
                        error_data = await response.json()
                        result.error_message = str(error_data)
                    except:
                        result.error_message = f"HTTP {response.status}"

                self.metrics.add_result(result)
                return result

        except Exception as e:
            response_time = time.time() - start_time
            result = TestResult(
                endpoint=endpoint,
                method=method,
                status_code=0,
                response_time=response_time,
                timestamp=start_time,
                success=False,
                error_message=str(e)
            )
            self.metrics.add_result(result)
            return result

    def _safe_int(self, value: Optional[str]) -> Optional[int]:
        """Safely convert string to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    async def health_check_load(self, duration: int, requests_per_second: int):
        """Generate health check load."""
        print(f"Generating health check load: {requests_per_second} req/s for {duration}s")
        
        interval = 1.0 / requests_per_second
        end_time = time.time() + duration
        
        while time.time() < end_time:
            start_batch = time.time()
            
            # Create batch of requests
            tasks = []
            for _ in range(requests_per_second):
                task = self.make_request('GET', '/health')
                tasks.append(task)
            
            # Execute batch
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for next batch
            elapsed = time.time() - start_batch
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
    
    async def chat_load(self, duration: int, requests_per_second: int):
        """Generate chat endpoint load."""
        if not self.api_key:
            print("Warning: No API key provided, skipping chat load test")
            return

        print(f"Generating chat load: {requests_per_second} req/s for {duration}s")

        end_time = time.time() + duration

        while time.time() < end_time:
            start_batch = time.time()

            # Create batch of chat requests
            tasks = []
            for i in range(requests_per_second):
                # REST API format for /v1/chat endpoint
                chat_data = {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Performance test message {i}: Hello, this is a test."
                        }
                    ],
                    "stream": False
                }

                headers = {
                    "Content-Type": "application/json"
                }

                task = self.make_request('POST', '/v1/chat', json=chat_data, headers=headers)
                tasks.append(task)

            # Execute batch
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for next batch
            elapsed = time.time() - start_batch
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
    
    async def mixed_load(self, duration: int, requests_per_second: int):
        """Generate mixed load across different endpoints."""
        print(f"Generating mixed load: {requests_per_second} req/s for {duration}s")
        
        endpoints = [
            ('GET', '/health'),
            ('GET', '/health/ready'),
            ('GET', '/health/adapters'),
            ('GET', '/health/system')
        ]
        
        if self.api_key:
            endpoints.extend([
                ('GET', '/admin/api-keys'),
                ('GET', '/admin/prompts')
            ])
        
        interval = 1.0 / requests_per_second
        end_time = time.time() + duration
        
        while time.time() < end_time:
            start_batch = time.time()
            
            # Create batch of mixed requests
            tasks = []
            for _ in range(requests_per_second):
                method, endpoint = endpoints[_ % len(endpoints)]
                task = self.make_request(method, endpoint)
                tasks.append(task)
            
            # Execute batch
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for next batch
            elapsed = time.time() - start_batch
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
    
    async def burst_load(self, burst_size: int, burst_count: int, delay: float):
        """Generate burst load pattern."""
        print(f"Generating burst load: {burst_size} requests per burst, {burst_count} bursts")
        
        for burst in range(burst_count):
            print(f"Burst {burst + 1}/{burst_count}")
            
            # Create burst of requests
            tasks = []
            for i in range(burst_size):
                method, endpoint = ('GET', '/health') if i % 2 == 0 else ('GET', '/health/ready')
                task = self.make_request(method, endpoint)
                tasks.append(task)
            
            # Execute burst
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait between bursts
            if burst < burst_count - 1:
                await asyncio.sleep(delay)
    
    async def ramp_load(self, start_rps: int, end_rps: int, duration: int):
        """Generate gradually increasing load."""
        print(f"Generating ramp load: {start_rps} to {end_rps} req/s over {duration}s")
        
        end_time = time.time() + duration
        
        while time.time() < end_time:
            elapsed = time.time() - (end_time - duration)
            progress = elapsed / duration
            
            # Calculate current RPS
            current_rps = start_rps + (end_rps - start_rps) * progress
            
            # Generate load for this second
            tasks = []
            for _ in range(int(current_rps)):
                method, endpoint = ('GET', '/health') if _ % 2 == 0 else ('GET', '/health/ready')
                task = self.make_request(method, endpoint)
                tasks.append(task)
            
            # Execute requests
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Wait for next second
            await asyncio.sleep(1.0)


async def main():
    """Main function to run performance tests."""
    parser = argparse.ArgumentParser(description='Advanced Performance Test for Orbit Inference Server')
    parser.add_argument('--host', default='http://localhost:3000', help='Server host URL')
    parser.add_argument('--api-key', help='API key for authenticated endpoints')
    parser.add_argument('--scenario', choices=['health', 'chat', 'mixed', 'burst', 'ramp'], default='mixed',
                       help='Load test scenario')
    parser.add_argument('--duration', type=int, default=60, help='Test duration in seconds')
    parser.add_argument('--rps', type=int, default=10, help='Requests per second')
    parser.add_argument('--burst-size', type=int, default=50, help='Burst size for burst scenario')
    parser.add_argument('--burst-count', type=int, default=5, help='Number of bursts for burst scenario')
    parser.add_argument('--start-rps', type=int, default=1, help='Starting RPS for ramp scenario')
    parser.add_argument('--end-rps', type=int, default=50, help='Ending RPS for ramp scenario')
    parser.add_argument('--output', default='performance_results', help='Output directory')
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    # Generate timestamp for this test run
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    
    print(f"🚀 Starting advanced performance test")
    print(f"Target: {args.host}")
    print(f"Scenario: {args.scenario}")
    print(f"Duration: {args.duration}s")
    print(f"Target RPS: {args.rps}")
    
    async with LoadGenerator(args.host, args.api_key) as loader:
        start_time = time.time()
        
        # Run selected scenario
        if args.scenario == 'health':
            await loader.health_check_load(args.duration, args.rps)
        elif args.scenario == 'chat':
            await loader.chat_load(args.duration, args.rps)
        elif args.scenario == 'mixed':
            await loader.mixed_load(args.duration, args.rps)
        elif args.scenario == 'burst':
            await loader.burst_load(args.burst_size, args.burst_count, 2.0)
        elif args.scenario == 'ramp':
            await loader.ramp_load(args.start_rps, args.end_rps, args.duration)
        
        end_time = time.time()
        
        # Generate and display results
        summary = loader.metrics.get_summary()
        
        print("\n📊 Performance Test Results")
        print("=" * 50)
        print(f"Total Requests: {summary.get('total_requests', 0)}")
        print(f"Successful: {summary.get('successful_requests', 0)}")
        print(f"Rate Limited (429): {summary.get('rate_limited_requests', 0)}")
        print(f"Failed (other): {summary.get('failed_requests', 0)}")
        print(f"Success Rate: {summary.get('success_rate', 0):.2f}%")
        print(f"Rate Limit Rate: {summary.get('rate_limit_rate', 0):.2f}%")
        print(f"Requests/Second: {summary.get('requests_per_second', 0):.2f}")
        print(f"Test Duration: {summary.get('test_duration', 0):.2f}s")
        
        if 'response_time_stats' in summary and summary['response_time_stats']:
            stats = summary['response_time_stats']
            print(f"\nResponse Time Statistics:")
            print(f"  Min: {stats['min']:.3f}s")
            print(f"  Max: {stats['max']:.3f}s")
            print(f"  Mean: {stats['mean']:.3f}s")
            print(f"  Median: {stats['median']:.3f}s")
            print(f"  95th Percentile: {stats['p95']:.3f}s")
            print(f"  99th Percentile: {stats['p99']:.3f}s")
        
        # Export results
        csv_file = output_dir / f"performance_test_{args.scenario}_{timestamp}.csv"
        html_file = output_dir / f"performance_test_{args.scenario}_{timestamp}.html"
        
        loader.metrics.export_csv(str(csv_file))
        
        # Generate HTML report
        html_content = generate_html_report(summary, args, timestamp)
        with open(html_file, 'w') as f:
            f.write(html_content)
        
        print(f"\n📁 Results exported to:")
        print(f"  CSV: {csv_file}")
        print(f"  HTML: {html_file}")
        
        print(f"\n🏁 Performance test completed in {end_time - start_time:.2f}s")


def generate_html_report(summary: Dict[str, Any], args: argparse.Namespace, timestamp: str) -> str:
    """Generate an HTML report for the performance test."""
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Orbit Inference Server Performance Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        .metric {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #007bff; }}
        .metric h3 {{ margin-top: 0; color: #007bff; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-align: center; }}
        .stat-value {{ font-size: 2em; font-weight: bold; color: #007bff; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        .success {{ color: #28a745; }}
        .warning {{ color: #ffc107; }}
        .danger {{ color: #dc3545; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Orbit Inference Server Performance Test Report</h1>
        
        <div class="metric">
            <h3>Test Configuration</h3>
            <p><strong>Target Host:</strong> {args.host}</p>
            <p><strong>Test Scenario:</strong> {args.scenario}</p>
            <p><strong>Duration:</strong> {args.duration} seconds</p>
            <p><strong>Target RPS:</strong> {args.rps}</p>
            <p><strong>Timestamp:</strong> {timestamp}</p>
        </div>
        
        <div class="metric">
            <h3>Overall Results</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{summary.get('total_requests', 0)}</div>
                    <div class="stat-label">Total Requests</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value success">{summary.get('successful_requests', 0)}</div>
                    <div class="stat-label">Successful</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value warning">{summary.get('rate_limited_requests', 0)}</div>
                    <div class="stat-label">Rate Limited (429)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value danger">{summary.get('failed_requests', 0)}</div>
                    <div class="stat-label">Failed (other)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value {'success' if summary.get('success_rate', 0) >= 95 else 'warning' if summary.get('success_rate', 0) >= 80 else 'danger'}">{summary.get('success_rate', 0):.1f}%</div>
                    <div class="stat-label">Success Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value warning">{summary.get('rate_limit_rate', 0):.1f}%</div>
                    <div class="stat-label">Rate Limit Rate</div>
                </div>
            </div>
        </div>
        
        <div class="metric">
            <h3>Performance Metrics</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{summary.get('requests_per_second', 0):.2f}</div>
                    <div class="stat-label">Requests/Second</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{summary.get('test_duration', 0):.2f}s</div>
                    <div class="stat-label">Test Duration</div>
                </div>
            </div>
        </div>
    """
    
    if 'response_time_stats' in summary and summary['response_time_stats']:
        stats = summary['response_time_stats']
        html += f"""
        <div class="metric">
            <h3>Response Time Statistics</h3>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{stats['min']:.3f}s</div>
                    <div class="stat-label">Minimum</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['mean']:.3f}s</div>
                    <div class="stat-label">Mean</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['median']:.3f}s</div>
                    <div class="stat-label">Median</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['p95']:.3f}s</div>
                    <div class="stat-label">95th Percentile</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['p99']:.3f}s</div>
                    <div class="stat-label">99th Percentile</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['max']:.3f}s</div>
                    <div class="stat-label">Maximum</div>
                </div>
            </div>
        </div>
        """
    
    html += """
    </div>
</body>
</html>
    """
    
    return html


if __name__ == "__main__":
    asyncio.run(main())
