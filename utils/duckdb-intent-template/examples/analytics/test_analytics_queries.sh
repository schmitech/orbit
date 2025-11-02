#!/bin/bash

# DuckDB Analytics Query Test Script
# Tests various analytical queries against the DuckDB analytics database
#
# Usage: ./test_analytics_queries.sh [database_file]
#   If database_file is not provided, defaults to examples/duckdb/analytics.duckdb

set -e

# Default database file path
DEFAULT_DB="examples/duckdb/analytics.duckdb"

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
    echo "  cd utils/duckdb-intent-template/examples/analytics"
    echo "  python generate_analytics_data.py --output ../../../../examples/duckdb/analytics.duckdb"
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
echo "DuckDB Analytics Query Test"
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
    header = ' | '.join(columns)
    print(header)
    print('-' * len(header))
    
# Print rows
for row in result:
    print(' | '.join(str(val) for val in row))
    
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

run_query "Table Counts" "
SELECT 
    'sales' as table_name, 
    COUNT(*) as row_count 
FROM sales
UNION ALL
SELECT 
    'products' as table_name, 
    COUNT(*) as row_count 
FROM products
UNION ALL
SELECT 
    'customers' as table_name, 
    COUNT(*) as row_count 
FROM customers;
"

# Test 2: Basic Sales Queries
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}2. Basic Sales Analysis${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Total Sales Count" "
SELECT COUNT(*) as total_sales FROM sales;
"

run_query "Total Revenue" "
SELECT 
    SUM(sales_amount) as total_revenue,
    COUNT(*) as transaction_count,
    AVG(sales_amount) as average_transaction
FROM sales;
"

run_query "Recent Sales (Last 10)" "
SELECT 
    sale_date,
    product_name,
    category,
    region,
    sales_amount,
    quantity
FROM sales
ORDER BY sale_date DESC
LIMIT 10;
"

# Test 3: Sales by Category
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}3. Sales by Category${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Sales Summary by Category" "
SELECT 
    category,
    COUNT(*) as transaction_count,
    SUM(sales_amount) as total_revenue,
    AVG(sales_amount) as avg_transaction,
    SUM(quantity) as total_quantity
FROM sales
WHERE category IS NOT NULL
GROUP BY category
ORDER BY total_revenue DESC;
"

# Test 4: Sales by Region
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}4. Sales by Region${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Sales Summary by Region" "
SELECT 
    region,
    COUNT(*) as transaction_count,
    SUM(sales_amount) as total_revenue,
    AVG(sales_amount) as avg_transaction
FROM sales
GROUP BY region
ORDER BY total_revenue DESC;
"

# Test 5: Top Products
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}5. Top Products by Revenue${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Top 10 Products by Revenue" "
SELECT 
    product_name,
    category,
    COUNT(*) as transaction_count,
    SUM(sales_amount) as total_revenue,
    SUM(quantity) as total_quantity_sold,
    AVG(sales_amount) as avg_sale_amount
FROM sales
GROUP BY product_name, category
ORDER BY total_revenue DESC
LIMIT 10;
"

# Test 6: Time-Based Analysis
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}6. Time-Based Sales Analysis${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Sales by Month" "
SELECT 
    strftime('%Y-%m', sale_date) as month,
    COUNT(*) as transaction_count,
    SUM(sales_amount) as total_revenue,
    AVG(sales_amount) as avg_transaction
FROM sales
GROUP BY month
ORDER BY month DESC
LIMIT 12;
"

run_query "Recent Daily Sales" "
SELECT 
    sale_date,
    COUNT(*) as transaction_count,
    SUM(sales_amount) as daily_revenue
FROM sales
GROUP BY sale_date
ORDER BY sale_date DESC
LIMIT 14;
"

# Test 7: Product Information
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}7. Product Catalog${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Products Summary" "
SELECT 
    p.category,
    COUNT(*) as product_count,
    AVG(p.price) as avg_price,
    MIN(p.price) as min_price,
    MAX(p.price) as max_price
FROM products p
GROUP BY p.category
ORDER BY p.category;
"

run_query "Top Products by Price" "
SELECT 
    product_name,
    category,
    price,
    cost,
    (price - COALESCE(cost, 0)) as profit_margin
FROM products
ORDER BY price DESC
LIMIT 10;
"

# Test 8: Customer Analysis
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}8. Customer Analysis${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Customers by Region" "
SELECT 
    region,
    COUNT(*) as customer_count
FROM customers
WHERE region IS NOT NULL
GROUP BY region
ORDER BY customer_count DESC;
"

run_query "Top Customers by Purchase Amount" "
SELECT 
    s.customer_id,
    c.customer_name,
    c.region,
    c.segment,
    COUNT(*) as transaction_count,
    SUM(s.sales_amount) as total_purchases
FROM sales s
LEFT JOIN customers c ON s.customer_id = c.id
WHERE s.customer_id IS NOT NULL
GROUP BY s.customer_id, c.customer_name, c.region, c.segment
ORDER BY total_purchases DESC
LIMIT 10;
"

# Test 9: Complex Joins
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}9. Complex Analytical Queries${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Sales with Product Details" "
SELECT 
    s.sale_date,
    s.product_name,
    p.category,
    p.price as product_price,
    s.sales_amount,
    s.quantity,
    s.region
FROM sales s
LEFT JOIN products p ON s.product_name = p.product_name
ORDER BY s.sale_date DESC
LIMIT 10;
"

run_query "Category Performance Across Regions" "
SELECT 
    s.category,
    s.region,
    COUNT(*) as transaction_count,
    SUM(s.sales_amount) as total_revenue,
    AVG(s.sales_amount) as avg_transaction
FROM sales s
WHERE s.category IS NOT NULL
GROUP BY s.category, s.region
ORDER BY s.category, total_revenue DESC;
"

# Test 10: Statistical Summary
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}10. Statistical Summary${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""

run_query "Sales Statistics" "
SELECT 
    COUNT(*) as total_transactions,
    SUM(sales_amount) as total_revenue,
    AVG(sales_amount) as mean_transaction,
    MIN(sales_amount) as min_transaction,
    MAX(sales_amount) as max_transaction,
    SUM(quantity) as total_quantity_sold,
    AVG(quantity) as avg_quantity_per_transaction
FROM sales;
"

# Summary
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Test Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "All queries executed successfully against: $DB_FILE"
echo ""

