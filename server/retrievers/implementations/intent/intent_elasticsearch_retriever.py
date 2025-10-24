"""
Elasticsearch-specific intent retriever implementation.

This retriever extends IntentHTTPRetriever to provide Elasticsearch Query DSL support,
allowing natural language queries to be translated into Elasticsearch searches.
Uses the Elasticsearch datasource from the datasource registry for connection pooling.
"""

import logging
import traceback
import json
from typing import Dict, Any, List, Optional, Tuple
from elasticsearch import AsyncElasticsearch

from retrievers.base.intent_http_base import IntentHTTPRetriever
from retrievers.base.base_retriever import RetrieverFactory
from datasources.registry import get_registry

logger = logging.getLogger(__name__)


class IntentElasticsearchRetriever(IntentHTTPRetriever):
    """
    Elasticsearch-specific intent retriever.

    Translates natural language queries to Elasticsearch Query DSL.
    Uses Elasticsearch datasource from registry for connection pooling.
    Features:
    - Elasticsearch Query DSL generation
    - Aggregation support
    - Index management
    - Elasticsearch-specific response processing
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None, datasource=None, **kwargs):
        """
        Initialize Elasticsearch retriever.

        Args:
            config: Configuration dictionary with datasource settings
            domain_adapter: Optional domain adapter
            datasource: Optional pre-initialized datasource
            **kwargs: Additional arguments
        """
        # Elasticsearch uses its own client from datasource, not the generic HTTP client
        # Provide a placeholder base_url to satisfy parent class if not already set
        if 'adapter_config' in config and 'base_url' not in config['adapter_config']:
            config['adapter_config']['base_url'] = 'http://localhost:9200'  # Placeholder, not used

        super().__init__(config=config, domain_adapter=domain_adapter, datasource=datasource, **kwargs)

        # Elasticsearch-specific settings from adapter config
        self.index_pattern = self.intent_config.get('index_pattern', '*')
        self.use_query_dsl = self.intent_config.get('use_query_dsl', True)
        self.enable_aggregations = self.intent_config.get('enable_aggregations', True)
        self.enable_highlighting = self.intent_config.get('enable_highlighting', True)
        self.default_size = self.intent_config.get('default_size', 100)

        # Store datasource reference (will be initialized in initialize())
        self.es_datasource = datasource
        self.es_client: Optional[AsyncElasticsearch] = None

        if self.verbose:
            logger.info(f"ElasticsearchRetriever initialized with index_pattern: {self.index_pattern}")

    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return "elasticsearch"

    async def initialize(self) -> None:
        """Initialize the retriever and get Elasticsearch datasource from registry."""
        # Call parent initialization
        await super().initialize()

        # Get or create Elasticsearch datasource from registry
        if not self.es_datasource:
            registry = get_registry()
            self.es_datasource = registry.get_or_create_datasource(
                datasource_name="elasticsearch",
                config=self.config,
                logger_instance=logger
            )

        if not self.es_datasource:
            raise RuntimeError("Failed to initialize Elasticsearch datasource")

        # Initialize the datasource if not already initialized
        if not self.es_datasource.is_initialized:
            await self.es_datasource.initialize()

        # Get the Elasticsearch client
        self.es_client = self.es_datasource.client

        if self.verbose:
            logger.info("Elasticsearch retriever initialized with datasource from registry")

    async def _execute_template(self, template: Dict[str, Any],
                                parameters: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """
        Execute Elasticsearch Query DSL template with parameters.

        Args:
            template: The template dictionary containing Query DSL
            parameters: Extracted parameters for the query

        Returns:
            Tuple of (results, error_message)
        """
        try:
            # Ensure we have an Elasticsearch client
            if not self.es_client:
                return [], "Elasticsearch client not initialized"

            # Get Query DSL from template
            query_dsl_template = template.get('query_dsl', template.get('elasticsearch_query'))
            if not query_dsl_template:
                return [], "Template has no Elasticsearch Query DSL"

            # Process the Query DSL template with parameters
            query_dsl = self._process_query_dsl_template(query_dsl_template, parameters)

            # Determine index and endpoint type
            index = template.get('index', self.index_pattern)
            endpoint_type = template.get('endpoint_type', '_search')

            if self.verbose:
                logger.info(f"Executing Elasticsearch {endpoint_type} on index: {index}")
                logger.debug(f"Query DSL: {json.dumps(query_dsl, indent=2)}")

            # Execute using the Elasticsearch client
            if endpoint_type == '_search':
                response = await self.es_client.search(
                    index=index,
                    body=query_dsl
                )
            elif endpoint_type == '_count':
                response = await self.es_client.count(
                    index=index,
                    body=query_dsl
                )
            else:
                # Generic request using the perform_request method
                response = await self.es_client.perform_request(
                    method='POST',
                    path=f"/{index}/{endpoint_type}",
                    body=query_dsl
                )

            # Extract results based on endpoint type
            if endpoint_type == '_search':
                results = self._extract_search_results(response, template)
            elif endpoint_type == '_count':
                results = [{'count': response.get('count', 0)}]
            else:
                results = [response]

            return results, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error executing Elasticsearch template: {error_msg}")
            logger.error(traceback.format_exc())
            return [], error_msg

    def _process_query_dsl_template(self, template: str, parameters: Dict[str, Any]) -> Dict:
        """
        Process Elasticsearch Query DSL template with variable substitution.

        Args:
            template: Query DSL template string (may contain Jinja2 syntax)
            parameters: Parameters for substitution

        Returns:
            Processed Query DSL as dictionary
        """
        try:
            if self.template_processor:
                # Use the template processor to render the Query DSL
                rendered = self.template_processor.render_sql(
                    template,
                    parameters=parameters,
                    preserve_unknown=False
                )
                return json.loads(rendered)
            else:
                # Fallback: simple parameter substitution
                rendered = template
                for key, value in parameters.items():
                    placeholder = f"{{{{{key}}}}}"
                    if isinstance(value, str):
                        rendered = rendered.replace(placeholder, f'"{value}"')
                    else:
                        rendered = rendered.replace(placeholder, str(value))
                return json.loads(rendered)

        except Exception as e:
            logger.error(f"Error processing Query DSL template: {e}")
            # Return an empty query as fallback
            return {"query": {"match_all": {}}}

    def _extract_search_results(self, response: Dict, template: Dict) -> List[Dict]:
        """
        Extract and format search hits from Elasticsearch response.

        Args:
            response: Elasticsearch response dictionary
            template: The template being executed

        Returns:
            List of result dictionaries
        """
        hits = response.get('hits', {}).get('hits', [])
        results = []

        # Handle regular search results
        for hit in hits:
            result = {
                '_index': hit.get('_index'),
                '_id': hit.get('_id'),
                '_score': hit.get('_score'),
                **hit.get('_source', {})
            }

            # Add highlights if present
            if 'highlight' in hit:
                result['_highlights'] = hit['highlight']

            results.append(result)

        # Handle aggregation results (when size=0 and aggregations are present)
        if not hits and 'aggregations' in response:
            aggregations = response['aggregations']
            
            # Convert aggregations to a format that can be processed
            for agg_name, agg_data in aggregations.items():
                if 'buckets' in agg_data:
                    # Terms aggregation
                    for bucket in agg_data['buckets']:
                        result = {
                            '_aggregation_type': 'terms',
                            '_aggregation_name': agg_name,
                            'key': bucket.get('key', bucket.get('key_as_string', 'Unknown')),
                            'doc_count': bucket.get('doc_count', 0)
                        }
                        
                        # Add sub-aggregations if present
                        for sub_agg_name, sub_agg_data in bucket.items():
                            if sub_agg_name not in ['key', 'key_as_string', 'doc_count']:
                                if 'buckets' in sub_agg_data:
                                    # Sub-terms aggregation
                                    result[f'{sub_agg_name}_buckets'] = [
                                        {
                                            'key': sub_bucket.get('key', sub_bucket.get('key_as_string', 'Unknown')),
                                            'doc_count': sub_bucket.get('doc_count', 0)
                                        }
                                        for sub_bucket in sub_agg_data['buckets']
                                    ]
                                elif 'value' in sub_agg_data:
                                    # Metric aggregation (avg, sum, etc.)
                                    result[f'{sub_agg_name}_value'] = sub_agg_data['value']
                        
                        results.append(result)
                elif 'value' in agg_data:
                    # Metric aggregation (single value)
                    result = {
                        '_aggregation_type': 'metric',
                        '_aggregation_name': agg_name,
                        'value': agg_data['value']
                    }
                    results.append(result)

        # Store the full response for advanced formatting
        if results:
            results[0]['_elasticsearch_response'] = response

        return results

    def _format_http_results(self, results: Any, template: Dict,
                            parameters: Dict, similarity: float) -> List[Dict[str, Any]]:
        """
        Format Elasticsearch results into context documents.

        Args:
            results: Elasticsearch search results
            template: The template that was executed
            parameters: Parameters used in the query
            similarity: Template matching similarity score

        Returns:
            List of formatted context items
        """
        if not results:
            return [{
                "content": "No results found for your query.",
                "metadata": {
                    "source": "elasticsearch",
                    "template_id": template.get('id'),
                    "parameters_used": parameters,
                    "similarity": similarity,
                    "result_count": 0
                },
                "confidence": similarity
            }]

        # Extract the full Elasticsearch response if available
        es_response = None
        if results and '_elasticsearch_response' in results[0]:
            es_response = results[0].pop('_elasticsearch_response')

        # Format the response
        content = self._format_elasticsearch_results(results, es_response, template)

        # Build metadata
        metadata = {
            "source": "elasticsearch",
            "template_id": template.get('id'),
            "query_intent": template.get('description', ''),
            "parameters_used": parameters,
            "similarity": similarity,
            "result_count": len(results),
            "results": results
        }

        # Add full response if available
        if es_response:
            metadata['elasticsearch_response'] = es_response
            metadata['total_hits'] = es_response.get('hits', {}).get('total', {}).get('value', 0)
            metadata['took_ms'] = es_response.get('took', 0)
            metadata['max_score'] = es_response.get('hits', {}).get('max_score')

            # Include aggregations if present
            if 'aggregations' in es_response:
                metadata['aggregations'] = es_response['aggregations']

        return [{
            "content": content,
            "metadata": metadata,
            "confidence": similarity
        }]

    def _format_elasticsearch_results(self, hits: List[Dict], full_response: Optional[Dict],
                                     template: Dict) -> str:
        """
        Format Elasticsearch results as human-readable text.

        Args:
            hits: List of hit documents
            full_response: Full Elasticsearch response (optional)
            template: The template being executed

        Returns:
            Formatted string representation
        """
        lines = []

        # Check if this is an aggregation result
        is_aggregation = hits and any('_aggregation_type' in hit for hit in hits)
        
        if is_aggregation:
            # Format aggregation results
            lines.append("Error Analysis by Service:")
            
            # Group by aggregation name
            agg_groups = {}
            for hit in hits:
                agg_name = hit.get('_aggregation_name', 'unknown')
                if agg_name not in agg_groups:
                    agg_groups[agg_name] = []
                agg_groups[agg_name].append(hit)
            
            for agg_name, agg_hits in agg_groups.items():
                lines.append(f"\n{agg_name.replace('_', ' ').title()}:")
                for hit in agg_hits:
                    key = hit.get('key', 'Unknown')
                    doc_count = hit.get('doc_count', 0)
                    lines.append(f"  {key}: {doc_count} errors")
                    
                    # Add sub-aggregations if present
                    for sub_key, sub_value in hit.items():
                        if sub_key.endswith('_buckets') and isinstance(sub_value, list):
                            sub_agg_name = sub_key.replace('_buckets', '').replace('_', ' ').title()
                            lines.append(f"    {sub_agg_name}:")
                            for sub_bucket in sub_value[:3]:  # Show first 3 sub-buckets
                                sub_key_name = sub_bucket.get('key', 'Unknown')
                                sub_count = sub_bucket.get('doc_count', 0)
                                lines.append(f"      {sub_key_name}: {sub_count}")
                        elif sub_key.endswith('_value') and sub_value is not None:
                            sub_agg_name = sub_key.replace('_value', '').replace('_', ' ').title()
                            lines.append(f"    {sub_agg_name}: {sub_value:.2f}ms")
        
        elif hits:
            # Format regular search results
            total = len(hits)
            lines.append(f"Found {total} results:")

            display_fields = template.get('display_fields', None)

            for i, hit in enumerate(hits[:10], 1):
                lines.append(f"\n{i}. (Score: {hit.get('_score', 'N/A')})")

                if display_fields:
                    for field in display_fields:
                        if field in hit:
                            lines.append(f"   {field}: {hit[field]}")
                else:
                    # Show all non-internal fields
                    for key, value in hit.items():
                        if not key.startswith('_'):
                            lines.append(f"   {key}: {value}")

                # Add highlights
                if '_highlights' in hit:
                    lines.append("   Highlights:")
                    for field, highlights in hit['_highlights'].items():
                        lines.append(f"     {field}: {highlights[0]}")

            if total > 10:
                lines.append(f"\n... and {total - 10} more results")
        else:
            lines.append("No results found.")

        # Format aggregations from full response
        if full_response and 'aggregations' in full_response:
            aggs = full_response['aggregations']
            lines.append("\n\nAggregations:")
            for agg_name, agg_data in aggs.items():
                lines.append(f"\n{agg_name}:")

                if 'buckets' in agg_data:
                    for bucket in agg_data['buckets'][:10]:
                        key = bucket.get('key', bucket.get('key_as_string', 'Unknown'))
                        doc_count = bucket.get('doc_count', 0)
                        lines.append(f"  {key}: {doc_count}")
                elif 'value' in agg_data:
                    lines.append(f"  Value: {agg_data['value']}")

        return '\n'.join(lines)

    async def get_index_mapping(self, index: str) -> Dict:
        """
        Get index mapping for template generation.

        Args:
            index: Index name

        Returns:
            Index mapping dictionary
        """
        try:
            endpoint = f"/{index}/_mapping"
            response = await self._execute_http_request(
                method='GET',
                url=endpoint
            )
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get index mapping: {e}")
            return {}

    async def execute_count_query(self, query_dsl: Dict, index: str) -> int:
        """
        Execute a count query to get total matching documents.

        Args:
            query_dsl: Elasticsearch Query DSL
            index: Index name

        Returns:
            Count of matching documents
        """
        try:
            endpoint = f"/{index}/_count"
            response = await self._execute_http_request(
                method='POST',
                url=endpoint,
                json=query_dsl
            )
            return response.json().get('count', 0)
        except Exception as e:
            logger.error(f"Failed to execute count query: {e}")
            return 0


# Register the Elasticsearch retriever
RetrieverFactory.register_retriever('intent_elasticsearch', IntentElasticsearchRetriever)
logger.info("Registered IntentElasticsearchRetriever as 'intent_elasticsearch'")
