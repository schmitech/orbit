#!/bin/bash
#
# Regenerate Contact Templates with Enrichment
#
# This script regenerates SQL intent templates for the contact example
# using the enriched test queries to produce diverse, specific templates.
#
# Usage:
#   ./regenerate_contact_templates.sh [OPTIONS]
#
# Options:
#   --use-seed        Use seed templates directly (no generation)
#   --auto-only       Generate from enriched queries only
#   --hybrid          Generate and merge with seed templates (manual)
#   --provider NAME   Specify inference provider (default: ollama_cloud)
#   --limit N         Limit number of queries to process (for testing)
#
# Examples:
#   # Generate 20-25 templates from enriched queries
#   ./regenerate_contact_templates.sh --auto-only
#
#   # Use high-quality seed templates directly
#   ./regenerate_contact_templates.sh --use-seed
#
#   # Test with limited queries
#   ./regenerate_contact_templates.sh --auto-only --limit 50

set -e  # Exit on error

# Default values
MODE="auto-only"
PROVIDER="ollama_cloud"
LIMIT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --use-seed)
      MODE="seed"
      shift
      ;;
    --auto-only)
      MODE="auto-only"
      shift
      ;;
    --hybrid)
      MODE="hybrid"
      shift
      ;;
    --provider)
      PROVIDER="$2"
      shift 2
      ;;
    --limit)
      LIMIT="--limit $2"
      shift 2
      ;;
    --help)
      grep '^#' "$0" | cut -c 2-
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run with --help for usage information"
      exit 1
      ;;
  esac
done

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Paths (relative to orbit root)
ORBIT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
UTILS_DIR="$ORBIT_ROOT/utils/sql-intent-template"
EXAMPLES_DIR="$UTILS_DIR/examples"
CONFIG_DIR="$ORBIT_ROOT/config/sql_intent_templates/examples/contact"

SCHEMA_FILE="$EXAMPLES_DIR/contact.sql"
ENRICHED_QUERIES="$EXAMPLES_DIR/contact_test_queries_enriched.md"
SEED_TEMPLATES="$EXAMPLES_DIR/contact_seed_templates.yaml"
DOMAIN_CONFIG="$CONFIG_DIR/contact-domain.yaml"
OUTPUT_FILE="$CONFIG_DIR/contact-templates.yaml"
BACKUP_FILE="$CONFIG_DIR/contact-templates.backup.$(date +%Y%m%d_%H%M%S).yaml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Contact Template Regeneration${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Mode: ${YELLOW}$MODE${NC}"
echo -e "Provider: ${YELLOW}$PROVIDER${NC}"
echo -e "ORBIT Root: $ORBIT_ROOT"
echo ""

# Check if files exist
if [ ! -f "$SCHEMA_FILE" ]; then
  echo -e "${RED}Error: Schema file not found: $SCHEMA_FILE${NC}"
  exit 1
fi

if [ ! -f "$ENRICHED_QUERIES" ]; then
  echo -e "${RED}Error: Enriched queries file not found: $ENRICHED_QUERIES${NC}"
  exit 1
fi

if [ ! -f "$DOMAIN_CONFIG" ]; then
  echo -e "${RED}Error: Domain config not found: $DOMAIN_CONFIG${NC}"
  exit 1
fi

# Backup existing templates if they exist
if [ -f "$OUTPUT_FILE" ]; then
  echo -e "${YELLOW}Backing up existing templates...${NC}"
  cp "$OUTPUT_FILE" "$BACKUP_FILE"
  echo -e "  Backup saved to: $BACKUP_FILE"
  echo ""
fi

# Execute based on mode
cd "$ORBIT_ROOT"

case $MODE in
  seed)
    echo -e "${GREEN}Using seed templates directly...${NC}"
    if [ ! -f "$SEED_TEMPLATES" ]; then
      echo -e "${RED}Error: Seed templates not found: $SEED_TEMPLATES${NC}"
      exit 1
    fi

    cp "$SEED_TEMPLATES" "$OUTPUT_FILE"
    echo -e "${GREEN}✓ Copied seed templates to: $OUTPUT_FILE${NC}"

    # Count templates
    TEMPLATE_COUNT=$(grep -c "^  - id:" "$OUTPUT_FILE" || true)
    echo -e "${GREEN}✓ Installed ${TEMPLATE_COUNT} production-ready templates${NC}"
    ;;

  auto-only)
    echo -e "${GREEN}Generating templates from enriched queries...${NC}"
    echo ""

    python utils/sql-intent-template/template_generator.py \
      --schema "$SCHEMA_FILE" \
      --queries "$ENRICHED_QUERIES" \
      --domain "$DOMAIN_CONFIG" \
      --output "$OUTPUT_FILE" \
      --config config/config.yaml \
      --provider "$PROVIDER" \
      $LIMIT

    echo ""
    echo -e "${GREEN}✓ Templates generated successfully${NC}"

    # Count templates
    TEMPLATE_COUNT=$(grep -c "^  - id:" "$OUTPUT_FILE" || true)
    echo -e "${GREEN}✓ Generated ${TEMPLATE_COUNT} templates${NC}"

    # List template IDs
    echo ""
    echo -e "${BLUE}Template IDs:${NC}"
    grep "^  - id:" "$OUTPUT_FILE" | sed 's/.*id: /  - /' | head -20
    if [ $TEMPLATE_COUNT -gt 20 ]; then
      echo "  ... and $((TEMPLATE_COUNT - 20)) more"
    fi
    ;;

  hybrid)
    echo -e "${GREEN}Generating templates for hybrid approach...${NC}"

    # Generate to temp file
    TEMP_OUTPUT="/tmp/contact-auto-generated.yaml"

    python utils/sql-intent-template/template_generator.py \
      --schema "$SCHEMA_FILE" \
      --queries "$ENRICHED_QUERIES" \
      --domain "$DOMAIN_CONFIG" \
      --output "$TEMP_OUTPUT" \
      --config config/config.yaml \
      --provider "$PROVIDER" \
      $LIMIT

    echo ""
    echo -e "${GREEN}✓ Auto-generated templates saved to: $TEMP_OUTPUT${NC}"
    echo ""
    echo -e "${YELLOW}Next steps for hybrid approach:${NC}"
    echo "  1. Review auto-generated templates: $TEMP_OUTPUT"
    echo "  2. Review seed templates: $SEED_TEMPLATES"
    echo "  3. Manually merge the best of both into: $OUTPUT_FILE"
    echo "  4. Test merged templates with ORBIT"
    echo ""
    echo -e "${BLUE}Tips for merging:${NC}"
    echo "  - Use seed templates as foundation (high quality)"
    echo "  - Add unique auto-generated templates that add value"
    echo "  - Remove duplicates"
    echo "  - Validate all templates before deployment"
    ;;
esac

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Done!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}To use the new templates:${NC}"
echo "  1. Ensure adapter config has reload enabled:"
echo "     reload_templates_on_start: true"
echo "     force_reload_templates: true"
echo ""
echo "  2. Restart ORBIT server:"
echo "     python main.py"
echo ""
echo "  3. Test with queries:"
echo "     curl -X POST http://localhost:8718/api/v1/chat \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -H 'x-api-key: demo-contact-key' \\"
echo "       -d '{\"session_id\":\"test\",\"message\":\"Find users from New York aged 25-35\"}'"
echo ""

if [ -f "$BACKUP_FILE" ]; then
  echo -e "${YELLOW}Note: Previous templates backed up to:${NC}"
  echo "  $BACKUP_FILE"
  echo ""
fi

echo -e "${GREEN}Template regeneration complete!${NC}"
