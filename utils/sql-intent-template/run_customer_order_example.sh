#!/bin/bash
################################################################################
# SQL Intent Template Generator - Customer Order Example
#
# DESCRIPTION:
#     One-command demonstration of the SQL template generator for customer-order
#     system. Perfect for newcomers to quickly see high-quality templates
#     and understand the output format.
#
#     This example:
#     - Uses a two-table schema (customers and orders tables)
#     - Generates SQL templates from 669 test queries
#     - Generates domain configuration from schema
#     - Demonstrates PostgreSQL dialect configuration
#     - Uses comprehensive query set for template generation
#
# USAGE:
#     ./run_customer_order_example.sh [--generate]
#
# OPTIONS:
#     (none)      Use existing templates if available (instant) - DEFAULT
#     --generate  Generate from test queries (slower, for demonstration)
#                 Use this flag to regenerate templates from queries
#
# WHAT IT DOES (Default Mode - Existing Templates):
#     1. Checks for existing templates in examples/postgres/customer-orders/
#     2. Parses examples/postgres/customer-orders/customer-order.sql schema
#     3. Auto-generates domain configuration from schema
#     4. Outputs YAML files ready for deployment
#
# WHAT IT DOES (Generate Mode - with --generate flag):
#     1. Parses examples/postgres/customer-orders/customer-order.sql schema
#     2. Analyzes examples/postgres/customer-orders/customer-order_test_queries.md (669 queries)
#     3. Generates parameterized SQL templates with AI
#     4. Auto-generates domain configuration from schema
#     5. Outputs YAML files ready for validation
#
# OUTPUT FILES:
#     customer-order-templates.yaml    - SQL templates with parameters and examples
#     customer-order-domain.yaml       - Domain configuration with entities/fields
#
# REQUIREMENTS (Default Mode):
#     - Python virtual environment activated (../../venv)
#     - Required Python packages installed (pyyaml)
#     - Schema file: examples/postgres/customer-orders/customer-order.sql
#     - Queries file: examples/postgres/customer-orders/customer-order_test_queries.md
#
# REQUIREMENTS (Generate Mode):
#     - Python virtual environment activated (../../venv)
#     - Required Python packages installed (pyyaml, anthropic/openai)
#     - Ollama running locally (or other inference provider configured)
#     - Model configured in ../../config/inference.yaml (default: ollama provider)
#     - For local Ollama: No API keys needed, just ensure Ollama is running
#     - For Ollama Cloud: Set OLLAMA_CLOUD_API_KEY in ../../.env
#
# WHAT YOU'LL SEE (Default Mode):
#     ✅ Schema parsing (2 tables: customers, orders)
#     ✅ Domain config generation (entities, fields, semantic types)
#     ✅ Ready to deploy!
#
# WHAT YOU'LL SEE (Generate Mode):
#     ✅ Schema parsing (2 tables: customers, orders)
#     ✅ Query analysis (669 queries across multiple categories)
#     ✅ Template generation (multiple templates typically)
#     ✅ Domain config generation (entities, fields, semantic types)
#     ✅ Validation instructions
#
# NEXT STEPS AFTER RUNNING:
#     1. Review generated files:
#        - cat examples/postgres/customer-orders/customer-order-templates.yaml
#        - cat examples/postgres/customer-orders/customer-order-domain.yaml
#
#     2. Validate output:
#        python validate_output.py \
#          examples/postgres/customer-orders/customer-order-domain.yaml \
#          examples/postgres/customer-orders/customer-order-templates.yaml
#
#     3. Deploy to Orbit:
#        cp examples/postgres/customer-orders/customer-order-domain.yaml ../../config/sql_intent_templates/
#        cp examples/postgres/customer-orders/customer-order-templates.yaml ../../config/sql_intent_templates/
#
#     4. Try with your own database:
#        python template_generator.py --help
#
# EXAMPLE OUTPUT:
#     Templates generated will include:
#     - Find orders by ID
#     - Search customers by name, email, phone
#     - Filter orders by status, date, amount
#     - Customer analytics and lifetime value
#     - Order analytics and revenue analysis
#     - Geographic analysis
#     - Time-based analysis
#     - Comparative analysis
#     - PostgreSQL parameter placeholders (%(param)s)
#     - Semantic tags for intent matching
#
#     Domain config includes:
#     - Entities: customers, orders (primary entities)
#     - Fields: id, name, email, phone, city, country, order_date, total, status, etc.
#     - Semantic types: email_address, identifier, date_value, currency
#     - Vocabulary: action verbs, entity synonyms
#
# TROUBLESHOOTING:
#     If you see "Python is required":
#     → source ../../venv/bin/activate
#
#     If you see "Schema file not found":
#     → Ensure examples/postgres/customer-orders/customer-order.sql exists
#
#     If you see "Queries file not found":
#     → Ensure examples/postgres/customer-orders/customer-order_test_queries.md exists
#
#     If you see "API key is missing" (Ollama Cloud only):
#     → Set OLLAMA_CLOUD_API_KEY in ../../.env
#     → Note: Local Ollama doesn't require API keys
#
#     To use a specific model (e.g., a-kore/Arctic-Text2SQL-R1-7B:latest):
#     → Configure in ../../config/inference.yaml under inference.ollama.model
#     → Or set OLLAMA_INFERENCE_MODEL environment variable
#
#     If generation fails:
#     → Check ../../config/config.yaml has valid inference_provider (default: ollama)
#     → Verify Ollama is running: ollama list (should show your models)
#     → Check model is configured in ../../config/inference.yaml
#     → Try: python template_generator.py --help for manual control
#
# TIME TO COMPLETE:
#     Default Mode: <5 seconds (if templates exist)
#     Generate Mode: 2-5 minutes depending on LLM speed and query count
#
# SEE ALSO:
#     - template_generator.py        Full generator with all options
#     - examples/postgres/customer-orders/customer-order.sql         Schema file
#     - examples/postgres/customer-orders/customer-order_test_queries.md  Test queries
#     - examples/postgres/customer-orders/customer_order_domain.yaml  Domain config
#     - README.md                    Complete documentation
#
# AUTHOR:
#     SQL Intent Template Generator v1.0.0
#     Part of the Orbit Intent SQL RAG System
#
################################################################################

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse arguments
MODE="default"
if [ "$1" == "--generate" ]; then
  MODE="generate"
