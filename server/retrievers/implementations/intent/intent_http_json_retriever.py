"""
HTTP JSON API intent retriever implementation.

This retriever extends IntentHTTPRetriever to provide generic HTTP JSON API support,
allowing natural language queries to be translated into HTTP requests for any JSON-based API
(RESTful, RPC-style, or other HTTP+JSON endpoints).
"""

import logging
import traceback
import json
import re
import httpx
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urljoin

from retrievers.base.intent_http_base import IntentHTTPRetriever
from retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)


class IntentHTTPJSONRetriever(IntentHTTPRetriever):
    """
    HTTP JSON API intent retriever.

    Translates natural language queries to HTTP API requests for any JSON-based API.
    Supports RESTful APIs, RPC-style APIs, and other HTTP+JSON endpoints.

    Features:
    - HTTP endpoint patterns with variable substitution
    - Support for all HTTP methods (GET, POST, PUT, PATCH, DELETE)
    - JSON request/response handling
    - Query parameter and path parameter substitution
    - Custom header support
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None, datasource=None, **kwargs):
        """
        Initialize HTTP JSON retriever.

        Args:
            config: Configuration dictionary with datasource settings
            domain_adapter: Optional domain adapter
            datasource: Optional pre-initialized datasource
            **kwargs: Additional arguments
        """
        super().__init__(config=config, domain_adapter=domain_adapter, datasource=datasource, **kwargs)

        # HTTP JSON API settings from adapter config
        self.default_timeout = self.intent_config.get('default_timeout', 30)
        self.enable_retries = self.intent_config.get('enable_retries', True)
        self.max_retries = self.intent_config.get('max_retries', 3)
        self.retry_delay = self.intent_config.get('retry_delay', 1.0)

        logger.debug(f"HTTP JSON Retriever initialized with base_url: {self.base_url}")

    def _get_datasource_name(self) -> str:
        """
        Return the datasource identifier for HTTP JSON APIs.

        Note: HTTP JSON adapters don't use a centralized datasource - they manage
        their own HTTP connections via base_url. This method is for identification only.
        """
        return "http_json_api"

    async def _execute_template(self, template: Dict[str, Any],
                                parameters: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """
        Execute REST API template with parameters.

        Args:
            template: The template dictionary containing REST endpoint configuration
            parameters: Extracted parameters for the request

        Returns:
            Tuple of (results, error_message)
        """
        try:
            # Get HTTP method (default to GET)
            http_method = template.get('http_method', 'GET').upper()

            # Process endpoint template with path parameters
            endpoint = self._process_endpoint_template(
                template.get('endpoint_template', template.get('endpoint', '/')),
                parameters
            )

            # Build query parameters
            query_params = self._build_query_params(template, parameters)

            # Build request headers
            headers = self._build_request_headers(template, parameters)

            # Build request body (for POST, PUT, PATCH)
            request_body = None
            if http_method in ['POST', 'PUT', 'PATCH']:
                request_body = self._build_request_body(template, parameters)

            template_id = template.get('id', 'unknown')
            logger.debug(f"[Template {template_id}] Executing REST {http_method} request to: {endpoint}")
            logger.debug(f"[Template {template_id}] Query params: {query_params}")
            logger.debug(f"[Template {template_id}] Headers: {headers}")
            if request_body:
                logger.debug(f"[Template {template_id}] Request body: {json.dumps(request_body, indent=2)}")

            # Execute the HTTP request
            response = await self._execute_rest_request(
                method=http_method,
                endpoint=endpoint,
                params=query_params,
                headers=headers,
                json_data=request_body,
                timeout=template.get('timeout', self.default_timeout)
            )

            # Parse and extract results
            results = self._parse_response(response, template)

            return results, None

        except httpx.HTTPStatusError as e:
            template_id = template.get('id', 'unknown')
            endpoint = template.get('endpoint_template', template.get('endpoint', '/'))
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"[Template {template_id}] REST API request failed for endpoint '{endpoint}': {error_msg}")
            return [], error_msg
        except Exception as e:
            template_id = template.get('id', 'unknown')
            error_msg = str(e)
            logger.error(f"[Template {template_id}] Error executing REST template: {error_msg}")
            logger.error(traceback.format_exc())
            return [], error_msg

    def _process_endpoint_template(self, endpoint_template: str, parameters: Dict[str, Any]) -> str:
        """
        Process endpoint template with path parameter substitution.

        Args:
            endpoint_template: Endpoint template like "/users/{username}/repos"
            parameters: Parameters for substitution

        Returns:
            Processed endpoint string
        """
        try:
            # Support both {{param}} and {param} syntax
            endpoint = endpoint_template
            logger.debug(f"Processing endpoint template: '{endpoint_template}' with parameters: {parameters}")

            # Check if template uses single braces {param} syntax (common in REST APIs)
            # Template processor only handles {{param}} (Jinja2), so use fallback for {param}
            uses_single_braces = bool(re.search(r'\{[^{]+\}', endpoint_template))
            uses_double_braces = '{{' in endpoint_template

            # Use template processor only if template uses {{param}} syntax and no {param} syntax
            # Otherwise use fallback which handles both
            if self.template_processor and uses_double_braces and not uses_single_braces:
                logger.debug(f"Using template processor for endpoint substitution (Jinja2 syntax detected)")
                endpoint = self.template_processor.render_sql(
                    endpoint_template,
                    parameters=parameters,
                    preserve_unknown=False
                )
                logger.debug(f"Template processor result: '{endpoint}'")
            else:
                # Fallback: simple string substitution (handles both {{param}} and {param})
                if uses_single_braces:
                    logger.debug(f"Using fallback string substitution (single braces {{param}} syntax detected)")
                else:
                    logger.debug(f"Using fallback string substitution (no template processor or mixed syntax)")
                
                for key, value in parameters.items():
                    # Handle both {{key}} and {key} placeholders
                    old_endpoint = endpoint
                    endpoint = endpoint.replace(f"{{{{{key}}}}}", str(value))
                    endpoint = endpoint.replace(f"{{{key}}}", str(value))
                    if old_endpoint != endpoint:
                        logger.debug(f"Substituted {{{{{key}}}}} and {{{key}}} with '{value}' -> '{endpoint}'")
                
                if endpoint == endpoint_template:
                    logger.warning(f"No substitutions were made! Template: '{endpoint_template}', Parameters: {parameters}")

            logger.debug(f"Final processed endpoint: '{endpoint}'")
            return endpoint

        except Exception as e:
            logger.error(f"Error processing endpoint template: {e}")
            logger.error(traceback.format_exc())
            return endpoint_template

    def _build_query_params(self, template: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build query parameters from template and extracted parameters.

        Args:
            template: Template dictionary
            parameters: Extracted parameters

        Returns:
            Dictionary of query parameters
        """
        query_params = {}

        # Get query parameter definitions from template
        template_query_params = template.get('query_params', {})

        # Process each query parameter
        for param_name, param_template in template_query_params.items():
            # Check if this is a template variable
            if isinstance(param_template, str) and param_template.startswith('{{') and param_template.endswith('}}'):
                # Extract variable name
                var_name = param_template.strip('{}')
                if var_name in parameters and parameters[var_name] is not None:
                    query_params[param_name] = parameters[var_name]
            elif param_template is not None:
                # Static value
                query_params[param_name] = param_template

        # Also check if parameters specify location as 'query'
        for param_def in template.get('parameters', []):
            param_name = param_def.get('name')
            param_location = param_def.get('location', 'path')

            if param_location == 'query' and param_name in parameters:
                value = parameters[param_name]
                if value is not None:
                    query_params[param_name] = value

        return query_params

    def _build_request_headers(self, template: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, str]:
        """
        Build request headers from template and parameters.

        Args:
            template: Template dictionary
            parameters: Extracted parameters

        Returns:
            Dictionary of headers
        """
        headers = {}

        # Get base authentication headers
        auth_headers = self._build_auth_headers(template)
        headers.update(auth_headers)

        # Get template-specific headers
        template_headers = template.get('headers', {})
        for header_name, header_value in template_headers.items():
            # Process template variables in header values
            if isinstance(header_value, str):
                processed_value = header_value
                for param_name, param_value in parameters.items():
                    if param_value is not None:
                        processed_value = processed_value.replace(f"{{{{{param_name}}}}}", str(param_value))
                        processed_value = processed_value.replace(f"{{{param_name}}}", str(param_value))
                headers[header_name] = processed_value
            else:
                headers[header_name] = str(header_value)

        # Check for parameters with location='header'
        for param_def in template.get('parameters', []):
            param_name = param_def.get('name')
            param_location = param_def.get('location', 'path')

            if param_location == 'header' and param_name in parameters:
                header_name = param_def.get('header_name', param_name)
                value = parameters[param_name]
                if value is not None:
                    headers[header_name] = str(value)

        return headers

    def _build_request_body(self, template: Dict[str, Any], parameters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Build request body from template and parameters.

        Args:
            template: Template dictionary
            parameters: Extracted parameters

        Returns:
            Request body as dictionary or None
        """
        # Get body template from template
        body_template = template.get('body_template')
        if not body_template:
            # Check if any parameters have location='body'
            body_params = {}
            for param_def in template.get('parameters', []):
                param_name = param_def.get('name')
                param_location = param_def.get('location', 'path')

                if param_location == 'body' and param_name in parameters:
                    value = parameters[param_name]
                    if value is not None:
                        body_params[param_name] = value

            return body_params if body_params else None

        # Process body template with parameters
        if isinstance(body_template, str):
            try:
                # Substitute parameters in JSON string
                body_str = body_template
                for param_name, param_value in parameters.items():
                    if param_value is not None:
                        # Handle string values with quotes, others without
                        if isinstance(param_value, str):
                            replacement = json.dumps(param_value)
                        else:
                            replacement = json.dumps(param_value)
                        body_str = body_str.replace(f'"{{{{{param_name}}}}}"', replacement)
                        body_str = body_str.replace(f"{{{{{param_name}}}}}", replacement)

                return json.loads(body_str)
            except Exception as e:
                logger.error(f"Error processing body template: {e}")
                return None
        elif isinstance(body_template, dict):
            # Process dictionary template
            return self._substitute_dict_params(body_template, parameters)

        return None

    def _substitute_dict_params(self, template_dict: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively substitute parameters in a dictionary template.

        Args:
            template_dict: Template dictionary
            parameters: Parameters for substitution

        Returns:
            Dictionary with substituted values
        """
        result = {}
        for key, value in template_dict.items():
            if isinstance(value, str):
                # Substitute string values
                processed = value
                for param_name, param_value in parameters.items():
                    if param_value is not None:
                        processed = processed.replace(f"{{{{{param_name}}}}}", str(param_value))
                        processed = processed.replace(f"{{{param_name}}}", str(param_value))
                result[key] = processed
            elif isinstance(value, dict):
                # Recursively process nested dictionaries
                result[key] = self._substitute_dict_params(value, parameters)
            elif isinstance(value, list):
                # Process lists
                result[key] = [
                    self._substitute_dict_params(item, parameters) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    async def _execute_rest_request(self, method: str, endpoint: str,
                                     params: Optional[Dict] = None,
                                     headers: Optional[Dict] = None,
                                     json_data: Optional[Dict] = None,
                                     timeout: int = 30) -> httpx.Response:
        """
        Execute REST API request with retry logic.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            headers: Request headers
            json_data: JSON request body
            timeout: Request timeout

        Returns:
            HTTP response
        """
        retries = 0
        last_error = None

        while retries <= (self.max_retries if self.enable_retries else 0):
            try:
                # Merge headers with existing client headers
                merged_headers = dict(self.http_client.headers)
                if headers:
                    merged_headers.update(headers)

                response = await self.http_client.request(
                    method=method,
                    url=endpoint,
                    params=params,
                    headers=merged_headers,
                    json=json_data,
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
                    logger.warning(f"Request failed with {e.response.status_code}, retrying ({retries}/{self.max_retries})...")
                    import asyncio
                    await asyncio.sleep(self.retry_delay * retries)
            except Exception as e:
                last_error = e
                retries += 1
                if retries <= self.max_retries:
                    logger.warning(f"Request failed: {e}, retrying ({retries}/{self.max_retries})...")
                    import asyncio
                    await asyncio.sleep(self.retry_delay * retries)

        # All retries failed
        if last_error:
            raise last_error
        raise Exception("Request failed after all retries")

    def _parse_response(self, response: httpx.Response, template: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse REST API response.

        Args:
            response: HTTP response
            template: Template configuration

        Returns:
            List of result dictionaries
        """
        try:
            # Get response content type
            content_type = response.headers.get('content-type', '').lower()

            # Parse JSON response
            if 'application/json' in content_type or not content_type:
                try:
                    data = response.json()
                except:
                    # If JSON parsing fails, return text
                    return [{'response': response.text}]
            else:
                # Non-JSON response
                return [{'response': response.text, 'content_type': content_type}]

            # Extract items based on response mapping
            response_mapping = template.get('response_mapping', {})
            items_path = response_mapping.get('items_path', '$')

            # If items_path is '$', the data is already a list or single item
            if items_path == '$':
                if isinstance(data, list):
                    results = data
                else:
                    results = [data]
            else:
                # Extract items using JSONPath-like syntax
                results = self._extract_items_from_response(data, items_path)

            # Map fields if field mapping is specified
            field_mapping = response_mapping.get('fields', [])
            if field_mapping:
                results = self._map_response_fields(results, field_mapping)

            return results

        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            logger.error(traceback.format_exc())
            return [{'error': str(e), 'raw_response': response.text[:500]}]

    def _extract_items_from_response(self, data: Any, path: str) -> List[Dict[str, Any]]:
        """
        Extract items from response data using a simple path expression.

        Args:
            data: Response data
            path: Path expression (e.g., "data.items", "results")

        Returns:
            List of extracted items
        """
        try:
            # Simple path navigation
            current = data
            for part in path.split('.'):
                if part and part != '$':
                    if isinstance(current, dict):
                        current = current.get(part)
                    elif isinstance(current, list) and part.isdigit():
                        current = current[int(part)]
                    else:
                        return []

            if isinstance(current, list):
                return current
            elif current is not None:
                return [current]
            return []

        except Exception as e:
            logger.error(f"Error extracting items from path {path}: {e}")
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

                # Extract value using simple path
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
            path: Field path (e.g., "$.data.name" or "name")

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

            return current

        except Exception:
            return None

    def _format_http_results(self, results: Any, template: Dict,
                            parameters: Dict, similarity: float) -> List[Dict[str, Any]]:
        """
        Format REST API results into context documents.

        Args:
            results: REST API results
            template: The template that was executed
            parameters: Parameters used in the request
            similarity: Template matching similarity score

        Returns:
            List of formatted context items
        """
        if not results:
            return [{
                "content": "No results found for your request.",
                "metadata": {
                    "source": "rest_api",
                    "template_id": template.get('id'),
                    "parameters_used": parameters,
                    "similarity": similarity,
                    "result_count": 0
                },
                "confidence": similarity
            }]

        # Format the response
        content = self._format_rest_results(results, template)

        # Build metadata
        metadata = {
            "source": "rest_api",
            "template_id": template.get('id'),
            "query_intent": template.get('description', ''),
            "parameters_used": parameters,
            "similarity": similarity,
            "result_count": len(results),
            "results": results
        }

        return [{
            "content": content,
            "metadata": metadata,
            "confidence": similarity
        }]

    def _format_rest_results(self, results: List[Dict], template: Dict) -> str:
        """
        Format REST API results as human-readable text.

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
                # Table header
                lines.append(" | ".join(display_fields))
                lines.append("-" * (len(" | ".join(display_fields))))

                # Table rows (show first 10)
                for result in results[:10]:
                    row = []
                    for field in display_fields:
                        value = result.get(field, '')
                        # Truncate long values
                        value_str = str(value)[:50]
                        row.append(value_str)
                    lines.append(" | ".join(row))

                if total > 10:
                    lines.append(f"\n... and {total - 10} more results")
        else:
            # Format as list
            lines.append(f"Found {total} results:")

            for i, result in enumerate(results[:10], 1):
                lines.append(f"\n{i}.")
                display_fields = template.get('display_fields')

                if display_fields:
                    for field in display_fields:
                        if field in result:
                            lines.append(f"   {field}: {result[field]}")
                else:
                    # Show all fields
                    for key, value in result.items():
                        if not key.startswith('_'):
                            lines.append(f"   {key}: {value}")

            if total > 10:
                lines.append(f"\n... and {total - 10} more results")

        return '\n'.join(lines)


# Register the HTTP JSON retriever
RetrieverFactory.register_retriever('intent_http_json', IntentHTTPJSONRetriever)
logger.info("Registered IntentHTTPJSONRetriever as 'intent_http_json'")
