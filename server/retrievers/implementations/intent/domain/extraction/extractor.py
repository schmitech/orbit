"""
Facade for domain-aware parameter extraction
"""

import logging
from typing import Dict, Any, Optional, List
from ...domain import DomainConfig
from .pattern_builder import PatternBuilder
from .value_extractor import ValueExtractor
from .llm_fallback import LLMFallback
from .validator import Validator

logger = logging.getLogger(__name__)


class DomainParameterExtractor:
    """
    Facade class that orchestrates parameter extraction using composable services.
    This is a refactored version that maintains backward compatibility while using
    the new modular components.
    """

    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None):
        """Initialize the domain parameter extractor"""
        # Convert dict config to DomainConfig if needed
        if isinstance(domain_config, dict):
            self.domain_config = DomainConfig(domain_config)
        elif isinstance(domain_config, DomainConfig):
            self.domain_config = domain_config
        else:
            self.domain_config = DomainConfig({})

        self.inference_client = inference_client

        # Initialize components
        self._initialize_components()

    def _initialize_components(self):
        """Initialize all extraction components"""
        # Build patterns
        self.pattern_builder = PatternBuilder(self.domain_config)
        self.patterns = self.pattern_builder.build_patterns()

        # Initialize extractor
        self.value_extractor = ValueExtractor(self.domain_config, self.patterns)

        # Initialize LLM fallback
        self.llm_fallback = LLMFallback(self.inference_client, self.domain_config)

        # Initialize validator
        self.validator = Validator(self.domain_config)

        logger.info(f"Initialized DomainParameterExtractor with {len(self.patterns)} patterns")

    async def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]:
        """
        Extract parameters from user query for a given template.
        Maintains backward compatibility with the original interface.
        """
        parameters = {}
        template_params = template.get('parameters', [])

        # First pass: Extract all values using patterns
        extracted_values = self.value_extractor.extract_all_values(user_query)

        # Map extracted values to template parameters
        for param in template_params:
            param_name = param['name']
            # Handle both 'type' and 'data_type' for backward compatibility
            param_type = param.get('type') or param.get('data_type', 'string')

            # Check if we have a direct match
            value = None

            # Look for entity.field pattern in extracted values
            entity = param.get('entity')
            field = param.get('field')

            if entity and field:
                key = f"{entity}.{field}"
                if key in extracted_values:
                    value = extracted_values[key]
            elif param_name in extracted_values:
                value = extracted_values[param_name]

            # If no value found through patterns, try context extraction
            if value is None and entity and field:
                value = self.value_extractor.extract_value(
                    user_query, entity, field, param_type
                )

            # If still no value and this is not an entity field, try template parameter extraction
            if value is None and not (entity and field):
                value = self.value_extractor.extract_template_parameter(user_query, param)

            # Store the value if found
            if value is not None:
                # Validate the value
                if entity and field:
                    is_valid, error_msg = self.validator.validate(value, entity, field)
                    if is_valid:
                        # Sanitize the value
                        value = self.validator.sanitize(value, entity, field)
                        parameters[param_name] = value
                    else:
                        logger.warning(f"Validation failed for {param_name}: {error_msg}")
                else:
                    # Ensure string type for certain parameters that need it
                    if param_type == 'string' and not isinstance(value, str):
                        value = str(value)
                    parameters[param_name] = value

        # Second pass: Use LLM for missing required parameters
        missing_params = [
            param for param in template_params
            if param.get('required', False) and param['name'] not in parameters
        ]

        if missing_params:
            template_desc = template.get('description', 'query')

            # Try batch extraction for efficiency
            if len(missing_params) > 1:
                llm_values = await self.llm_fallback.extract_multiple(
                    user_query, missing_params, template_desc
                )
                for param_name, value in llm_values.items():
                    if value is not None and param_name not in parameters:
                        parameters[param_name] = value
            else:
                # Single parameter extraction
                for param in missing_params:
                    value = await self.llm_fallback.extract_with_llm(
                        user_query, param, template_desc
                    )
                    if value is not None:
                        parameters[param['name']] = value

        # Apply defaults for missing optional parameters
        for param in template_params:
            param_name = param['name']
            if param_name not in parameters and 'default' in param:
                parameters[param_name] = param['default']

        logger.debug(f"Extracted parameters: {parameters}")
        return parameters

    def get_patterns_info(self) -> Dict[str, str]:
        """Get information about loaded patterns (useful for debugging)"""
        info = {}
        for key, pattern in self.patterns.items():
            info[key] = pattern.pattern
        return info

    def get_domain_info(self) -> Dict[str, Any]:
        """Get domain configuration info"""
        return {
            'domain_name': self.domain_config.domain_name,
            'entities': list(self.domain_config.entities.keys()),
            'total_patterns': len(self.patterns),
            'searchable_fields': len(self.domain_config.get_searchable_fields()),
            'filterable_fields': len(self.domain_config.get_filterable_fields())
        }

    def validate_parameters(self, parameters: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Validate a set of parameters.

        Returns:
            Dictionary of validation errors (empty if all valid)
        """
        return self.validator.validate_all(parameters)
