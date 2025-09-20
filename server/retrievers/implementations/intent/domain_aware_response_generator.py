"""
Domain-aware response generation for Intent retriever.
This is a backward-compatibility wrapper that delegates to the new modular components.
"""

import logging
from typing import Dict, List, Any, Optional
from .domain.response import DomainResponseGenerator as NewDomainResponseGenerator

logger = logging.getLogger(__name__)


class DomainAwareResponseGenerator:
    """
    Domain-aware response generation using domain configuration and LLM.
    This class maintains backward compatibility by wrapping the new modular implementation.
    """

    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None):
        # Delegate to the new implementation
        self._generator = NewDomainResponseGenerator(inference_client, domain_config)

        # Keep references for backward compatibility
        self.inference_client = inference_client
        self.domain_config = domain_config or {}

    async def generate_response(self, user_query: str, results: List[Dict], template: Dict,
                                 error: Optional[str] = None,
                                 conversation_context: Optional[str] = None) -> str:
        """
        Generate response using domain configuration.
        Delegates to the new modular implementation.
        """
        return await self._generator.generate_response(
            user_query, results, template, error, conversation_context
        )

    # Backward compatibility methods
    def _format_results_for_domain(self, results: List[Dict], template: Dict) -> List[Dict]:
        """Provided for backward compatibility"""
        return self._generator.format_results(results, template)

    def _format_date(self, value) -> str:
        """Provided for backward compatibility"""
        if hasattr(self._generator.formatter, '_format_date'):
            return self._generator.formatter._format_date(value)
        return str(value)

    def _format_phone(self, value) -> str:
        """Provided for backward compatibility"""
        if hasattr(self._generator.formatter, '_format_phone'):
            return self._generator.formatter._format_phone(value)
        return str(value)

    async def _generate_error_response(self, error: str, user_query: str) -> str:
        """Provided for backward compatibility"""
        strategy = self._generator.strategy_factory.get_strategy('error')
        return await strategy.generate(error, user_query)

    async def _generate_no_results_response(self, user_query: str, template: Dict) -> str:
        """Provided for backward compatibility"""
        strategy = self._generator.strategy_factory.get_strategy('no_results')
        return await strategy.generate(user_query, template)

    async def _generate_summary_response(self, user_query: str, results: List[Dict], template: Dict) -> str:
        """Provided for backward compatibility"""
        strategy = self._generator.strategy_factory.get_strategy('summary')
        return await strategy.generate(user_query, results, template)

    async def _generate_table_response(self, user_query: str, results: List[Dict], template: Dict,
                                        conversation_context: Optional[str] = None) -> str:
        """Provided for backward compatibility"""
        strategy = self._generator.strategy_factory.get_strategy('table')
        context = {'conversation_context': conversation_context}
        return await strategy.generate(user_query, results, template, context)