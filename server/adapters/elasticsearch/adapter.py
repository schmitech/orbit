"""
Elasticsearch adapter for Elasticsearch/OpenSearch datasources

This adapter extends HttpAdapter to provide Elasticsearch-specific functionality
while reusing the core HTTP domain management capabilities.
"""

import logging
from typing import Dict, Any, List, Optional, Union

from adapters.http.adapter import HttpAdapter
from adapters.factory import DocumentAdapterFactory

logger = logging.getLogger(__name__)

# Register with the factory
DocumentAdapterFactory.register_adapter("elasticsearch", lambda **kwargs: ElasticsearchAdapter(**kwargs))
logger.info("Registered ElasticsearchAdapter as 'elasticsearch'")


class ElasticsearchAdapter(HttpAdapter):
    """
    Elasticsearch adapter that manages domain-specific knowledge for Elasticsearch intent retriever.

    This component extends HttpAdapter to provide Elasticsearch-specific features:
    - Elasticsearch Query DSL template management
    - Aggregation support
    - Index/mapping awareness
    - Elasticsearch-specific response formatting
    """

    def __init__(self,
                 domain_config_path: Optional[str] = None,
                 template_library_path: Optional[Union[str, List[str]]] = None,
                 base_url: Optional[str] = None,
                 auth_config: Optional[Dict[str, Any]] = None,
                 confidence_threshold: float = 0.1,
                 verbose: bool = False,
                 config: Dict[str, Any] = None,
                 **kwargs):
        """
        Initialize the Elasticsearch adapter.

        Args:
            domain_config_path: Path to Elasticsearch domain configuration YAML file
            template_library_path: Path(s) to Elasticsearch template library YAML file(s)
            base_url: Elasticsearch cluster URL
            auth_config: Elasticsearch authentication configuration
            confidence_threshold: Minimum confidence score for template matching
            verbose: Whether to enable verbose logging
            config: Optional configuration dictionary
            **kwargs: Additional keyword arguments
        """
        super().__init__(
            domain_config_path=domain_config_path,
            template_library_path=template_library_path,
            base_url=base_url,
            auth_config=auth_config,
            confidence_threshold=confidence_threshold,
            verbose=verbose,
            config=config,
            **kwargs
        )

        # Elasticsearch-specific configuration
        self.index_pattern = config.get('index_pattern', '*') if config else '*'
        self.use_query_dsl = config.get('use_query_dsl', True) if config else True

        logger.info(f"ElasticsearchAdapter initialized for index pattern: {self.index_pattern}")

    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format Elasticsearch response into a structured document.

        Args:
            raw_doc: The raw document text (Elasticsearch response as JSON string)
            metadata: Additional metadata about the response

        Returns:
            A formatted context item
        """
        if self.verbose:
            logger.info(f"ElasticsearchAdapter.format_document called with metadata keys: {list(metadata.keys())}")

        # Create the base item
        item = {
            "raw_document": raw_doc,
            "metadata": metadata.copy(),
        }

        # Add Elasticsearch-specific metadata
        if 'template_id' in metadata:
            item['template_id'] = metadata['template_id']
        if 'query_intent' in metadata:
            item['query_intent'] = metadata['query_intent']
        if 'parameters_used' in metadata:
            item['parameters'] = metadata['parameters_used']

        # Handle Elasticsearch-specific response structure
        if 'elasticsearch_response' in metadata:
            es_response = metadata['elasticsearch_response']
            item['content'] = self._format_elasticsearch_response(es_response)
            item['result_count'] = es_response.get('hits', {}).get('total', {}).get('value', 0)
        elif 'results' in metadata and isinstance(metadata['results'], list):
            # Standard results formatting
            results = metadata['results']
            if results:
                result_count = len(results)
                if result_count == 1:
                    item['content'] = self._format_single_result(results[0])
                else:
                    item['content'] = self._format_multiple_results(results)
                item['result_count'] = result_count
            else:
                item['content'] = "No results found for the query."
                item['result_count'] = 0
        else:
            # Use raw document as content
            item['content'] = raw_doc

        return item

    def _format_elasticsearch_response(self, es_response: Dict[str, Any]) -> str:
        """
        Format an Elasticsearch response into readable text.

        Args:
            es_response: Elasticsearch response dictionary

        Returns:
            Formatted string representation
        """
        lines = []

        # Extract hits
        hits = es_response.get('hits', {}).get('hits', [])
        total_hits = es_response.get('hits', {}).get('total', {}).get('value', 0)

        if hits:
            lines.append(f"Found {total_hits} total results (showing {len(hits)}):")
            for i, hit in enumerate(hits, 1):
                lines.append(f"\n{i}. (Score: {hit.get('_score', 'N/A')})")
                source = hit.get('_source', {})
                for key, value in source.items():
                    if not key.startswith('_'):
                        lines.append(f"   {key}: {value}")

                # Add highlights if present
                if 'highlight' in hit:
                    lines.append("   Highlights:")
                    for field, highlights in hit['highlight'].items():
                        lines.append(f"     {field}: {highlights[0]}")
        else:
            lines.append("No results found.")

        # Format aggregations if present
        if 'aggregations' in es_response:
            lines.append("\n\nAggregations:")
            for agg_name, agg_data in es_response['aggregations'].items():
                lines.append(f"\n{agg_name}:")
                if 'buckets' in agg_data:
                    for bucket in agg_data['buckets'][:10]:
                        key = bucket.get('key', bucket.get('key_as_string', 'Unknown'))
                        doc_count = bucket.get('doc_count', 0)
                        lines.append(f"  {key}: {doc_count}")
                elif 'value' in agg_data:
                    lines.append(f"  Value: {agg_data['value']}")

        return '\n'.join(lines)

    def get_elasticsearch_config(self) -> Dict[str, Any]:
        """
        Get Elasticsearch-specific configuration from domain config.

        Returns:
            Elasticsearch configuration dictionary
        """
        if not self.domain_config:
            return {}

        return self.domain_config.get('elasticsearch_config', {})

    def get_index_pattern(self) -> str:
        """
        Get the index pattern for Elasticsearch queries.

        Returns:
            Index pattern string
        """
        return self.index_pattern


# Register adapter with the global registry for dynamic loading
def register_elasticsearch_adapter():
    """Register Elasticsearch adapter with the global adapter registry"""
    logger.info("Registering Elasticsearch adapter with global registry...")

    try:
        from adapters.registry import ADAPTER_REGISTRY

        # Register for Elasticsearch datasource
        ADAPTER_REGISTRY.register(
            adapter_type="retriever",
            datasource="elasticsearch",
            adapter_name="intent",
            implementation='adapters.elasticsearch.adapter.ElasticsearchAdapter',
            config={
                'confidence_threshold': 0.1,
                'verbose': False,
                'use_query_dsl': True
            }
        )
        logger.info("Registered Elasticsearch adapter for elasticsearch datasource")

        # Also register for OpenSearch (compatible with Elasticsearch)
        ADAPTER_REGISTRY.register(
            adapter_type="retriever",
            datasource="opensearch",
            adapter_name="intent",
            implementation='adapters.elasticsearch.adapter.ElasticsearchAdapter',
            config={
                'confidence_threshold': 0.1,
                'verbose': False,
                'use_query_dsl': True
            }
        )
        logger.info("Registered Elasticsearch adapter for opensearch datasource")

        logger.info("Elasticsearch adapter registration complete")

    except Exception as e:
        logger.error(f"Failed to register Elasticsearch adapter: {e}")


# Register when module is imported
register_elasticsearch_adapter()
