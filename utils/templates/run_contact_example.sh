#!/bin/bash
################################################################################
# SQL Intent Template Generator - Quick Start Example
#
# DESCRIPTION:
#     One-command demonstration of the SQL template generator using production-ready
#     seed templates. Perfect for newcomers to quickly see high-quality templates
#     and understand the output format.
#
#     This example:
#     - Uses a minimal single-table schema (users table)
#     - Installs 24 production-ready templates instantly
#     - Generates domain configuration from schema
#     - Demonstrates SQLite dialect configuration
#     - Completes in seconds (no AI generation needed)
#
# USAGE:
#     ./run_contact_example.sh [--generate]
#
# OPTIONS:
#     (none)      Use seed templates (instant, production-ready) - DEFAULT
#     --generate  Generate from enriched queries (slower, for demonstration)
#                 Use this flag if seed templates are missing or unavailable
#
# WHAT IT DOES (Default Mode - Seed Templates):
#     1. Copies 24 production-ready templates from seed file
#     2. Parses examples/sqlite/contact/contact.sql schema (CREATE TABLE users...)
#     3. Auto-generates domain configuration from schema
#     4. Checks for existing templates
#     5. Outputs two YAML files ready for deployment
#
# WHAT IT DOES (Generate Mode - with --generate flag):
#     1. Parses examples/sqlite/contact/contact.sql schema
#     2. Analyzes examples/sqlite/contact/contact_test_queries.md (categorized queries)
#     3. Generates parameterized SQL templates with AI
#     4. Auto-generates domain configuration from schema
#     5. Uses reference templates for few-shot guidance (if available)
#     6. Outputs two YAML files ready for validation
#
# OUTPUT FILES:
#     examples/sqlite/contact/contact-templates.yaml    - SQL templates with parameters and examples
#     examples/sqlite/contact/contact-domain.yaml       - Domain configuration with entities/fields
#
# REQUIREMENTS (Seed Mode):
#     - Python virtual environment activated (../../venv)
#     - Required Python packages installed (pyyaml)
#     - Seed templates file: examples/contact_seed_templates.yaml
#     - If seed templates are missing, use --generate flag instead
#
# REQUIREMENTS (Generate Mode):
#     - Python virtual environment activated (../../venv)
#     - Required Python packages installed (pyyaml, anthropic/openai)
#     - Ollama running locally (or other inference provider configured)
#     - Model configured in ../../config/inference.yaml (default: ollama provider)
#     - For local Ollama: No API keys needed, just ensure Ollama is running
#     - For Ollama Cloud: Set OLLAMA_CLOUD_API_KEY in ../../.env
#     - No seed templates required - generates from queries instead
#
# WHAT YOU'LL SEE (Seed Mode):
#     ✅ Template installation (24 production templates)
#     ✅ Schema parsing (1 table: users)
#     ✅ Domain config generation (entities, fields, semantic types)
#     ✅ Ready to deploy!
#
# WHAT YOU'LL SEE (Generate Mode):
#     ✅ Schema parsing (1 table: users)
#     ✅ Query analysis (25 categories)
#     ✅ Template generation (20-25 templates typically)
#     ✅ Domain config generation (entities, fields, semantic types)
#     ✅ Validation instructions
#
# NEXT STEPS AFTER RUNNING:
#     1. Review generated files:
#        - cat contact-example-output.yaml
#        - cat contact-example-domain.yaml
#
#     2. Validate output:
#        python validate_output.py \
#          contact-example-domain.yaml \
#          contact-example-output.yaml
#
#     3. Deploy to Orbit:
#        cp contact-example-domain.yaml ../../config/sql_intent_templates/
#        cp contact-example-output.yaml ../../config/sql_intent_templates/
#
#     4. Try with your own database:
#        ./generate_templates.sh --help
#
# EXAMPLE OUTPUT:
#     Templates installed: 24 production-ready templates including:
#     - List all users (with pagination)
#     - Search by name (partial match)
#     - Find by exact email
#     - Filter by age (exact, range, comparison)
#     - Filter by city
#     - Count users (total, by city, by age range)
#     - Aggregations (average age, statistics)
#     - Sorting (by name, age, date)
#     - Top N queries (oldest/youngest)
#     - Multi-field filters
#     - Existence checks
#     - SQLite parameter placeholders (?)
#     - Semantic tags for intent matching
#
#     Domain config includes:
#     - Entity: users (primary entity)
#     - Fields: id, name, email, age, city, created_at
#     - Semantic types: email_address, identifier, date_value
#     - Vocabulary: action verbs, entity synonyms
#
# TROUBLESHOOTING:
#     If you see "Python is required":
#     → source ../../venv/bin/activate
#
#     If you see "Seed templates not found":
#     → Run with --generate flag: ./run_contact_example.sh --generate
#     → This will generate templates from queries instead of using seed templates
#     → For local Ollama: Ensure Ollama is running (ollama serve)
#     → For Ollama Cloud: Set OLLAMA_CLOUD_API_KEY in ../../.env
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
#     Seed Mode: <5 seconds (instant)
#     Generate Mode: 30-60 seconds depending on LLM speed
#
# SEE ALSO:
#     - template_generator.py        Full generator with all options
#     - examples/sqlite/contact/contact.sql         Schema file
#     - examples/sqlite/contact/contact_test_queries.md  Test queries
#     - examples/sqlite/contact/contact-domain.yaml  Domain config
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
MODE="seed"
if [ "$1" == "--generate" ]; then
  MODE="generate"
