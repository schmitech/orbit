#!/usr/bin/env python3
"""
Enhanced Base RAG System with Domain Configuration Support
=========================================================

This enhanced version integrates domain configuration and template library
to make the RAG system fully reusable across different business domains.
"""

import yaml
import chromadb
from chromadb.config import Settings
import json
import logging
from typing import Dict, List, Optional, Any, Tuple, Type
from abc import ABC, abstractmethod
from datetime import datetime, date
import os

from base_rag_system import (
    BaseRAGSystem,
    BaseEmbeddingClient,
    BaseInferenceClient,
    BaseDatabaseClient,
    BaseParameterExtractor,
    BaseResponseGenerator
)

from domain_configuration import DomainConfiguration, DomainEntity, DomainField
from template_library import TemplateLibrary, QueryTemplateBuilder, TemplateType

logger = logging.getLogger(__name__)


class DomainAwareParameterExtractor(BaseParameterExtractor):
    """Domain-aware parameter extraction using domain configuration"""
    
    def __init__(self, inference_client: BaseInferenceClient, domain: DomainConfiguration):
        super().__init__(inference_client)
        self.domain = domain
        self._build_extraction_patterns()
    
    def _build_extraction_patterns(self):
        """Build extraction patterns from domain configuration"""
        import re
        self.patterns = {}
        
        # Build patterns for each entity's searchable fields
        for entity_name, entity in self.domain.entities.items():
            for field_name, field in self.domain.fields[entity_name].items():
                if field.searchable or field.filterable:
                    # Create pattern based on field type and aliases
                    pattern_key = f"{entity_name}.{field_name}"
                    
                    if field.data_type.value == "integer" and "id" in field_name.lower():
                        # ID pattern
                        entity_patterns = [entity_name] + self.domain.vocabulary.entity_synonyms.get(entity_name, [])
                        pattern_str = f"({'|'.join(entity_patterns)})\\s*(?:id\\s*)?(?:#|number|id)?\\s*(\\d+)"
                        self.patterns[pattern_key] = re.compile(pattern_str, re.IGNORECASE)
                    
                    elif field.data_type.value == "string" and field_name == "email":
                        # Email pattern
                        self.patterns[pattern_key] = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+', re.IGNORECASE)
                    
                    elif field.data_type.value == "decimal":
                        # Amount pattern
                        self.patterns[pattern_key] = re.compile(r'\$?\s*(\d+(?:\.\d{2})?)', re.IGNORECASE)
                    
                    elif field.data_type.value == "date":
                        # Date pattern
                        self.patterns[pattern_key] = re.compile(r'\d{4}-\d{2}-\d{2}')
    
    def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]:
        """Extract parameters using domain configuration"""
        parameters = {}
        
        # Try pattern-based extraction first
        for param in template.get('parameters', []):
            param_name = param['name']
            param_type = param['type']
            
            # Look for matching field in domain
            field_found = False
            for entity_name, fields in self.domain.fields.items():
                for field_name, field in fields.items():
                    if field_name == param_name or param_name in field.aliases:
                        field_found = True
                        pattern_key = f"{entity_name}.{field_name}"
                        
                        if pattern_key in self.patterns:
                            match = self.patterns[pattern_key].search(user_query)
                            if match:
                                # Extract based on field type
                                if field.data_type.value == "integer":
                                    parameters[param_name] = int(match.group(len(match.groups())))
                                elif field.data_type.value == "decimal":
                                    parameters[param_name] = float(match.group(1))
                                elif field.data_type.value == "string":
                                    if "name" in field_name.lower():
                                        # Use LLM for name extraction
                                        name = self._extract_with_llm(user_query, field.description)
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
                elif param_type == "string" and param_name in template.get('allowed_values', []):
                    # Extract enum value
                    value = self._extract_enum_value(user_query, param['allowed_values'])
                    if value:
                        parameters[param_name] = value
        
        # Use LLM for missing required parameters
        missing_params = [p for p in template.get('parameters', []) 
                         if p.get('required', False) and p['name'] not in parameters]
        
        if missing_params:
            llm_params = self._extract_missing_with_llm(user_query, template, missing_params)
            parameters.update(llm_params)
        
        # Apply defaults
        for param in template.get('parameters', []):
            if param['name'] not in parameters and 'default' in param:
                parameters[param['name']] = param['default']
        
        return parameters
    
    def _extract_time_period(self, text: str) -> Optional[int]:
        """Extract time period from text"""
        import re
        
        time_mappings = self.domain.vocabulary.time_expressions
        text_lower = text.lower()
        
        # Check vocabulary mappings first
        for phrase, days_expr in time_mappings.items():
            if phrase in text_lower:
                # Evaluate expression if it's a number
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
        
        return None
    
    def _extract_enum_value(self, text: str, allowed_values: List[str]) -> Optional[str]:
        """Extract enum value from text"""
        text_lower = text.lower()
        for value in allowed_values:
            if value.lower() in text_lower:
                return value
        return None
    
    def _extract_with_llm(self, text: str, field_description: str) -> Optional[str]:
        """Extract value using LLM"""
        prompt = f"""Extract the {field_description} from this text. Return ONLY the value, nothing else.
If no value is found, return "None".

Text: "{text}"

Value:"""
        
        response = self.inference_client.generate_response(prompt, temperature=0.1)
        response = response.strip()
        
        if response and response.lower() != 'none' and len(response) < 100:
            return response
        return None
    
    def _extract_missing_with_llm(self, user_query: str, template: Dict, missing_params: List[Dict]) -> Dict[str, Any]:
        """Extract missing parameters using LLM"""
        param_descriptions = []
        for param in missing_params:
            desc = f"- {param['name']} ({param['type']}): {param['description']}"
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
            response = self.inference_client.generate_response(extraction_prompt, temperature=0.1)
            
            # Extract JSON from response
            import re
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
            param_type = param['type']
            required = param.get('required', False)
            
            if required and param_name not in parameters:
                errors.append(f"Missing required parameter: {param_name}")
                continue
            
            if param_name in parameters:
                value = parameters[param_name]
                
                # Find corresponding field in domain
                field = None
                for entity_name, fields in self.domain.fields.items():
                    if param_name in fields:
                        field = fields[param_name]
                        break
                
                # Validate using field configuration
                if field:
                    # Type validation
                    if field.data_type.value == "integer" and not isinstance(value, int):
                        errors.append(f"Parameter {param_name} must be an integer")
                    elif field.data_type.value == "decimal" and not isinstance(value, (int, float)):
                        errors.append(f"Parameter {param_name} must be a number")
                    elif field.data_type.value == "string" and not isinstance(value, str):
                        errors.append(f"Parameter {param_name} must be a string")
                    
                    # Enum validation
                    if field.enum_values and value not in field.enum_values:
                        errors.append(f"Parameter {param_name} must be one of: {', '.join(field.enum_values)}")
                    
                    # Custom validation rules
                    for rule in field.validation_rules:
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
            import re
            return bool(re.match(rule.get('value', '.*'), value))
        elif rule_type == 'length' and isinstance(value, str):
            return len(value) <= rule.get('value', 255)
        
        return True


