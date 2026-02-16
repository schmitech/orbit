#!/usr/bin/env python3
"""
GraphQL Template Validator

Validates GraphQL intent templates and domain configurations for correctness.
Checks GraphQL syntax, parameter definitions, and required fields.

Usage:
    python validate_output.py --templates templates.yaml
    python validate_output.py --templates templates.yaml --domain domain.yaml
    python validate_output.py --templates templates.yaml --strict
"""

import argparse
import re
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Any


# Required fields for templates
REQUIRED_TEMPLATE_FIELDS = [
    'id',
    'description',
    'graphql_template',
    'parameters',
    'nl_examples',
]

# Optional but recommended fields
RECOMMENDED_TEMPLATE_FIELDS = [
    'version',
    'graphql_type',
    'semantic_tags',
    'response_mapping',
    'result_format',
]

# Required fields for domain configuration
REQUIRED_DOMAIN_FIELDS = [
    'domain_name',
    'domain_type',
    'version',
]

# Valid GraphQL operation types
VALID_GRAPHQL_TYPES = ['query', 'mutation', 'subscription']

# Valid parameter types
VALID_PARAM_TYPES = ['string', 'integer', 'float', 'boolean', 'object', 'array']


class ValidationResult:
    """Container for validation results."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def add_error(self, message: str):
        self.errors.append(message)

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_info(self, message: str):
        self.info.append(message)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def print_results(self):
        """Print all validation results."""
        if self.errors:
            print("\n❌ ERRORS:")
            for error in self.errors:
                print(f"  • {error}")

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  • {warning}")

        if self.info:
            print("\n📋 INFO:")
            for info in self.info:
                print(f"  • {info}")

        if self.is_valid:
            print("\n✅ Validation passed!")
        else:
            print(f"\n❌ Validation failed with {len(self.errors)} error(s)")


def validate_graphql_syntax(graphql_template: str, template_id: str) -> List[str]:
    """
    Perform basic GraphQL syntax validation.

    Args:
        graphql_template: The GraphQL operation string
        template_id: Template ID for error messages

    Returns:
        List of syntax errors
    """
    errors = []

    # Check for balanced braces
    open_braces = graphql_template.count('{')
    close_braces = graphql_template.count('}')
    if open_braces != close_braces:
        errors.append(f"Template '{template_id}': Unbalanced braces "
                     f"(found {open_braces} '{{' and {close_braces} '}}')")

    # Check for balanced parentheses
    open_parens = graphql_template.count('(')
    close_parens = graphql_template.count(')')
    if open_parens != close_parens:
        errors.append(f"Template '{template_id}': Unbalanced parentheses "
                     f"(found {open_parens} '(' and {close_parens} ')')")

    # Check for operation type
    if not re.search(r'\b(query|mutation|subscription)\b', graphql_template, re.IGNORECASE):
        # Might be a shorthand query (just fields)
        pass

    # Check for at least one field selection
    if '{' in graphql_template:
        # Extract content between outermost braces
        inner_content = re.search(r'\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', graphql_template)
        if inner_content and not inner_content.group(1).strip():
            errors.append(f"Template '{template_id}': Empty field selection")

    return errors


def extract_graphql_variables(graphql_template: str) -> List[str]:
    """
    Extract variable names from a GraphQL operation.

    Args:
        graphql_template: The GraphQL operation string

    Returns:
        List of variable names (without $)
    """
    # Pattern: $varName in variable definitions
    var_pattern = r'\$(\w+)\s*:'
    return re.findall(var_pattern, graphql_template)


def validate_template(template: Dict[str, Any], result: ValidationResult, strict: bool = False):
    """
    Validate a single template.

    Args:
        template: Template dictionary
        result: ValidationResult to accumulate results
        strict: If True, treat warnings as errors
    """
    template_id = template.get('id', '<unknown>')

    # Check required fields
    for field in REQUIRED_TEMPLATE_FIELDS:
        if field not in template:
            result.add_error(f"Template '{template_id}': Missing required field '{field}'")
        elif template[field] is None:
            result.add_error(f"Template '{template_id}': Field '{field}' is null")

    # Check recommended fields
    for field in RECOMMENDED_TEMPLATE_FIELDS:
        if field not in template:
            msg = f"Template '{template_id}': Missing recommended field '{field}'"
            if strict:
                result.add_error(msg)
            else:
                result.add_warning(msg)

    # Validate GraphQL type
    graphql_type = template.get('graphql_type', 'query')
    if graphql_type not in VALID_GRAPHQL_TYPES:
        result.add_error(f"Template '{template_id}': Invalid graphql_type '{graphql_type}' "
                        f"(must be one of: {', '.join(VALID_GRAPHQL_TYPES)})")

    # Validate GraphQL syntax
    graphql_template = template.get('graphql_template', '')
    if graphql_template:
        syntax_errors = validate_graphql_syntax(graphql_template, template_id)
        for error in syntax_errors:
            result.add_error(error)

        # Extract variables from GraphQL and compare with parameters
        graphql_vars = set(extract_graphql_variables(graphql_template))
        param_names = set(p.get('name', '') for p in template.get('parameters', []))

        # Check for variables without parameter definitions
        undefined_vars = graphql_vars - param_names
        if undefined_vars:
            msg = (f"Template '{template_id}': GraphQL variables without parameter definitions: "
                   f"{', '.join(undefined_vars)}")
            if strict:
                result.add_error(msg)
            else:
                result.add_warning(msg)

        # Check for parameters not used in GraphQL
        unused_params = param_names - graphql_vars
        if unused_params:
            result.add_warning(f"Template '{template_id}': Parameters not used in GraphQL: "
                             f"{', '.join(unused_params)}")

    # Validate parameters
    for param in template.get('parameters', []):
        param_name = param.get('name', '<unknown>')

        # Check parameter type
        param_type = param.get('type')
        if param_type and param_type not in VALID_PARAM_TYPES:
            result.add_warning(f"Template '{template_id}': Parameter '{param_name}' "
                             f"has unusual type '{param_type}'")

        # Check GraphQL type notation
        graphql_type = param.get('graphql_type', '')
        if graphql_type:
            # Required parameters should have ! in GraphQL type
            if param.get('required', False) and '!' not in graphql_type:
                result.add_warning(f"Template '{template_id}': Required parameter '{param_name}' "
                                 f"doesn't have ! in graphql_type")

    # Validate natural language examples
    nl_examples = template.get('nl_examples', [])
    if not nl_examples:
        msg = f"Template '{template_id}': No natural language examples provided"
        if strict:
            result.add_error(msg)
        else:
            result.add_warning(msg)
    elif len(nl_examples) < 3:
        result.add_warning(f"Template '{template_id}': Only {len(nl_examples)} nl_examples "
                          f"(recommend at least 3 for better matching)")

    # Validate semantic tags
    semantic_tags = template.get('semantic_tags', {})
    if semantic_tags:
        if 'action' not in semantic_tags:
            result.add_warning(f"Template '{template_id}': semantic_tags missing 'action'")
        if 'primary_entity' not in semantic_tags:
            result.add_warning(f"Template '{template_id}': semantic_tags missing 'primary_entity'")

    # Validate response mapping
    response_mapping = template.get('response_mapping', {})
    if response_mapping and 'items_path' not in response_mapping:
        result.add_warning(f"Template '{template_id}': response_mapping missing 'items_path'")


def validate_domain_config(domain: Dict[str, Any], result: ValidationResult, strict: bool = False):
    """
    Validate a domain configuration.

    Args:
        domain: Domain configuration dictionary
        result: ValidationResult to accumulate results
        strict: If True, treat warnings as errors
    """
    # Check required fields
    for field in REQUIRED_DOMAIN_FIELDS:
        if field not in domain:
            result.add_error(f"Domain config: Missing required field '{field}'")

    # Validate domain type
    domain_type = domain.get('domain_type', '')
    if domain_type != 'graphql':
        result.add_warning(f"Domain config: domain_type is '{domain_type}' (expected 'graphql')")

    # Validate API config
    api_config = domain.get('api_config', {})
    if not api_config.get('base_url') and not api_config.get('graphql_endpoint'):
        result.add_warning("Domain config: api_config missing base_url or graphql_endpoint")

    # Validate entities
    entities = domain.get('entities', {})
    if not entities:
        result.add_warning("Domain config: No entities defined")
    else:
        for entity_name, entity_config in entities.items():
            if not entity_config.get('graphql_type') and not entity_config.get('entity_type'):
                result.add_warning(f"Domain config: Entity '{entity_name}' missing graphql_type")

    # Validate vocabulary
    vocabulary = domain.get('vocabulary', {})
    if not vocabulary.get('entity_synonyms') and not vocabulary.get('action_synonyms'):
        result.add_warning("Domain config: vocabulary missing entity_synonyms or action_synonyms")


def validate_templates_file(file_path: Path, result: ValidationResult, strict: bool = False):
    """
    Validate a templates YAML file.

    Args:
        file_path: Path to the templates file
        result: ValidationResult to accumulate results
        strict: If True, treat warnings as errors
    """
    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result.add_error(f"YAML parsing error: {e}")
        return
    except Exception as e:
        result.add_error(f"Error reading file: {e}")
        return

    if not data:
        result.add_error("Templates file is empty")
        return

    templates = data.get('templates', [])
    if not templates:
        result.add_error("No templates found in file")
        return

    result.add_info(f"Found {len(templates)} templates")

    # Track template IDs for duplicates
    seen_ids = set()

    for template in templates:
        template_id = template.get('id', '')
        if template_id in seen_ids:
            result.add_error(f"Duplicate template ID: '{template_id}'")
        seen_ids.add(template_id)

        validate_template(template, result, strict)


def validate_domain_file(file_path: Path, result: ValidationResult, strict: bool = False):
    """
    Validate a domain configuration YAML file.

    Args:
        file_path: Path to the domain file
        result: ValidationResult to accumulate results
        strict: If True, treat warnings as errors
    """
    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result.add_error(f"YAML parsing error: {e}")
        return
    except Exception as e:
        result.add_error(f"Error reading file: {e}")
        return

    if not data:
        result.add_error("Domain file is empty")
        return

    validate_domain_config(data, result, strict)


def cross_validate(templates_path: Path, domain_path: Path, result: ValidationResult):
    """
    Cross-validate templates against domain configuration.

    Args:
        templates_path: Path to templates file
        domain_path: Path to domain file
        result: ValidationResult to accumulate results
    """
    try:
        with open(templates_path, 'r') as f:
            templates_data = yaml.safe_load(f)
        with open(domain_path, 'r') as f:
            domain_data = yaml.safe_load(f)
    except Exception as e:
        result.add_error(f"Error loading files for cross-validation: {e}")
        return

    templates = templates_data.get('templates', [])
    entities = set(domain_data.get('entities', {}).keys())

    # Check that template entities exist in domain
    for template in templates:
        template_id = template.get('id', '<unknown>')
        semantic_tags = template.get('semantic_tags', {})
        primary_entity = semantic_tags.get('primary_entity')

        if primary_entity and primary_entity not in entities:
            result.add_warning(f"Template '{template_id}': primary_entity '{primary_entity}' "
                             f"not found in domain entities")


def main():
    parser = argparse.ArgumentParser(
        description='Validate GraphQL intent templates and domain configurations'
    )

    parser.add_argument('--templates', '-t', required=True,
                       help='Path to templates YAML file')
    parser.add_argument('--domain', '-d',
                       help='Path to domain configuration YAML file')
    parser.add_argument('--strict', '-s', action='store_true',
                       help='Treat warnings as errors')

    args = parser.parse_args()

    result = ValidationResult()

    # Validate templates
    templates_path = Path(args.templates)
    if not templates_path.exists():
        print(f"Error: Templates file not found: {templates_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Validating templates: {templates_path}")
    validate_templates_file(templates_path, result, args.strict)

    # Validate domain if provided
    if args.domain:
        domain_path = Path(args.domain)
        if not domain_path.exists():
            print(f"Error: Domain file not found: {domain_path}", file=sys.stderr)
            sys.exit(1)

        print(f"Validating domain: {domain_path}")
        validate_domain_file(domain_path, result, args.strict)

        # Cross-validate
        print("Cross-validating templates against domain...")
        cross_validate(templates_path, domain_path, result)

    # Print results
    result.print_results()

    # Exit with appropriate code
    sys.exit(0 if result.is_valid else 1)


if __name__ == '__main__':
    main()
