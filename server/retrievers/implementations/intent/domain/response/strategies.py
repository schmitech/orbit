"""
Response generation strategies for different query types
"""

import logging
from typing import Dict, List, Any, Optional, Protocol
from abc import abstractmethod

logger = logging.getLogger(__name__)


class ResponseStrategy(Protocol):
    """Protocol for response generation strategies"""

    @abstractmethod
    async def generate(self, user_query: str, results: List[Dict], template: Dict,
                       context: Optional[Dict[str, Any]] = None) -> str:
        """Generate a response based on the strategy"""
        pass


class TableResponseStrategy:
    """Strategy for generating table-based responses"""

    def __init__(self, inference_client, prompt_builder, formatter):
        self.inference_client = inference_client
        self.prompt_builder = prompt_builder
        self.formatter = formatter

    async def generate(self, user_query: str, results: List[Dict], template: Dict,
                       context: Optional[Dict[str, Any]] = None) -> str:
        """Generate a table-style response"""
        # Format results
        formatted_results = self.formatter.format_results(results, template)

        # Build prompt
        conversation_context = context.get('conversation_context') if context else None
        prompt = self.prompt_builder.build_table_response_prompt(
            user_query, formatted_results, template, conversation_context
        )

        # Generate response
        try:
            if hasattr(self.inference_client, 'generate'):
                response = await self.inference_client.generate(prompt)
            else:
                response = await self.inference_client.generate_response(prompt)

            # Add table data if requested
            if context and context.get('include_table_data'):
                table_data = self.formatter.format_table_data(formatted_results)
                response = self._append_table_data(response, table_data)

            return response

        except Exception as e:
            logger.error(f"Error generating table response: {e}")
            return self._fallback_table_response(user_query, formatted_results)

    def _append_table_data(self, response: str, table_data: Dict) -> str:
        """Append formatted table data to response"""
        if not table_data.get('rows'):
            return response

        # Create simple text table
        table_str = "\n\n"
        columns = table_data['columns']
        rows = table_data['rows']

        # Header
        table_str += " | ".join(columns) + "\n"
        table_str += "-" * (len(" | ".join(columns))) + "\n"

        # Rows (limit to 10 for display)
        for row in rows[:10]:
            table_str += " | ".join(str(v) for v in row) + "\n"

        if len(rows) > 10:
            table_str += f"... and {len(rows) - 10} more rows\n"

        return response + table_str

    def _fallback_table_response(self, user_query: str, results: List[Dict]) -> str:
        """Fallback response when LLM fails"""
        count = len(results)
        if count == 0:
            return "No results found for your query."
        elif count == 1:
            return f"Found 1 result matching your query."
        else:
            return f"Found {count} results matching your query."


class SummaryResponseStrategy:
    """Strategy for generating summary-based responses"""

    def __init__(self, inference_client, prompt_builder, formatter):
        self.inference_client = inference_client
        self.prompt_builder = prompt_builder
        self.formatter = formatter

    async def generate(self, user_query: str, results: List[Dict], template: Dict,
                       context: Optional[Dict[str, Any]] = None) -> str:
        """Generate a summary-style response"""
        # Format results
        formatted_results = self.formatter.format_results(results, template)

        # Build prompt
        prompt = self.prompt_builder.build_summary_response_prompt(
            user_query, formatted_results, template
        )

        # Generate response
        try:
            if hasattr(self.inference_client, 'generate'):
                response = await self.inference_client.generate(prompt)
            else:
                response = await self.inference_client.generate_response(prompt)

            return response

        except Exception as e:
            logger.error(f"Error generating summary response: {e}")
            return self._fallback_summary_response(formatted_results)

    def _fallback_summary_response(self, results: List[Dict]) -> str:
        """Fallback response when LLM fails"""
        if not results:
            return "No data available for summary."

        # Try to create a basic summary
        summary = self.formatter.format_summary_data(results)
        return f"Summary of results:\n{summary}"


class ErrorResponseStrategy:
    """Strategy for generating error responses"""

    def __init__(self, inference_client, prompt_builder):
        self.inference_client = inference_client
        self.prompt_builder = prompt_builder

    async def generate(self, error: str, user_query: str) -> str:
        """Generate an error response"""
        prompt = self.prompt_builder.build_error_response_prompt(error, user_query)

        try:
            if hasattr(self.inference_client, 'generate'):
                return await self.inference_client.generate(prompt)
            else:
                return await self.inference_client.generate_response(prompt)

        except Exception as e:
            logger.error(f"Error generating error response: {e}")
            return f"I encountered an error processing your request. Please try rephrasing your question."


class NoResultsResponseStrategy:
    """Strategy for generating no-results responses"""

    def __init__(self, inference_client, prompt_builder):
        self.inference_client = inference_client
        self.prompt_builder = prompt_builder

    async def generate(self, user_query: str, template: Dict) -> str:
        """Generate a no-results response"""
        prompt = self.prompt_builder.build_no_results_prompt(user_query, template)

        try:
            if hasattr(self.inference_client, 'generate'):
                return await self.inference_client.generate(prompt)
            else:
                return await self.inference_client.generate_response(prompt)

        except Exception as e:
            logger.error(f"Error generating no-results response: {e}")
            return "I didn't find any results for your query. You might want to try different search criteria."


class ResponseStrategyFactory:
    """Factory for creating response strategies"""

    def __init__(self, inference_client, prompt_builder, formatter):
        self.inference_client = inference_client
        self.prompt_builder = prompt_builder
        self.formatter = formatter

        # Initialize strategies
        self.strategies = {
            'table': TableResponseStrategy(inference_client, prompt_builder, formatter),
            'summary': SummaryResponseStrategy(inference_client, prompt_builder, formatter),
            'error': ErrorResponseStrategy(inference_client, prompt_builder),
            'no_results': NoResultsResponseStrategy(inference_client, prompt_builder)
        }

    def get_strategy(self, strategy_type: str) -> Optional[ResponseStrategy]:
        """Get a response strategy by type"""
        return self.strategies.get(strategy_type)

    def register_strategy(self, name: str, strategy: ResponseStrategy):
        """Register a custom response strategy"""
        self.strategies[name] = strategy