class DomainAwareResponseGenerator(BaseResponseGenerator):
    """Domain-aware response generation"""
    
    def __init__(self, inference_client: BaseInferenceClient, domain: DomainConfiguration):
        super().__init__(inference_client)
        self.domain = domain
    
    def generate_response(self, user_query: str, results: List[Dict], template: Dict, 
                         error: Optional[str] = None) -> str:
        """Generate response using domain configuration"""
        
        if error:
            return self._generate_error_response(error, user_query)
        
        if not results:
            return self._generate_no_results_response(user_query, template)
        
        # Format results based on domain configuration
        formatted_results = self._format_results_for_domain(results, template)
        
        # Choose response strategy based on result format
        if template.get('result_format') == 'summary':
            return self._generate_summary_response(user_query, formatted_results, template)
        else:
            return self._generate_table_response(user_query, formatted_results, template)
    
    def _format_results_for_domain(self, results: List[Dict], template: Dict) -> List[Dict]:
        """Format results according to domain field configurations"""
        formatted = []
        
        for result in results:
            formatted_result = {}
            
            for key, value in result.items():
                # Find field configuration
                field = None
                for entity_name, fields in self.domain.fields.items():
                    if key in fields:
                        field = fields[key]
                        break
                
                if field and field.display_format:
                    # Apply display formatting
                    if field.display_format == "currency" and isinstance(value, (int, float)):
                        formatted_result[key] = f"${value:,.2f}"
                    elif field.display_format == "percentage" and isinstance(value, (int, float)):
                        formatted_result[key] = f"{value:.1%}"
                    elif field.display_format == "date" and value:
                        formatted_result[key] = self._format_date(value)
                    elif field.display_format == "email":
                        formatted_result[key] = value  # Keep as is
                    else:
                        formatted_result[key] = value
                else:
                    formatted_result[key] = value
            
            formatted.append(formatted_result)
        
        return formatted
    
    def _format_date(self, value) -> str:
        """Format date value"""
        try:
            if isinstance(value, str):
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return dt.strftime("%B %d, %Y")
            elif isinstance(value, (date, datetime)):
                return value.strftime("%B %d, %Y")
        except:
            pass
        return str(value)
    
    def _generate_error_response(self, error: str, user_query: str) -> str:
        """Generate helpful error response"""
        prompt = f"""The user asked: "{user_query}"

However, there was an error: {error}

Provide a helpful, conversational response that acknowledges the issue and suggests what might have gone wrong or alternative ways to ask. Be brief and friendly.

Important: Give ONLY the direct response."""
        
        return self.inference_client.generate_response(prompt)
    
    def _generate_no_results_response(self, user_query: str, template: Dict) -> str:
        """Generate response when no results found"""
        prompt = f"""The user asked: "{user_query}"

The query returned no results. This was a {template['description']} query.

Provide a helpful response explaining no results were found and suggest why this might be (e.g., no matching records, time period too restrictive). Be conversational and helpful.

Important: Give ONLY the direct response."""
        
        return self.inference_client.generate_response(prompt)
    
    def _generate_summary_response(self, user_query: str, results: List[Dict], template: Dict) -> str:
        """Generate response for summary queries"""
        # Create context about the domain
        domain_context = f"This is a {self.domain.domain_name} system query."
        
        # Format results
        if len(results) == 1:
            result = results[0]
            formatted_result = json.dumps(result, indent=2, default=str, ensure_ascii=False)
        else:
            formatted_result = json.dumps(results[:5], indent=2, default=str, ensure_ascii=False)
        
        prompt = f"""{domain_context}

The user asked: "{user_query}"

This is a {template['description']} query that returned summary data:

{formatted_result}

Provide a natural, conversational response that directly answers the question. Include specific details from the data. Be specific and informative.

Important: Give ONLY the direct response."""
        
        return self.inference_client.generate_response(prompt, temperature=0.3)
    
    def _generate_table_response(self, user_query: str, results: List[Dict], template: Dict) -> str:
        """Generate response for table/list queries"""
        result_count = len(results)
        
        # Get primary entity for better context
        primary_entity = None
        if 'semantic_tags' in template:
            primary_entity = template['semantic_tags'].get('primary_entity')
        
        if primary_entity and primary_entity in self.domain.entities:
            entity = self.domain.entities[primary_entity]
            entity_desc = entity.description
        else:
            entity_desc = "records"
        
        # Show sample of results
        sample_size = min(5, result_count)
        sample_results = results[:sample_size]
        formatted_sample = json.dumps(sample_results, indent=2, default=str, ensure_ascii=False)
        
        prompt = f"""This is a {self.domain.domain_name} system query.

The user asked: "{user_query}"

This query returned {result_count} {entity_desc}. Here's a sample of the data:

{formatted_sample}

Provide a natural, conversational response that:
- States how many results were found
- Mentions specific details from the results
- Highlights interesting patterns or notable items

Important: Give ONLY the direct response. Use the actual data details."""
        
        return self.inference_client.generate_response(prompt, temperature=0.3)