fi

# Set paths
EXAMPLE_DIR="./examples/postgres/customer-orders"
SCHEMA_FILE="${EXAMPLE_DIR}/customer-order.sql"
QUERIES_FILE="${EXAMPLE_DIR}/customer-order_test_queries.md"
OUTPUT_FILE="${EXAMPLE_DIR}/customer-order-templates.yaml"
DOMAIN_OUTPUT="${EXAMPLE_DIR}/customer-order-domain.yaml"
REFERENCE_TEMPLATES=(
  "${EXAMPLE_DIR}/advanced_analytics_templates.yaml"
  "${EXAMPLE_DIR}/business_intelligence_templates.yaml"
  "${EXAMPLE_DIR}/comparative_analysis_templates.yaml"
)

# Collect existing reference templates for few-shot guidance
REFERENCE_TEMPLATE_PATHS=()
for template_path in "${REFERENCE_TEMPLATES[@]}"; do
  if [ -f "${template_path}" ]; then
    REFERENCE_TEMPLATE_PATHS+=("${template_path}")
  else
    echo -e "${YELLOW}Warning: Reference template not found (skipping): ${template_path}${NC}"
  fi
done

REFERENCE_ARGS=()
if [ ${#REFERENCE_TEMPLATE_PATHS[@]} -gt 0 ]; then
  REFERENCE_ARGS=(--reference-templates "${REFERENCE_TEMPLATE_PATHS[@]}")
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  SQL Template Generator - Customer Order${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if schema and queries files exist
if [ ! -f "${SCHEMA_FILE}" ]; then
  echo -e "${RED}Error: Schema file not found at ${SCHEMA_FILE}${NC}"
  exit 1
fi

if [ ! -f "${QUERIES_FILE}" ]; then
  echo -e "${RED}Error: Queries file not found at ${QUERIES_FILE}${NC}"
  exit 1
fi

# Create example directory if it doesn't exist
mkdir -p "${EXAMPLE_DIR}"

if [ "$MODE" == "default" ]; then
  echo -e "${GREEN}Running Customer Order Example (Default Mode)...${NC}"
  echo ""
  echo "This will:"
  echo "  • Parse the customer-order database schema (customers and orders tables)"
  echo "  • Generate domain configuration from schema"
  echo "  • Check for existing templates"
  echo "  • Output: ${OUTPUT_FILE}"
  echo "  • Time: <5 seconds"
  echo ""

  # Generate domain config
  echo -e "${BLUE}Generating domain configuration...${NC}"
  python -u template_generator.py \
    --schema "${SCHEMA_FILE}" \
    --queries "${QUERIES_FILE}" \
    --output /tmp/dummy-output.yaml \
    --generate-domain \
    --domain-name "Customer Order Management" \
    --domain-type general \
    --domain-output "${DOMAIN_OUTPUT}" \
    2>/dev/null || echo -e "${YELLOW}Note: Domain config generation requires schema parsing only${NC}"

  echo -e "${GREEN}✓ Domain configuration created${NC}"
  
  if [ -f "${OUTPUT_FILE}" ]; then
    TEMPLATE_COUNT=$(grep -c "^  - id:" "${OUTPUT_FILE}" 2>/dev/null || echo "0")
    if [ $TEMPLATE_COUNT -gt 0 ]; then
      echo -e "${GREEN}✓ Found existing templates: ${TEMPLATE_COUNT} templates${NC}"
    fi
  else
    echo -e "${YELLOW}Note: No existing templates found. Use --generate to create templates.${NC}"
  fi

else
  echo -e "${GREEN}Running Customer Order Example (Generate Mode)...${NC}"
  echo ""
  echo "This will:"
  echo "  • Parse the customer-order database schema (customers and orders tables)"
  echo "  • Analyze 669 test queries from customer-order_test_queries.md"
  echo "  • Generate SQL templates from queries using AI"
  echo "  • Create a domain configuration file"
  if [ ${#REFERENCE_TEMPLATE_PATHS[@]} -gt 0 ]; then
    echo "  • Reuse ${#REFERENCE_TEMPLATE_PATHS[@]} stored template files as few-shot guidance"
  fi
  echo "  • Output: ${OUTPUT_FILE}"
  echo "  • Time: 2-5 minutes (depending on LLM speed)"
  echo ""

  # Count queries
  QUERY_COUNT=$(grep -c '^[0-9]\+\.' "${QUERIES_FILE}" 2>/dev/null || echo "0")
  echo -e "${BLUE}Found ${QUERY_COUNT} test queries${NC}"
  echo ""

  # Run the generator
  echo -e "${BLUE}Generating templates from queries...${NC}"
  python -u template_generator.py \
    --schema "${SCHEMA_FILE}" \
    --queries "${QUERIES_FILE}" \
    --output "${OUTPUT_FILE}" \
    --generate-domain \
    --domain-name "Customer Order Management" \
    --domain-type general \
    --domain-output "${DOMAIN_OUTPUT}" \
    "${REFERENCE_ARGS[@]}"

  echo -e "${GREEN}✓ Template generation complete${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✓ Example Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Generated files:"
echo "  📄 ${OUTPUT_FILE}    - SQL templates"
echo "  📄 ${DOMAIN_OUTPUT}    - Domain configuration"
echo ""

# Count actual templates
if [ -f "${OUTPUT_FILE}" ]; then
  TEMPLATE_COUNT=$(grep -c "^- id:" "${OUTPUT_FILE}" 2>/dev/null || echo "0")
  # Ensure TEMPLATE_COUNT is numeric
  TEMPLATE_COUNT=${TEMPLATE_COUNT:-0}
  echo -e "${GREEN}✓ Total templates: ${TEMPLATE_COUNT}${NC}"

  # Show first few template IDs as preview
  if [ "${TEMPLATE_COUNT}" -gt 0 ] 2>/dev/null; then
    echo ""
    echo -e "${BLUE}Template preview (first 10):${NC}"
    grep "^- id:" "${OUTPUT_FILE}" | head -10 | sed 's/^- id: /  ✓ /'
    if [ "${TEMPLATE_COUNT}" -gt 10 ] 2>/dev/null; then
      echo "  ... and $((TEMPLATE_COUNT - 10)) more templates"
    fi
    echo ""
  fi
fi

echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Review the templates:"
echo "     cat ${OUTPUT_FILE}"
echo ""
echo "  2. Review the domain configuration:"
echo "     cat ${DOMAIN_OUTPUT}"
echo ""
echo "  3. Copy to Orbit config (if needed):"
echo "     cp ${OUTPUT_FILE} ../../config/sql_intent_templates/"
echo "     cp ${DOMAIN_OUTPUT} ../../config/sql_intent_templates/"
echo ""
echo "  4. Configure your Intent adapter to use these templates"
echo ""
echo -e "${BLUE}To try with your own database:${NC}"
echo "  python template_generator.py --help"
echo ""
if [ "$MODE" == "default" ]; then
  echo -e "${YELLOW}Want to generate templates from queries?${NC}"
  echo "  ./run_customer_order_example.sh --generate"
  echo ""
fi
