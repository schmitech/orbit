#!/bin/bash
################################################################################
# Create Seed Templates from Schema
#
# This script generates seed template files from any schema by:
# 1. Using AI to generate templates from enriched queries
# 2. Providing guidance for manual review and refinement
# 3. Saving the result as a reusable seed template file
#
# USAGE:
#   ./create_seed_templates.sh <schema_name> [options]
#
# ARGUMENTS:
#   schema_name    Name of the example (e.g., classified-data, customer-order, library)
#
# OPTIONS:
#   --provider NAME    Inference provider (default: ollama_cloud)
#   --auto-save       Save directly without review (not recommended)
#   --skip-domain     Skip domain config generation
#
# EXAMPLES:
#   # Generate seed templates for classified-data
#   ./create_seed_templates.sh classified-data
#
#   # Use different provider
#   ./create_seed_templates.sh customer-order --provider anthropic
#
# PREREQUISITES:
#   1. Schema file exists: examples/<schema_name>.sql
#   2. Enriched queries exist: examples/<schema_name>_test_queries_enriched.md
#      (or create from examples/<schema_name>_test_queries.md)
#   3. Domain config exists (optional): config/sql_intent_templates/examples/<schema_name>/
#
# OUTPUT:
#   1. Auto-generated templates: /tmp/<schema_name>-auto-generated.yaml
#   2. Seed templates (after review): examples/<schema_name>_seed_templates.yaml
#
################################################################################

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Parse arguments
SCHEMA_NAME=""
PROVIDER="ollama_cloud"
AUTO_SAVE=false
SKIP_DOMAIN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --provider)
      PROVIDER="$2"
      shift 2
      ;;
    --auto-save)
      AUTO_SAVE=true
      shift
      ;;
    --skip-domain)
      SKIP_DOMAIN=true
      shift
      ;;
    --help)
      grep '^#' "$0" | cut -c 2-
      exit 0
      ;;
    *)
      if [ -z "$SCHEMA_NAME" ]; then
        SCHEMA_NAME="$1"
      else
        echo -e "${RED}Unknown argument: $1${NC}"
        exit 1
      fi
      shift
      ;;
  esac
done

# Validate schema name
if [ -z "$SCHEMA_NAME" ]; then
  echo -e "${RED}Error: Schema name required${NC}"
  echo ""
  echo "Usage: ./create_seed_templates.sh <schema_name>"
  echo "Example: ./create_seed_templates.sh classified-data"
  exit 1
fi

# Paths
SCHEMA_FILE="examples/${SCHEMA_NAME}.sql"
QUERIES_FILE_ENRICHED="examples/${SCHEMA_NAME}_test_queries_enriched.md"
QUERIES_FILE_ORIGINAL="examples/${SCHEMA_NAME}_test_queries.md"
DOMAIN_CONFIG="config/sql_intent_templates/examples/${SCHEMA_NAME}/*_domain.yaml"
OUTPUT_AUTO="/tmp/${SCHEMA_NAME}-auto-generated.yaml"
OUTPUT_SEED="examples/${SCHEMA_NAME}_seed_templates.yaml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Seed Template Generator${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Schema: ${YELLOW}${SCHEMA_NAME}${NC}"
echo -e "Provider: ${YELLOW}${PROVIDER}${NC}"
echo ""

# Check if schema exists
if [ ! -f "$SCHEMA_FILE" ]; then
  echo -e "${RED}Error: Schema file not found: $SCHEMA_FILE${NC}"
  exit 1
fi

# Check for enriched queries, fall back to original
QUERIES_FILE=""
if [ -f "$QUERIES_FILE_ENRICHED" ]; then
  QUERIES_FILE="$QUERIES_FILE_ENRICHED"
  echo -e "${GREEN}✓ Found enriched queries${NC}"
elif [ -f "$QUERIES_FILE_ORIGINAL" ]; then
  QUERIES_FILE="$QUERIES_FILE_ORIGINAL"
  echo -e "${YELLOW}⚠ Using original queries (consider creating enriched version)${NC}"
else
  echo -e "${RED}Error: No queries file found${NC}"
  echo "  Expected: $QUERIES_FILE_ENRICHED"
  echo "  Or: $QUERIES_FILE_ORIGINAL"
  exit 1