class EnhancedRAGSystem(BaseRAGSystem):
    """Enhanced RAG system with domain configuration support"""
    
    def __init__(self,
                 domain: DomainConfiguration,
                 template_library: Optional[TemplateLibrary] = None,
                 chroma_persist_directory: str = "./chroma_db",
                 embedding_client: BaseEmbeddingClient = None,
                 inference_client: BaseInferenceClient = None,
                 db_client: BaseDatabaseClient = None):
        """
        Initialize enhanced RAG system with domain configuration
        
        Args:
            domain: Domain configuration object
            template_library: Optional template library
            chroma_persist_directory: Directory for ChromaDB persistence
            embedding_client: Client for generating embeddings
            inference_client: Client for generating responses
            db_client: Client for database operations
        """
        self.domain = domain
        self.template_library = template_library or TemplateLibrary(domain)
        
        # Create domain-aware components
        parameter_extractor = DomainAwareParameterExtractor(inference_client, domain)
        response_generator = DomainAwareResponseGenerator(inference_client, domain)
        
        # Initialize base class
        super().__init__(
            chroma_persist_directory=chroma_persist_directory,
            embedding_client=embedding_client,
            inference_client=inference_client,
            db_client=db_client,
            parameter_extractor=parameter_extractor,
            response_generator=response_generator
        )
    
    def populate_chromadb_from_library(self, clear_first: bool = False):
        """Populate ChromaDB from template library"""
        if clear_first:
            self.clear_chromadb()
        
        templates = list(self.template_library.templates.values())
        
        if not templates:
            logger.error("No templates in library")
            return
        
        logger.info(f"Loading {len(templates)} templates from library into ChromaDB...")
        
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for template in templates:
            template_id = template['id']
            
            # Create embedding text
            embedding_text = self.create_embedding_text(template)
            
            # Get embedding
            embedding = self.embedding_client.get_embedding(embedding_text)
            
            if embedding:
                ids.append(template_id)
                embeddings.append(embedding)
                documents.append(embedding_text)
                metadatas.append(self.create_metadata(template))
        
        if ids:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Successfully loaded {len(ids)} templates")
        else:
            logger.error("No valid embeddings generated")
    
    def create_embedding_text(self, template: Dict) -> str:
        """Create text for embedding from template using domain vocabulary"""
        parts = [
            template.get('description', ''),
            ' '.join(template.get('nl_examples', [])),
            ' '.join(template.get('tags', []))
        ]
        
        # Add parameter names
        param_names = [p['name'].replace('_', ' ') for p in template.get('parameters', [])]
        parts.extend(param_names)
        
        # Add semantic tags if available
        if 'semantic_tags' in template:
            tags = template['semantic_tags']
            parts.append(tags.get('action', ''))
            parts.append(tags.get('primary_entity', ''))
            if tags.get('secondary_entity'):
                parts.append(tags['secondary_entity'])
            parts.extend(tags.get('qualifiers', []))
        
        # Add entity synonyms from domain vocabulary
        if 'semantic_tags' in template:
            primary_entity = template['semantic_tags'].get('primary_entity')
            if primary_entity in self.domain.vocabulary.entity_synonyms:
                parts.extend(self.domain.vocabulary.entity_synonyms[primary_entity])
        
        return ' '.join(parts)
    
    def rerank_templates(self, templates: List[Dict], user_query: str) -> List[Dict]:
        """Rerank templates using domain-specific rules"""
        query_lower = user_query.lower()
        
        for template_info in templates:
            template = template_info['template']
            boost = 0.0
            
            # Check for entity matches using domain vocabulary
            if 'semantic_tags' in template:
                primary_entity = template['semantic_tags'].get('primary_entity')
                if primary_entity:
                    # Check entity synonyms
                    entity_terms = [primary_entity] + self.domain.vocabulary.entity_synonyms.get(primary_entity, [])
                    for term in entity_terms:
                        if term.lower() in query_lower:
                            boost += 0.2
                            break
            
            # Check for action verb matches
            for action, verbs in self.domain.vocabulary.action_verbs.items():
                if any(verb.lower() in query_lower for verb in verbs):
                    if 'semantic_tags' in template and template['semantic_tags'].get('action') == action:
                        boost += 0.15
            
            # Apply boost
            template_info['similarity'] = min(1.0, template_info['similarity'] + boost)
        
        # Re-sort by adjusted similarity
        return sorted(templates, key=lambda x: x['similarity'], reverse=True)
    
    def print_configuration(self):
        """Print enhanced configuration"""
        print(f"🤖 Enhanced RAG System Configuration:")
        print(f"  Domain: {self.domain.domain_name}")
        print(f"  Description: {self.domain.description}")
        print(f"  Entities: {', '.join(self.domain.entities.keys())}")
        print(f"  Templates: {len(self.template_library.templates)}")
        print(f"  ChromaDB Path: {self.chroma_persist_directory}")
        
        # Test embedding dimensions
        if self.embedding_client:
            try:
                test_embedding = self.embedding_client.get_embedding("test")
                if test_embedding:
                    print(f"  Embedding Dimensions: {len(test_embedding)}")
                else:
                    print("  Embedding Dimensions: Failed to get test embedding")
            except Exception as e:
                print(f"  Embedding Dimensions: Error - {e}")