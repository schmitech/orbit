#!/bin/bash

# Template Generator Shell Script
# Run this script from the sql-intent-template directory
#
# Usage: ./generate_templates.sh [options]
#
# Examples:
#   ./generate_templates.sh --schema database-schema.sql --queries test_queries.md
#   ./generate_templates.sh --schema examples/postgres/customer-order.sql --queries examples/postgres/test/test_queries.md
#   ./generate_templates.sh --help

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
SCHEMA_FILE=""
QUERIES_FILE=""
OUTPUT_FILE=""
DOMAIN_CONFIG_FILE=""
PROVIDER=""
LIMIT=""
VERBOSE=false
MAIN_CONFIG_FILE="../../config/config.yaml"
GENERATE_DOMAIN=false
DOMAIN_OUTPUT_FILE=""
DOMAIN_NAME=""
DOMAIN_TYPE="general"

# Function to read provider from config.yaml
get_provider_from_config() {
    local config_file="../../config/config.yaml"
    if [ -f "$config_file" ]; then
        local provider=$(grep "inference_provider:" "$config_file" | head -1 | sed 's/.*inference_provider: *"\([^"]*\)".*/\1/' | sed 's/.*inference_provider: *\([^ ]*\).*/\1/')
        if [ -n "$provider" ]; then
            echo "$provider"
        else
            echo "ollama"  # fallback
        fi
    else
        echo "ollama"  # fallback
    fi
}

# Function to print colored output
print_info() {
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
    cat << EOF
Template Generator Shell Script

USAGE:
    ./generate_templates.sh [options]

REQUIRED OPTIONS:
    --schema FILE        Path to SQL schema file
    --queries FILE       Path to test queries markdown file
    --domain FILE        Path to domain configuration file

OPTIONAL OPTIONS:
    --output FILE        Path to output YAML file (default: auto-generated)
    --provider NAME      Override inference provider (default: from config.yaml)
    --limit NUMBER       Limit number of queries to process
    --verbose            Enable verbose output
    --generate-domain    Generate domain configuration file from schema
    --domain-output FILE Path to output domain config file (default: <schema>_domain.yaml)
    --domain-name NAME   Name for the domain (default: inferred from schema)
    --domain-type TYPE   Type of domain: general, ecommerce, security, etc. (default: general)
    --help               Show this help message

EXAMPLES:
    # Basic usage with specific configuration
    ./generate_templates.sh --schema database-schema.sql --queries test_queries.md --domain configs/classified-data-config.yaml

    # Contact example (recommended for testing)
    ./generate_templates.sh --schema examples/contact.sql --queries examples/contact_test_queries.md --domain configs/contact-config.yaml

    # Library management example
    ./generate_templates.sh --schema examples/library_management.sql --queries examples/library_test_queries.md --domain configs/library-config.yaml

    # Test with limited queries
    ./generate_templates.sh --schema database-schema.sql --queries test_queries.md --domain configs/contact-config.yaml --limit 10

    # Verbose output
    ./generate_templates.sh --schema database-schema.sql --queries test_queries.md --domain configs/contact-config.yaml --verbose

    # Generate domain configuration file from schema
    ./generate_templates.sh --schema examples/contact.sql --queries examples/contact_test_queries.md --domain configs/contact-config.yaml --generate-domain --domain-name "Contact Management" --domain-type general

DOMAIN CONFIGURATION FILES:
    configs/contact-config.yaml            - For ultra-simple single-table schemas
    configs/classified-data-config.yaml    - For security/classified data systems
    configs/ecommerce-config.yaml          - For e-commerce systems
    configs/financial-config.yaml          - For financial/accounting systems
    configs/library-config.yaml            - For library management systems

EOF
}

# Function to check if file exists
check_file() {
    if [ ! -f "$1" ]; then
        print_error "File not found: $1"
        exit 1
    fi
}


# Function to generate output filename
generate_output_filename() {
    local schema_file="$1"
    local base_name=$(basename "$schema_file" .sql)
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    echo "${base_name}_templates_${timestamp}.yaml"
}

# Function to run template generator
run_template_generator() {
    local -a cmd=(
        "python"
        "template_generator.py"
        "--schema" "$SCHEMA_FILE"
        "--queries" "$QUERIES_FILE"
        "--output" "$OUTPUT_FILE"
        "--config" "$MAIN_CONFIG_FILE"
        "--domain" "$DOMAIN_CONFIG_FILE"
    )

    if [ -n "$PROVIDER" ]; then
        cmd+=("--provider" "$PROVIDER")
    fi

    if [ -n "$LIMIT" ]; then
        cmd+=("--limit" "$LIMIT")
    fi

    if [ "$GENERATE_DOMAIN" = true ]; then
        cmd+=("--generate-domain")

        if [ -n "$DOMAIN_OUTPUT_FILE" ]; then
            cmd+=("--domain-output" "$DOMAIN_OUTPUT_FILE")
        fi

        if [ -n "$DOMAIN_NAME" ]; then
            cmd+=("--domain-name" "$DOMAIN_NAME")
        fi

        if [ -n "$DOMAIN_TYPE" ]; then
            cmd+=("--domain-type" "$DOMAIN_TYPE")
        fi
    fi

    local cmd_display
    cmd_display=$(printf '%q ' "${cmd[@]}")
    cmd_display="${cmd_display% }"

    print_info "Running template generator..."
    print_info "Command: $cmd_display"

    if [ "$VERBOSE" = true ]; then
        if ! "${cmd[@]}"; then
            print_error "Template generation failed"
            exit 1
        fi
    else
        local output
        if ! output=$("${cmd[@]}" 2>&1); then
            print_error "Template generation failed"
            printf '%s\n' "$output" >&2
            exit 1
        fi
    fi

    print_success "Templates generated successfully: $OUTPUT_FILE"
}

