"""
Domain-aware parameter extraction for Intent retriever
"""

import logging
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, date

logger = logging.getLogger(__name__)


class DomainAwareParameterExtractor:
    """Domain-aware parameter extraction using domain configuration and LLM"""
    
    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None):
        self.inference_client = inference_client
        self.domain_config = domain_config or {}
        self._build_extraction_patterns()
        
    def _build_extraction_patterns(self):
        """Build extraction patterns from domain configuration"""
        self.patterns = {}
        
        # Build patterns for each entity's searchable fields
        entities = self.domain_config.get('entities', {})
        fields = self.domain_config.get('fields', {})
        vocabulary = self.domain_config.get('vocabulary', {})
        
        for entity_name, entity_data in entities.items():
            entity_fields = fields.get(entity_name, {})
            
            for field_name, field_data in entity_fields.items():
                if field_data.get('searchable') or field_data.get('filterable'):
                    pattern_key = f"{entity_name}.{field_name}"
                    data_type = field_data.get('data_type', 'string')
                    
                    if data_type == "integer" and "id" in field_name.lower():
                        # ID pattern - more flexible
                        entity_synonyms = vocabulary.get('entity_synonyms', {}).get(entity_name, [])
                        entity_patterns = [entity_name] + entity_synonyms
                        pattern_str = f"({'|'.join(entity_patterns)})\\s*(?:id\\s*)?(?:#|number|id)?\\s*(\\d+)"
                        self.patterns[pattern_key] = re.compile(pattern_str, re.IGNORECASE)
                    
                    elif data_type == "string" and field_name == "email":
                        # Email pattern
                        self.patterns[pattern_key] = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+', re.IGNORECASE)
                    
                    elif data_type == "decimal" or data_type == "integer":
                        # Amount/number pattern
                        self.patterns[pattern_key] = re.compile(r'\$?\s*(\d+(?:\.\d{2})?)', re.IGNORECASE)
                        # Range pattern
                        range_pattern_key = f"{pattern_key}_range"
                        self.patterns[range_pattern_key] = re.compile(r'between\s*\$?(\d+(?:\.\d{2})?)\s*and\s*\$?(\d+(?:\.\d{2})?)', re.IGNORECASE)
                    
                    elif data_type == "date":
                        # Date pattern
                        self.patterns[pattern_key] = re.compile(r'\d{4}-\d{2}-\d{2}')
    
    async def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]:
        """Extract parameters using domain configuration and patterns"""
        parameters = {}
        
        # Try pattern-based extraction first
        for param in template.get('parameters', []):
            param_name = param['name']
            param_type = param.get('type', 'string')
            
            # Look for matching field in domain
            field_found = False
            entities = self.domain_config.get('entities', {})
            fields = self.domain_config.get('fields', {})
            
            for entity_name, entity_data in entities.items():
                entity_fields = fields.get(entity_name, {})
                for field_name, field_data in entity_fields.items():
                    aliases = field_data.get('aliases', [])
                    if field_name == param_name or param_name in aliases:
                        field_found = True
                        pattern_key = f"{entity_name}.{field_name}"
                        
                        if pattern_key in self.patterns:
                            match = self.patterns[pattern_key].search(user_query)
                            if match:
                                # Extract based on field type
                                data_type = field_data.get('data_type', 'string')
                                if data_type == "integer":
                                    parameters[param_name] = int(match.group(len(match.groups())))
                                elif data_type == "decimal":
                                    # Check for range pattern first
                                    range_pattern_key = f"{pattern_key}_range"
                                    if range_pattern_key in self.patterns:
                                        range_match = self.patterns[range_pattern_key].search(user_query)
                                        if range_match:
                                            parameters["min_amount"] = float(range_match.group(1))
                                            parameters["max_amount"] = float(range_match.group(2))
                                            # Found a range, so we can skip other decimal matches for this field
                                            continue
                                    
                                    # Fallback to single amount
                                    parameters[param_name] = float(match.group(1))
                                elif data_type == "string":
                                    if "name" in field_name.lower():
                                        # Use LLM for name extraction
                                        name = await self._extract_with_llm(user_query, field_data.get('description', ''))
                                        if name:
                                            parameters[param_name] = f'%{name}%'
                                    else:
                                        parameters[param_name] = match.group(0)
                        break
                if field_found:
                    break
            
            # Special handling for common parameter types
            if not field_found and param_name not in parameters:
                if "days" in param_name or "period" in param_name:
                    days = self._extract_time_period(user_query)
                    if days is not None:
                        parameters[param_name] = days
                elif param_type == "string" and param.get('allowed_values'):
                    # Extract enum value
                    value = self._extract_enum_value(user_query, param.get('allowed_values', []))
                    if value:
                        parameters[param_name] = value
        
        # Use LLM for missing required parameters
        missing_params = [p for p in template.get('parameters', []) 
                         if p.get('required', False) and p['name'] not in parameters]
        
        if missing_params:
            llm_params = await self._extract_missing_with_llm(user_query, template, missing_params)
            parameters.update(llm_params)
        
        # Apply defaults
        for param in template.get('parameters', []):
            if param['name'] not in parameters and 'default' in param:
                parameters[param['name']] = param['default']
        
        return parameters
    
    def _extract_time_period(self, text: str) -> Optional[int]:
        """Extract time period from text using domain vocabulary"""
        vocabulary = self.domain_config.get('vocabulary', {})
        time_mappings = vocabulary.get('time_expressions', {})
        text_lower = text.lower()
        
        # Check vocabulary mappings first
        for phrase, days_expr in time_mappings.items():
            if phrase in text_lower:
                try:
                    return int(days_expr)
                except:
                    pass
        
        # Pattern matching
        days_match = re.search(r'(?:last|past|previous)\s*(\d+)\s*days?', text_lower)
        if days_match:
            return int(days_match.group(1))
        
        weeks_match = re.search(r'(\d+)\s*weeks?', text_lower)
        if weeks_match:
            return int(weeks_match.group(1)) * 7
        
        months_match = re.search(r'(\d+)\s*months?', text_lower)
        if months_match:
            return int(months_match.group(1)) * 30
        
        return None
    
    def _extract_enum_value(self, text: str, allowed_values: List[str]) -> Optional[str]:
        """Extract enum value from text"""
        text_lower = text.lower()
        for value in allowed_values:
            if value.lower() in text_lower:
                return value
        return None
    
    async def _extract_with_llm(self, text: str, field_description: str) -> Optional[str]:
        """Extract value using LLM"""
        prompt = f"""Extract the {field_description} from this text. Return ONLY the value, nothing else.
If no value is found, return "None".

Text: "{text}"

Value:"""
        
        try:
            if hasattr(self.inference_client, 'generate'):
                response = await self.inference_client.generate(prompt)
            else:
                response = await self.inference_client.generate_response(prompt)
            
            response = response.strip()
            
            if response and response.lower() != 'none' and len(response) < 100:
                return response
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
        
        return None
    
    async def _extract_missing_with_llm(self, user_query: str, template: Dict, missing_params: List[Dict]) -> Dict[str, Any]:
        """Extract missing parameters using LLM"""
        param_descriptions = []
        for param in missing_params:
            desc = f"- {param['name']} ({param.get('type', 'string')}): {param.get('description', '')}"
            if 'example' in param:
                desc += f" (Example: {param['example']})"
            if 'allowed_values' in param:
                desc += f" - Allowed values: {', '.join(param['allowed_values'])}"
            param_descriptions.append(desc)
        
        extraction_prompt = f"""Extract the following parameters from the user query.
Return ONLY a valid JSON object with the extracted values.
Use null for parameters that cannot be found.

Parameters needed:
{chr(10).join(param_descriptions)}

User query: "{user_query}"

JSON:"""
        
        try:
            if hasattr(self.inference_client, 'generate'):
                response = await self.inference_client.generate(extraction_prompt)
            else:
                response = await self.inference_client.generate_response(extraction_prompt)
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
        
        return {}
    
    def validate_parameters(self, parameters: Dict[str, Any], template: Dict) -> Tuple[bool, List[str]]:
        """Validate parameters using domain configuration"""
        errors = []
        
        for param in template.get('parameters', []):
            param_name = param['name']
            param_type = param.get('type', 'string')
            required = param.get('required', False)
            
            if required and (param_name not in parameters or parameters.get(param_name) is None):
                errors.append(f"Missing required parameter: {param_name}")
                continue
            
            if param_name in parameters:
                value = parameters.get(param_name)
                
                if value is None:
                    continue
                
                # Find corresponding field in domain
                field = None
                fields = self.domain_config.get('fields', {})
                for entity_name, entity_fields in fields.items():
                    if param_name in entity_fields:
                        field = entity_fields[param_name]
                        break
                
                # Validate using field configuration
                if field:
                    data_type = field.get('data_type', 'string')
                    # Type validation
                    if data_type == "integer" and not isinstance(value, int):
                        try:
                            parameters[param_name] = int(value)
                        except:
                            errors.append(f"Parameter {param_name} must be an integer")
                    elif data_type == "decimal" and not isinstance(value, (int, float)):
                        try:
                            parameters[param_name] = float(value)
                        except:
                            errors.append(f"Parameter {param_name} must be a number")
                    elif data_type == "string" and not isinstance(value, str):
                        parameters[param_name] = str(value)
                    
                    # Enum validation
                    enum_values = field.get('enum_values')
                    if enum_values and value not in enum_values:
                        errors.append(f"Parameter {param_name} must be one of: {', '.join(enum_values)}")
                    
                    # Custom validation rules
                    validation_rules = field.get('validation_rules', [])
                    for rule in validation_rules:
                        if not self._validate_rule(value, rule):
                            errors.append(f"Parameter {param_name} failed validation: {rule.get('message', 'Invalid value')}")
        
        return len(errors) == 0, errors
    
    def _validate_rule(self, value: Any, rule: Dict[str, Any]) -> bool:
        """Validate value against a rule"""
        rule_type = rule.get('type')
        
        if rule_type == 'min' and isinstance(value, (int, float)):
            return value >= rule.get('value', 0)
        elif rule_type == 'max' and isinstance(value, (int, float)):
            return value <= rule.get('value', float('inf'))
        elif rule_type == 'pattern' and isinstance(value, str):
            return bool(re.match(rule.get('value', '.*'), value))
        elif rule_type == 'length' and isinstance(value, str):
            return len(value) <= rule.get('value', 255)
        
        return True