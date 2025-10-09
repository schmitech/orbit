#!/bin/bash

# Quick Start: Contact Example
# This script demonstrates the template generator with a simple contact database
#
# Usage: ./run_contact_example.sh

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  SQL Template Generator - Quick Start${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}Running Contact Example...${NC}"
echo ""
echo "This will:"
echo "  • Parse the contact database schema (users table)"
echo "  • Generate SQL templates from example queries"
echo "  • Create a domain configuration file"
echo "  • Output: contact-example-output.yaml"
echo ""

# Run the generator with contact example
./generate_templates.sh \
  --schema ./examples/contact.sql \
  --queries ./examples/contact_test_queries.md \
  --output contact-example-output.yaml \
  --domain configs/contact-config.yaml \
  --generate-domain \
  --domain-name "Contact Management" \
  --domain-type general \
  --domain-output contact-example-domain.yaml \
  --limit 10

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✓ Example Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Generated files:"
echo "  📄 contact-example-output.yaml    - SQL templates"
echo "  📄 contact-example-domain.yaml    - Domain configuration"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Review the generated templates in contact-example-output.yaml"
echo "  2. Copy contact-example-domain.yaml to ../../config/sql_intent_templates/"
echo "  3. Configure your Intent adapter to use these templates"
echo ""
echo -e "${BLUE}To try with your own database:${NC}"
echo "  ./generate_templates.sh --help"
echo ""
