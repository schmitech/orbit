#!/bin/bash

# Performance Test Runner for Orbit Inference Server
# This script runs different performance test scenarios

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
HOST="http://localhost:3000"
USERS=10
SPAWN_RATE=2
RUN_TIME="5m"
OUTPUT_DIR="results"
SCENARIO="basic"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --host HOST          Server host (default: http://localhost:3000)"
    echo "  -u, --users USERS        Number of users (default: 10)"
    echo "  -s, --spawn-rate RATE    User spawn rate (default: 2)"
    echo "  -t, --run-time TIME      Test run time (default: 5m)"
    echo "  -o, --output DIR         Output directory (default: results)"
    echo "  -S, --scenario SCENARIO  Test scenario (default: basic)"
    echo "  --help                   Show this help message"
    echo ""
    echo "Available scenarios:"
    echo "  basic      - Basic performance test (default)"
    echo "  health     - Health check focused test"
    echo "  chat       - Chat endpoint focused test"
    echo "  admin      - Admin endpoints focused test"
    echo "  stress     - High load stress test"
    echo "  endurance  - Long duration endurance test"
    echo ""
    echo "Examples:"
    echo "  $0 --scenario stress --users 50 --run-time 10m"
    echo "  $0 -h http://192.168.1.100:3000 -u 20 -t 15m"
}

# Function to check if server is running
check_server() {
    print_status "Checking if server is running at $HOST..."
    
    if curl -s --max-time 10 "$HOST/health" > /dev/null; then
        print_success "Server is running and responding"
    else
        print_error "Server is not responding at $HOST"
        print_error "Please ensure the Orbit Inference Server is running"
        exit 1
    fi
}

# Function to create output directory
create_output_dir() {
    if [ ! -d "$OUTPUT_DIR" ]; then
        mkdir -p "$OUTPUT_DIR"
        print_status "Created output directory: $OUTPUT_DIR"
    fi
    
    # Create timestamped subdirectory
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    SCENARIO_DIR="$OUTPUT_DIR/${SCENARIO}_${TIMESTAMP}"
    mkdir -p "$SCENARIO_DIR"
    print_status "Created scenario directory: $SCENARIO_DIR"
}

# Function to run basic performance test
run_basic_test() {
    print_status "Running basic performance test..."
    
    locust \
        --locustfile=locustfile.py \
        --host="$HOST" \
        --users="$USERS" \
        --spawn-rate="$SPAWN_RATE" \
        --run-time="$RUN_TIME" \
        --headless \
        --csv="$SCENARIO_DIR/locust_basic" \
        --html="$SCENARIO_DIR/locust_basic.html" \
        --loglevel=INFO \
        --logfile="$SCENARIO_DIR/locust_basic.log"
}

# Function to run health-focused test
run_health_test() {
    print_status "Running health check focused test..."
    
    # Override user classes to focus on health checks
    export LOCUST_USER_CLASSES="HealthCheckUser"
    
    locust \
        --locustfile=locustfile.py \
        --host="$HOST" \
        --users="$USERS" \
        --spawn-rate="$SPAWN_RATE" \
        --run-time="$RUN_TIME" \
        --headless \
        --csv="$SCENARIO_DIR/locust_health" \
        --html="$SCENARIO_DIR/locust_health.html" \
        --loglevel=INFO \
        --logfile="$SCENARIO_DIR/locust_health.log"
}

# Function to run chat-focused test
run_chat_test() {
    print_status "Running chat endpoint focused test..."
    
    # Override user classes to focus on chat
    export LOCUST_USER_CLASSES="ChatUser"
    
    locust \
        --locustfile=locustfile.py \
        --host="$HOST" \
        --users="$USERS" \
        --spawn-rate="$SPAWN_RATE" \
        --run-time="$RUN_TIME" \
        --headless \
        --csv="$SCENARIO_DIR/locust_chat" \
        --html="$SCENARIO_DIR/locust_chat.html" \
        --loglevel=INFO \
        --logfile="$SCENARIO_DIR/locust_chat.log"
}

