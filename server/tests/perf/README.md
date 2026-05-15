# Performance Testing for Orbit Inference Server

This directory contains comprehensive performance testing tools for the Orbit Inference Server, designed to test the system under various load conditions and identify performance bottlenecks.

## 🚀 Overview

The performance testing suite includes:

- **Locust-based load testing** - Web-based and command-line load testing
- **Advanced Python performance tests** - Custom scenarios and detailed metrics
- **Multiple test scenarios** - Health checks, chat endpoints, admin operations, and more
- **Comprehensive reporting** - CSV exports, HTML reports, and real-time metrics

## 📋 Prerequisites

### 1. Install Dependencies

First, ensure you have the development dependencies installed:

```bash
# From the project root
pip install -r install/requirements.txt --profile development
```

Or install Locust directly:

```bash
pip install locust
```

### 2. Server Setup

Ensure your Orbit Inference Server is running and accessible. The tests default to `http://localhost:3000`.

## 🧪 Test Scenarios

### Basic Load Testing (Locust)

The main Locust test file (`locustfile.py`) includes three user types:

1. **OrbitInferenceServerUser** - General user performing various operations
2. **HealthCheckUser** - Dedicated health monitoring user
3. **ChatUser** - Chat-focused user for testing chat endpoints

### Advanced Test Scenarios

The `advanced_performance_test.py` script provides these scenarios:

- **Health** - Focused health check testing
- **Chat** - Chat endpoint performance testing
- **Mixed** - Mixed endpoint testing (default)
- **Burst** - Burst load pattern testing
- **Ramp** - Gradually increasing load testing

## 🏃‍♂️ Running Tests

### Option 1: Locust Web Interface

Start Locust with the web interface:

```bash
cd server/tests/perf
locust -f locustfile.py --host=http://localhost:3000
```

Then open your browser to `http://localhost:8089` to configure and run tests.

### Option 2: Command Line Locust

Run Locust in headless mode:

```bash
cd server/tests/perf
locust -f locustfile.py --host=http://localhost:3000 --users 20 --spawn-rate 5 --run-time 5m --headless
```

### Option 3: Shell Script Runner

Use the provided shell script for different scenarios:

```bash
cd server/tests/perf
chmod +x run_performance_tests.sh

# Basic test
./run_performance_tests.sh --scenario basic --users 10 --run-time 5m

# Stress test
./run_performance_tests.sh --scenario stress --users 50 --run-time 10m

# Health check focused
./run_performance_tests.sh --scenario health --users 20 --run-time 3m

# Chat endpoint focused
./run_performance_tests.sh --scenario chat --users 15 --run-time 5m

# Admin endpoints focused
./run_performance_tests.sh --scenario admin --users 10 --run-time 5m

# Endurance test
./run_performance_tests.sh --scenario endurance --users 25 --run-time 30m
```

### Option 4: Advanced Python Script

Use the advanced performance test script for custom scenarios:

```bash
cd server/tests/perf

# Mixed load test
python advanced_performance_test.py --scenario mixed --duration 120 --rps 20

# Burst load test
python advanced_performance_test.py --scenario burst --burst-size 100 --burst-count 10

# Ramp load test
python advanced_performance_test.py --scenario ramp --start-rps 1 --end-rps 50 --duration 60

# Chat endpoint test (requires API key)
python advanced_performance_test.py --scenario chat --duration 300 --rps 10 --api-key YOUR_API_KEY
```

### Option 5: Memray Leak Profiling

Use `memray_leak_test.py` when you want to profile allocations in the server
process while driving one of the existing advanced performance scenarios. This
is intentionally separate from the normal runners because memray adds profiling
overhead and writes larger binary/HTML artifacts.

```bash
cd server/tests/perf

# Profile the server during a lightweight mixed workload
python memray_leak_test.py --scenario mixed --duration 120 --rps 5

# Profile authenticated chat traffic
python memray_leak_test.py \
  --scenario chat \
  --duration 300 \
  --rps 2 \
  --api-key YOUR_API_KEY
```

The script starts `server/main.py` through memray, waits for `/health`, runs the
selected workload, gracefully stops the server, and writes reports under
`server/tests/perf/results/memray/`:

- `orbit_memray.bin` - raw memray capture
- `memray_summary.txt` and `memray_stats.txt` - terminal summaries
- `memray_peak_flamegraph.html` - peak allocation flamegraph
- `memray_leaks_flamegraph.html` and `memray_leaks_table.html` - allocations
  still live at process exit
- `server.log` and `workload_summary.txt` - run context

Stop any server already listening on the target `--base-url` before running the
script; otherwise the workload could hit the wrong process. If your config uses
a non-default port, pass the matching URL with `--base-url`.

If you see this message:

```text
http://127.0.0.1:3000/health is already reachable. Stop the existing server or choose a config/base URL with a free port before profiling.
```

it means something is already responding on port `3000`. The script stops at
that point because it profiles only the server process it starts itself; if it
continued, the workload might hit an existing unprofiled server and produce a
misleading memray report.

You can either stop the existing server:

```bash
# From the project root
./bin/orbit.sh stop

cd server/tests/perf
python memray_leak_test.py --scenario mixed --duration 120 --rps 5
```

or run the profiled server on a different port. The `--base-url` value must
match the port in the config file passed with `--config`:

