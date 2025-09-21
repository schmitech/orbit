"""
Domain response generator that formats SQL results for intent retrieval
"""

import logging
from typing import Dict, List, Any, Optional
from ...domain import DomainConfig
from .formatters import ResponseFormatter

logger = logging.getLogger(__name__)


class DomainResponseGenerator:
    """
    Handles formatting of SQL query results according to domain configuration.
    Returns formatted data suitable for the inference pipeline.
    """

    def __init__(self, domain_config: DomainConfig, domain_strategy: Any):
        """Initialize the domain response generator"""
        self.domain_config = domain_config
        self.domain_strategy = domain_strategy

        # Initialize formatter with domain strategy
        self.formatter = ResponseFormatter(self.domain_config, domain_strategy)

        logger.info(f"Initialized DomainResponseGenerator for {self.domain_config.domain_name}")


    def format_response_data(self, results: List[Dict], template: Dict, error: Optional[str] = None) -> Dict[str, Any]:
        """
        Format query results for the inference pipeline.

        Args:
            results: Raw SQL query results
            template: Template configuration containing result format preferences
            error: Optional error message

        Returns:
            Formatted data structure suitable for context retrieval
        """
        # Handle error case
        if error:
            return {
                "error": error,
                "results": [],
                "format": "error",
                "result_count": 0
            }

        # Handle no results
        if not results:
            return {
                "results": [],
                "format": template.get('result_format', 'table'),
                "result_count": 0,
                "message": "No results found"
            }

        # Format results
        formatted_results = self.formatter.format_results(results, template)

        # Determine response format from template
        result_format = template.get('result_format', 'table')

        response_data = {
            "results": formatted_results,
            "format": result_format,
            "result_count": len(results)
        }

        # Add formatted table or summary data based on format
        if result_format == 'summary':
            response_data["summary"] = self.formatter.format_summary_data(formatted_results)
        else:
            response_data["table"] = self.formatter.format_table_data(formatted_results)

        return response_data

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

