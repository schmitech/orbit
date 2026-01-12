#!/usr/bin/env python3
"""
Validate HTTP Template Output

This script validates HTTP intent templates and domain configurations
for correctness, completeness, and consistency.
"""

import argparse
import yaml
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple


class HTTPTemplateValidator:
    """Validates HTTP intent templates and domain configurations."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate_domain_config(self, domain_path: str) -> bool:
        """
        Validate a domain configuration file.

        Args:
            domain_path: Path to the domain YAML file

        Returns:
            True if valid, False otherwise
        """
        print(f"\n📋 Validating domain configuration: {domain_path}")

        try:
            with open(domain_path, 'r') as f:
                domain = yaml.safe_load(f)

            # Check required top-level fields
            required_fields = ['domain_name', 'domain_type', 'version']
            for field in required_fields:
                if field not in domain:
                    self.errors.append(f"Missing required field: {field}")

            # Validate domain_type
            if domain.get('domain_type') not in ['rest_api', 'graphql', 'soap', 'webhook']:
                self.warnings.append(f"Unusual domain_type: {domain.get('domain_type')}")

            # Validate api_config if present
            if 'api_config' in domain:
                self._validate_api_config(domain['api_config'])

            # Validate authentication if present
            if 'authentication' in domain:
                self._validate_authentication(domain['authentication'])

            # Validate entities if present
            if 'entities' in domain:
                self._validate_entities(domain['entities'])

            # Validate vocabulary if present
            if 'vocabulary' in domain:
                self._validate_vocabulary(domain['vocabulary'])

            if self.errors:
                print(f"❌ Found {len(self.errors)} errors:")
                for error in self.errors:
                    print(f"   - {error}")
                return False

            if self.warnings:
                print(f"⚠️  Found {len(self.warnings)} warnings:")
                for warning in self.warnings:
                    print(f"   - {warning}")

            print(f"✓ Domain configuration is valid")
            return True

        except yaml.YAMLError as e:
            self.errors.append(f"YAML parsing error: {e}")
            print(f"❌ YAML parsing error: {e}")
            return False
        except FileNotFoundError:
            self.errors.append(f"File not found: {domain_path}")
            print(f"❌ File not found: {domain_path}")
            return False
        except Exception as e:
            self.errors.append(f"Unexpected error: {e}")
            print(f"❌ Unexpected error: {e}")
            return False

    def _validate_api_config(self, api_config: Dict):
        """Validate API configuration section."""
        if 'base_url' not in api_config:
            self.errors.append("api_config: Missing base_url")
        elif not api_config['base_url'].startswith(('http://', 'https://')):
            self.errors.append(f"api_config: Invalid base_url: {api_config['base_url']}")

    def _validate_authentication(self, auth: Dict):
        """Validate authentication configuration."""
        valid_auth_types = ['bearer_token', 'api_key', 'basic_auth', 'oauth2', 'none']
        auth_type = auth.get('type')

        if not auth_type:
            self.errors.append("authentication: Missing type")
        elif auth_type not in valid_auth_types:
            self.warnings.append(f"authentication: Unusual type: {auth_type}")

        # Check for environment variable references
        if auth_type in ['bearer_token', 'api_key']:
            if 'token_env' not in auth and 'api_key_env' not in auth:
                self.warnings.append("authentication: No environment variable reference found")

    def _validate_entities(self, entities: Dict):
        """Validate entity definitions."""
        for entity_name, entity_config in entities.items():
            if 'entity_type' not in entity_config:
                self.errors.append(f"entity '{entity_name}': Missing entity_type")

            if 'endpoint_base' not in entity_config:
                self.errors.append(f"entity '{entity_name}': Missing endpoint_base")

    def _validate_vocabulary(self, vocabulary: Dict):
        """Validate vocabulary section."""
        expected_sections = ['entity_synonyms', 'action_synonyms', 'qualifier_synonyms']
        for section in expected_sections:
            if section not in vocabulary:
                self.warnings.append(f"vocabulary: Missing {section}")

    def validate_template_library(self, template_path: str, domain_config: Dict = None) -> bool:
        """
        Validate a template library file.

        Args:
            template_path: Path to the template YAML file
            domain_config: Optional domain configuration for cross-validation

        Returns:
            True if valid, False otherwise
        """
        print(f"\n📋 Validating template library: {template_path}")

        try:
            with open(template_path, 'r') as f:
                data = yaml.safe_load(f)

            if 'templates' not in data:
                self.errors.append("Missing 'templates' key in template file")
                print(f"❌ Missing 'templates' key")
                return False

            templates = data['templates']
            if not isinstance(templates, list):
                self.errors.append("'templates' must be a list")
                print(f"❌ 'templates' must be a list")
                return False

            print(f"   Found {len(templates)} templates")

            # Validate each template
            template_ids = set()
            for i, template in enumerate(templates, 1):
                template_errors = self._validate_template(template, i, domain_config)
                if template_errors:
                    self.errors.extend(template_errors)

                # Check for duplicate IDs
                template_id = template.get('id')
                if template_id:
                    if template_id in template_ids:
                        self.errors.append(f"Duplicate template ID: {template_id}")
                    template_ids.add(template_id)

            if self.errors:
                print(f"❌ Found {len(self.errors)} errors:")
                for error in self.errors[:10]:  # Show first 10 errors
                    print(f"   - {error}")
                if len(self.errors) > 10:
                    print(f"   ... and {len(self.errors) - 10} more errors")
                return False

            if self.warnings:
                print(f"⚠️  Found {len(self.warnings)} warnings:")
                for warning in self.warnings[:10]:
                    print(f"   - {warning}")
                if len(self.warnings) > 10:
                    print(f"   ... and {len(self.warnings) - 10} more warnings")

            print(f"✓ Template library is valid")
            return True

        except yaml.YAMLError as e:
            self.errors.append(f"YAML parsing error: {e}")
            print(f"❌ YAML parsing error: {e}")
            return False
        except FileNotFoundError:
            self.errors.append(f"File not found: {template_path}")
            print(f"❌ File not found: {template_path}")
            return False
        except Exception as e:
            self.errors.append(f"Unexpected error: {e}")
            print(f"❌ Unexpected error: {e}")
            return False

    def _validate_template(self, template: Dict, index: int, domain_config: Dict = None) -> List[str]:
        """
        Validate a single template.

        Args:
            template: Template dictionary
            index: Template index (for error messages)
            domain_config: Optional domain configuration

        Returns:
            List of error messages
        """
        errors = []
        prefix = f"Template #{index}"

        # Required fields
        required_fields = ['id', 'version', 'description', 'http_method', 'endpoint_template']
        for field in required_fields:
            if field not in template:
                errors.append(f"{prefix}: Missing required field '{field}'")

        # Validate ID
        if 'id' in template:
            template_id = template['id']
            if not template_id:
                errors.append(f"{prefix}: Empty template ID")
            prefix = f"Template '{template_id}'"

        # Validate HTTP method
        valid_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
        http_method = template.get('http_method', '').upper()
        if http_method and http_method not in valid_methods:
            errors.append(f"{prefix}: Invalid HTTP method: {http_method}")

        # Validate endpoint template
        endpoint = template.get('endpoint_template', '')
        if endpoint and not endpoint.startswith('/'):
            self.warnings.append(f"{prefix}: Endpoint should start with '/': {endpoint}")

        # Validate parameters
        if 'parameters' in template:
            param_errors = self._validate_parameters(template['parameters'], prefix, endpoint)
            errors.extend(param_errors)

        # Validate natural language examples
        if 'nl_examples' not in template:
            self.warnings.append(f"{prefix}: Missing nl_examples")
        elif not template['nl_examples']:
            self.warnings.append(f"{prefix}: Empty nl_examples")
        elif len(template['nl_examples']) < 3:
            self.warnings.append(f"{prefix}: Should have at least 3 nl_examples")

        # Validate semantic tags
        if 'semantic_tags' in template:
            if 'action' not in template['semantic_tags']:
                self.warnings.append(f"{prefix}: semantic_tags missing 'action'")
            if 'primary_entity' not in template['semantic_tags']:
                self.warnings.append(f"{prefix}: semantic_tags missing 'primary_entity'")

        # Validate response mapping
        if 'response_mapping' in template:
            mapping = template['response_mapping']
            if 'items_path' not in mapping:
                self.warnings.append(f"{prefix}: response_mapping missing 'items_path'")

        return errors

    def _validate_parameters(self, parameters: List[Dict], prefix: str, endpoint: str) -> List[str]:
        """Validate template parameters."""
        errors = []

        # Extract path parameters from endpoint
        import re
        path_params = set(re.findall(r'\{(\w+)\}', endpoint))

        param_names = set()
        for i, param in enumerate(parameters, 1):
            if 'name' not in param:
                errors.append(f"{prefix}, param #{i}: Missing 'name'")
                continue

            param_name = param['name']
            param_names.add(param_name)

            # Check required fields
            if 'type' not in param:
                self.warnings.append(f"{prefix}, param '{param_name}': Missing 'type'")
            if 'description' not in param:
                self.warnings.append(f"{prefix}, param '{param_name}': Missing 'description'")
            if 'location' not in param:
                self.warnings.append(f"{prefix}, param '{param_name}': Missing 'location'")

            # Validate location
            valid_locations = ['path', 'query', 'header', 'body']
            location = param.get('location', 'path')
            if location not in valid_locations:
                errors.append(f"{prefix}, param '{param_name}': Invalid location: {location}")

            # Check if required field is set
            if 'required' not in param:
                self.warnings.append(f"{prefix}, param '{param_name}': Missing 'required' flag")

        # Check that all path parameters are defined
        missing_params = path_params - param_names
        if missing_params:
            errors.append(f"{prefix}: Path parameters not defined: {missing_params}")

        return errors


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Validate HTTP intent templates and domain configurations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate templates only
  python validate_output.py \\
      --templates examples/github-api/templates/github_templates.yaml

  # Validate templates and domain
  python validate_output.py \\
      --templates examples/github-api/templates/github_templates.yaml \\
      --domain examples/github-api/templates/github_domain.yaml
        """
    )

    parser.add_argument('--templates', required=True, help='Path to template library YAML file')
    parser.add_argument('--domain', help='Path to domain configuration YAML file')

    args = parser.parse_args()

    validator = HTTPTemplateValidator()

    print("\n" + "=" * 60)
    print("HTTP Template Validation")
    print("=" * 60)

    # Validate domain if provided
    domain_config = None
    domain_valid = True
    if args.domain:
        domain_valid = validator.validate_domain_config(args.domain)
        if domain_valid:
            with open(args.domain, 'r') as f:
                domain_config = yaml.safe_load(f)

    # Validate templates
    templates_valid = validator.validate_template_library(args.templates, domain_config)

    # Summary
    print("\n" + "=" * 60)
    if domain_valid and templates_valid:
        print("✅ All validations passed!")
    else:
        print("❌ Validation failed")
        sys.exit(1)
    print("=" * 60 + "\n")


if __name__ == '__main__':
    main()
