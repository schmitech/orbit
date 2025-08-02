"""
Domain-aware parameter extraction for Intent retriever
"""

import logging
import json
import re
from typing import Dict, List, Any, Optional, Tuple, Callable
from datetime import datetime, date

logger = logging.getLogger(__name__)


class DomainAwareParameterExtractor:
    """Domain-aware parameter extraction using domain configuration and LLM"""
    
    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None):
        self.inference_client = inference_client
        self.domain_config = domain_config or {}
        self._initialize_components()
        
    def _initialize_components(self):
        """Initialize all components of the extractor"""
        self._build_extraction_patterns()
        self._initialize_validators()
        self._initialize_converters()
        
    # ==================== Pattern Building Section ====================
    
    def _build_extraction_patterns(self):
        """Build extraction patterns from domain configuration"""
        self.patterns = {}
        self.pattern_builders = self._initialize_pattern_builders()
        
        entities = self.domain_config.get('entities', {})
        fields = self.domain_config.get('fields', {})
        
        for entity_name, entity_data in entities.items():
            entity_fields = fields.get(entity_name, {})
            
            for field_name, field_data in entity_fields.items():
                if self._should_create_pattern(field_data):
                    self._create_field_patterns(entity_name, field_name, field_data)

    def _initialize_pattern_builders(self) -> Dict[str, Callable]:
        """Initialize pattern builder functions for each data type"""
        return {
            'id': self._build_id_pattern,
            'email': self._build_email_pattern,
            'decimal': self._build_numeric_patterns,
            'integer': self._build_numeric_patterns,
            'date': self._build_date_pattern,
            'string': self._build_string_pattern,
        }

    def _should_create_pattern(self, field_data: Dict) -> bool:
        """Check if a pattern should be created for this field"""
        return field_data.get('searchable', False) or field_data.get('filterable', False)

    def _create_field_patterns(self, entity_name: str, field_name: str, field_data: Dict):
        """Create patterns for a specific field"""
        pattern_key = f"{entity_name}.{field_name}"
        data_type = field_data.get('data_type', 'string')
        
        pattern_type = self._get_pattern_type(field_name, data_type)
        builder = self.pattern_builders.get(pattern_type, self._build_default_pattern)
        builder(pattern_key, entity_name, field_name, field_data)

    def _get_pattern_type(self, field_name: str, data_type: str) -> str:
        """Determine the pattern type based on field name and data type"""
        field_lower = field_name.lower()
        
        if data_type == "integer" and "id" in field_lower:
            return 'id'
        elif data_type == "string" and field_name == "email":
            return 'email'
        
        return data_type

    def _build_id_pattern(self, pattern_key: str, entity_name: str, field_name: str, field_data: Dict):
        """Build pattern for ID fields"""
        entity_synonyms = self._get_entity_synonyms(entity_name)
        entity_patterns = [entity_name] + entity_synonyms
        
        entity_options = '|'.join(re.escape(p) for p in entity_patterns)
        pattern_str = rf"({entity_options})\s*(?:id\s*)?(?:#|number|id)?\s*(\d+)"
        
        self.patterns[pattern_key] = re.compile(pattern_str, re.IGNORECASE)

    def _build_email_pattern(self, pattern_key: str, entity_name: str, field_name: str, field_data: Dict):
        """Build pattern for email fields"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        self.patterns[pattern_key] = re.compile(email_pattern, re.IGNORECASE)

    def _build_numeric_patterns(self, pattern_key: str, entity_name: str, field_name: str, field_data: Dict):
        """Build patterns for numeric fields (decimal and integer)"""
        data_type = field_data.get('data_type', 'integer')
        
        # Single value pattern
        if data_type == "decimal":
            single_pattern = r'\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)'
        else:  # integer
            single_pattern = r'\$?\s*(\d{1,3}(?:,\d{3})*)'
        
        self.patterns[pattern_key] = re.compile(single_pattern, re.IGNORECASE)
        
        # Range pattern for numeric fields
        range_pattern_key = f"{pattern_key}_range"
        if data_type == "decimal":
            range_pattern = r'between\s*\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*and\s*\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)'
        else:
            range_pattern = r'between\s*\$?\s*(\d{1,3}(?:,\d{3})*)\s*and\s*\$?\s*(\d{1,3}(?:,\d{3})*)'
        
        self.patterns[range_pattern_key] = re.compile(range_pattern, re.IGNORECASE)

    def _build_date_pattern(self, pattern_key: str, entity_name: str, field_name: str, field_data: Dict):
        """Build pattern for date fields"""
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # ISO format: 2024-01-31
            r'\d{2}/\d{2}/\d{4}',  # US format: 01/31/2024
            r'\d{2}-\d{2}-\d{4}',  # Alternative: 01-31-2024
        ]
        
        combined_pattern = '|'.join(f'({p})' for p in date_patterns)
        self.patterns[pattern_key] = re.compile(combined_pattern)

    def _build_string_pattern(self, pattern_key: str, entity_name: str, field_name: str, field_data: Dict):
        """Build pattern for string fields"""
        # Placeholder for future string-specific patterns
        pass

    def _build_default_pattern(self, pattern_key: str, entity_name: str, field_name: str, field_data: Dict):
        """Default pattern builder for unhandled types"""
        logger.debug(f"No specific pattern builder for {pattern_key}")

    def _get_entity_synonyms(self, entity_name: str) -> List[str]:
        """Get synonyms for an entity from vocabulary"""
        vocabulary = self.domain_config.get('vocabulary', {})
        entity_synonyms = vocabulary.get('entity_synonyms', {})
        return entity_synonyms.get(entity_name, [])
    
    # ==================== Parameter Extraction Section ====================
    
    async def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]:
        """Extract parameters using domain configuration and patterns"""
        parameters = {}
        
        for param in template.get('parameters', []):
            param_name = param['name']
            
            if param_name not in parameters:
                value = await self._extract_single_parameter(
                    user_query, param_name, param.get('type', 'string'), param
                )
                
                if value is not None:
                    parameters[param_name] = value
        
        # Extract missing required parameters using LLM
        missing_params = [
            p for p in template.get('parameters', []) 
            if p.get('required', False) and p['name'] not in parameters
        ]
        
        if missing_params:
            llm_params = await self._extract_missing_with_llm(
                user_query, template, missing_params
            )
            parameters.update(llm_params)
        
        # Apply defaults
        for param in template.get('parameters', []):
            if param['name'] not in parameters and 'default' in param:
                parameters[param['name']] = param['default']
        
        return parameters

    async def _extract_single_parameter(
        self, user_query: str, param_name: str, param_type: str, param: Dict
    ) -> Any:
        """Extract a single parameter value"""
        # Try domain-based extraction first
        value = await self._extract_from_domain(user_query, param_name)
        if value is not None:
            return value
        
        # Then try common parameter patterns
        value = self._extract_common_parameter(user_query, param_name, param_type, param)
        if value is not None:
            return value
        
        return None

    async def _extract_from_domain(self, user_query: str, param_name: str) -> Any:
        """Extract parameter using domain configuration"""
        entities = self.domain_config.get('entities', {})
        fields = self.domain_config.get('fields', {})
        
        for entity_name, entity_data in entities.items():
            entity_fields = fields.get(entity_name, {})
            
            for field_name, field_data in entity_fields.items():
                if not self._field_matches_parameter(field_name, field_data, param_name):
                    continue
                
                pattern_key = f"{entity_name}.{field_name}"
                value = await self._extract_by_pattern(
                    user_query, pattern_key, field_data
                )
                
                if value is not None:
                    return value
        
        return None

    def _field_matches_parameter(
        self, field_name: str, field_data: Dict, param_name: str
    ) -> bool:
        """Check if a field matches the parameter name"""
        aliases = field_data.get('aliases', [])
        return field_name == param_name or param_name in aliases

    async def _extract_by_pattern(
        self, user_query: str, pattern_key: str, field_data: Dict
    ) -> Any:
        """Extract value using pattern matching"""
        if pattern_key not in self.patterns:
            return None
        
        data_type = field_data.get('data_type', 'string')
        
        # Special handling for decimal ranges
        if data_type == "decimal":
            range_value = self._extract_decimal_range(user_query, pattern_key)
            if range_value:
                return range_value
        
        # Standard pattern matching
        match = self.patterns[pattern_key].search(user_query)
        if not match:
            return None
        
        # Convert based on data type
        if data_type == "integer":
            value_str = match.group(len(match.groups()))
            return int(value_str.replace(',', ''))
        elif data_type == "decimal":
            value_str = match.group(1)
            return float(value_str.replace(',', ''))
        elif data_type == "string":
            if "name" in pattern_key.lower():
                name = await self._extract_with_llm(
                    user_query, field_data.get('description', '')
                )
                return f'%{name}%' if name else None
            return match.group(0)
        
        return None

    def _extract_decimal_range(self, user_query: str, pattern_key: str) -> Optional[Dict[str, float]]:
        """Extract decimal range if present"""
        range_pattern_key = f"{pattern_key}_range"
        if range_pattern_key not in self.patterns:
            return None
        
        range_match = self.patterns[range_pattern_key].search(user_query)
        if range_match:
            min_val = float(range_match.group(1).replace(',', ''))
            max_val = float(range_match.group(2).replace(',', ''))
            return {
                "min_amount": min_val,
                "max_amount": max_val
            }
        
        return None

    def _extract_common_parameter(
        self, user_query: str, param_name: str, param_type: str, param: Dict
    ) -> Any:
        """Extract common parameter types"""
        # Time period parameters
        if any(keyword in param_name.lower() for keyword in ["days", "period", "time"]):
            days = self._extract_time_period(user_query)
            if days is not None:
                return days
        
        # Enum parameters
        if param_type == "string" and param.get('allowed_values'):
            value = self._extract_enum_value(user_query, param['allowed_values'])
            if value:
                return value
        
        return None
    
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
        patterns = [
            (r'(?:last|past|previous)\s*(\d+)\s*days?', 1),
            (r'(\d+)\s*weeks?', 7),
            (r'(\d+)\s*months?', 30),
            (r'(\d+)\s*years?', 365),
        ]
        
        for pattern, multiplier in patterns:
            match = re.search(pattern, text_lower)
            if match:
                return int(match.group(1)) * multiplier
        
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
            response = await self._call_llm(prompt)
            response = response.strip()
            
            if response and response.lower() != 'none' and len(response) < 100:
                return response
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
        
        return None
    
    async def _extract_missing_with_llm(
        self, user_query: str, template: Dict, missing_params: List[Dict]
    ) -> Dict[str, Any]:
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
            response = await self._call_llm(extraction_prompt)
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
        
        return {}
    
    async def _call_llm(self, prompt: str) -> str:
        """Unified LLM call method"""
        if hasattr(self.inference_client, 'generate'):
            return await self.inference_client.generate(prompt)
        else:
            return await self.inference_client.generate_response(prompt)
    
    # ==================== Validation Section ====================
    
    def _initialize_validators(self):
        """Initialize validation rules"""
        self.rule_validators = {
            'min': lambda v, r: v >= r.get('value', 0),
            'max': lambda v, r: v <= r.get('value', float('inf')),
            'min_length': lambda v, r: len(str(v)) >= r.get('value', 0),
            'max_length': lambda v, r: len(str(v)) <= r.get('value', float('inf')),
            'length': lambda v, r: len(str(v)) <= r.get('value', 255),
            'pattern': lambda v, r: bool(re.match(r.get('value', ''), str(v))),
            'custom': lambda v, r: self._validate_custom_rule(v, r),
        }
    
    def _initialize_converters(self):
        """Initialize type converters"""
        self.type_converters = {
            'integer': self._convert_to_integer,
            'decimal': self._convert_to_decimal,
            'string': self._convert_to_string,
            'boolean': self._convert_to_boolean,
            'date': self._convert_to_date,
        }
    
    def validate_parameters(self, parameters: Dict[str, Any], template: Dict) -> Tuple[bool, List[str]]:
        """Validate parameters using domain configuration"""
        errors = []
        
        for param in template.get('parameters', []):
            param_errors = self._validate_single_parameter(parameters, param)
            errors.extend(param_errors)
        
        return len(errors) == 0, errors

    def _validate_single_parameter(self, parameters: Dict[str, Any], param: Dict) -> List[str]:
        """Validate a single parameter"""
        param_name = param['name']
        required = param.get('required', False)
        
        # Check required parameters
        if required and not self._has_value(parameters, param_name):
            return [f"Missing required parameter: {param_name}"]
        
        # Skip validation if parameter not provided or is None
        if param_name not in parameters or parameters[param_name] is None:
            return []
        
        value = parameters[param_name]
        errors = []
        
        # Find field configuration
        field = self._find_field_config(param_name)
        
        if field:
            # Validate and convert based on field configuration
            converted_value, conversion_errors = self._validate_and_convert_type(
                value, param_name, field
            )
            
            if conversion_errors:
                errors.extend(conversion_errors)
            else:
                # Update parameter with converted value
                parameters[param_name] = converted_value
                
                # Perform additional validations
                errors.extend(self._validate_enum(converted_value, param_name, field))
                errors.extend(self._validate_custom_rules(converted_value, param_name, field))
        
        return errors

    def _has_value(self, parameters: Dict[str, Any], param_name: str) -> bool:
        """Check if parameter has a non-null value"""
        return param_name in parameters and parameters[param_name] is not None

    def _find_field_config(self, param_name: str) -> Optional[Dict]:
        """Find field configuration for a parameter"""
        fields = self.domain_config.get('fields', {})
        
        for entity_name, entity_fields in fields.items():
            if param_name in entity_fields:
                return entity_fields[param_name]
            
            # Also check aliases
            for field_name, field_data in entity_fields.items():
                aliases = field_data.get('aliases', [])
                if param_name in aliases:
                    return field_data
        
        return None

    def _validate_and_convert_type(
        self, value: Any, param_name: str, field: Dict
    ) -> Tuple[Any, List[str]]:
        """Validate and convert value to the correct type"""
        data_type = field.get('data_type', 'string')
        converter = self.type_converters.get(data_type, self._convert_to_string)
        return converter(value, param_name)

    def _convert_to_integer(self, value: Any, param_name: str) -> Tuple[Optional[int], List[str]]:
        """Convert value to integer"""
        if isinstance(value, int):
            return value, []
        
        try:
            if isinstance(value, str):
                value = value.replace(',', '')
            return int(float(value)), []
        except (ValueError, TypeError):
            return None, [f"Parameter {param_name} must be an integer"]

    def _convert_to_decimal(self, value: Any, param_name: str) -> Tuple[Optional[float], List[str]]:
        """Convert value to decimal/float"""
        if isinstance(value, (int, float)):
            return float(value), []
        
        try:
            if isinstance(value, str):
                value = value.replace(',', '').replace('$', '').strip()
            return float(value), []
        except (ValueError, TypeError):
            return None, [f"Parameter {param_name} must be a number"]

    def _convert_to_string(self, value: Any, param_name: str) -> Tuple[str, List[str]]:
        """Convert value to string"""
        return str(value), []

    def _convert_to_boolean(self, value: Any, param_name: str) -> Tuple[Optional[bool], List[str]]:
        """Convert value to boolean"""
        if isinstance(value, bool):
            return value, []
        
        if isinstance(value, str):
            lower_value = value.lower()
            if lower_value in ('true', '1', 'yes', 'on'):
                return True, []
            elif lower_value in ('false', '0', 'no', 'off'):
                return False, []
        
        return None, [f"Parameter {param_name} must be a boolean"]

    def _convert_to_date(self, value: Any, param_name: str) -> Tuple[Any, List[str]]:
        """Convert value to date"""
        if isinstance(value, str):
            # Simple validation - extend as needed
            if re.match(r'\d{4}-\d{2}-\d{2}', value):
                return value, []
        
        return None, [f"Parameter {param_name} must be a valid date"]

    def _validate_enum(self, value: Any, param_name: str, field: Dict) -> List[str]:
        """Validate enum values"""
        enum_values = field.get('enum_values', [])
        if enum_values and value not in enum_values:
            return [f"Parameter {param_name} must be one of: {', '.join(map(str, enum_values))}"]
        return []

    def _validate_custom_rules(self, value: Any, param_name: str, field: Dict) -> List[str]:
        """Validate custom rules"""
        errors = []
        validation_rules = field.get('validation_rules', [])
        
        for rule in validation_rules:
            if not self._validate_rule(value, rule):
                message = rule.get('message', f'Invalid value for {param_name}')
                errors.append(f"Parameter {param_name} failed validation: {message}")
        
        return errors

    def _validate_rule(self, value: Any, rule: Dict[str, Any]) -> bool:
        """Validate value against a rule"""
        rule_type = rule.get('type')
        validator = self.rule_validators.get(rule_type)
        return validator(value, rule) if validator else True

    def _validate_custom_rule(self, value: Any, rule: Dict) -> bool:
        """Placeholder for custom rule validation"""
        # Implement custom validation logic here
        return True