```bash
cd server/tests/perf
python memray_leak_test.py \
  --config ../../../config/config-memray.yaml \
  --base-url http://127.0.0.1:3001 \
  --scenario mixed \
  --duration 120 \
  --rps 5
```

To see what is using port `3000`:

```bash
lsof -i :3000
```

For focused leak hunts in `server/inference`, keep `performance.workers: 1` in
the active server config. Memray reports are per process; multiple uvicorn
workers split allocations across processes and make attribution harder. If you
prefer a manual command, use the configured app factory rather than the bare
global app:

```bash
cd server
OIS_CONFIG_PATH=../config/config.yaml \
  python -m memray run --native -o output.bin \
  -m uvicorn main:create_app --factory --host 0.0.0.0 --port 3000
```

Then drive traffic from another shell with Locust or
`advanced_performance_test.py`, stop the server, and generate leak views:

```bash
python -m memray flamegraph --leaks output.bin
python -m memray table --leaks output.bin
python -m memray summary output.bin
```

## 📊 Understanding Results

### Locust Results

Locust provides real-time metrics including:
- **Response Time** - Min, max, mean, and percentiles
- **Requests per Second** - Current and average throughput
- **Failure Rate** - Percentage of failed requests
- **User Count** - Active and total users

### Advanced Script Results

The advanced script generates:
- **CSV Reports** - Detailed request-by-request data
- **HTML Reports** - Visual performance summaries
- **Console Output** - Real-time test progress and final summary

### Key Metrics to Monitor

1. **Response Time Percentiles**
   - P95: 95% of requests complete within this time
   - P99: 99% of requests complete within this time

2. **Throughput**
   - Requests per second (RPS)
   - Total requests processed

3. **Error Rates**
   - Success rate percentage
   - Common error types and frequencies

4. **Resource Utilization**
   - CPU and memory usage during tests
   - Database connection pool status

## 🔧 Configuration

### Locust Configuration

Edit `locust.conf` to customize default settings:

```ini
# Basic configuration
host = http://localhost:3000
users = 10
spawn-rate = 2
run-time = 5m

# Output settings
csv = locust_results
html = locust_report.html
```

### Test Parameters

Adjust test parameters based on your server capacity:

- **Users**: Start with 10-20, increase gradually
- **Spawn Rate**: How quickly to add users (2-5 users/second recommended)
- **Run Time**: 5-10 minutes for basic tests, 30+ minutes for endurance tests
- **RPS**: Start with 10-20, increase based on server performance

## 🚨 Best Practices

### 1. Start Small
- Begin with low user counts and RPS
- Gradually increase load to find breaking points
- Monitor server resources during tests

### 2. Test Realistic Scenarios
- Test the endpoints your application actually uses
- Include authentication if required
- Test with realistic data sizes

### 3. Monitor Server Health
- Watch CPU, memory, and disk usage
- Monitor database connection pools
- Check for memory leaks or resource exhaustion

### 4. Baseline Testing
- Run tests before and after changes
- Document performance baselines
- Track performance regression over time

## 🐛 Troubleshooting

### Common Issues

1. **Connection Refused**
   - Ensure server is running
   - Check host and port configuration
   - Verify firewall settings

2. **Authentication Errors**
   - Provide valid API key for protected endpoints
   - Check API key permissions
   - Verify authentication configuration

3. **High Failure Rates**
   - Reduce load (users/RPS)
   - Check server logs for errors
   - Monitor server resource usage

4. **Slow Response Times**
   - Check database performance
   - Monitor external service dependencies
   - Review server configuration

### Debug Mode

Enable logging in Locust:

```bash
locust -f locustfile.py --host=http://localhost:3000 --loglevel=DEBUG
```

## 📈 Performance Optimization

### Server-Side Optimizations

1. **Database Tuning**
   - Optimize database queries
   - Use connection pooling
   - Implement caching strategies

2. **Async Processing**
   - Use async/await for I/O operations
   - Implement background task queues
   - Optimize thread pool configurations

3. **Resource Management**
   - Monitor memory usage
   - Optimize garbage collection
   - Use efficient data structures

### Client-Side Optimizations

1. **Request Batching**
   - Group related requests
   - Use bulk operations where possible
   - Implement request deduplication

2. **Connection Reuse**
   - Use persistent connections
   - Implement connection pooling
   - Minimize connection overhead

## 🔄 Continuous Performance Testing

### Integration with CI/CD

Add performance tests to your CI/CD pipeline:

```yaml
# Example GitHub Actions workflow
- name: Run Performance Tests
  run: |
    cd server/tests/perf
    python advanced_performance_test.py --scenario mixed --duration 300 --rps 20
```

### Automated Monitoring

Set up automated performance monitoring:

```bash
# Daily performance check
0 2 * * * cd /path/to/orbit/server/tests/perf && ./run_performance_tests.sh --scenario health --users 5 --run-time 10m
```

## 📚 Additional Resources

- [Locust Documentation](https://docs.locust.io/)
- [FastAPI Performance Best Practices](https://fastapi.tiangolo.com/tutorial/performance/)
- [Python Async Performance](https://docs.python.org/3/library/asyncio.html)

## 🤝 Contributing

To add new test scenarios or improve existing tests:

1. Follow the existing code structure
2. Add comprehensive error handling
3. Include detailed documentation
4. Test with various server configurations
5. Update this README with new features

## 📄 License

This performance testing suite is part of the Orbit project and follows the same license terms.
