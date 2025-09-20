"""
Domain-aware parameter extraction for Intent retriever.
This is a backward-compatibility wrapper that delegates to the new modular components.
"""

import logging
from typing import Dict, Any, Optional, List
from .domain.extraction import DomainParameterExtractor as NewDomainParameterExtractor

logger = logging.getLogger(__name__)


class DomainAwareParameterExtractor:
    """
    Domain-aware parameter extraction using domain configuration and LLM.
    This class maintains backward compatibility by wrapping the new modular implementation.
    """

    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None):
        # Delegate to the new implementation
        self._extractor = NewDomainParameterExtractor(inference_client, domain_config)

        # Keep references for backward compatibility
        self.inference_client = inference_client
        self.domain_config = domain_config or {}
        self.patterns = self._extractor.patterns
        self.validator = self._extractor.validator

    async def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]:
        """
        Extract parameters using domain configuration and patterns.
        Delegates to the new modular implementation.
        """
        return await self._extractor.extract_parameters(user_query, template)

    def validate_parameters(
        self,
        parameters: Dict[str, Any],
        template: Dict
    ) -> tuple[bool, Dict[str, List[str]]]:
        """Validate extracted parameters against template requirements and domain rules."""
        errors: Dict[str, List[str]] = {}
        template_params = template.get('parameters', []) or []

        if not template_params:
            return True, errors

        for param in template_params:
            name = param.get('name')
            if not name:
                continue

            value_present = name in parameters and not self._is_missing_value(parameters[name])

            # Check required flag from template definition
            if param.get('required', False) and not value_present:
                errors.setdefault(name, []).append('Parameter is required.')
                continue

            if not value_present:
                continue

            entity = param.get('entity')
            field = param.get('field')
            if entity and field and self.validator:
                is_valid, error_msg = self.validator.validate(parameters[name], entity, field)
                if not is_valid:
                    errors.setdefault(name, []).append(error_msg or 'Invalid value.')
                else:
                    parameters[name] = self.validator.sanitize(parameters[name], entity, field)

        return len(errors) == 0, errors

    # Backward compatibility methods that might be used elsewhere
    def _initialize_components(self):
        """Provided for backward compatibility - initialization happens in constructor"""
        pass

    def _build_extraction_patterns(self):
        """Provided for backward compatibility - patterns are built in the new extractor"""
        pass

    def _initialize_validators(self):
        """Provided for backward compatibility - validators are in the new extractor"""
        pass

    def _initialize_converters(self):
        """Provided for backward compatibility - converters are in the new extractor"""
        pass

    @staticmethod
    def _is_missing_value(value: Any) -> bool:
        """Check if a parameter value should be treated as missing."""
        if value is None:
            return True

        if isinstance(value, str) and value.strip() == '':
            return True

        return False