# Function to run admin-focused test
run_admin_test() {
    print_status "Running admin endpoints focused test..."
    
    # Use all user classes but focus on admin operations
    locust \
        --locustfile=locustfile.py \
        --host="$HOST" \
        --users="$USERS" \
        --spawn-rate="$SPAWN_RATE" \
        --run-time="$RUN_TIME" \
        --headless \
        --csv="$SCENARIO_DIR/locust_admin" \
        --html="$SCENARIO_DIR/locust_admin.html" \
        --loglevel=INFO \
        --logfile="$SCENARIO_DIR/locust_admin.log"
}

# Function to run stress test
run_stress_test() {
    print_status "Running high load stress test..."
    
    # Increase load for stress testing
    STRESS_USERS=$((USERS * 3))
    STRESS_SPAWN_RATE=$((SPAWN_RATE * 2))
    
    locust \
        --locustfile=locustfile.py \
        --host="$HOST" \
        --users="$STRESS_USERS" \
        --spawn-rate="$STRESS_SPAWN_RATE" \
        --run-time="$RUN_TIME" \
        --headless \
        --csv="$SCENARIO_DIR/locust_stress" \
        --html="$SCENARIO_DIR/locust_stress.html" \
        --loglevel=INFO \
        --logfile="$SCENARIO_DIR/locust_stress.log"
}

# Function to run endurance test
run_endurance_test() {
    print_status "Running long duration endurance test..."
    
    # Longer run time for endurance testing
    ENDURANCE_TIME="30m"
    
    locust \
        --locustfile=locustfile.py \
        --host="$HOST" \
        --users="$USERS" \
        --spawn-rate="$SPAWN_RATE" \
        --run-time="$ENDURANCE_TIME" \
        --headless \
        --csv="$SCENARIO_DIR/locust_endurance" \
        --html="$SCENARIO_DIR/locust_endurance.html" \
        --loglevel=INFO \
        --logfile="$SCENARIO_DIR/locust_endurance.log"
}

# Function to generate summary report
generate_summary() {
    print_status "Generating performance test summary..."
    
    SUMMARY_FILE="$SCENARIO_DIR/summary.txt"
    
    cat > "$SUMMARY_FILE" << EOF
Orbit Inference Server Performance Test Summary
===============================================

Test Configuration:
- Host: $HOST
- Users: $USERS
- Spawn Rate: $SPAWN_RATE
- Run Time: $RUN_TIME
- Scenario: $SCENARIO
- Timestamp: $(date)

Test Results:
- CSV Results: locust_*.csv
- HTML Report: locust_*.html
- Logs: locust_*.log

To view results:
- Open HTML reports in a web browser
- Analyze CSV files with Excel or similar tools
- Check logs for detailed information

EOF
    
    print_success "Summary generated: $SUMMARY_FILE"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--host)
            HOST="$2"
            shift 2
            ;;
        -u|--users)
            USERS="$2"
            shift 2
            ;;
        -s|--spawn-rate)
            SPAWN_RATE="$2"
            shift 2
            ;;
        -t|--run-time)
            RUN_TIME="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -S|--scenario)
            SCENARIO="$2"
            shift 2
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_status "Starting Orbit Inference Server Performance Tests"
    print_status "Host: $HOST"
    print_status "Users: $USERS"
    print_status "Spawn Rate: $SPAWN_RATE"
    print_status "Run Time: $RUN_TIME"
    print_status "Scenario: $SCENARIO"
    
    # Check if locust is installed
    if ! command -v locust &> /dev/null; then
        print_error "Locust is not installed. Please install it first:"
        print_error "pip install locust"
        exit 1
    fi
    
    # Check server status
    check_server
    
    # Create output directory
    create_output_dir
    
    # Run appropriate test based on scenario
    case $SCENARIO in
        basic)
            run_basic_test
            ;;
        health)
            run_health_test
            ;;
        chat)
            run_chat_test
            ;;
        admin)
            run_admin_test
            ;;
        stress)
            run_stress_test
            ;;
        endurance)
            run_endurance_test
            ;;
        *)
            print_error "Unknown scenario: $SCENARIO"
            show_usage
            exit 1
            ;;
    esac
    
    # Generate summary
    generate_summary
    
    print_success "Performance test completed successfully!"
    print_status "Results saved in: $SCENARIO_DIR"
}

# Run main function
main "$@"
