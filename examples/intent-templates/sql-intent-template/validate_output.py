#!/usr/bin/env python3
"""
Validation Script for Intent SQL Template Generator Output

DESCRIPTION:
    Validates that generated domain configuration and SQL template files match
    the expected structure required by the Orbit Intent SQL Retriever adapter.

    This script checks:
    - Domain configuration structure (entities, fields, relationships, vocabulary)
    - Template library structure (templates, parameters, semantic tags)
    - Required vs optional fields
    - Data type validity
    - Semantic type configuration
    - Parameter definitions

USAGE:
    python validate_output.py <domain_config.yaml> <templates.yaml>

ARGUMENTS:
    domain_config.yaml    Path to the generated domain configuration file
    templates.yaml        Path to the generated SQL template library file

EXAMPLES:
    # Validate contact example output
    python validate_output.py contact-example-domain.yaml contact-example-output.yaml

    # Validate custom domain
    python validate_output.py my-domain.yaml my-templates.yaml

    # Validate with absolute paths
    python validate_output.py /path/to/domain.yaml /path/to/templates.yaml

OUTPUT:
    The script prints validation results showing:
    - ✅ Success messages for valid structures
    - ❌ Errors for missing required fields or invalid structures
    - ⚠️  Warnings for missing recommended fields

    Exit codes:
    - 0: All validations passed (no errors)
    - 1: Validation failed (has errors) or files not found

VALIDATION CHECKS:

    Domain Configuration:
    - Required fields: domain_name, description, entities, fields, relationships, vocabulary
    - Optional fields: domain_type, semantic_types (recommended)
    - Entity structure: name, entity_type, table_name, primary_key, display_name_field
    - Field structure: name, data_type, db_column, description, required, searchable, filterable, sortable
    - Relationship structure: name, from_entity, to_entity, relation_type, from_field, to_field
    - Vocabulary structure: entity_synonyms, action_verbs, field_synonyms
    - Semantic types: description, patterns, regex_patterns

    Template Library:
    - Required fields: templates (list)
    - Template structure: id, description, nl_examples, parameters, result_format
    - SQL query: sql or sql_template field
    - Parameters: name, type, description, required
    - Semantic tags: action, primary_entity (recommended)
    - Approved field (recommended for production use)

WHEN TO USE:
    - After generating templates with template_generator.py
    - Before deploying to config/sql_intent_templates/
    - Before starting Orbit server with new domain configs
    - When troubleshooting Intent adapter loading issues
    - As part of CI/CD validation pipeline

SEE ALSO:
    - compare_structures.py: Compare with reference examples
    - test_adapter_loading.py: Test Intent adapter loading
    - VALIDATION_REPORT.md: Full validation report and deployment guide
    - README.md: Generator usage and configuration

AUTHOR:
    SQL Intent Template Generator v1.0.0
    Part of the Orbit Intent SQL RAG System
"""

import yaml
import sys
from pathlib import Path
from typing import Dict, List, Any

