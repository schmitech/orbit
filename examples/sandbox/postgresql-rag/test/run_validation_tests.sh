#!/bin/bash

# RAG System Validation Test Runner
# =================================

echo "🧪 RAG System Validation Test Suite"
echo "===================================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3."
    exit 1
fi

# Check if the validation script exists
if [[ ! -f "validate_rag_results.py" ]]; then
    echo "❌ validate_rag_results.py not found in current directory"
    exit 1
fi

# Function to run a test with error handling
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo ""
    echo "🔍 Running: $test_name"
    echo "Command: python3 $test_command"
    echo "----------------------------------------"
    
    # Get the directory where this script is located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # Get the parent directory (postgresql-rag)
    PARENT_DIR="$(dirname "$SCRIPT_DIR")"
    
    # Change to the parent directory and run with proper Python path
    cd "$PARENT_DIR"
    if PYTHONPATH="$PARENT_DIR" python3 "$SCRIPT_DIR/validate_rag_results.py" $test_command; then
        echo "✅ $test_name completed successfully"
    else
        echo "❌ $test_name failed"
        return 1
    fi
}

# Default behavior - show menu
if [[ $# -eq 0 ]]; then
    echo ""
    echo "Available test options:"
    echo "  basic     - Run basic validation tests (8 queries)"
    echo "  customer  - Test customer-related queries"
    echo "  orders    - Test order value and status queries" 
    echo "  location  - Test location-based queries"
    echo "  payment   - Test payment method queries"
    echo "  analytics - Test analytics and summary queries"
    echo "  sample10  - Test 10 random queries"
    echo "  sample25  - Test 25 random queries"
    echo "  full      - Run all test categories (comprehensive)"
    echo "  debug     - Run basic tests with debug output"
    echo ""
    echo "Usage: $0 [test_type]"
    echo "Example: $0 basic"
    exit 0
fi

# Parse command line argument
case "$1" in
    "basic")
        run_test "Basic Validation Tests" ""
        ;;
    "customer")
        run_test "Customer Query Tests" "--category customer"
        ;;
    "orders")
        run_test "Order Value Query Tests" "--category order_value"
        ;;
    "location")
        run_test "Location-Based Query Tests" "--category location"
        ;;
    "payment")  
        run_test "Payment Method Query Tests" "--category payment"
        ;;
    "analytics")
        run_test "Analytics Query Tests" "--category analytics"  
        ;;
    "sample10")
        run_test "Random Sample (10 queries)" "--sample 10"
        ;;
    "sample25")
        run_test "Random Sample (25 queries)" "--sample 25"
        ;;
    "full")
        run_test "Full Test Suite (All Categories)" "--full"
        ;;
    "debug")
        run_test "Basic Tests (Debug Mode)" "--debug"
        ;;
    "custom")
        if [[ -z "$2" ]]; then
            echo "❌ Please provide a query for custom test"
            echo "Usage: $0 custom \"Your query here\""
            exit 1
        fi
        run_test "Custom Query Test" "--custom \"$2\""
        ;;
    *)
        echo "❌ Unknown test type: $1"
        echo "Run '$0' without arguments to see available options"
        exit 1
        ;;
esac

echo ""
echo "🎯 Validation testing completed!"
echo ""
echo "💡 Tips for interpreting results:"
echo "   ✅ PASS = RAG results match SQL results (within tolerance)"
echo "   ❌ FAIL = Significant discrepancy between RAG and SQL"
echo "   Count differences within 10% are usually acceptable"
echo "   Focus on queries with large count mismatches"
echo ""
echo "📊 For detailed analysis, check the output above for:"
echo "   - Exact count differences (RAG vs SQL)"
echo "   - Template matching accuracy"
echo "   - Parameter extraction issues"
echo "   - Query execution errors"