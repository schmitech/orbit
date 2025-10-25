"""
Firecrawl intent retriever implementation.

This retriever extends IntentHTTPRetriever to provide web scraping capabilities using Firecrawl,
allowing natural language queries to be translated into web scraping requests.
Supports both cloud API (api.firecrawl.dev) and self-hosted Firecrawl deployments.
"""

import logging
import traceback
import json
import httpx
from typing import Dict, Any, List, Optional, Tuple

from retrievers.base.intent_http_base import IntentHTTPRetriever
from retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)


class IntentFirecrawlRetriever(IntentHTTPRetriever):
    """
    Firecrawl intent retriever for web scraping.

    Translates natural language queries to Firecrawl web scraping requests.
    Supports both cloud API and self-hosted Firecrawl deployments.

    Features:
    - URL extraction from natural language
    - Format specification (markdown, html, text)
    - Support for both cloud and self-hosted Firecrawl
    - Fresh content fetching (no local caching)
    - Error handling for invalid URLs and API failures
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None, datasource=None, **kwargs):
        """
        Initialize Firecrawl retriever.

        Args:
            config: Configuration dictionary with datasource settings
            domain_adapter: Optional domain adapter
            datasource: Optional pre-initialized datasource
            **kwargs: Additional arguments
        """
        super().__init__(config=config, domain_adapter=domain_adapter, datasource=datasource, **kwargs)

        # Disable response_generator to use custom Firecrawl formatting
        # The generic response_generator doesn't understand Firecrawl's response structure
        self.response_generator = None
        self.parameter_extractor = None

        # Firecrawl-specific settings from adapter config
        self.default_timeout = self.intent_config.get('default_timeout', 60)
        self.default_formats = self.intent_config.get('default_formats', ['markdown'])
        self.enable_retries = self.intent_config.get('enable_retries', True)
        self.max_retries = self.intent_config.get('max_retries', 2)
        self.retry_delay = self.intent_config.get('retry_delay', 2.0)

        if self.verbose:
            logger.info(f"Firecrawl retriever initialized with base_url: {self.base_url}")

    def _get_datasource_name(self) -> str:
        """
        Return the datasource identifier for Firecrawl.

        Note: Firecrawl uses the HTTP placeholder datasource since it's a remote API.
        """
        return "http"

    async def _execute_template(self, template: Dict[str, Any],
                                parameters: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """
        Execute Firecrawl scraping template with parameters.

        Args:
            template: The template dictionary containing scraping configuration
            parameters: Extracted parameters for the scraping request

        Returns:
            Tuple of (results, error_message)
        """
        try:
            # Extract URL from parameters or template's url_mapping (for hardcoded URLs)
            url = parameters.get('url')
            if not url and 'url_mapping' in template:
                url = template['url_mapping'].get('url')

            if not url:
                # Try to extract from request_body JSON
                request_body_str = template.get('request_body', '')
                if request_body_str:
                    try:
                        request_data = json.loads(request_body_str)
                        url = request_data.get('url')
                    except json.JSONDecodeError:
                        pass

            if not url:
                return [], "URL parameter is required for web scraping. Provide url in parameters, url_mapping, or request_body."

            # Extract formats from parameters, template, or use defaults
            formats = parameters.get('formats')
            if not formats and 'url_mapping' not in template:
                # Only try extracting from request_body if we're using hardcoded templates
                request_body_str = template.get('request_body', '')
                if request_body_str:
                    try:
                        request_data = json.loads(request_body_str)
                        formats = request_data.get('formats', self.default_formats)
                    except json.JSONDecodeError:
                        formats = self.default_formats
            elif not formats:
                formats = self.default_formats

            if isinstance(formats, str):
                formats = [formats]

            # Build Firecrawl scrape parameters
            scrape_params = self._build_scrape_params(url, formats, template)

            if self.verbose:
                logger.info(f"Scraping URL: {url} with formats: {formats}")
                logger.debug(f"Scrape params: {json.dumps(scrape_params, indent=2)}")

            # Execute the Firecrawl scrape request
            response = await self._execute_firecrawl_request(scrape_params)

            # Parse and extract results
            results = self._parse_firecrawl_response(response, formats)

            return results, None

        except httpx.HTTPStatusError as e:
            error_msg = f"Firecrawl API error {e.response.status_code}: {e.response.text}"
            logger.error(f"Firecrawl request failed: {error_msg}")
            return [], error_msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error executing Firecrawl template: {error_msg}")
            logger.error(traceback.format_exc())
            return [], error_msg

    def _build_scrape_params(self, url: str, formats: List[str], template: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build Firecrawl scrape parameters from URL, formats, and template.

        Args:
            url: URL to scrape
            formats: List of desired output formats
            template: Template configuration

        Returns:
            Dictionary of Firecrawl API parameters
        """
        params = {
            'url': url,
            'formats': formats,
            'timeout': template.get('timeout', self.default_timeout) * 1000,  # Convert to milliseconds
        }

        # Add optional parameters from template
        if 'mobile' in template:
            params['mobile'] = template['mobile']
        
        if 'wait_for' in template:
            params['waitFor'] = template['wait_for']
        
        if 'wait_time' in template:
            params['waitTime'] = template['wait_time']
        
        if 'screenshot' in template:
            params['screenshot'] = template['screenshot']
        
        if 'include_tags' in template:
            params['includeTags'] = template['include_tags']
        
        if 'exclude_tags' in template:
            params['excludeTags'] = template['exclude_tags']

        return params

    async def _execute_firecrawl_request(self, params: Dict[str, Any]) -> httpx.Response:
        """
        Execute Firecrawl scrape request with retry logic.

        Args:
            params: Firecrawl API parameters

        Returns:
            HTTP response
        """
        retries = 0
        last_error = None

        while retries <= (self.max_retries if self.enable_retries else 0):
            try:
                # Execute the scrape request
                response = await self.http_client.post(
                    '/scrape',
                    json=params,
                    timeout=self.default_timeout
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

    def _parse_firecrawl_response(self, response: httpx.Response, formats: List[str]) -> List[Dict[str, Any]]:
        """
        Parse Firecrawl API response.

        Args:
            response: HTTP response from Firecrawl
            formats: List of requested formats

        Returns:
            List of result dictionaries
        """
        try:
            response_data = response.json()

            # Debug logging to see actual response structure
            if self.verbose:
                logger.debug(f"Raw Firecrawl API response: {json.dumps(response_data, indent=2)[:1000]}")

            # Firecrawl v1 API nests content in 'data' field
            data = response_data.get('data', {})

            # Extract the scraped content
            result = {
                'url': data.get('metadata', {}).get('url', ''),
                'success': response_data.get('success', False),
                'metadata': data.get('metadata', {}),
            }

            # Add content based on requested formats
            for format_type in formats:
                if format_type in data:
                    result[format_type] = data[format_type]
                    if self.verbose:
                        content_preview = str(data[format_type])[:200]
                        logger.debug(f"Extracted {format_type} content: {content_preview}...")

            # Add screenshot if present
            if 'screenshot' in data:
                result['screenshot'] = data['screenshot']

            # Add links if present
            if 'links' in data:
                result['links'] = data['links']

            if self.verbose:
                logger.debug(f"Parsed result keys: {list(result.keys())}")
                logger.debug(f"Has markdown: {'markdown' in result}, Has metadata: {bool(result.get('metadata'))}")

            return [result]

        except Exception as e:
            logger.error(f"Error parsing Firecrawl response: {e}")
            logger.error(traceback.format_exc())
            return [{'error': str(e), 'raw_response': response.text[:500]}]

    def _format_http_results(self, results: Any, template: Dict,
                            parameters: Dict, similarity: float) -> List[Dict[str, Any]]:
        """
        Format Firecrawl results into context documents.

        Args:
            results: Firecrawl scraping results
            template: The template that was executed
            parameters: Parameters used in the request
            similarity: Template matching similarity score

        Returns:
            List of formatted context items
        """
        if not results:
            return [{
                "content": "No content was scraped from the provided URL.",
                "metadata": {
                    "source": "firecrawl",
                    "template_id": template.get('id'),
                    "parameters_used": parameters,
                    "similarity": similarity,
                    "result_count": 0
                },
                "confidence": similarity
            }]

        # Format the response
        content = self._format_firecrawl_results(results, template)

        # Build metadata
        metadata = {
            "source": "firecrawl",
            "template_id": template.get('id'),
            "query_intent": template.get('description', ''),
            "parameters_used": parameters,
            "similarity": similarity,
            "result_count": len(results),
            "results": results
        }

        # Add URL and success status
        if results and len(results) > 0:
            result = results[0]
            metadata['scraped_url'] = result.get('url', '')
            metadata['scrape_success'] = result.get('success', False)
            
            # Add metadata from Firecrawl
            if 'metadata' in result:
                metadata['page_metadata'] = result['metadata']

        return [{
            "content": content,
            "metadata": metadata,
            "confidence": similarity
        }]

    def _format_firecrawl_results(self, results: List[Dict], template: Dict) -> str:
        """
        Format Firecrawl results as human-readable text.

        Args:
            results: List of Firecrawl result dictionaries
            template: The template being executed

        Returns:
            Formatted string representation
        """
        lines = []

        if not results:
            return "No content was scraped."

        result = results[0]
        url = result.get('url', 'Unknown URL')
        success = result.get('success', False)

        if not success:
            lines.append(f"Failed to scrape content from: {url}")
            if 'error' in result:
                lines.append(f"Error: {result['error']}")
            return '\n'.join(lines)

        lines.append(f"Successfully scraped content from: {url}")

        # Add page metadata if available
        if 'metadata' in result and result['metadata']:
            metadata = result['metadata']
            lines.append("\nPage Information:")
            if metadata.get('title'):
                lines.append(f"Title: {metadata['title']}")
            if metadata.get('description'):
                lines.append(f"Description: {metadata['description']}")
            if metadata.get('author'):
                lines.append(f"Author: {metadata['author']}")
            if metadata.get('language'):
                lines.append(f"Language: {metadata['language']}")

        # Add content based on available formats
        content_added = False
        
        if 'markdown' in result and result['markdown']:
            lines.append(f"\nMarkdown Content:\n{result['markdown']}")
            content_added = True
        elif 'html' in result and result['html']:
            lines.append(f"\nHTML Content:\n{result['html']}")
            content_added = True
        elif 'text' in result and result['text']:
            lines.append(f"\nText Content:\n{result['text']}")
            content_added = True

        if not content_added:
            lines.append("\nNo content was extracted from the page.")

        # Add links if present
        if 'links' in result and result['links']:
            links = result['links']
            lines.append(f"\nFound {len(links)} links:")
            for i, link in enumerate(links[:10], 1):  # Show first 10 links
                lines.append(f"{i}. {link}")
            if len(links) > 10:
                lines.append(f"... and {len(links) - 10} more links")

        return '\n'.join(lines)


# Register the Firecrawl retriever
RetrieverFactory.register_retriever('intent_firecrawl', IntentFirecrawlRetriever)
logger.info("Registered IntentFirecrawlRetriever as 'intent_firecrawl'")
