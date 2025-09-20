"""
Prompt assembly for response generation
"""

import logging
from typing import Dict, List, Any, Optional
from ...domain import DomainConfig

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds prompts for LLM-based response generation"""

    def __init__(self, domain_config: DomainConfig):
        """Initialize prompt builder with domain configuration"""
        self.domain_config = domain_config

    def build_table_response_prompt(self, user_query: str, formatted_results: List[Dict],
                                     template: Dict, conversation_context: Optional[str] = None) -> str:
        """Build prompt for table-style response generation"""
        domain_context = self._get_domain_context()
        template_desc = template.get('description', 'query')

        # Prepare results summary
        results_summary = self._summarize_results(formatted_results[:10])  # Limit to 10 for context

        prompt = f"""Generate a natural language response for the user's query about {domain_context}.

User Query: "{user_query}"
Query Type: {template_desc}

Results Found: {len(formatted_results)} records
Sample Results:
{results_summary}

{self._get_conversation_context(conversation_context)}

Instructions:
1. Provide a conversational response that summarizes the results
2. Mention the total number of results found
3. Highlight key findings, patterns, and insights from the detailed data
4. Use specific metrics and details from the results (order counts, spending patterns, customer locations, payment methods, etc.)
5. Identify trends, outliers, or notable characteristics in the data
6. Be informative and analytical while remaining conversational
7. Use natural language, not technical database terms
8. If there are multiple customers, mention geographic distribution, spending ranges, or other patterns

Important: Give ONLY the direct response, no meta-commentary."""

        return prompt

    def build_summary_response_prompt(self, user_query: str, formatted_results: List[Dict],
                                       template: Dict) -> str:
        """Build prompt for summary-style response generation"""
        domain_context = self._get_domain_context()
        template_desc = template.get('description', 'query')

        # Get aggregation details if present
        aggregations = self._extract_aggregations(formatted_results)

        prompt = f"""Generate a summary response for the user's analytical query about {domain_context}.

User Query: "{user_query}"
Analysis Type: {template_desc}

Results:
{self._format_for_summary(formatted_results)}

{self._format_aggregations(aggregations)}

Instructions:
1. Provide a clear summary of the findings
2. Highlight important metrics or totals
3. Explain what the data shows in business terms
4. Be analytical but accessible
5. Focus on insights, not just numbers

Important: Give ONLY the direct response."""

        return prompt

    def build_error_response_prompt(self, error: str, user_query: str) -> str:
        """Build prompt for error response generation"""
        domain_context = self._get_domain_context()

        prompt = f"""The user asked a question about {domain_context}, but there was an error.

User Query: "{user_query}"
Error: {error}

Provide a helpful, conversational response that:
1. Acknowledges the issue without technical details
2. Suggests what might have gone wrong
3. Offers alternative ways to phrase the question if applicable
4. Remains friendly and helpful

Important: Give ONLY the direct response."""

        return prompt

    def build_no_results_prompt(self, user_query: str, template: Dict) -> str:
        """Build prompt for no results response"""
        domain_context = self._get_domain_context()
        template_desc = template.get('description', 'query')

        # Get searchable fields for suggestions
        searchable_fields = self._get_searchable_fields_summary()

        prompt = f"""The user searched in {domain_context} but no results were found.

User Query: "{user_query}"
Query Type: {template_desc}

Available search criteria:
{searchable_fields}

Provide a helpful response that:
1. Explains no results were found
2. Suggests why this might be (e.g., no matching records, criteria too specific)
3. Offers suggestions for modifying the search
4. Remains conversational and helpful

