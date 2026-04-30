#!/usr/bin/env python3
"""
Structure Comparison Script for Intent SQL Template Generator

DESCRIPTION:
    Compares the structure of generated domain configuration and template files
    with official Orbit reference examples to ensure compatibility.

    This script performs a deep structural comparison to identify:
    - Missing fields that exist in reference but not in generated files
    - Extra fields in generated files that aren't in reference
    - Common fields that match between both
    - Critical field presence validation

USAGE:
    python compare_structures.py <gen_domain> <gen_templates> <ref_domain> <ref_templates>

ARGUMENTS:
    gen_domain       Path to generated domain configuration file
    gen_templates    Path to generated template library file
    ref_domain       Path to reference domain configuration file
    ref_templates    Path to reference template library file

EXAMPLES:
    # Compare contact example with customer-orders reference
    python compare_structures.py \
      contact-example-domain.yaml \
      contact-example-output.yaml \
      ../../config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml \
      ../../config/sql_intent_templates/examples/customer-orders/postgres_customer_orders.yaml

    # Compare with healthcare reference
    python compare_structures.py \
      my-domain.yaml \
      my-templates.yaml \
      ../../config/sql_intent_templates/examples/healthcare/healthcare_domain.yaml \
      ../../config/sql_intent_templates/examples/healthcare/healthcare_templates.yaml

OUTPUT:
    Displays detailed comparison showing:
    - 📊 Structure analysis (common, missing, extra fields)
    - ⚠️  Fields in reference but not in generated
    - ✨ Extra fields in generated (not in reference)
    - ✅ Critical field presence check

    Exit codes:
    - 0: Structures match or only minor differences
    - 1: Significant structural differences or files not found

NOTES:
    - Differences don't always indicate errors - domain complexity varies
    - Reference examples may have more entities/fields than your domain
    - Focus on critical fields matching rather than exact structure match
    - Extra fields in generated files are usually fine

WHEN TO USE:
    - When validating against a specific reference implementation
    - To understand structural differences from examples
    - Before deploying to production to verify completeness
    - When creating domain configs based on existing examples

SEE ALSO:
    - validate_output.py: Validate structure against schema
    - test_adapter_loading.py: Test Intent adapter loading
    - docs/intent-sql-rag-system.md: Full documentation

AUTHOR:
    SQL Intent Template Generator v1.0.0
    Part of the Orbit Intent SQL RAG System
"""

import yaml
import sys
from pathlib import Path
from typing import Any, Set

