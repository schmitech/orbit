#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print usage
print_usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -h, --help           Show this help message"
    echo "  -t, --test-file      Specify a custom test file (default: test_cases.json)"
    echo "  -q, --query          Run a single query test"
    echo "  -v, --verbose        Show detailed output"
    echo "  -r, --run-all        Run all test cases (default behavior if no options provided)"
}

# Default values
TEST_FILE="test_cases.json"
VERBOSE=false
RUN_ALL=false
SINGLE_QUERY=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            print_usage
            exit 0
            ;;
        -t|--test-file)
            TEST_FILE="$2"
            shift 2
            ;;
        -q|--query)
            SINGLE_QUERY="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -r|--run-all)
            RUN_ALL=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# Check if we're in the correct directory
if [ ! -f "test_prompt_guardrails.py" ]; then
    echo -e "${RED}Error: Please run this script from the tests directory${NC}"
    exit 1
fi

# Run the tests
if [ ! -z "$SINGLE_QUERY" ]; then
    echo -e "${YELLOW}Running single query test...${NC}"
    python3 test_prompt_guardrails.py --single-query "$SINGLE_QUERY"
elif [ "$RUN_ALL" = true ] || [ $# -eq 0 ]; then
    echo -e "${YELLOW}Running all test cases from $TEST_FILE...${NC}"
    python3 test_prompt_guardrails.py --test-file "$TEST_FILE"
else
    print_usage
    exit 1
fi

# Check the exit status
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Tests completed successfully${NC}"
else
    echo -e "${RED}Tests failed${NC}"
    exit 1
fi 