# Function to show results summary
show_results() {
    if [ -f "$OUTPUT_FILE" ]; then
        print_info "Results summary:"
        echo "  Output file: $OUTPUT_FILE"
        echo "  Domain configuration: $DOMAIN_CONFIG_FILE"
        echo "  Provider: $PROVIDER"
        if [ -n "$LIMIT" ]; then
            echo "  Query limit: $LIMIT"
        fi
        
        # Count templates if possible
        if command -v python >/dev/null 2>&1; then
            local template_count=$(python -c "
import yaml
try:
    with open('$OUTPUT_FILE', 'r') as f:
        data = yaml.safe_load(f)
        print(data.get('total_templates', 'unknown'))
except:
    print('unknown')
" 2>/dev/null)
            echo "  Templates generated: $template_count"
        fi
    fi
}

# Function to load environment variables from a dotenv file without sourcing it directly
load_env_file() {
    local env_path="$1"

    if [ ! -f "$env_path" ]; then
        print_warning "No .env file found at $env_path"
        return
    fi

    print_info "Loading environment variables from $env_path"

    while IFS= read -r raw_line || [ -n "$raw_line" ]; do
        local line
        line="$(printf '%s' "$raw_line" | sed 's/^[[:space:]]*//')"

        # Skip empty lines and comments
        if [ -z "$line" ] || [[ "$line" == \#* ]]; then
            continue
        fi

        # Support optional leading "export " statements
        if [[ "$line" == export* ]]; then
            line="${line#export }"
            line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//')"
        fi

        if [[ "$line" != *=* ]]; then
            print_warning "Skipping invalid env line: $line"
            continue
        fi

        local key="${line%%=*}"
        local value="${line#*=}"

        # Trim trailing whitespace from the key
        key="$(printf '%s' "$key" | sed 's/[[:space:]]*$//')"

        # Strip surrounding quotes from the value if present
        if [[ "$value" =~ ^\".*\"$ ]] || [[ "$value" =~ ^\'.*\'$ ]]; then
            value="${value:1:-1}"
        fi

        export "$key=$value"
    done < "$env_path"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --schema)
            SCHEMA_FILE="$2"
            shift 2
            ;;
        --queries)
            QUERIES_FILE="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --domain)
            DOMAIN_CONFIG_FILE="$2"
            shift 2
            ;;
        --provider)
            PROVIDER="$2"
            shift 2
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --generate-domain)
            GENERATE_DOMAIN=true
            shift
            ;;
        --domain-output)
            DOMAIN_OUTPUT_FILE="$2"
            shift 2
            ;;
        --domain-name)
            DOMAIN_NAME="$2"
            shift 2
            ;;
        --domain-type)
            DOMAIN_TYPE="$2"
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

# Validate required arguments
if [ -z "$SCHEMA_FILE" ] || [ -z "$QUERIES_FILE" ] || [ -z "$DOMAIN_CONFIG_FILE" ]; then
    print_error "Missing required arguments"
    show_usage
    exit 1
fi

# Check if files exist
check_file "$SCHEMA_FILE"
check_file "$QUERIES_FILE"

# Check if domain config file exists
check_file "$DOMAIN_CONFIG_FILE"

# Set provider from config if not provided
if [ -z "$PROVIDER" ]; then
    PROVIDER=$(get_provider_from_config)
    print_info "Using provider from config: $PROVIDER"
fi

# Generate output filename if not provided
if [ -z "$OUTPUT_FILE" ]; then
    OUTPUT_FILE=$(generate_output_filename "$SCHEMA_FILE")
    print_info "Output file: $OUTPUT_FILE"
fi

# Load environment variables from parent .env file
load_env_file "../../.env"

# Activate virtual environment if it exists
if [ -f "../../venv/bin/activate" ]; then
    print_info "Activating virtual environment"
    source ../../venv/bin/activate
    
    # Re-export environment variables after virtual environment activation
    print_info "Re-exporting environment variables after venv activation"
    load_env_file "../../.env"
else
    print_warning "Virtual environment not found at ../../venv/bin/activate"
fi

# Check if Python is available
if ! command -v python >/dev/null 2>&1; then
    print_error "Python is required but not installed. Please activate the virtual environment first."
    exit 1
fi

# Check if required Python modules are available
if ! python -c "import yaml, asyncio" >/dev/null 2>&1; then
    print_error "Required Python modules not found. Please install: pip install pyyaml"
    exit 1
fi

# Run the template generator
print_info "Starting template generation..."
print_info "Schema: $SCHEMA_FILE"
print_info "Queries: $QUERIES_FILE"
print_info "Output: $OUTPUT_FILE"
print_info "Domain Config: $DOMAIN_CONFIG_FILE"

run_template_generator
show_results

print_success "Template generation complete!"
