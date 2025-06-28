#!/bin/bash

#==============================================================================
# Git Changelog Generator
#==============================================================================
# 
# Description:
#   Generates a changelog from git commits between specified dates.
#   Organizes commits by type (features, bug fixes, other changes) and
#   formats them into a readable markdown changelog.
#
# macOS Users - IMPORTANT:
#   If you encounter date parsing errors, install GNU date via Homebrew:
#   brew install coreutils
#   This provides better date validation and avoids BSD date compatibility issues.
#
# Usage:
#   ./generate_changelog.sh <start_date> <end_date>
#   ./generate_changelog.sh 2025-01-01 2025-01-31
#   ./generate_changelog.sh "2025-01-01" "2025-01-31"
#
# Arguments:
#   start_date  - Start date in YYYY-MM-DD format (e.g., 2024-01-01)
#   end_date    - End date in YYYY-MM-DD format (e.g., 2024-12-31)
#
# Output:
#   Prints formatted changelog to stdout. Redirect to file if needed:
#   ./generate_changelog.sh 2024-01-01 2024-12-31 > CHANGELOG.md
#
# Requirements:
#   - Git repository
#   - Git command line tool
#   - Bash shell
#   - For macOS: Consider installing coreutils via Homebrew for best results
#
# Note:
#   This script works best with conventional commit messages:
#   - feat: for new features
#   - fix: for bug fixes
#   - Other prefixes will be categorized as "Other Changes"
#
#==============================================================================

# Function to display usage information
show_usage() {
    echo "Usage: $0 <start_date> <end_date>"
    echo ""
    echo "Generate a changelog from git commits between specified dates."
    echo ""
    echo "Arguments:"
    echo "  start_date    Start date in YYYY-MM-DD format (e.g., 2024-01-01)"
    echo "  end_date      End date in YYYY-MM-DD format (e.g., 2024-12-31)"
    echo ""
    echo "Examples:"
    echo "  $0 2024-01-01 2024-12-31"
    echo "  $0 2024-06-01 2024-06-30 > june_changelog.md"
    echo ""
    echo "Note: Dates are inclusive. The script will include commits from"
    echo "      the start date through the end date."
}