fi

# Find domain config
DOMAIN_ARG=""
if [ "$SKIP_DOMAIN" = false ]; then
  DOMAIN_FILE=$(ls $DOMAIN_CONFIG 2>/dev/null | head -1 || echo "")
  if [ -n "$DOMAIN_FILE" ]; then
    DOMAIN_ARG="--domain $DOMAIN_FILE"
    echo -e "${GREEN}✓ Found domain config: $(basename $DOMAIN_FILE)${NC}"
  else
    echo -e "${YELLOW}⚠ No domain config found (will generate basic templates)${NC}"
  fi
fi

echo ""
echo -e "${BLUE}Step 1: Generating Templates with AI...${NC}"
echo ""

# Generate templates
python template_generator.py \
  --schema "$SCHEMA_FILE" \
  --queries "$QUERIES_FILE" \
  --output "$OUTPUT_AUTO" \
  $DOMAIN_ARG \
  --config config/config.yaml \
  --provider "$PROVIDER"

# Count generated templates
TEMPLATE_COUNT=$(grep -c "^  - id:" "$OUTPUT_AUTO" 2>/dev/null || echo "0")

echo ""
echo -e "${GREEN}✓ Generated ${TEMPLATE_COUNT} templates${NC}"
echo -e "  Output: ${OUTPUT_AUTO}"
echo ""

# Show template IDs
echo -e "${BLUE}Template IDs generated:${NC}"
grep "^  - id:" "$OUTPUT_AUTO" | sed 's/  - id: /  • /' | head -20
if [ $TEMPLATE_COUNT -gt 20 ]; then
  echo "  ... and $((TEMPLATE_COUNT - 20)) more"
fi
echo ""

# Review guidance
if [ "$AUTO_SAVE" = false ]; then
  echo -e "${YELLOW}========================================${NC}"
  echo -e "${YELLOW}Step 2: Manual Review Required${NC}"
  echo -e "${YELLOW}========================================${NC}"
  echo ""
  echo "Please review and refine the generated templates:"
  echo ""
  echo "1. Open the file:"
  echo "   code $OUTPUT_AUTO"
  echo ""
  echo "2. Check each template for:"
  echo "   ✓ SQL correctness and optimization"
  echo "   ✓ Parameter defaults (no null values)"
  echo "   ✓ Clear descriptions"
  echo "   ✓ Good nl_examples (3-5 per template)"
  echo "   ✓ Appropriate tags"
  echo "   ✓ Correct result_format (table vs summary)"
  echo ""
  echo "3. Common fixes needed:"
  echo "   • Add missing indexes to SQL"
  echo "   • Improve WHERE clause logic"
  echo "   • Better parameter descriptions"
  echo "   • More diverse nl_examples"
  echo "   • Fix parameter order for readability"
  echo ""
  echo "4. Save your changes to: $OUTPUT_AUTO"
  echo ""
  echo -e "${BLUE}When ready, save as seed templates:${NC}"
  echo ""
  echo "  cp $OUTPUT_AUTO $OUTPUT_SEED"
  echo ""
  echo "Or run this script with --auto-save (not recommended)"
  echo ""

  # Offer to open in editor
  read -p "Open in default editor now? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    ${EDITOR:-nano} "$OUTPUT_AUTO"

    echo ""
    read -p "Save as seed templates? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      cp "$OUTPUT_AUTO" "$OUTPUT_SEED"
      echo -e "${GREEN}✓ Saved seed templates to: $OUTPUT_SEED${NC}"
    fi
  fi
else
  # Auto-save without review
  echo -e "${YELLOW}Auto-saving without review...${NC}"
  cp "$OUTPUT_AUTO" "$OUTPUT_SEED"
  echo -e "${GREEN}✓ Saved seed templates to: $OUTPUT_SEED${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Done!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Files created:"
echo "  📄 $OUTPUT_AUTO (AI-generated)"
if [ -f "$OUTPUT_SEED" ]; then
  echo "  📄 $OUTPUT_SEED (seed templates)"
fi
echo ""
echo "Next steps:"
echo "  1. Test the templates with your adapter"
echo "  2. Refine based on real queries"
echo "  3. Update enriched queries if needed"
echo "  4. Regenerate and iterate"
echo ""