class StructureComparator:
    """Compare YAML structure between generated and reference files"""

    def __init__(self):
        self.differences = []
        self.matches = []

    def get_structure(self, data: Any, prefix: str = "") -> Set[str]:
        """Recursively extract structure keys from nested dict/list"""
        keys = set()

        if isinstance(data, dict):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                keys.add(full_key)
                keys.update(self.get_structure(value, full_key))
        elif isinstance(data, list) and data:
            # For lists, analyze first element
            keys.update(self.get_structure(data[0], prefix + "[0]"))

        return keys

    def compare_domain_configs(self, generated_path: str, reference_path: str):
        """Compare domain config structures"""
        print("🔍 Comparing Domain Config Structures")
        print("=" * 60)

        with open(generated_path, 'r') as f:
            generated = yaml.safe_load(f)

        with open(reference_path, 'r') as f:
            reference = yaml.safe_load(f)

        gen_structure = self.get_structure(generated)
        ref_structure = self.get_structure(reference)

        # Fields in reference but not in generated
        missing = ref_structure - gen_structure
        # Fields in generated but not in reference
        extra = gen_structure - ref_structure
        # Common fields
        common = gen_structure & ref_structure

        print("\n📊 Domain Config Structure Analysis:")
        print(f"   Generated file:  {generated_path}")
        print(f"   Reference file:  {reference_path}")
        print(f"\n   Common fields:   {len(common)}")
        print(f"   Missing fields:  {len(missing)}")
        print(f"   Extra fields:    {len(extra)}")

        if missing:
            print("\n⚠️  Fields in reference but not in generated:")
            for field in sorted(missing):
                print(f"     - {field}")
                self.differences.append(f"Missing: {field}")

        if extra:
            print("\n✨ Extra fields in generated (not in reference):")
            for field in sorted(extra):
                print(f"     - {field}")

        # Check critical domain config fields
        critical_fields = [
            'domain_name', 'description', 'entities', 'fields',
            'relationships', 'vocabulary'
        ]

        print("\n✅ Critical Field Check:")
        for field in critical_fields:
            if field in generated:
                print(f"   ✅ {field}: present")
                self.matches.append(f"Critical field '{field}' present")
            else:
                print(f"   ❌ {field}: MISSING")
                self.differences.append(f"Critical field '{field}' missing")

        return len(missing) == 0

    def compare_template_libraries(self, generated_path: str, reference_path: str):
        """Compare template library structures"""
        print("\n🔍 Comparing Template Library Structures")
        print("=" * 60)

        with open(generated_path, 'r') as f:
            generated = yaml.safe_load(f)

        with open(reference_path, 'r') as f:
            reference = yaml.safe_load(f)

        if 'templates' not in generated or 'templates' not in reference:
            print("❌ Templates field missing")
            return False

        # Get structure from first template of each
        gen_templates = generated['templates']
        ref_templates = reference['templates']

        if not gen_templates or not ref_templates:
            print("❌ Empty templates list")
            return False

        gen_structure = self.get_structure(gen_templates[0])
        ref_structure = self.get_structure(ref_templates[0])

        missing = ref_structure - gen_structure
        extra = gen_structure - ref_structure
        common = gen_structure & ref_structure

        print("\n📊 Template Structure Analysis:")
        print(f"   Generated file:  {generated_path}")
        print(f"   Reference file:  {reference_path}")
        print(f"\n   Common fields:   {len(common)}")
        print(f"   Missing fields:  {len(missing)}")
        print(f"   Extra fields:    {len(extra)}")

        if missing:
            print("\n⚠️  Fields in reference template but not in generated:")
            for field in sorted(missing):
                print(f"     - {field}")
                self.differences.append(f"Template missing: {field}")

        if extra:
            print("\n✨ Extra fields in generated template:")
            for field in sorted(extra):
                print(f"     - {field}")

        # Check critical template fields
        critical_fields = [
            'id', 'description', 'nl_examples', 'parameters',
            'result_format', 'semantic_tags'
        ]

        print("\n✅ Critical Template Field Check:")
        gen_template = gen_templates[0]
        for field in critical_fields:
            # Check for 'sql' or 'sql_template'
            if field == 'sql' and 'sql_template' in gen_template:
                print("   ✅ sql (as sql_template): present")
                self.matches.append("Critical field 'sql' present")
            elif field in gen_template:
                print(f"   ✅ {field}: present")
                self.matches.append(f"Critical field '{field}' present")
            else:
                print(f"   ❌ {field}: MISSING")
                self.differences.append(f"Critical field '{field}' missing")

        return len(missing) == 0

    def print_summary(self):
        """Print comparison summary"""
        print("\n" + "=" * 60)
        print("COMPARISON SUMMARY")
        print("=" * 60)

        print(f"\n✅ Matches: {len(self.matches)}")
        for match in self.matches:
            print(f"   ✅ {match}")

        if self.differences:
            print(f"\n⚠️  Differences: {len(self.differences)}")
            for diff in self.differences:
                print(f"   ⚠️  {diff}")

        if not self.differences:
            print("\n✅ STRUCTURES MATCH!")
            print("   Generated files are compatible with Intent adapter.")
        else:
            print("\n⚠️  MINOR DIFFERENCES FOUND")
            print("   Files may still be compatible, check differences above.")

        return len(self.differences) == 0

def main():
    """Main comparison function"""
    if len(sys.argv) < 5:
        print("Usage: python compare_structures.py <gen_domain> <gen_templates> <ref_domain> <ref_templates>")
        print("\nExample:")
        print("  python compare_structures.py \\")
        print("    contact-example-domain.yaml \\")
        print("    contact-example-output.yaml \\")
        print("    ../../config/sql_intent_templates/examples/customer-orders/customer_order_domain.yaml \\")
        print("    ../../config/sql_intent_templates/examples/customer-orders/postgres_customer_orders.yaml")
        sys.exit(1)

    gen_domain = sys.argv[1]
    gen_templates = sys.argv[2]
    ref_domain = sys.argv[3]
    ref_templates = sys.argv[4]

    # Check files exist
    for path in [gen_domain, gen_templates, ref_domain, ref_templates]:
        if not Path(path).exists():
            print(f"❌ File not found: {path}")
            sys.exit(1)

    # Run comparison
    comparator = StructureComparator()

    comparator.compare_domain_configs(gen_domain, ref_domain)
    comparator.compare_template_libraries(gen_templates, ref_templates)

    success = comparator.print_summary()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
