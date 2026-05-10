#!/bin/bash
################################################################################
# SQL Intent Template Generator - Contact Example
#
# DESCRIPTION:
#     One-command demonstration of the SQL template generator for a contact/users
#     database. Uses a single-table SQLite schema (users) with 25 categorized
#     query types covering search, filtering, aggregation, sorting, and more.
#
# USAGE:
#     ./run_contact_example.sh [--generate]
#
# OPTIONS:
#     (none)      Use existing templates if available (instant) - DEFAULT
#     --generate  Generate from test queries using AI (30-60 seconds)
#                 Use this flag to create or regenerate templates
#
# WHAT IT DOES (Default Mode):
#     1. Checks for existing templates in examples/sqlite/contact/
#     2. Parses examples/sqlite/contact/contact.sql schema (CREATE TABLE users...)
#     3. Auto-generates domain configuration from schema
#     4. Outputs YAML files ready for deployment
#
# WHAT IT DOES (Generate Mode - with --generate flag):
#     1. Parses examples/sqlite/contact/contact.sql schema
#     2. Analyzes examples/sqlite/contact/contact_test_queries.md (125 queries)
#     3. Generates parameterized SQL templates with AI
#     4. Auto-generates domain configuration from schema
#     5. Outputs two YAML files ready for validation
#
# OUTPUT FILES:
#     examples/sqlite/contact/contact-templates.yaml  - SQL templates
#     examples/sqlite/contact/contact-domain.yaml     - Domain configuration
#
# REQUIREMENTS:
#     - Python virtual environment activated (../../venv)
#     - Required Python packages installed (pyyaml)
#     - For Generate Mode: Ollama running locally (or other inference provider)
#       Configure the provider in ../../config/inference.yaml
#
# WHAT YOU'LL SEE (Default Mode):
#     ✅ Schema parsing (1 table: users)
#     ✅ Domain config generation (entities, fields, semantic types)
#     ✅ Ready to deploy!
#
# WHAT YOU'LL SEE (Generate Mode):
#     ✅ Schema parsing (1 table: users)
#     ✅ Query analysis (25 categories, 125 queries)
#     ✅ Template generation (20-25 templates typically)
#     ✅ Domain config generation (entities, fields, semantic types)
#
# TROUBLESHOOTING:
#     If you see "Python is required":
#     → source ../../venv/bin/activate
#
#     If you see "API key is missing" (Ollama Cloud only):
#     → Set OLLAMA_CLOUD_API_KEY in ../../.env
#     → Note: Local Ollama doesn't require API keys
#
#     If generation fails:
#     → Check ../../config/config.yaml has valid inference_provider (default: ollama)
#     → Verify Ollama is running: ollama list
#     → Try: python template_generator.py --help for manual control
#
# TIME TO COMPLETE:
#     Default Mode: <5 seconds (if templates exist)
#     Generate Mode: 30-60 seconds depending on LLM speed
#
# SEE ALSO:
#     - template_generator.py                              Full generator
#     - examples/sqlite/contact/contact.sql                Schema file
#     - examples/sqlite/contact/contact_test_queries.md    Test queries
#     - README.md                                          Complete documentation
#
################################################################################

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse arguments: --generate forces regeneration; default auto-generates if no templates exist
MODE="default"
if [ "$1" == "--generate" ]; then
  MODE="generate"
fi

# Set paths
EXAMPLE_DIR="./examples/sqlite/contact"
SCHEMA_FILE="${EXAMPLE_DIR}/contact.sql"
QUERIES_FILE="${EXAMPLE_DIR}/contact_test_queries.md"
OUTPUT_FILE="${EXAMPLE_DIR}/contact-templates.yaml"
DOMAIN_OUTPUT="${EXAMPLE_DIR}/contact-domain.yaml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  SQL Template Generator - Contact${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check required files
if [ ! -f "${SCHEMA_FILE}" ]; then
  echo -e "${RED}Error: Schema file not found at ${SCHEMA_FILE}${NC}"
  exit 1
fi

if [ ! -f "${QUERIES_FILE}" ]; then
  echo -e "${RED}Error: Queries file not found at ${QUERIES_FILE}${NC}"
  exit 1
fi

mkdir -p "${EXAMPLE_DIR}"

# Auto-generate if no templates exist yet
if [ "$MODE" == "default" ] && [ ! -f "${OUTPUT_FILE}" ]; then
  echo -e "${YELLOW}No existing templates found — running generator automatically.${NC}"
  echo -e "${YELLOW}Re-run with --generate at any time to regenerate.${NC}"
  echo ""
  MODE="generate"
fi

if [ "$MODE" == "default" ]; then
  echo -e "${GREEN}Running Contact Example (Default Mode)...${NC}"
  echo ""
  echo "This will:"
  echo "  • Parse the contact database schema (users table)"
  echo "  • Generate domain configuration from schema"
  echo "  • Show existing templates"
  echo "  • Output: ${OUTPUT_FILE}"
  echo "  • Time: <5 seconds"
  echo ""

  echo -e "${BLUE}Generating domain configuration...${NC}"
  python -u template_generator.py \
    --schema "${SCHEMA_FILE}" \
    --queries "${QUERIES_FILE}" \
    --output /tmp/dummy-output.yaml \
    --generate-domain \
    --domain-name "Contact Management" \
    --domain-type general \
    --domain-output "${DOMAIN_OUTPUT}" \
    2>/dev/null || echo -e "${YELLOW}Note: Domain config generation requires schema parsing only${NC}"

  echo -e "${GREEN}✓ Domain configuration created${NC}"

else
  echo -e "${GREEN}Running Contact Example (Generate Mode)...${NC}"
  echo ""
  echo "This will:"
  echo "  • Parse the contact database schema (users table)"
  echo "  • Analyze test queries from contact_test_queries.md"
  echo "  • Generate SQL templates from queries using AI"
  echo "  • Create a domain configuration file"
  echo "  • Output: ${OUTPUT_FILE}"
  echo "  • Time: 30-60 seconds (depending on LLM speed)"
  echo ""

  QUERY_COUNT=$(grep -c '^[0-9]\+\.' "${QUERIES_FILE}" 2>/dev/null || echo "0")
  echo -e "${BLUE}Found ${QUERY_COUNT} test queries${NC}"
  echo ""

  echo -e "${BLUE}Generating templates from queries...${NC}"
  python -u template_generator.py \
    --schema "${SCHEMA_FILE}" \
    --queries "${QUERIES_FILE}" \
    --output "${OUTPUT_FILE}" \
    --generate-domain \
    --domain-name "Contact Management" \
    --domain-type general \
    --domain-output "${DOMAIN_OUTPUT}" \
    --dialect sqlite

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

# Count and preview templates
if [ -f "${OUTPUT_FILE}" ]; then
  TEMPLATE_COUNT=$(grep -c "^- id:" "${OUTPUT_FILE}" 2>/dev/null || echo "0")
  TEMPLATE_COUNT=${TEMPLATE_COUNT:-0}
  echo -e "${GREEN}✓ Total templates: ${TEMPLATE_COUNT}${NC}"

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
echo -e "${YELLOW}To regenerate templates from scratch:${NC}"
echo "  ./run_contact_example.sh --generate"
echo ""
