#!/bin/bash
#
# query-sqlite.sh - Query tables in the Orbit SQLite database
#
# DESCRIPTION:
#   A utility script to quickly inspect tables in orbit.db.
#   Displays the table schema followed by the most recent rows.
#   Optionally exports results to a CSV file.
#
# USAGE:
#   ./query_table.sh <table_name> [limit] [output.csv]
#
# ARGUMENTS:
#   table_name  (required)  Name of the table to query
#   limit       (optional)  Number of rows to display (default: 10)
#   output.csv  (optional)  Path to save results as CSV file
#
# EXAMPLES:
#   ./query_table.sh audit_logs               # Show schema + last 10 rows
#   ./query_table.sh audit_logs 50            # Show schema + last 50 rows
#   ./query_table.sh audit_logs out.csv       # Export last 10 rows to out.csv
#   ./query_table.sh audit_logs 100 out.csv   # Export last 100 rows to out.csv
#   ./query_table.sh                          # Show usage help and list available tables
#
# OUTPUT:
#   Terminal mode:
#     1. Table schema (CREATE TABLE statement and indexes)
#     2. Most recent rows ordered by rowid descending
#   CSV mode:
#     - Saves data to specified CSV file (no schema output)
#     - Includes header row with column names
#
# DEPENDENCIES:
#   - sqlite3 (install via: sudo dnf install -y sqlite)
#
# AUTHOR: Auto-generated
# DATE:   January 2026
#

DB_PATH="/home/ec2-user/orbit/orbit.db"
TABLE_NAME="${1:-audit_logs}"

# Smart argument parsing: detect if $2 is a filename or a number
if [[ "$2" =~ \.csv$ ]] || [[ "$2" =~ / ]]; then
    # Second arg looks like a file path, use default limit
    LIMIT=10
    OUTPUT_CSV="$2"
elif [ -n "$2" ]; then
    # Second arg is a number (limit)
    LIMIT="$2"
    OUTPUT_CSV="$3"
else
    LIMIT=10
    OUTPUT_CSV=""
fi

if [ -z "$1" ]; then
    echo "Usage: $0 <table_name> [limit] [output.csv]"
    echo ""
    echo "Examples:"
    echo "  $0 audit_logs               # Show last 10 rows in terminal"
    echo "  $0 audit_logs 50            # Show last 50 rows in terminal"
    echo "  $0 audit_logs out.csv       # Export last 10 rows to CSV"
    echo "  $0 audit_logs 100 out.csv   # Export last 100 rows to CSV"
    echo ""
    echo "Available tables:"
    sqlite3 "$DB_PATH" ".tables"
    exit 1
fi

# CSV export mode
if [ -n "$OUTPUT_CSV" ]; then
    sqlite3 "$DB_PATH" -cmd ".headers on" -cmd ".mode csv" \
        "SELECT * FROM $TABLE_NAME ORDER BY rowid DESC LIMIT $LIMIT;" > "$OUTPUT_CSV"
    echo "Exported $LIMIT rows from '$TABLE_NAME' to: $OUTPUT_CSV"
    exit 0
fi

# Terminal display mode
echo "=== Schema for '$TABLE_NAME' ==="
sqlite3 "$DB_PATH" ".schema $TABLE_NAME"
echo ""
echo "=== Last $LIMIT rows from '$TABLE_NAME' ==="
sqlite3 "$DB_PATH" -cmd ".headers on" -cmd ".mode column" "SELECT * FROM $TABLE_NAME ORDER BY rowid DESC LIMIT $LIMIT;"
