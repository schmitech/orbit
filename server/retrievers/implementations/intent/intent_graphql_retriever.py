"""
GraphQL API intent retriever implementation.

This retriever extends IntentHTTPRetriever to provide GraphQL API support,
allowing natural language queries to be translated into GraphQL operations
for any GraphQL endpoint.
"""

import logging
import traceback
import json
import httpx
from typing import Dict, Any, List, Optional, Tuple

from retrievers.base.intent_http_base import IntentHTTPRetriever
from retrievers.base.base_retriever import RetrieverFactory
from retrievers.implementations.intent.domain.response.table_renderer import TableRenderer

logger = logging.getLogger(__name__)


class IntentGraphQLRetriever(IntentHTTPRetriever):
    """
    GraphQL API intent retriever.

    Translates natural language queries to GraphQL operations for any GraphQL API.
    Supports queries and mutations with variable substitution.

    Features:
    - GraphQL query and mutation support
    - Variable extraction and type coercion
    - GraphQL-specific error handling
    - Optional schema introspection
    - Response mapping for nested GraphQL responses
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None, datasource=None, **kwargs):
        """
        Initialize GraphQL retriever.

        Args:
            config: Configuration dictionary with datasource settings
            domain_adapter: Optional domain adapter
            datasource: Optional pre-initialized datasource
            **kwargs: Additional arguments
        """
        super().__init__(config=config, domain_adapter=domain_adapter, datasource=datasource, **kwargs)

        # GraphQL-specific settings from adapter config
        self.graphql_endpoint = self.intent_config.get('graphql_endpoint', '/graphql')
        self.supports_introspection = self.intent_config.get('supports_introspection', False)
        self.default_timeout = self.intent_config.get('default_timeout', 30)
        self.enable_retries = self.intent_config.get('enable_retries', True)
        self.max_retries = self.intent_config.get('max_retries', 3)
        self.retry_delay = self.intent_config.get('retry_delay', 1.0)

        # Cache for introspected schema
        self._schema_cache: Optional[Dict] = None

        logger.debug(f"GraphQL Retriever initialized with base_url: {self.base_url}, endpoint: {self.graphql_endpoint}")

    def _get_datasource_name(self) -> str:
        """
        Return the datasource identifier for GraphQL APIs.

        Note: GraphQL adapters don't use a centralized datasource - they manage
        their own HTTP connections via base_url. This method is for identification only.
        """
        return "graphql_api"

    async def _execute_template(self, template: Dict[str, Any],
                                parameters: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """
        Execute GraphQL template with parameters.

        Args:
            template: The template dictionary containing GraphQL operation configuration
            parameters: Extracted parameters for the request

        Returns:
            Tuple of (results, error_message)
        """
        try:
            template_id = template.get('id', 'unknown')

            # Get the GraphQL query/mutation
            graphql_query = template.get('graphql_template')
            if not graphql_query:
                return [], f"Template {template_id} missing graphql_template"

            # Get optional operation name
            operation_name = template.get('operation_name')

            # Build GraphQL variables from parameters
            variables = self._build_graphql_variables(template, parameters)

            # Construct the GraphQL request body
            request_body = {
                'query': graphql_query,
                'variables': variables
            }
            if operation_name:
                request_body['operationName'] = operation_name

            logger.debug(f"[Template {template_id}] Executing GraphQL {template.get('graphql_type', 'query')}")
            logger.debug(f"[Template {template_id}] Variables: {json.dumps(variables, indent=2)}")

            # Execute the GraphQL request (always POST to the GraphQL endpoint)
            response = await self._execute_graphql_request(
                request_body=request_body,
                timeout=template.get('timeout', self.default_timeout)
            )

            # Parse and extract results from GraphQL response
            results, error = self._parse_graphql_response(response, template)

            if error:
                return [], error

            return results, None

        except httpx.HTTPStatusError as e:
            template_id = template.get('id', 'unknown')
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"[Template {template_id}] GraphQL request failed: {error_msg}")
            return [], error_msg
        except Exception as e:
            template_id = template.get('id', 'unknown')
            error_msg = str(e)
            logger.error(f"[Template {template_id}] Error executing GraphQL template: {error_msg}")
            logger.error(traceback.format_exc())
            return [], error_msg

    def _build_graphql_variables(self, template: Dict[str, Any],
                                  parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build GraphQL variables from extracted parameters.

        Args:
            template: Template dictionary with parameter definitions
            parameters: Extracted parameter values

        Returns:
            Dictionary of GraphQL variables
        """
        variables = {}

        for param_def in template.get('parameters', []):
            param_name = param_def.get('name')
            if not param_name:
                continue

            # Check if parameter was extracted
            if param_name in parameters and parameters[param_name] is not None:
                value = parameters[param_name]
                graphql_type = param_def.get('graphql_type', 'String')

                # Coerce value to appropriate GraphQL type
                variables[param_name] = self._coerce_graphql_type(value, graphql_type)

            elif param_def.get('default') is not None:
                # Use default value
                variables[param_name] = param_def['default']

            elif param_def.get('required', False):
                # Required parameter missing - log warning
                logger.warning(f"Required parameter '{param_name}' not found in extracted parameters")

        logger.debug(f"Built GraphQL variables: {variables}")
        return variables

    def _coerce_graphql_type(self, value: Any, graphql_type: str) -> Any:
        """
        Coerce a value to the appropriate GraphQL type.

        Args:
            value: The value to coerce
            graphql_type: GraphQL type string (e.g., "Int", "String!", "ID", "[String]")

        Returns:
            Coerced value
        """
        # Remove non-null indicator and list brackets for base type detection
        base_type = graphql_type.rstrip('!').strip('[]')

        try:
            if base_type in ('Int', 'Integer'):
                return int(value)
            elif base_type == 'Float':
                return float(value)
            elif base_type == 'Boolean':
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ('true', 'yes', '1')
                return bool(value)
            elif base_type == 'ID':
                return str(value)
            elif base_type == 'String':
                return str(value)
            else:
                # Unknown type - return as-is
                return value
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to coerce value '{value}' to GraphQL type '{graphql_type}': {e}")
            return value

    async def _execute_graphql_request(self, request_body: Dict[str, Any],
                                        timeout: int = 30) -> httpx.Response:
        """
        Execute GraphQL request with retry logic.

        Args:
            request_body: GraphQL request body with query, variables, operationName
            timeout: Request timeout in seconds

        Returns:
            HTTP response
        """
        retries = 0
        last_error = None

        while retries <= (self.max_retries if self.enable_retries else 0):
            try:
                # GraphQL requests are always POST
                response = await self.http_client.request(
                    method='POST',
                    url=self.graphql_endpoint,
                    json=request_body,
                    timeout=timeout
                )
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                # Don't retry client errors (4xx), only server errors (5xx)
                if e.response.status_code < 500:
                    raise
                last_error = e
                retries += 1
                if retries <= self.max_retries:
                    logger.warning(f"GraphQL request failed with {e.response.status_code}, "
                                 f"retrying ({retries}/{self.max_retries})...")
                    import asyncio
                    await asyncio.sleep(self.retry_delay * retries)
            except Exception as e:
                last_error = e
                retries += 1
                if retries <= self.max_retries:
                    logger.warning(f"GraphQL request failed: {e}, retrying ({retries}/{self.max_retries})...")
                    import asyncio
                    await asyncio.sleep(self.retry_delay * retries)

        # All retries failed
        if last_error:
            raise last_error
        raise Exception("GraphQL request failed after all retries")

    def _parse_graphql_response(self, response: httpx.Response,
                                 template: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Parse GraphQL response, handling errors and extracting data.

        GraphQL responses have the format:
        {
            "data": { ... },
            "errors": [ ... ]  // optional
        }

        Args:
            response: HTTP response
            template: Template configuration

        Returns:
            Tuple of (results list, error message or None)
        """
        try:
            data = response.json()

            # Check for GraphQL errors
            if 'errors' in data and data['errors']:
                error_messages = []
                for error in data['errors']:
                    msg = error.get('message', str(error))
                    if 'locations' in error:
                        locations = error['locations']
                        if locations:
                            loc = locations[0]
                            msg += f" (line {loc.get('line')}, column {loc.get('column')})"
                    error_messages.append(msg)

                error_str = "; ".join(error_messages)
                logger.warning(f"GraphQL errors: {error_str}")

                # If there's partial data, we might still want to return it
                if 'data' not in data or data['data'] is None:
                    return [], error_str

            # No data in response
            if 'data' not in data or data['data'] is None:
                return [], "GraphQL response contained no data"

            # Extract results using response mapping
            response_mapping = template.get('response_mapping', {})
            items_path = response_mapping.get('items_path', 'data')

            # Navigate to the items
            results = self._extract_items_from_response(data, items_path)

            # Apply field mapping if specified
            field_mapping = response_mapping.get('fields', [])
            if field_mapping:
                results = self._map_response_fields(results, field_mapping)

            return results, None

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GraphQL response as JSON: {e}")
            return [], f"Invalid JSON response: {e}"
        except Exception as e:
            logger.error(f"Error parsing GraphQL response: {e}")
            logger.error(traceback.format_exc())
            return [], f"Response parsing error: {e}"

    def _extract_items_from_response(self, data: Any, path: str) -> List[Dict[str, Any]]:
        """
        Extract items from GraphQL response data using a path expression.

        Args:
            data: Response data
            path: Path expression (e.g., "data.launches", "data.rocket")

        Returns:
            List of extracted items
        """
        try:
            current = data

            # Navigate the path
            for part in path.split('.'):
                if not part or part == '$':
                    continue

                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list) and part.isdigit():
                    current = current[int(part)]
                else:
                    logger.warning(f"Cannot navigate path '{path}' at '{part}' - current is {type(current)}")
                    return []

                if current is None:
                    return []

            # Ensure we return a list
            if isinstance(current, list):
                return current
            elif current is not None:
                return [current]
            return []

        except Exception as e:
            logger.error(f"Error extracting items from path '{path}': {e}")
            return []

    def _map_response_fields(self, items: List[Dict], field_mapping: List[Dict]) -> List[Dict]:
        """
        Map response fields according to field mapping configuration.

        Args:
            items: List of response items
            field_mapping: Field mapping configuration

        Returns:
            List of mapped items
        """
        mapped_items = []

        for item in items:
            mapped_item = {}

            for field_config in field_mapping:
                field_name = field_config.get('name')
                field_path = field_config.get('path', f'$.{field_name}')

                # Extract value using path
                value = self._extract_field_value(item, field_path)
                if value is not None:
                    mapped_item[field_name] = value

            if mapped_item:
                mapped_items.append(mapped_item)
            else:
                # If no fields mapped, return original item
                mapped_items.append(item)

        return mapped_items

    def _extract_field_value(self, item: Dict, path: str) -> Any:
        """
        Extract field value from item using simple path.

        Args:
            item: Item dictionary
            path: Field path (e.g., "$.rocket.rocket_name" or "mission_name")

        Returns:
            Extracted value or None
        """
        try:
            # Remove leading $ if present
            path = path.lstrip('$').lstrip('.')

            current = item
            for part in path.split('.'):
                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list) and part.isdigit():
                    current = current[int(part)]
                else:
                    return None

                if current is None:
                    return None

            return current

        except Exception:
            return None

    def _format_http_results(self, results: Any, template: Dict,
                            parameters: Dict, similarity: float) -> List[Dict[str, Any]]:
        """
        Format GraphQL results into context documents.

        Args:
            results: GraphQL query results
            template: The template that was executed
            parameters: Parameters used in the request
            similarity: Template matching similarity score

        Returns:
            List of formatted context items
        """
        if not results:
            return [{
                "content": "No results found for your GraphQL query.",
                "metadata": {
                    "source": "graphql_api",
                    "template_id": template.get('id'),
                    "parameters_used": parameters,
                    "similarity": similarity,
                    "result_count": 0
                },
                "confidence": similarity
            }]

        # Format the response
        content = self._format_graphql_results(results, template)

        # Build metadata
        metadata = {
            "source": "graphql_api",
            "template_id": template.get('id'),
            "query_intent": template.get('description', ''),
            "graphql_type": template.get('graphql_type', 'query'),
            "operation_name": template.get('operation_name'),
            "parameters_used": parameters,
            "similarity": similarity,
            "result_count": len(results) if isinstance(results, list) else 1,
            "results": results
        }

        return [{
            "content": content,
            "metadata": metadata,
            "confidence": similarity
        }]

    def _format_graphql_results(self, results: List[Dict], template: Dict) -> str:
        """
        Format GraphQL results as human-readable text.

        All results are included in the formatted output to ensure the LLM
        has access to complete query results for accurate responses.

        Args:
            results: List of result dictionaries
            template: The template being executed

        Returns:
            Formatted string representation
        """
        lines = []

        if not results:
            return "No results found."

        total = len(results)
        result_format = template.get('result_format', 'list')

        if result_format == 'table':
            # Format as table
            lines.append(f"Found {total} results:")

            # Get display fields
            display_fields = template.get('display_fields')
            if not display_fields and results:
                # Use all fields from first result
                display_fields = list(results[0].keys())

            if display_fields:
                # Build rows for TableRenderer
                table_rows = []
                for result in results:
                    row = []
                    for field in display_fields:
                        value = result.get(field, '')
                        value_str = str(value)[:100] if value is not None else ''
                        row.append(value_str)
                    table_rows.append(row)

                columns = [str(f) for f in display_fields]
                lines.append(TableRenderer.render(columns, table_rows, format=self.context_format).rstrip())
        else:
            # Format as list
            lines.append(f"Found {total} result(s):")

            # Include ALL results for complete LLM context
            for i, result in enumerate(results, 1):
                lines.append(f"\n{i}.")
                display_fields = template.get('display_fields')

                if display_fields:
                    for field in display_fields:
                        if field in result:
                            value = result[field]
                            # Truncate very long string values for readability
                            if isinstance(value, str) and len(value) > 500:
                                value = value[:500] + "..."
                            lines.append(f"   {field}: {value}")
                else:
                    # Show all fields
                    for key, value in result.items():
                        if not key.startswith('_'):
                            if isinstance(value, str) and len(value) > 500:
                                value = value[:500] + "..."
                            lines.append(f"   {key}: {value}")

        return '\n'.join(lines)

    async def introspect_schema(self) -> Optional[Dict]:
        """
        Fetch GraphQL schema via introspection query.

        Returns:
            Schema dictionary or None if introspection is disabled/fails
        """
        if not self.supports_introspection:
            logger.debug("Schema introspection is disabled")
            return None

        # Return cached schema if available
        if self._schema_cache:
            return self._schema_cache

        introspection_query = """
        query IntrospectionQuery {
          __schema {
            queryType { name }
            mutationType { name }
            types {
              name
              kind
              description
              fields {
                name
                description
                type {
                  name
                  kind
                  ofType {
                    name
                    kind
                  }
                }
                args {
                  name
                  type {
                    name
                    kind
                  }
                }
              }
            }
          }
        }
        """

        try:
            request_body = {'query': introspection_query}
            response = await self._execute_graphql_request(request_body, timeout=30)
            data = response.json()

            if 'data' in data and '__schema' in data['data']:
                self._schema_cache = data['data']['__schema']
                logger.info("Successfully introspected GraphQL schema")
                return self._schema_cache
            else:
                logger.warning("Introspection query returned no schema")
                return None

        except Exception as e:
            logger.warning(f"Schema introspection failed: {e}")
            return None

    async def validate_template_against_schema(self, template: Dict[str, Any]) -> List[str]:
        """
        Validate a template against the introspected schema.

        Args:
            template: Template to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        schema = await self.introspect_schema()
        if not schema:
            return ["Schema introspection not available"]

        # Extract operation type from template
        graphql_type = template.get('graphql_type', 'query')

        # Check if operation type is supported
        if graphql_type == 'query' and not schema.get('queryType'):
            errors.append("Schema does not support queries")
        elif graphql_type == 'mutation' and not schema.get('mutationType'):
            errors.append("Schema does not support mutations")

        # Additional validation could check:
        # - Field names exist in schema
        # - Argument types match
        # - Required fields are present

        return errors


# Register the GraphQL retriever
RetrieverFactory.register_retriever('intent_graphql', IntentGraphQLRetriever)
logger.info("Registered IntentGraphQLRetriever as 'intent_graphql'")
