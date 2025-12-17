#!/bin/bash

# Electric Vehicle Population Query Test Script
# Tests various analytical queries against the EV population DuckDB database
#
# Usage: ./test_ev_queries.sh [database_file]
#   If database_file is not provided, defaults to ev_population.duckdb

set -e

# Get script directory and resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default database file path (relative to script directory)
DEFAULT_DB="$SCRIPT_DIR/ev_population.duckdb"

# Get database file from argument or use default
if [ -n "$1" ]; then
    if [[ "$1" == /* ]]; then
        DB_FILE="$1"
    else
        DB_FILE="$(cd "$SCRIPT_DIR" && cd "$(dirname "$1")" && pwd)/$(basename "$1")"
    fi
else
    DB_FILE="$DEFAULT_DB"
fi

# Check if database file exists
if [ ! -f "$DB_FILE" ]; then
    echo "Error: Database file '$DB_FILE' not found!"
    echo ""
    echo "Usage: $0 [database_file]"
    echo "  database_file: Path to DuckDB database file"
    echo "  If not provided, defaults to: $DEFAULT_DB"
    echo ""
    echo "To load data, run:"
    echo "  cd $SCRIPT_DIR"
    echo "  python3 load_ev_data.py --csv Electric_Vehicle_Population_Data.csv"
    exit 1
fi

# Check for venv and activate it if it exists
PROJECT_ROOT=""
if [ -d "$SCRIPT_DIR/../../../../venv" ]; then
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../" && pwd)"
elif [ -d "$SCRIPT_DIR/../../../../../venv" ]; then
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../../" && pwd)"
fi

VENV_PATH=""
if [ -n "$PROJECT_ROOT" ]; then
    VENV_PATH="$PROJECT_ROOT/venv"
fi

if [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
    echo "Activated virtual environment: $VENV_PATH"
fi

# Check if duckdb CLI or Python module is available
DUCKDB_CMD=""
if command -v duckdb &> /dev/null; then
    DUCKDB_CMD="duckdb"
elif python3 -c "import duckdb" 2>/dev/null; then
    DUCKDB_CMD="python3"
elif python -c "import duckdb" 2>/dev/null; then
    DUCKDB_CMD="python"
else
    echo "Error: duckdb command or Python module not found!"
    echo "Please install DuckDB: pip install duckdb"
    exit 1
fi

echo "=========================================="
echo "EV Population Query Test"
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

    if [ "$DUCKDB_CMD" = "duckdb" ]; then
        duckdb -readonly "$DB_FILE" <<EOF
.mode column
.headers on
$query
EOF
    else
        $DUCKDB_CMD <<EOF
import duckdb

conn = duckdb.connect('$DB_FILE', read_only=True)
relation = conn.execute('''$query''')

columns = []
try:
    if hasattr(relation, 'description') and relation.description:
        columns = [desc[0] for desc in relation.description]
except (AttributeError, TypeError):
    pass

rows = relation.fetchall()

if not columns and rows:
    columns = [f'col_{i+1}' for i in range(len(rows[0]))]

if columns:
    header = ' | '.join(columns)
    print(header)
    print('-' * len(header))

for row in rows:
    print(' | '.join(str(val) if val is not None else 'NULL' for val in row))

conn.close()
EOF
    fi

    echo ""
    echo ""
}

# Test 1: Database Overview
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}1. Database Overview${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Total EV Count" "
SELECT COUNT(*) as total_vehicles FROM electric_vehicles;
"

run_query "BEV vs PHEV Breakdown" "
SELECT
    ev_type,
    COUNT(*) as vehicle_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
FROM electric_vehicles
GROUP BY ev_type
ORDER BY vehicle_count DESC;
"

run_query "Overview Statistics" "
SELECT
    COUNT(*) as total_vehicles,
    COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev_count,
    COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev_count,
    COUNT(DISTINCT make) as unique_manufacturers,
    COUNT(DISTINCT model) as unique_models,
    COUNT(DISTINCT county) as counties_covered,
    MIN(model_year) as oldest_year,
    MAX(model_year) as newest_year,
    ROUND(AVG(CASE WHEN electric_range > 0 THEN electric_range END), 1) as avg_range
FROM electric_vehicles;
"

# Test 2: Geographic Analysis
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}2. Geographic Analysis - Counties${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Top 10 Counties by EV Count" "
SELECT
    county,
    COUNT(*) as total_vehicles,
    COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev_count,
    COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev_count,
    ROUND(100.0 * COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) / COUNT(*), 1) as bev_pct
FROM electric_vehicles
GROUP BY county
ORDER BY total_vehicles DESC
LIMIT 10;
"

run_query "Top 10 Cities by EV Count" "
SELECT
    city,
    county,
    COUNT(*) as total_vehicles,
    COUNT(DISTINCT make) as unique_makes
FROM electric_vehicles
GROUP BY city, county
ORDER BY total_vehicles DESC
LIMIT 10;
"

# Test 3: Legislative District Analysis
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}3. Legislative District Analysis${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Top 10 Legislative Districts" "
SELECT
    legislative_district,
    COUNT(*) as total_vehicles,
    COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev_count,
    COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev_count,
    COUNT(DISTINCT county) as counties_in_district
FROM electric_vehicles
WHERE legislative_district IS NOT NULL
GROUP BY legislative_district
ORDER BY total_vehicles DESC
LIMIT 10;
"

# Test 4: Manufacturer Analysis
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}4. Manufacturer Analysis${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "EV Market Share by Manufacturer" "
SELECT
    make,
    COUNT(*) as total_vehicles,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as market_share,
    COUNT(DISTINCT model) as models,
    ROUND(AVG(CASE WHEN electric_range > 0 THEN electric_range END), 1) as avg_range
FROM electric_vehicles
GROUP BY make
ORDER BY total_vehicles DESC
LIMIT 15;
"

run_query "Top 15 Models by Registration" "
SELECT
    make,
    model,
    ev_type,
    COUNT(*) as total_vehicles,
    ROUND(AVG(CASE WHEN electric_range > 0 THEN electric_range END), 1) as avg_range
FROM electric_vehicles
GROUP BY make, model, ev_type
ORDER BY total_vehicles DESC
LIMIT 15;
"

# Test 5: Model Year Trends
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}5. EV Adoption Trends by Model Year${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Registrations by Model Year" "
SELECT
    model_year,
    COUNT(*) as total_vehicles,
    COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev_count,
    COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev_count,
    ROUND(100.0 * COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) / COUNT(*), 1) as bev_pct,
    ROUND(AVG(CASE WHEN electric_range > 0 THEN electric_range END), 1) as avg_range
FROM electric_vehicles
GROUP BY model_year
ORDER BY model_year DESC
LIMIT 15;
"

# Test 6: Electric Range Analysis
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}6. Electric Range Analysis${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Range Distribution" "
SELECT
    CASE
        WHEN electric_range = 0 THEN 'Unknown'
        WHEN electric_range < 50 THEN 'Under 50 mi'
        WHEN electric_range < 100 THEN '50-99 mi'
        WHEN electric_range < 150 THEN '100-149 mi'
        WHEN electric_range < 200 THEN '150-199 mi'
        WHEN electric_range < 250 THEN '200-249 mi'
        WHEN electric_range < 300 THEN '250-299 mi'
        ELSE '300+ mi'
    END as range_category,
    COUNT(*) as vehicle_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as percentage
FROM electric_vehicles
GROUP BY range_category
ORDER BY
    CASE range_category
        WHEN 'Unknown' THEN 0
        WHEN 'Under 50 mi' THEN 1
        WHEN '50-99 mi' THEN 2
        WHEN '100-149 mi' THEN 3
        WHEN '150-199 mi' THEN 4
        WHEN '200-249 mi' THEN 5
        WHEN '250-299 mi' THEN 6
        ELSE 7
    END;
"

run_query "Top 10 Longest Range Models" "
SELECT
    make,
    model,
    MAX(electric_range) as max_range,
    COUNT(*) as vehicles_registered
FROM electric_vehicles
WHERE electric_range > 0
GROUP BY make, model
ORDER BY max_range DESC
LIMIT 10;
"

# Test 7: CAFV Eligibility
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}7. CAFV Eligibility Analysis${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "CAFV Eligibility Distribution" "
SELECT
    cafv_eligibility,
    COUNT(*) as vehicle_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
FROM electric_vehicles
GROUP BY cafv_eligibility
ORDER BY vehicle_count DESC;
"

# Test 8: Electric Utility Analysis
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}8. Electric Utility Analysis${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Top 10 Utilities by EV Count" "
SELECT
    electric_utility,
    COUNT(*) as total_vehicles,
    COUNT(DISTINCT county) as counties_served,
    COUNT(DISTINCT city) as cities_served
FROM electric_vehicles
WHERE electric_utility IS NOT NULL
GROUP BY electric_utility
ORDER BY total_vehicles DESC
LIMIT 10;
"

# Test 9: Sample Records
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}9. Sample Records${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Sample EV Records" "
SELECT
    vin_prefix,
    model_year,
    make,
    model,
    ev_type,
    electric_range,
    county,
    city
FROM electric_vehicles
ORDER BY model_year DESC, make, model
LIMIT 10;
"

# Summary
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Test Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "All queries executed successfully against: $DB_FILE"
echo ""
echo "Next steps:"
echo "  1. Configure Intent adapter in config/adapters.yaml"
echo "  2. Start Orbit server"
echo "  3. Try natural language queries like:"
echo "     - 'How many EVs are registered in Washington?'"
echo "     - 'Which counties have the most electric vehicles?'"
echo "     - 'Show me Tesla market share'"
echo ""