class IntentConfigValidator:
    """Validates domain config and template files against expected schema"""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate_domain_config(self, config_path: str) -> bool:
        """Validate domain configuration file structure"""
        print(f"📋 Validating Domain Config: {config_path}")
        print("=" * 60)

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            self.errors.append(f"Failed to load domain config: {e}")
            return False

        # Check required top-level fields
        required_fields = ['domain_name', 'description', 'entities', 'fields', 'relationships', 'vocabulary']
        for field in required_fields:
            if field not in config:
                self.errors.append(f"Missing required field: {field}")

        # Check optional but recommended fields
        if 'domain_type' not in config:
            self.warnings.append("Missing 'domain_type' field (recommended)")

        if 'semantic_types' not in config:
            self.warnings.append("Missing 'semantic_types' field (recommended for better parameter extraction)")

        # Validate entities structure
        if 'entities' in config:
            self._validate_entities(config['entities'])

        # Validate fields structure
        if 'fields' in config:
            self._validate_fields(config['fields'])

        # Validate relationships structure
        if 'relationships' in config:
            self._validate_relationships(config['relationships'])

        # Validate vocabulary structure
        if 'vocabulary' in config:
            self._validate_vocabulary(config['vocabulary'])

        # Validate semantic_types if present
        if 'semantic_types' in config:
            self._validate_semantic_types(config['semantic_types'])

        return len(self.errors) == 0

    def _validate_entities(self, entities: Dict[str, Any]):
        """Validate entities structure"""
        required_entity_fields = ['name', 'entity_type', 'table_name', 'primary_key', 'display_name_field']

        for entity_name, entity_config in entities.items():
            for field in required_entity_fields:
                if field not in entity_config:
                    self.errors.append(f"Entity '{entity_name}' missing required field: {field}")

            # Check entity_type is valid
            if 'entity_type' in entity_config:
                valid_types = ['primary', 'transaction', 'reference', 'lookup']
                if entity_config['entity_type'] not in valid_types:
                    self.warnings.append(f"Entity '{entity_name}' has unusual entity_type: {entity_config['entity_type']}")

    def _validate_fields(self, fields: Dict[str, Dict[str, Any]]):
        """Validate fields structure"""
        required_field_attrs = ['name', 'data_type', 'db_column', 'description', 'required',
                               'searchable', 'filterable', 'sortable']

        for entity_name, entity_fields in fields.items():
            for field_name, field_config in entity_fields.items():
                for attr in required_field_attrs:
                    if attr not in field_config:
                        self.errors.append(f"Field '{entity_name}.{field_name}' missing required attribute: {attr}")

                # Check data_type is valid
                if 'data_type' in field_config:
                    valid_types = ['string', 'integer', 'decimal', 'datetime', 'date', 'boolean', 'enum']
                    if field_config['data_type'] not in valid_types:
                        self.warnings.append(f"Field '{entity_name}.{field_name}' has unusual data_type: {field_config['data_type']}")

    def _validate_relationships(self, relationships: List[Dict[str, Any]]):
        """Validate relationships structure"""
        required_rel_fields = ['name', 'from_entity', 'to_entity', 'relation_type', 'from_field', 'to_field']

        for i, rel in enumerate(relationships):
            for field in required_rel_fields:
                if field not in rel:
                    self.errors.append(f"Relationship {i} missing required field: {field}")

    def _validate_vocabulary(self, vocabulary: Dict[str, Any]):
        """Validate vocabulary structure"""
        recommended_vocab_fields = ['entity_synonyms', 'action_verbs', 'field_synonyms']

        for field in recommended_vocab_fields:
            if field not in vocabulary:
                self.warnings.append(f"Vocabulary missing recommended field: {field}")

    def _validate_semantic_types(self, semantic_types: Dict[str, Any]):
        """Validate semantic_types structure"""
        for type_name, type_config in semantic_types.items():
            if 'description' not in type_config:
                self.warnings.append(f"Semantic type '{type_name}' missing description")
            if 'patterns' not in type_config and 'regex_patterns' not in type_config:
                self.warnings.append(f"Semantic type '{type_name}' missing patterns/regex_patterns")

    def validate_template_library(self, template_path: str) -> bool:
        """Validate template library file structure"""
        print(f"\n📋 Validating Template Library: {template_path}")
        print("=" * 60)

        try:
            with open(template_path, 'r') as f:
                library = yaml.safe_load(f)
        except Exception as e:
            self.errors.append(f"Failed to load template library: {e}")
            return False

        # Check for templates
        if 'templates' not in library:
            self.errors.append("Template library missing 'templates' field")
            return False

        templates = library['templates']
        if not isinstance(templates, list):
            self.errors.append("'templates' must be a list")
            return False

        # Validate each template
        for i, template in enumerate(templates):
            self._validate_template(template, i)

        return len(self.errors) == 0

    def _validate_template(self, template: Dict[str, Any], index: int):
        """Validate individual template structure"""
        required_template_fields = ['id', 'description', 'nl_examples', 'parameters', 'result_format']

        for field in required_template_fields:
            if field not in template:
                self.errors.append(f"Template {index} (id: {template.get('id', 'unknown')}) missing required field: {field}")

        # Check SQL field (can be 'sql' or 'sql_template')
        if 'sql' not in template and 'sql_template' not in template:
            self.errors.append(f"Template {index} (id: {template.get('id', 'unknown')}) missing SQL query ('sql' or 'sql_template')")

        # Validate parameters
        if 'parameters' in template and template['parameters']:
            self._validate_template_parameters(template['parameters'], template.get('id', 'unknown'))

        # Validate semantic_tags
        if 'semantic_tags' not in template:
            self.warnings.append(f"Template '{template.get('id', 'unknown')}' missing semantic_tags (recommended)")
        else:
            self._validate_semantic_tags(template['semantic_tags'], template.get('id', 'unknown'))

        # Check approved field
        if 'approved' not in template:
            self.warnings.append(f"Template '{template.get('id', 'unknown')}' missing 'approved' field")

    def _validate_template_parameters(self, parameters: List[Dict[str, Any]], template_id: str):
        """Validate template parameters"""
        required_param_fields = ['name', 'type', 'description', 'required']

        for param in parameters:
            for field in required_param_fields:
                if field not in param:
                    self.errors.append(f"Template '{template_id}' parameter '{param.get('name', 'unknown')}' missing field: {field}")

            # Check type is valid
            if 'type' in param:
                valid_types = ['string', 'integer', 'decimal', 'date', 'datetime', 'boolean', 'enum']
                if param['type'] not in valid_types:
                    self.warnings.append(f"Template '{template_id}' parameter '{param['name']}' has unusual type: {param['type']}")

    def _validate_semantic_tags(self, semantic_tags: Dict[str, Any], template_id: str):
        """Validate semantic tags structure"""
        required_tag_fields = ['action', 'primary_entity']

        for field in required_tag_fields:
            if field not in semantic_tags:
                self.warnings.append(f"Template '{template_id}' semantic_tags missing field: {field}")

    def print_results(self):
        """Print validation results"""
        print("\n" + "=" * 60)
        print("VALIDATION RESULTS")
        print("=" * 60)

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  ❌ {error}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")

        if not self.errors and not self.warnings:
            print("\n✅ ALL CHECKS PASSED!")
            print("   Generated files are fully compatible with the Intent SQL Retriever adapter.")
        elif not self.errors:
            print("\n✅ NO ERRORS FOUND")
            print("   Files are compatible but could be improved (see warnings above).")
        else:
            print("\n❌ VALIDATION FAILED")
            print(f"   Found {len(self.errors)} errors and {len(self.warnings)} warnings.")
            print("   Fix errors before using with Intent adapter.")

        return len(self.errors) == 0

def main():
    """Main validation function"""
    if len(sys.argv) < 3:
        print("Usage: python validate_output.py <domain_config.yaml> <templates.yaml>")
        print("\nExample:")
        print("  python validate_output.py contact-example-domain.yaml contact-example-output.yaml")
        sys.exit(1)

    domain_path = sys.argv[1]
    template_path = sys.argv[2]

    # Check files exist
    if not Path(domain_path).exists():
        print(f"❌ Domain config file not found: {domain_path}")
        sys.exit(1)

    if not Path(template_path).exists():
        print(f"❌ Template file not found: {template_path}")
        sys.exit(1)

    # Run validation
    validator = IntentConfigValidator()

    validator.validate_domain_config(domain_path)
    validator.validate_template_library(template_path)

    success = validator.print_results()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
