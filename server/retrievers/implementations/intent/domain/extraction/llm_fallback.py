"""
LLM fallback for parameter extraction when pattern matching fails
"""

import json
import logging
from typing import Dict, Any, Optional, List
from ...domain import DomainConfig

logger = logging.getLogger(__name__)


class LLMFallback:
    """Fallback to LLM for complex parameter extraction"""

    def __init__(self, inference_client, domain_config: DomainConfig):
        """Initialize LLM fallback with inference client"""
        self.inference_client = inference_client
        self.domain_config = domain_config

    async def extract_with_llm(self, user_query: str, parameter: Dict[str, Any],
                                template_description: str) -> Optional[Any]:
        """Use LLM to extract a parameter value when patterns fail"""
        prompt = self._build_extraction_prompt(user_query, parameter, template_description)

        try:
            if hasattr(self.inference_client, 'generate'):
                response = await self.inference_client.generate(prompt)
            else:
                response = await self.inference_client.generate_response(prompt)

            return self._parse_llm_response(response, parameter)

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return None

    def _build_extraction_prompt(self, user_query: str, parameter: Dict[str, Any],
                                  template_description: str) -> str:
        """Build prompt for LLM extraction"""
        param_name = parameter['name']
        param_type = parameter.get('data_type', 'string')
        description = parameter.get('description', '')

        # Get domain context
        domain_context = self._get_domain_context(parameter)

        prompt = f"""Extract the value for parameter "{param_name}" from the user's query.

User Query: "{user_query}"

Template Context: {template_description}
Parameter Details:
- Name: {param_name}
- Type: {param_type}
- Description: {description}

{domain_context}

Instructions:
1. Look for the {param_name} value in the user's query
2. If found, extract and format it according to the type
3. If not explicitly stated, infer from context if possible
4. Return ONLY the extracted value or "NOT_FOUND" if not present

For date values, use YYYY-MM-DD format.
For numeric values, return the number without currency symbols or commas.

Response:"""

        return prompt

    def _get_domain_context(self, parameter: Dict[str, Any]) -> str:
        """Get domain-specific context for the parameter"""
        context_parts = []

        # Add entity context if available
        entity_name = parameter.get('entity')
        if entity_name:
            entity = self.domain_config.get_entity(entity_name)
            if entity:
                context_parts.append(f"Entity: {entity.display_name or entity.name}")
                if entity.description:
                    context_parts.append(f"Entity Description: {entity.description}")

                # Add entity synonyms
                synonyms = self.domain_config.get_entity_synonyms(entity_name)
                if synonyms:
                    context_parts.append(f"Entity Synonyms: {', '.join(synonyms)}")

        # Add field context if available
        field_name = parameter.get('field')
        if field_name and entity_name:
            field = self.domain_config.get_field(entity_name, field_name)
            if field:
                if field.display_name:
                    context_parts.append(f"Field Display Name: {field.display_name}")

                # Add field synonyms
                synonyms = self.domain_config.get_field_synonyms(field_name)
                if synonyms:
                    context_parts.append(f"Field Synonyms: {', '.join(synonyms)}")

        if context_parts:
            return "Domain Context:\n" + "\n".join(context_parts)
        return ""

    def _parse_llm_response(self, response: str, parameter: Dict[str, Any]) -> Optional[Any]:
        """Parse LLM response to extract parameter value"""
        response = response.strip()

        if response == "NOT_FOUND" or not response:
            return None

        param_type = parameter.get('data_type', 'string')

        try:
            # Try to parse as JSON first (for complex types)
            if response.startswith('{') or response.startswith('['):
                return json.loads(response)

            # Parse based on type
            if param_type == "integer":
                # Remove any non-numeric characters except negative sign
                clean = ''.join(c for c in response if c.isdigit() or c == '-')
                return int(clean) if clean else None

            elif param_type == "decimal":
                # Remove currency symbols and commas
                clean = response.replace('$', '').replace(',', '').strip()
                return float(clean)

            elif param_type == "boolean":
                response_lower = response.lower()
                if response_lower in ['true', 'yes', '1']:
                    return True
                elif response_lower in ['false', 'no', '0']:
                    return False
                return None

            else:  # string or other types
                return response

        except (ValueError, json.JSONDecodeError) as e:
            logger.debug(f"Failed to parse LLM response '{response}': {e}")
            return response if param_type == "string" else None

    async def extract_multiple(self, user_query: str, parameters: List[Dict[str, Any]],
                                template_description: str) -> Dict[str, Any]:
        """Extract multiple parameters using LLM in a single call"""
        prompt = self._build_batch_extraction_prompt(user_query, parameters, template_description)

        try:
            if hasattr(self.inference_client, 'generate'):
                response = await self.inference_client.generate(prompt)
            else:
                response = await self.inference_client.generate_response(prompt)

            return self._parse_batch_response(response, parameters)

        except Exception as e:
            logger.error(f"Batch LLM extraction failed: {e}")
            return {}

    def _build_batch_extraction_prompt(self, user_query: str, parameters: List[Dict[str, Any]],
                                        template_description: str) -> str:
        """Build prompt for extracting multiple parameters"""
        param_descriptions = []
        for param in parameters:
            desc = f"- {param['name']} ({param.get('data_type', 'string')})"
            if param.get('description'):
                desc += f": {param['description']}"
            param_descriptions.append(desc)

        prompt = f"""Extract parameter values from the user's query.

User Query: "{user_query}"

Template Context: {template_description}

Parameters to extract:
{chr(10).join(param_descriptions)}

Return a JSON object with parameter names as keys and extracted values.
Use null for parameters that cannot be extracted from the query.

Example response format:
{{
    "parameter1": "value1",
    "parameter2": 123,
    "parameter3": null
}}

Response:"""

        return prompt

    def _parse_batch_response(self, response: str, parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Parse batch LLM response"""
        try:
            # Try to extract JSON from response
            response = response.strip()
            if '```json' in response:
                response = response.split('```json')[1].split('```')[0].strip()
            elif '```' in response:
                response = response.split('```')[1].split('```')[0].strip()

            result = json.loads(response)

            # Validate and convert types
            typed_result = {}
            for param in parameters:
                param_name = param['name']
                if param_name in result and result[param_name] is not None:
                    typed_result[param_name] = self._convert_type(
                        result[param_name], param.get('data_type', 'string')
                    )

            return typed_result

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse batch LLM response: {e}")
            return {}

    def _convert_type(self, value: Any, data_type: str) -> Any:
        """Convert value to specified type"""
        if value is None:
            return None

        try:
            if data_type == "integer":
                return int(value)
            elif data_type == "decimal":
                return float(value)
            elif data_type == "boolean":
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ['true', 'yes', '1']
            else:
                return str(value)
        except (ValueError, TypeError):
            return value