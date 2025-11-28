#!/bin/bash

# DuckDB Travel Expenses Query Test Script
# Tests various analytical queries against the DuckDB travel expenses database
#
# Usage: ./test_travel_expenses_queries.sh [database_file]
#   If database_file is not provided, defaults to travel_expenses.duckdb

set -e

# Default database file path
DEFAULT_DB="travel_expenses.duckdb"

# Get database file from argument or use default
DB_FILE="${1:-$DEFAULT_DB}"

# Check if database file exists
if [ ! -f "$DB_FILE" ]; then
    echo "Error: Database file '$DB_FILE' not found!"
    echo ""
    echo "Usage: $0 [database_file]"
    echo "  database_file: Path to DuckDB database file"
    echo "  If not provided, defaults to: $DEFAULT_DB"
    echo ""
    echo "To generate sample data, run:"
    echo "  cd utils/duckdb-intent-template/examples/open-gov-travel-expenses"
    echo "  python generate_travel_expenses_data.py --output travel_expenses.duckdb"
    exit 1
fi

# Check for venv and activate it if it exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"

if [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
    echo "Activated virtual environment: $VENV_PATH"
fi

# Check if duckdb CLI or Python module is available
DUCKDB_CMD=""
if command -v duckdb &> /dev/null; then
    DUCKDB_CMD="duckdb"
elif python -c "import duckdb" 2>/dev/null; then
    DUCKDB_CMD="python"
else
    echo "Error: duckdb command or Python module not found!"
    echo "Please install DuckDB:"
    echo "  pip install duckdb"
    echo ""
    echo "Or install DuckDB CLI from: https://duckdb.org/docs/installation/"
    echo ""
    echo "Note: If using venv, make sure it's activated or run:"
    echo "  source venv/bin/activate"
    exit 1
fi

echo "=========================================="
echo "DuckDB Travel Expenses Query Test"
echo "=========================================="
echo "Database: $DB_FILE"
echo "Date: $(date)"
echo "=========================================="
echo ""

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run a query and display results
run_query() {
    local query_name="$1"
    local query="$2"
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}Query: $query_name${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    # Run query using duckdb (CLI or Python module)
    # Use read-only mode to allow concurrent reads when Orbit is running
    if [ "$DUCKDB_CMD" = "duckdb" ]; then
        # Use DuckDB CLI with read-only mode
        duckdb -readonly "$DB_FILE" <<EOF
.mode column
.headers on
$query
EOF
    else
        # Use Python duckdb module with read-only mode
        python <<EOF
import duckdb
import sys

# Connect in read-only mode to allow concurrent reads when Orbit is running
conn = duckdb.connect('$DB_FILE', read_only=True)
result = conn.execute('''$query''').fetchall()
columns = [desc[0] for desc in conn.description] if conn.description else []

# Print headers
if columns:
    header = ' | '.join(f"{col:<20}" for col in columns)
    print(header)
    print('-' * len(header))

# Print rows
for row in result:
    row_str = ' | '.join(f"{str(val):<20}" if val is not None else f"{'NULL':<20}" for val in row)
    print(row_str)

conn.close()
EOF
    fi
    
    echo ""
}

# Test queries
echo -e "${GREEN}Running test queries...${NC}"
echo ""

# Basic queries
run_query "Total number of travel expenses" \
    "SELECT COUNT(*) AS total_expenses FROM travel_expenses;"

run_query "Total expense amount" \
    "SELECT SUM(total) AS total_amount FROM travel_expenses WHERE total IS NOT NULL;"

run_query "Average expense amount" \
    "SELECT AVG(total) AS avg_amount FROM travel_expenses WHERE total IS NOT NULL;"

run_query "Date range of expenses" \
    "SELECT MIN(start_date) AS earliest_date, MAX(start_date) AS latest_date FROM travel_expenses WHERE start_date IS NOT NULL;"

# Top queries
run_query "Top 10 most expensive trips" \
    "SELECT ref_number, name, start_date, destination_en, total FROM travel_expenses WHERE total IS NOT NULL ORDER BY total DESC LIMIT 10;"

run_query "Top 5 organizations by expense count" \
    "SELECT owner_org_title, COUNT(*) AS expense_count FROM travel_expenses WHERE owner_org_title IS NOT NULL GROUP BY owner_org_title ORDER BY expense_count DESC LIMIT 5;"

run_query "Top 5 organizations by total expenses" \
    "SELECT owner_org_title, SUM(total) AS total_expenses FROM travel_expenses WHERE owner_org_title IS NOT NULL AND total IS NOT NULL GROUP BY owner_org_title ORDER BY total_expenses DESC LIMIT 5;"

run_query "Top 5 destinations by trip count" \
    "SELECT destination_en, COUNT(*) AS trip_count FROM travel_expenses WHERE destination_en IS NOT NULL GROUP BY destination_en ORDER BY trip_count DESC LIMIT 5;"

# Grouped analysis
run_query "Expenses by organization" \
    "SELECT owner_org_title, COUNT(*) AS count, SUM(total) AS total_expenses, AVG(total) AS avg_expense FROM travel_expenses WHERE owner_org_title IS NOT NULL AND total IS NOT NULL GROUP BY owner_org_title ORDER BY total_expenses DESC LIMIT 10;"

run_query "Expenses by destination" \
    "SELECT destination_en, COUNT(*) AS count, SUM(total) AS total_expenses FROM travel_expenses WHERE destination_en IS NOT NULL AND total IS NOT NULL GROUP BY destination_en ORDER BY total_expenses DESC LIMIT 10;"

run_query "Expenses by person" \
    "SELECT name, COUNT(*) AS count, SUM(total) AS total_expenses FROM travel_expenses WHERE name IS NOT NULL AND total IS NOT NULL GROUP BY name ORDER BY total_expenses DESC LIMIT 10;"

# Expense category breakdown
run_query "Total by expense category" \
    "SELECT 
        SUM(airfare) AS total_airfare,
        SUM(other_transport) AS total_other_transport,
        SUM(lodging) AS total_lodging,
        SUM(meals) AS total_meals,
        SUM(other_expenses) AS total_other_expenses,
        SUM(total) AS grand_total
    FROM travel_expenses
    WHERE total IS NOT NULL;"

# Time-based analysis
run_query "Expenses by year" \
    "SELECT 
        EXTRACT(YEAR FROM start_date) AS year,
        COUNT(*) AS count,
        SUM(total) AS total_expenses
    FROM travel_expenses 
    WHERE start_date IS NOT NULL AND total IS NOT NULL
    GROUP BY year 
    ORDER BY year DESC;"

run_query "Expenses by month (2020)" \
    "SELECT 
        EXTRACT(MONTH FROM start_date) AS month,
        COUNT(*) AS count,
        SUM(total) AS total_expenses
    FROM travel_expenses 
    WHERE start_date >= '2020-01-01' AND start_date < '2021-01-01' AND total IS NOT NULL
    GROUP BY month 
    ORDER BY month;"

# Sample records
run_query "Sample travel expenses (last 5)" \
    "SELECT ref_number, name, start_date, destination_en, total FROM travel_expenses ORDER BY start_date DESC LIMIT 5;"

echo -e "${GREEN}✅ All test queries completed!${NC}"
echo ""
echo "💡 To test with Orbit Intent adapter:"
echo "   1. Configure adapter in config/adapters.yaml"
echo "   2. Start Orbit server"
echo "   3. Query: 'Show me travel expenses for 2020'"