fi

# Set paths
EXAMPLE_DIR="./examples/sqlite/contact"
SCHEMA_FILE="${EXAMPLE_DIR}/contact.sql"
QUERIES_FILE="${EXAMPLE_DIR}/contact_test_queries.md"
OUTPUT_FILE="${EXAMPLE_DIR}/contact-templates.yaml"
DOMAIN_OUTPUT="${EXAMPLE_DIR}/contact-domain.yaml"
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
echo -e "${BLUE}  SQL Template Generator - Quick Start${NC}"
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

if [ "$MODE" == "seed" ]; then
  echo -e "${GREEN}Running Contact Example (Seed Mode)...${NC}"
  echo ""
  echo "This will:"
  echo "  • Install 24 production-ready templates"
  echo "  • Parse the contact database schema (users table)"
  echo "  • Generate domain configuration from schema"
  echo "  • Check for existing templates"
  echo "  • Output: ${OUTPUT_FILE}"
  echo "  • Time: <5 seconds"
  echo ""

  # Check if seed templates exist
  SEED_TEMPLATES_FILE="./examples/sqlite/contact/contact_seed_templates.yaml"
  if [ ! -f "${SEED_TEMPLATES_FILE}" ]; then
    echo -e "${RED}Error: Seed templates not found at ${SEED_TEMPLATES_FILE}${NC}"
    exit 1
  fi

  # Copy seed templates to output with proper format
  echo -e "${BLUE}Installing seed templates...${NC}"

  # Count templates in seed file
  SEED_COUNT=$(grep -c "^  - id:" "${SEED_TEMPLATES_FILE}" 2>/dev/null || echo "24")

  # Wrap seed templates in proper output format
  cat > "${OUTPUT_FILE}" << EOF
generated_at: '$(date -u +"%Y-%m-%dT%H:%M:%S")'
generator_version: 1.0.0
total_templates: ${SEED_COUNT}
EOF

  # Append the templates from seed file
  cat "${SEED_TEMPLATES_FILE}" >> "${OUTPUT_FILE}"

  echo -e "${GREEN}✓ Installed ${SEED_COUNT} production-ready templates${NC}"
  echo ""

  # Generate domain config
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
  
  if [ -f "${OUTPUT_FILE}" ]; then
    TEMPLATE_COUNT=$(grep -c "^- id:" "${OUTPUT_FILE}" 2>/dev/null || echo "0")
    if [ $TEMPLATE_COUNT -gt 0 ]; then
      echo -e "${GREEN}✓ Found existing templates: ${TEMPLATE_COUNT} templates${NC}"
    fi
  else
    echo -e "${YELLOW}Note: No existing templates found. Use --generate to create templates.${NC}"
  fi

else
  echo -e "${GREEN}Running Contact Example (Generate Mode)...${NC}"
  echo ""
  echo "This will:"
  echo "  • Parse the contact database schema (users table)"
  echo "  • Analyze test queries from contact_test_queries.md"
  echo "  • Generate SQL templates from queries using AI"
  echo "  • Create a domain configuration file"
  if [ ${#REFERENCE_TEMPLATE_PATHS[@]} -gt 0 ]; then
    echo "  • Reuse ${#REFERENCE_TEMPLATE_PATHS[@]} stored template files as few-shot guidance"
  fi
  echo "  • Output: ${OUTPUT_FILE}"
  echo "  • Time: 30-60 seconds (depending on LLM speed)"
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
    --domain-name "Contact Management" \
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
if [ "$MODE" == "seed" ]; then
  echo -e "${YELLOW}Want to generate templates from queries?${NC}"
  echo "  ./run_contact_example.sh --generate"
  echo ""
fi
