"""
Domain-aware response generation for Intent retriever
"""

import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, date

logger = logging.getLogger(__name__)


class DomainAwareResponseGenerator:
    """Domain-aware response generation using domain configuration and LLM"""
    
    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None):
        self.inference_client = inference_client
        self.domain_config = domain_config or {}
    
    async def generate_response(self, user_query: str, results: List[Dict], template: Dict, 
                         error: Optional[str] = None, conversation_context: Optional[str] = None) -> str:
        """Generate response using domain configuration"""
        
        if error:
            return await self._generate_error_response(error, user_query)
        
        if not results:
            return await self._generate_no_results_response(user_query, template)
        
        # Format results based on domain configuration
        formatted_results = self._format_results_for_domain(results, template)
        
        # Choose response strategy based on result format
        result_format = template.get('result_format', 'table')
        if result_format == 'summary':
            return await self._generate_summary_response(user_query, formatted_results, template)
        else:
            return await self._generate_table_response(user_query, formatted_results, template, conversation_context)
    
    def _format_results_for_domain(self, results: List[Dict], template: Dict) -> List[Dict]:
        """Format results according to domain field configurations"""
        formatted = []
        
        fields = self.domain_config.get('fields', {})
        
        for result in results:
            formatted_result = {}
            
            for key, value in result.items():
                # Find field configuration
                field = None
                for entity_name, entity_fields in fields.items():
                    if key in entity_fields:
                        field = entity_fields[key]
                        break
                
                if field and field.get('display_format'):
                    # Apply display formatting
                    display_format = field['display_format']
                    if display_format == "currency" and isinstance(value, (int, float)):
                        formatted_result[key] = f"${value:,.2f}"
                    elif display_format == "percentage" and isinstance(value, (int, float)):
                        formatted_result[key] = f"{value:.1%}"
                    elif display_format == "date" and value:
                        formatted_result[key] = self._format_date(value)
                    elif display_format == "email":
                        formatted_result[key] = value  # Keep as is
                    elif display_format == "phone":
                        formatted_result[key] = self._format_phone(value)
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
    
    def _format_phone(self, value) -> str:
        """Format phone number"""
        if not value:
            return ""
        
        # Simple phone formatting
        phone = str(value).replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        if len(phone) == 10:
            return f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
        return str(value)
    
    async def _generate_error_response(self, error: str, user_query: str) -> str:
        """Generate helpful error response"""
        prompt = f"""The user asked: "{user_query}"

However, there was an error: {error}

Provide a helpful, conversational response that acknowledges the issue and suggests what might have gone wrong or alternative ways to ask. Be brief and friendly.

Important: Give ONLY the direct response."""
        
        try:
            if hasattr(self.inference_client, 'generate'):
                return await self.inference_client.generate(prompt)
            else:
                return await self.inference_client.generate_response(prompt)
        except Exception as e:
            logger.error(f"Error generating error response: {e}")
            return f"I encountered an error processing your request: {error}. Please try rephrasing your question."
    
    async def _generate_no_results_response(self, user_query: str, template: Dict) -> str:
        """Generate response when no results found"""
        domain_name = self.domain_config.get('domain_name', 'system')
        template_description = template.get('description', 'query')
        
        prompt = f"""The user asked: "{user_query}"

This was a {template_description} in the {domain_name} system, but no results were found.

Provide a helpful response explaining no results were found and suggest why this might be (e.g., no matching records, criteria too restrictive). Be conversational and helpful.

Important: Give ONLY the direct response."""
        
        try:
            if hasattr(self.inference_client, 'generate'):
                return await self.inference_client.generate(prompt)
            else:
                return await self.inference_client.generate_response(prompt)
        except Exception as e:
            logger.error(f"Error generating no results response: {e}")
            return "I didn't find any results for your query. You might want to try different search criteria."
    
    async def _generate_summary_response(self, user_query: str, results: List[Dict], template: Dict) -> str:
        """Generate response for summary queries"""
        domain_name = self.domain_config.get('domain_name', 'system')
        domain_description = self.domain_config.get('description', '')
        
        # Create context about the domain
        domain_context = f"This is a {domain_name} system"
        if domain_description:
            domain_context += f" for {domain_description.lower()}"
        
        # Format results
        if len(results) == 1:
            result = results[0]
            formatted_result = json.dumps(result, indent=2, default=str, ensure_ascii=False)
        else:
            formatted_result = json.dumps(results[:5], indent=2, default=str, ensure_ascii=False)
        
        prompt = f"""{domain_context}.

The user asked: "{user_query}"

This is a {template.get('description', 'query')} that returned summary data:

{formatted_result}

Provide a natural, conversational response that directly answers the question. Include specific details from the data. Be specific and informative.

Important: Give ONLY the direct response."""
        
        try:
            if hasattr(self.inference_client, 'generate'):
                return await self.inference_client.generate(prompt)
            else:
                return await self.inference_client.generate_response(prompt)
        except Exception as e:
            logger.error(f"Error generating summary response: {e}")
            return self._format_fallback_summary(results)
    
    async def _generate_table_response(self, user_query: str, results: List[Dict], template: Dict, conversation_context: Optional[str] = None) -> str:
        """Generate response for table/list queries"""
        result_count = len(results)
        domain_name = self.domain_config.get('domain_name', 'system')
        
        # Get primary entity for better context
        primary_entity = None
        semantic_tags = template.get('semantic_tags', {})
        if semantic_tags:
            primary_entity = semantic_tags.get('primary_entity')
        
        entity_desc = "records"
        if primary_entity:
            entities = self.domain_config.get('entities', {})
            if primary_entity in entities:
                entity_desc = entities[primary_entity].get('description', f"{primary_entity} records")
        
        # Show sample of results
        sample_size = min(5, result_count)
        sample_results = results[:sample_size]
        formatted_sample = json.dumps(sample_results, indent=2, default=str, ensure_ascii=False)
        
        context_info = ""
        if conversation_context:
            context_info = f"\\nConversation context:\\n{conversation_context}\\n"
        
        prompt = f"""This is a {domain_name} system.
{context_info}
The user asked: "{user_query}"

This query returned {result_count} {entity_desc}. Here's a sample of the data:

{formatted_sample}

Provide a natural, conversational response that:
- States how many results were found
- Mentions specific details from the results
- Highlights interesting patterns or notable items

Important: Give ONLY the direct response. Use the actual data details."""
        
        try:
            if hasattr(self.inference_client, 'generate'):
                return await self.inference_client.generate(prompt)
            else:
                return await self.inference_client.generate_response(prompt)
        except Exception as e:
            logger.error(f"Error generating table response: {e}")
            return self._format_fallback_table(results, result_count, entity_desc)
    
    def _format_fallback_summary(self, results: List[Dict]) -> str:
        """Fallback summary formatting when LLM fails"""
        if not results:
            return "No results found."
        
        result = results[0]
        lines = []
        for key, value in result.items():
            if value is not None:
                formatted_key = key.replace('_', ' ').title()
                lines.append(f"{formatted_key}: {value}")
        
        return "\\n".join(lines)
    
    def _format_fallback_table(self, results: List[Dict], count: int, entity_desc: str) -> str:
        """Fallback table formatting when LLM fails"""
        if not results:
            return "No results found."
        
        lines = [f"Found {count} {entity_desc}:"]
        
        for i, result in enumerate(results[:3]):
            lines.append(f"\\n{i+1}. ")
            item_parts = []
            for key, value in result.items():
                if value is not None and key in ['id', 'name', 'title', 'total', 'amount', 'date']:
                    item_parts.append(f"{key}: {value}")
            lines.append(", ".join(item_parts))
        
        if count > 3:
            lines.append(f"\\n... and {count - 3} more results")
        
        return "".join(lines)