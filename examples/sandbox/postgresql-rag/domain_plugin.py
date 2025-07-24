#!/usr/bin/env python3
"""
Domain Plugin for RAG System
============================

This plugin provides domain-specific functionality using the domain configuration,
making it easy to add business logic without modifying the core system.
"""

import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from plugin_system import BaseRAGPlugin, PluginContext, PluginPriority
from domain_configuration import DomainConfiguration, DataType
from base_classes import BaseInferenceClient

logger = logging.getLogger(__name__)


class DomainSpecificPlugin(BaseRAGPlugin):
    """Plugin that provides domain-specific functionality based on configuration"""
    
    def __init__(self, domain: DomainConfiguration, inference_client: BaseInferenceClient = None):
        super().__init__(
            name=f"{domain.domain_name}Plugin",
            version="1.0.0",
            priority=PluginPriority.HIGH
        )
        self.domain = domain
        self.inference_client = inference_client
        self._build_patterns()
    
    def _build_patterns(self):
        """Build patterns from domain vocabulary"""
        self.entity_patterns = {}
        
        # Build patterns for entity recognition
        for entity_name, synonyms in self.domain.vocabulary.entity_synonyms.items():
            all_terms = [entity_name] + synonyms
            pattern = r'\b(' + '|'.join(re.escape(term) for term in all_terms) + r')\b'
            self.entity_patterns[entity_name] = re.compile(pattern, re.IGNORECASE)
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Pre-process query with domain-specific enhancements"""
        processed = query
        
        # Apply common phrase replacements
        for phrase, replacement in self.domain.vocabulary.common_phrases.items():
            if phrase.lower() in processed.lower():
                processed = re.sub(
                    re.escape(phrase), 
                    replacement, 
                    processed, 
                    flags=re.IGNORECASE
                )
        
        # Enhance with metadata
        if not context.metadata:
            context.metadata = {}
        
        # Detect entities mentioned
        mentioned_entities = []
        for entity_name, pattern in self.entity_patterns.items():
            if pattern.search(processed):
                mentioned_entities.append(entity_name)
        
        if mentioned_entities:
            context.metadata['mentioned_entities'] = mentioned_entities
        
        return processed
    
    def extract_parameters(self, query: str, template: Dict, context: PluginContext) -> Dict[str, Any]:
        """Extract domain-specific parameters"""
        parameters = {}
        
        # Extract based on domain query patterns
        for pattern in self.domain.query_patterns:
            if self._matches_pattern(query, pattern):
                # Extract parameters based on pattern configuration
                for filter_field in pattern.common_filters:
                    value = self._extract_filter_value(query, filter_field)
                    if value is not None:
                        parameters[filter_field] = value
        
        # Extract time-based parameters using domain vocabulary
        for time_expr, time_value in self.domain.vocabulary.time_expressions.items():
            if time_expr.lower() in query.lower():
                # Look for time-related parameters in template
                for param in template.get('parameters', []):
                    if 'time' in param['name'] or 'date' in param['name'] or 'days' in param['name']:
                        try:
                            if param['type'] == 'integer':
                                parameters[param['name']] = int(time_value)
                            elif param['type'] == 'date':
                                # Calculate date based on days back
                                days_back = int(time_value)
                                date_value = (datetime.now() - timedelta(days=days_back)).date()
                                parameters[param['name']] = str(date_value)
                        except:
                            pass
        
        return parameters
    
    def _matches_pattern(self, query: str, pattern: Any) -> bool:
        """Check if query matches a domain pattern"""
        query_lower = query.lower()
        
        # Check if required entities are mentioned
        for entity in pattern.required_entities:
            if entity in self.entity_patterns:
                if not self.entity_patterns[entity].search(query):
                    return False
        
        # Check for pattern-specific keywords
        pattern_keywords = pattern.name.lower().split('_')
        matches = sum(1 for keyword in pattern_keywords if keyword in query_lower)
        
        return matches >= len(pattern_keywords) / 2
    
    def _extract_filter_value(self, query: str, filter_field: str) -> Optional[Any]:
        """Extract filter value from query"""
        # Find field configuration
        field = None
        for entity_name, fields in self.domain.fields.items():
            if filter_field in fields:
                field = fields[filter_field]
                break
        
        if not field:
            return None
        
        # Extract based on field type
        if field.data_type == DataType.STRING and field.enum_values:
            # Look for enum values
            query_lower = query.lower()
            for value in field.enum_values:
                if value.lower() in query_lower:
                    return value
        
        elif field.data_type == DataType.DECIMAL:
            # Look for amount patterns
            amount_pattern = re.compile(r'\$?\s*(\d+(?:\.\d{2})?)')
            match = amount_pattern.search(query)
            if match:
                return float(match.group(1))
        
        elif field.data_type == DataType.INTEGER:
            # Look for number patterns specific to this field
            if 'id' in filter_field.lower():
                id_pattern = re.compile(rf'{filter_field}\s*(?:#|:)?\s*(\d+)', re.IGNORECASE)
                match = id_pattern.search(query)
                if match:
                    return int(match.group(1))
        
        return None
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Apply domain-specific post-processing"""
        if not results:
            return results
        
        processed_results = []
        
        for result in results:
            processed = result.copy()
            
            # Apply domain-specific enrichment
            for entity_name, entity in self.domain.entities.items():
                # Add display names if configured
                if entity.display_name_field and entity.primary_key in result:
                    pk_value = result[entity.primary_key]
                    if entity.display_name_field in result:
                        processed[f'{entity_name}_display'] = result[entity.display_name_field]
            
            # Apply field-specific formatting
            for key, value in result.items():
                field = self._find_field(key)
                if field and field.display_format:
                    formatted_key = f"{key}_formatted"
                    if field.display_format == "currency" and isinstance(value, (int, float)):
                        processed[formatted_key] = f"${value:,.2f}"
                    elif field.display_format == "percentage" and isinstance(value, (int, float)):
                        processed[formatted_key] = f"{value:.1%}"
                    elif field.display_format == "phone" and isinstance(value, str):
                        processed[formatted_key] = self._format_phone(value)
            
            processed_results.append(processed)
        
        return processed_results
    
    def _find_field(self, field_name: str):
        """Find field configuration by name"""
        for entity_name, fields in self.domain.fields.items():
            if field_name in fields:
                return fields[field_name]
        return None
    
    def _format_phone(self, phone: str) -> str:
        """Format phone number"""
        # Remove non-digits
        digits = re.sub(r'\D', '', phone)
        
        # Format based on length
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        else:
            return phone
    
    def validate_template(self, template: Dict, context: PluginContext) -> bool:
        """Validate template against domain rules"""
        # Check if template uses valid entities
        if 'semantic_tags' in template:
            primary_entity = template['semantic_tags'].get('primary_entity')
            if primary_entity and primary_entity not in self.domain.entities:
                logger.warning(f"Template uses unknown entity: {primary_entity}")
                return False
        
        # Check if parameters reference valid fields
        for param in template.get('parameters', []):
            param_name = param['name']
            field_found = False
            
            for entity_name, fields in self.domain.fields.items():
                if param_name in fields or any(param_name in field.aliases for field in fields.values()):
                    field_found = True
                    break
            
            if not field_found and param.get('required', False):
                logger.warning(f"Template has unknown required parameter: {param_name}")
                # Still allow it, but log the warning
        
        return True
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Enhance response with domain-specific information"""
        enhanced = response
        
        # Add domain context if helpful
        if context.metadata and 'mentioned_entities' in context.metadata:
            entities = context.metadata['mentioned_entities']
            if entities and not any(entity.lower() in response.lower() for entity in entities):
                # Response doesn't mention the entities, might want to clarify
                entity_descriptions = []
                for entity_name in entities:
                    if entity_name in self.domain.entities:
                        entity_descriptions.append(self.domain.entities[entity_name].description)
                
                if entity_descriptions:
                    enhanced += f"\n\n📌 Context: Query involved {', '.join(entity_descriptions)}"
        
        return enhanced


class DomainAnalyticsPlugin(BaseRAGPlugin):
    """Plugin for domain-specific analytics and insights"""
    
    def __init__(self, domain: DomainConfiguration):
        super().__init__(
            name=f"{domain.domain_name}Analytics",
            version="1.0.0",
            priority=PluginPriority.NORMAL
        )
        self.domain = domain
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Add analytics insights to results"""
        if not results or len(results) < 2:
            return results
        
        # Add analytics metadata to context
        if not context.metadata:
            context.metadata = {}
        
        analytics = {}
        
        # Analyze numeric fields
        for field_name, field in self._get_numeric_fields().items():
            values = [r.get(field_name) for r in results if field_name in r and r[field_name] is not None]
            if values:
                analytics[field_name] = {
                    'min': min(values),
                    'max': max(values),
                    'avg': sum(values) / len(values),
                    'count': len(values)
                }
        
        # Analyze categorical fields
        for field_name, field in self._get_categorical_fields().items():
            values = [r.get(field_name) for r in results if field_name in r and r[field_name] is not None]
            if values:
                from collections import Counter
                value_counts = Counter(values)
                analytics[field_name] = {
                    'distribution': dict(value_counts),
                    'most_common': value_counts.most_common(1)[0][0] if value_counts else None
                }
        
        context.metadata['analytics'] = analytics
        
        return results
    
    def _get_numeric_fields(self) -> Dict[str, Any]:
        """Get numeric fields from domain"""
        numeric_fields = {}
        for entity_name, fields in self.domain.fields.items():
            for field_name, field in fields.items():
                if field.data_type in [DataType.INTEGER, DataType.DECIMAL]:
                    numeric_fields[field_name] = field
        return numeric_fields
    
    def _get_categorical_fields(self) -> Dict[str, Any]:
        """Get categorical fields from domain"""
        categorical_fields = {}
        for entity_name, fields in self.domain.fields.items():
            for field_name, field in fields.items():
                if field.enum_values or (field.data_type == DataType.STRING and field.filterable):
                    categorical_fields[field_name] = field
        return categorical_fields
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Add analytics insights to response"""
        if not context.metadata or 'analytics' not in context.metadata:
            return response
        
        analytics = context.metadata['analytics']
        if not analytics:
            return response
        
        # Add relevant insights
        insights = []
        
        for field_name, stats in analytics.items():
            field = self._find_field(field_name)
            if not field:
                continue
            
            if 'avg' in stats:
                if field.display_format == "currency":
                    insights.append(f"Average {field_name}: ${stats['avg']:,.2f}")
                else:
                    insights.append(f"Average {field_name}: {stats['avg']:.2f}")
            
            if 'distribution' in stats and len(stats['distribution']) > 1:
                most_common = stats['most_common']
                insights.append(f"Most common {field_name}: {most_common}")
        
        if insights and len(insights) <= 3:
            response += f"\n\n📊 Insights: {' | '.join(insights)}"
        
        return response
    
    def _find_field(self, field_name: str):
        """Find field configuration by name"""
        for entity_name, fields in self.domain.fields.items():
            if field_name in fields:
                return fields[field_name]
        return None