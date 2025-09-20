"""
Main response generator facade using modular components
"""

import logging
from typing import Dict, List, Any, Optional
from ...domain import DomainConfig
from .formatters import ResponseFormatter
from .prompts import PromptBuilder
from .strategies import ResponseStrategyFactory

logger = logging.getLogger(__name__)


class DomainResponseGenerator:
    """
    Facade class for domain-aware response generation.
    Orchestrates formatting, prompt building, and strategy selection.
    """

    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None):
        """Initialize the domain response generator"""
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
        """Initialize all response generation components"""
        # Initialize formatter
        self.formatter = ResponseFormatter(self.domain_config)

        # Initialize prompt builder
        self.prompt_builder = PromptBuilder(self.domain_config)

        # Initialize strategy factory
        self.strategy_factory = ResponseStrategyFactory(
            self.inference_client,
            self.prompt_builder,
            self.formatter
        )

        logger.info(f"Initialized DomainResponseGenerator for {self.domain_config.domain_name}")

    async def generate_response(self, user_query: str, results: List[Dict], template: Dict,
                                 error: Optional[str] = None,
                                 conversation_context: Optional[str] = None) -> str:
        """
        Generate response using domain configuration.
        Main entry point that maintains backward compatibility.
        """
        # Handle error case
        if error:
            strategy = self.strategy_factory.get_strategy('error')
            return await strategy.generate(error, user_query)

        # Handle no results
        if not results:
            strategy = self.strategy_factory.get_strategy('no_results')
            return await strategy.generate(user_query, template)

        # Determine response format from template
        result_format = template.get('result_format', 'table')

        # Select strategy based on format
        if result_format == 'summary':
            strategy = self.strategy_factory.get_strategy('summary')
        else:
            strategy = self.strategy_factory.get_strategy('table')

        # Generate response with context
        context = {
            'conversation_context': conversation_context,
            'include_table_data': False  # Can be configured
        }

        return await strategy.generate(user_query, results, template, context)

    def format_results(self, results: List[Dict], template: Dict) -> List[Dict]:
        """
        Format results according to domain configuration.
        Public method for direct formatting without LLM generation.
        """
        return self.formatter.format_results(results, template)

    def get_table_data(self, results: List[Dict], columns: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Get formatted table data for UI display.
        Returns structured data with columns and rows.
        """
        formatted_results = self.formatter.format_results(results, {})
        return self.formatter.format_table_data(formatted_results, columns)

    def get_summary_data(self, results: List[Dict], fields: Optional[List[str]] = None) -> str:
        """
        Get formatted summary text.
        Returns a text summary of the results.
        """
        formatted_results = self.formatter.format_results(results, {})
        return self.formatter.format_summary_data(formatted_results, fields)

    async def generate_custom_response(self, user_query: str, results: List[Dict],
                                        custom_prompt: str) -> str:
        """
        Generate response with a custom prompt.
        Allows for domain-specific response generation.
        """
        try:
            # Format results first
            formatted_results = self.formatter.format_results(results, {})

            # Create custom prompt with domain context
            domain_context = f"Domain: {self.domain_config.domain_name}"
            if self.domain_config.description:
                domain_context += f" - {self.domain_config.description}"

            full_prompt = f"""{domain_context}

User Query: "{user_query}"

Results:
{self._results_to_text(formatted_results[:10])}

{custom_prompt}"""

            # Generate response
            if hasattr(self.inference_client, 'generate'):
                return await self.inference_client.generate(full_prompt)
            else:
                return await self.inference_client.generate_response(full_prompt)

        except Exception as e:
            logger.error(f"Error generating custom response: {e}")
            return "Unable to generate custom response."

    def _results_to_text(self, results: List[Dict]) -> str:
        """Convert results to text format for prompts"""
        if not results:
            return "No results"

        text_lines = []
        for idx, result in enumerate(results, 1):
            items = [f"{k}: {v}" for k, v in result.items()]
            text_lines.append(f"{idx}. {', '.join(items)}")

        return "\n".join(text_lines)

    def register_custom_strategy(self, name: str, strategy):
        """
        Register a custom response strategy.
        Allows for domain-specific response strategies.
        """
        self.strategy_factory.register_strategy(name, strategy)