# Function to validate date format
validate_date() {
    local date_string="$1"
    local date_name="$2"
    
    # Check if date matches YYYY-MM-DD format
    if [[ ! $date_string =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        echo "Error: Invalid $date_name format. Expected YYYY-MM-DD, got: $date_string"
        return 1
    fi
    
    # Extract year, month, day for validation
    local year="${date_string:0:4}"
    local month="${date_string:5:2}"
    local day="${date_string:8:2}"
    
    # Basic range validation
    if [[ $year -lt 1900 || $year -gt 2100 ]]; then
        echo "Error: Invalid $date_name. Year must be between 1900-2100: $date_string"
        return 1
    fi
    
    if [[ $month -lt 01 || $month -gt 12 ]]; then
        echo "Error: Invalid $date_name. Month must be between 01-12: $date_string"
        return 1
    fi
    
    if [[ $day -lt 01 || $day -gt 31 ]]; then
        echo "Error: Invalid $date_name. Day must be between 01-31: $date_string"
        return 1
    fi
    
    # Try to parse the date (compatible with both GNU and BSD date)
    if command -v gdate >/dev/null 2>&1; then
        # Use GNU date if available (common via Homebrew on macOS)
        if ! gdate -d "$date_string" >/dev/null 2>&1; then
            echo "Error: Invalid $date_name. Cannot parse: $date_string"
            return 1
        fi
    elif date -d "$date_string" >/dev/null 2>&1; then
        # GNU date (Linux)
        return 0
    elif date -j -f "%Y-%m-%d" "$date_string" >/dev/null 2>&1; then
        # BSD date (macOS)
        return 0
    else
        # If we can't validate with date command, rely on regex validation above
        echo "Warning: Could not validate date with system date command, relying on format check only" >&2
    fi
    
    return 0
}

# Function to check if we're in a git repository
check_git_repo() {
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        echo "Error: Not in a git repository. Please run this script from within a git repository."
        exit 1
    fi
}

# Function to get commit count for a section
get_commit_count() {
    local since="$1"
    local until="$2"
    local grep_pattern="$3"
    local invert_grep="$4"
    
    local git_cmd="git log --since=\"$since\" --until=\"$until\" --no-merges --oneline"
    
    if [[ -n "$grep_pattern" ]]; then
        git_cmd="$git_cmd --grep=\"$grep_pattern\""
    fi
    
    if [[ "$invert_grep" == "true" ]]; then
        git_cmd="$git_cmd --invert-grep"
    fi
    
    eval "$git_cmd" | wc -l
}

# Function to generate commit list
generate_commit_list() {
    local since="$1"
    local until="$2"
    local grep_pattern="$3"
    local invert_grep="$4"
    
    local git_cmd="git log --since=\"$since\" --until=\"$until\" --no-merges --pretty=format:\"- %s (%an, %ad)\" --date=short"
    
    if [[ -n "$grep_pattern" ]]; then
        git_cmd="$git_cmd --grep=\"$grep_pattern\""
    fi
    
    if [[ "$invert_grep" == "true" ]]; then
        git_cmd="$git_cmd --invert-grep"
    fi
    
    eval "$git_cmd"
}

#==============================================================================
# Main Script Logic
#==============================================================================

# Check command line arguments
if [[ $# -ne 2 ]]; then
    echo "Error: Incorrect number of arguments."
    echo ""
    show_usage
    exit 1
fi

# Handle help requests
if [[ "$1" == "-h" || "$1" == "--help" || "$1" == "help" ]]; then
    show_usage
    exit 0
fi

# Assign arguments to variables
START_DATE="$1"
END_DATE="$2"

# Validate inputs
echo "Validating inputs..." >&2

# Check if we're in a git repository
check_git_repo

# Validate date formats
if ! validate_date "$START_DATE" "start date"; then
    exit 1
fi

if ! validate_date "$END_DATE" "end date"; then
    exit 1
fi

# Check that start date is before end date
if [[ "$START_DATE" > "$END_DATE" ]]; then
    echo "Error: Start date ($START_DATE) must be before or equal to end date ($END_DATE)"
    exit 1
fi

echo "Generating changelog from $START_DATE to $END_DATE..." >&2
echo "" >&2

#==============================================================================
# Generate Changelog
#==============================================================================

# Header
echo "# Changelog"
echo ""
echo "**Period:** $START_DATE to $END_DATE"
echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Get commit counts for summary
FEAT_COUNT=$(get_commit_count "$START_DATE" "$END_DATE" "^feat:")
FIX_COUNT=$(get_commit_count "$START_DATE" "$END_DATE" "^fix:")
OTHER_COUNT=$(get_commit_count "$START_DATE" "$END_DATE" "^feat:|^fix:" "true")
TOTAL_COUNT=$((FEAT_COUNT + FIX_COUNT + OTHER_COUNT))

# Summary
echo "## Summary"
echo ""
echo "- **Total commits:** $TOTAL_COUNT"
echo "- **Features:** $FEAT_COUNT"
echo "- **Bug fixes:** $FIX_COUNT"
echo "- **Other changes:** $OTHER_COUNT"
echo ""

# Features section
echo "## 🚀 Features"
echo ""
if [[ $FEAT_COUNT -gt 0 ]]; then
    generate_commit_list "$START_DATE" "$END_DATE" "^feat:"
else
    echo "_No new features in this period._"
fi
echo ""

# Bug fixes section
echo "## 🐛 Bug Fixes"
echo ""
if [[ $FIX_COUNT -gt 0 ]]; then
    generate_commit_list "$START_DATE" "$END_DATE" "^fix:"
else
    echo "_No bug fixes in this period._"
fi
echo ""

# Other changes section
echo "## 📝 Other Changes"
echo ""
if [[ $OTHER_COUNT -gt 0 ]]; then
    generate_commit_list "$START_DATE" "$END_DATE" "^feat:|^fix:" "true"
else
    echo "_No other changes in this period._"
fi
echo ""

# Detailed commit history section
echo "---"
echo ""
echo "## 📋 Complete Commit History"
echo ""
echo "_All commits in chronological order with full details for AI summarization:_"
echo ""

# Get all commits with title and full description
git log --since="$START_DATE" --until="$END_DATE" --no-merges \
  --pretty=format:"### %s%n**Author:** %an (%ae)%n**Date:** %ad%n**Hash:** %h%n%n**Description:**%n%B%n---" \
  --date=format:"%Y-%m-%d %H:%M:%S" \
  --reverse

echo ""
echo ""
echo "---"
echo ""
echo "_This changelog was automatically generated from git commit history._"

# Log completion to stderr so it doesn't interfere with output redirection
echo "" >&2
echo "Changelog generation completed successfully!" >&2