Important: Give ONLY the direct response."""

        return prompt

    def _get_domain_context(self) -> str:
        """Get domain context description"""
        domain_name = self.domain_config.domain_name
        description = self.domain_config.description

        if description:
            return f"the {domain_name} ({description})"
        return f"the {domain_name} system"

    def _get_conversation_context(self, context: Optional[str]) -> str:
        """Format conversation context if provided"""
        if context:
            return f"Conversation Context:\n{context}\n"
        return ""

    def _summarize_results(self, results: List[Dict]) -> str:
        """Create a summary of results for the prompt"""
        if not results:
            return "No results"

        summaries = []
        for idx, result in enumerate(results[:5], 1):
            # Pick key fields to show
            key_fields = self._identify_key_fields(result)
            field_values = []

            for field in key_fields[:6]:  # Increased from 4 to 6 fields for more context
                value = result.get(field, "")
                field_values.append(f"{field}: {value}")

            summaries.append(f"{idx}. {', '.join(field_values)}")

        return "\n".join(summaries)

    def _identify_key_fields(self, result: Dict) -> List[str]:
        """Identify the most important fields in a result"""
        # Priority order for common field types - enhanced for better insights
        priority_patterns = [
            ['id', 'number', 'code'],
            ['name', 'title'],
            ['amount', 'total', 'price', 'spent', 'value'],
            ['date', 'created_at', 'last_order', 'first_order'],
            ['status', 'state', 'order_statuses'],
            ['count', 'order_count', 'completed_orders'],
            ['email', 'phone', 'contact'],
            ['city', 'country', 'location'],
            ['payment_methods', 'payment'],
            ['days_since', 'span_days', 'lifespan'],
            ['avg_', 'median_', 'min_', 'max_'],
            ['percentage', 'analysis_period']
        ]

        key_fields = []
        for patterns in priority_patterns:
            for field in result.keys():
                field_lower = field.lower()
                if any(pattern in field_lower for pattern in patterns):
                    key_fields.append(field)
                    break

        # Add remaining fields if needed
        for field in result.keys():
            if field not in key_fields:
                key_fields.append(field)
            if len(key_fields) >= 8:  # Increased from 5 to 8 for more context
                break

        return key_fields

    def _format_for_summary(self, results: List[Dict]) -> str:
        """Format results specifically for summary responses"""
        if not results:
            return "No data available"

        # For summary queries, often we have aggregated results
        if len(results) == 1 and any(key in str(results[0]).lower() for key in ['sum', 'avg', 'count', 'max', 'min']):
            # Single row with aggregations
            result = results[0]
            formatted = []
            for key, value in result.items():
                formatted.append(f"- {key}: {value}")
            return "\n".join(formatted)

        # Multiple results
        return self._summarize_results(results)

    def _extract_aggregations(self, results: List[Dict]) -> Dict[str, Any]:
        """Extract aggregation values from results"""
        aggregations = {}

        if not results:
            return aggregations

        # Look for common aggregation patterns in field names
        agg_patterns = ['sum', 'avg', 'average', 'count', 'total', 'max', 'min']

        for result in results:
            for key, value in result.items():
                key_lower = key.lower()
                if any(pattern in key_lower for pattern in agg_patterns):
                    aggregations[key] = value

        return aggregations

    def _format_aggregations(self, aggregations: Dict[str, Any]) -> str:
        """Format aggregations for prompt"""
        if not aggregations:
            return ""

        formatted = ["Key Metrics:"]
        for key, value in aggregations.items():
            formatted.append(f"- {key}: {value}")

        return "\n".join(formatted)

    def _get_searchable_fields_summary(self) -> str:
        """Get a summary of searchable fields for suggestions"""
        searchable = self.domain_config.get_searchable_fields()

        if not searchable:
            return "Various fields"

        # Group by entity
        by_entity = {}
        for field in searchable[:10]:  # Limit to 10 fields
            # Find which entity this field belongs to
            for entity_name, entity in self.domain_config.entities.items():
                if field.name in entity.fields:
                    if entity_name not in by_entity:
                        by_entity[entity_name] = []
                    by_entity[entity_name].append(field.display_name or field.name)
                    break

        # Format for display
        formatted = []
        for entity, fields in by_entity.items():
            formatted.append(f"{entity}: {', '.join(fields)}")

        return "\n".join(formatted) if formatted else "Various searchable fields"