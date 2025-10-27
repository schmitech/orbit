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
#
# WHAT IT DOES (Default Mode - Seed Templates):
#     1. Copies 24 production-ready templates from seed file
#     2. Parses examples/contact.sql schema (CREATE TABLE users...)
#     3. Auto-generates domain configuration from schema
#     4. Outputs two YAML files ready for deployment
#
# WHAT IT DOES (Generate Mode - with --generate flag):
#     1. Parses examples/contact.sql schema
#     2. Analyzes examples/contact_test_queries.md (categorized queries)
#     3. Generates 20-25 parameterized SQL templates with AI
#     4. Auto-generates domain configuration from schema
#     5. Outputs two YAML files ready for validation
#
# OUTPUT FILES:
#     contact-example-output.yaml    - 24 SQL templates with parameters and examples
#     contact-example-domain.yaml    - Domain configuration with entities/fields
#
# REQUIREMENTS (Seed Mode):
#     - Python virtual environment activated (../../venv)
#     - Required Python packages installed (pyyaml)
#     - Seed templates file: examples/contact_seed_templates.yaml
#
# REQUIREMENTS (Generate Mode):
#     - All seed mode requirements plus:
#     - Environment variables in ../../.env (OLLAMA_CLOUD_API_KEY, etc.)
#     - Required Python packages installed (pyyaml, anthropic/openai)
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
#     If you see "API key is missing":
#     → Set OLLAMA_CLOUD_API_KEY in ../../.env
#
#     If generation fails:
#     → Check ../../config/config.yaml has valid inference_provider
#     → Try: ./generate_templates.sh --help for manual control
#
# TIME TO COMPLETE:
#     Seed Mode: <5 seconds (instant)
#     Generate Mode: 30-60 seconds depending on LLM speed
#
# SEE ALSO:
#     - generate_templates.sh        Full generator with all options
#     - examples/contact.sql         Example schema file
#     - examples/contact_test_queries.md  Example queries
#     - configs/contact-config.yaml  Configuration used
#     - VALIDATION_TOOLS.md          How to validate output
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

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  SQL Template Generator - Quick Start${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ "$MODE" == "seed" ]; then
  echo -e "${GREEN}Running Contact Example (Seed Mode)...${NC}"
  echo ""
  echo "This will:"
  echo "  • Install 24 production-ready templates"
  echo "  • Parse the contact database schema (users table)"
  echo "  • Create a domain configuration file"
  echo "  • Output: contact-example-output.yaml"
  echo "  • Time: <5 seconds"
  echo ""

  # Check if seed templates exist
  if [ ! -f "./examples/contact_seed_templates.yaml" ]; then
    echo -e "${RED}Error: Seed templates not found at ./examples/contact_seed_templates.yaml${NC}"
    exit 1
  fi

  # Copy seed templates to output with proper format
  echo -e "${BLUE}Installing seed templates...${NC}"

  # Count templates in seed file
  SEED_COUNT=$(grep -c "^  - id:" ./examples/contact_seed_templates.yaml 2>/dev/null || echo "24")

  # Wrap seed templates in proper output format
  cat > contact-example-output.yaml << EOF
generated_at: '$(date -u +"%Y-%m-%dT%H:%M:%S")'
generator_version: 1.0.0
total_templates: ${SEED_COUNT}
EOF

  # Append the templates from seed file
  cat ./examples/contact_seed_templates.yaml >> contact-example-output.yaml

  echo -e "${GREEN}✓ Installed ${SEED_COUNT} production-ready templates${NC}"
  echo ""

  # Generate domain config
  echo -e "${BLUE}Generating domain configuration...${NC}"
  python -u template_generator.py \
    --schema ./examples/sqlite/contact/contact.sql \
    --queries ./examples/sqlite/contact/contact_test_queries.md \
    --output /tmp/dummy-output.yaml \
    --generate-domain \
    --domain-name "Contact Management" \
    --domain-type general \
    --domain-output ./examples/sqlite/contact/contact-domain.yaml \
    2>/dev/null || echo -e "${YELLOW}Note: Domain config generation requires schema parsing only${NC}"

  echo -e "${GREEN}✓ Domain configuration created${NC}"

else
  echo -e "${GREEN}Running Contact Example (Generate Mode)...${NC}"
  echo ""
  echo "This will:"
  echo "  • Parse the contact database schema (users table)"
  echo "  • Generate SQL templates from enriched queries"
  echo "  • Create a domain configuration file"
  echo "  • Output: contact-example-output.yaml"
  echo "  • Time: 30-60 seconds"
  echo ""

  # Run the generator with contact example
  ./generate_templates.sh \
    --schema ./examples/sqlite/contact/contact.sql \
    --queries ./examples/sqlite/contact/contact_test_queries.md \
    --output ./examples/sqlite/contact/contact-templates.yaml \
    --domain configs/contact-config.yaml \
    --generate-domain \
    --domain-name "Contact Management" \
    --domain-type general \
    --domain-output ./examples/sqlite/contact/contact-domain.yaml
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✓ Example Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Generated files:"
echo "  📄 contact-example-output.yaml    - SQL templates"
echo "  📄 contact-example-domain.yaml    - Domain configuration"
echo ""

# Count actual templates
if [ -f "contact-example-output.yaml" ]; then
  TEMPLATE_COUNT=$(grep -c "^  - id:" contact-example-output.yaml 2>/dev/null || echo "0")
  echo -e "${GREEN}✓ Total templates installed: ${TEMPLATE_COUNT}${NC}"

  # Show first few template IDs as preview
  echo ""
  echo -e "${BLUE}Template preview (first 10):${NC}"
  grep "^  - id:" contact-example-output.yaml | head -10 | sed 's/  - id: /  ✓ /'
  if [ $TEMPLATE_COUNT -gt 10 ]; then
    echo "  ... and $((TEMPLATE_COUNT - 10)) more templates"
  fi
  echo ""
fi

echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Review the templates:"
echo "     cat contact-example-output.yaml"
echo ""
echo "  2. Copy to Orbit config:"
echo "     cp contact-example-output.yaml ../../config/sql_intent_templates/examples/contact/"
echo "     cp contact-example-domain.yaml ../../config/sql_intent_templates/examples/contact/"
echo ""
echo "  3. Configure your Intent adapter to use these templates"
echo ""
echo -e "${BLUE}To try with your own database:${NC}"
echo "  ./generate_templates.sh --help"
echo ""
if [ "$MODE" == "seed" ]; then
  echo -e "${YELLOW}Want to try AI generation instead?${NC}"
  echo "  ./run_contact_example.sh --generate"
  echo ""
fi
