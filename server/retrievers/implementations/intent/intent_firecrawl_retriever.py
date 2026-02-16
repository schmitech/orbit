"""
Firecrawl intent retriever implementation.

This retriever extends IntentHTTPRetriever to provide web scraping capabilities using Firecrawl,
allowing natural language queries to be translated into web scraping requests.
Supports both cloud API (api.firecrawl.dev) and self-hosted Firecrawl deployments.

Features:
- Intelligent content chunking for large documents
- Vector store caching for improved performance
- Embedding-based chunk ranking for relevance
"""

import logging
import traceback
import json
import httpx
from typing import Dict, Any, List, Optional, Tuple

from retrievers.base.intent_http_base import IntentHTTPRetriever
from retrievers.base.base_retriever import RetrieverFactory
from utils.content_chunker import ContentChunker
from utils.chunk_manager import ChunkManager

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

        # Content chunking configuration
        self.enable_chunking = self.intent_config.get('enable_chunking', True)
        self.max_chunk_tokens = self.intent_config.get('max_chunk_tokens', 4000)
        self.chunk_overlap_tokens = self.intent_config.get('chunk_overlap_tokens', 200)
        self.min_chunk_tokens = self.intent_config.get('min_chunk_tokens', 500)
        self.chunks_collection = self.intent_config.get('chunks_collection', 'firecrawl_chunks')
        self.chunk_cache_ttl_hours = self.intent_config.get('chunk_cache_ttl_hours', 24)
        self.top_chunks_to_return = self.intent_config.get('top_chunks_to_return', 3)
        self.min_chunk_similarity = self.intent_config.get('min_chunk_similarity', 0.3)
        # Max tokens for embedding model (OpenAI: 8191, Cohere: 512, Jina: 8192)
        # Use 7500 default to provide safety buffer for estimation errors
        self.max_embedding_tokens = self.intent_config.get('max_embedding_tokens', 7500)

        # Initialize chunking components (will be set up in initialize())
        self.content_chunker: Optional[ContentChunker] = None
        self.chunk_manager: Optional[ChunkManager] = None

        
        logger.debug(f"Firecrawl retriever initialized with base_url: {self.base_url}")
        if self.enable_chunking:
            logger.debug(
                f"Content chunking enabled: max_tokens={self.max_chunk_tokens}, "
                f"top_chunks={self.top_chunks_to_return}"
            )

    async def initialize(self) -> None:
        """Initialize the Firecrawl retriever and chunking components."""
        # Call parent initialization
        await super().initialize()

        # Initialize chunking if enabled
        if self.enable_chunking:
            # Create content chunker
            self.content_chunker = ContentChunker(
                max_chunk_tokens=self.max_chunk_tokens,
                chunk_overlap_tokens=self.chunk_overlap_tokens,
                min_chunk_tokens=self.min_chunk_tokens
            )

            # Create chunk manager with vector store and embedding client
            if self.store_manager and self.embedding_client:
                try:
                    # Get store configuration from config
                    store_config = self._get_store_config()

                    # Get or create vector store for chunks
                    # Use the same store as templates but with a different collection
                    chunk_store = await self.store_manager.get_or_create_store(
                        name=f'firecrawl_chunks_{self.store_name}',
                        store_type=self.store_name,  # Use same type (chroma, qdrant, etc.)
                        config={'connection_params': store_config.get('connection_params', {})}
                    )

                    if not chunk_store:
                        raise Exception("Failed to create/get chunk vector store")

                    self.chunk_manager = ChunkManager(
                        vector_store=chunk_store,
                        embedding_client=self.embedding_client,
                        collection_name=self.chunks_collection,
                        cache_ttl_hours=self.chunk_cache_ttl_hours,
                        min_similarity_score=self.min_chunk_similarity,
                        max_embedding_tokens=self.max_embedding_tokens
                    )

                    # Initialize chunk manager
                    await self.chunk_manager.initialize()

                    logger.info(f"Chunk manager initialized successfully with {self.store_name} store")
                except Exception as e:
                    logger.warning(f"Failed to initialize chunk manager: {e}")
                    logger.warning("Chunking will be disabled for this session")
                    logger.error(traceback.format_exc())
                    self.enable_chunking = False
            else:
                logger.warning("Store manager or embedding client not available, disabling chunking")
                self.enable_chunking = False

    def _get_datasource_name(self) -> str:
        """
        Return the datasource identifier for Firecrawl.

        Note: Firecrawl uses the HTTP placeholder datasource since it's a remote API.
        """
        return "http"

    async def get_relevant_context(self, query: str, api_key: Optional[str] = None,
                                   collection_name: Optional[str] = None,
                                   **kwargs) -> List[Dict[str, Any]]:
        """
        Process a natural language query using intent-based Firecrawl scraping with chunking.

        This override adds chunking support to the base intent HTTP retriever.

        Args:
            query: The natural language query
            api_key: Optional API key
            collection_name: Optional collection name
            **kwargs: Additional arguments

        Returns:
            List of context dictionaries with scraped and chunked content
        """
        try:
            logger.debug(f"Processing Firecrawl query with chunking: {query}")

            # Find best matching templates
            templates = await self._find_best_templates(query)

            if not templates:
                logger.warning("No matching templates found")
                return [{
                    "content": "I couldn't find a matching query pattern for your request.",
                    "metadata": {"source": "firecrawl", "error": "no_matching_template"},
                    "confidence": 0.0
                }]

            # Rerank templates using domain-specific rules
            if self.template_reranker:
                templates = self.template_reranker.rerank_templates(templates, query)

            # Try templates in order of relevance
            for template_info in templates:
                template = template_info['template']
                similarity = template_info['similarity']

                if similarity < self.confidence_threshold:
                    continue

                logger.debug(f"Trying template: {template.get('id')} (similarity: {similarity:.2%})")

                # Extract parameters
                if self.parameter_extractor:
                    parameters = await self.parameter_extractor.extract_parameters(query, template)
                    validation_errors = self.parameter_extractor.validate_parameters(parameters)
                    if validation_errors:
                        logger.debug(f"Parameter validation failed: {validation_errors}")
                        continue
                else:
                    parameters = await self._extract_parameters(query, template)

                # Execute template (scrape content)
                results, error = await self._execute_template(template, parameters)

                if error:
                    logger.debug(f"Template execution failed: {error}")
                    continue

                # Format results with chunking support
                formatted_results = await self._format_http_results_async(
                    results=results,
                    template=template,
                    parameters=parameters,
                    similarity=similarity,
                    query=query  # Pass query for chunk ranking
                )

                logger.debug("Successfully processed Firecrawl query")

                return formatted_results

            # If no template succeeded
            logger.warning("All templates failed to execute")
            return [{
                "content": "I couldn't scrape content with the available templates.",
                "metadata": {"source": "firecrawl", "error": "all_templates_failed"},
                "confidence": 0.0
            }]

        except Exception as e:
            logger.error(f"Error in get_relevant_context: {e}")
            logger.error(traceback.format_exc())
            return [{
                "content": f"An error occurred while processing your query: {str(e)}",
                "metadata": {"source": "firecrawl", "error": "exception"},
                "confidence": 0.0
            }]

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

            logger.debug(f"Scraping URL: {url} with formats: {formats}")
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
                    content_preview = str(data[format_type])[:200]
                    logger.debug(f"Extracted {format_type} content: {content_preview}...")

            # Add screenshot if present
            if 'screenshot' in data:
                result['screenshot'] = data['screenshot']

            # Add links if present
            if 'links' in data:
                result['links'] = data['links']

            logger.debug(f"Parsed result keys: {list(result.keys())}")
            logger.debug(f"Has markdown: {'markdown' in result}, Has metadata: {bool(result.get('metadata'))}")

            return [result]

        except Exception as e:
            logger.error(f"Error parsing Firecrawl response: {e}")
            logger.error(traceback.format_exc())
            return [{'error': str(e), 'raw_response': response.text[:500]}]

    async def _format_http_results_async(self, results: Any, template: Dict,
                                         parameters: Dict, similarity: float,
                                         query: str) -> List[Dict[str, Any]]:
        """
        Format Firecrawl results with chunking support (async version).

        Args:
            results: Firecrawl scraping results
            template: The template that was executed
            parameters: Parameters used in the request
            similarity: Template matching similarity score
            query: The original user query for chunk ranking

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

        # Get the scraped result
        result = results[0] if results else {}
        source_url = result.get('url', parameters.get('url', ''))

        # Check if we should use chunking
        should_chunk = False
        if self.enable_chunking and self.content_chunker and self.chunk_manager:
            # Check if content exists and is markdown
            if 'markdown' in result and result['markdown']:
                should_chunk = self.content_chunker.should_chunk(result['markdown'])

        # If chunking is enabled and content is large enough
        if should_chunk:
            try:
                content = await self._process_with_chunking(
                    results, template, parameters, query, source_url
                )
            except Exception as e:
                logger.warning(f"Chunking failed, falling back to full content: {e}")
                content = self._format_firecrawl_results(results, template)
        else:
            # Use regular formatting
            content = self._format_firecrawl_results(results, template)

        # Build metadata
        metadata = {
            "source": "firecrawl",
            "template_id": template.get('id'),
            "query_intent": template.get('description', ''),
            "parameters_used": parameters,
            "similarity": similarity,
            "result_count": len(results),
            "results": results,
            "chunked": should_chunk
        }

        # Add URL and success status
        if results and len(results) > 0:
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

    def _format_http_results(self, results: Any, template: Dict,
                            parameters: Dict, similarity: float) -> List[Dict[str, Any]]:
        """
        Format Firecrawl results into context documents (sync wrapper).

        Note: This is kept for compatibility but chunking requires the async version.

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

        # Format the response (without chunking)
        content = self._format_firecrawl_results(results, template)

        # Build metadata
        metadata = {
            "source": "firecrawl",
            "template_id": template.get('id'),
            "query_intent": template.get('description', ''),
            "parameters_used": parameters,
            "similarity": similarity,
            "result_count": len(results),
            "results": results,
            "chunked": False
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

    async def _process_with_chunking(self, results: List[Dict], template: Dict,
                                     parameters: Dict, query: str,
                                     source_url: str) -> str:
        """
        Process large content with chunking and ranking.

        Args:
            results: Firecrawl results
            template: Template used
            parameters: Extracted parameters
            query: User's query for ranking
            source_url: URL of the scraped page

        Returns:
            Formatted string with relevant chunks
        """
        result = results[0]
        markdown_content = result.get('markdown', '')

        if not markdown_content:
            return "No markdown content available."

        # Prepare metadata for chunking
        page_metadata = result.get('metadata', {})
        chunk_metadata = {
            'url': source_url,
            'title': page_metadata.get('title', 'Document'),
            'description': page_metadata.get('description', ''),
            'author': page_metadata.get('author', ''),
            'language': page_metadata.get('language', '')
        }

        # Check if we have cached chunks
        if await self.chunk_manager.has_cached_chunks(source_url):
            logger.debug(f"Using cached chunks for {source_url}")
        else:
            # Chunk the content
            logger.debug(f"Chunking content ({len(markdown_content)} chars)")

            chunks = self.content_chunker.chunk_markdown(markdown_content, chunk_metadata)

            # Store chunks in vector store
            await self.chunk_manager.store_chunks(chunks, source_url, chunk_metadata)

            logger.debug(f"Created and stored {len(chunks)} chunks")

        # Retrieve relevant chunks based on query
        relevant_chunks = await self.chunk_manager.retrieve_chunks(
            query=query,
            source_url=source_url,
            top_k=self.top_chunks_to_return,
            min_score=self.min_chunk_similarity
        )

        if not relevant_chunks:
            logger.warning("No relevant chunks found, returning full content")
            return self._format_firecrawl_results(results, template)

        # Format the chunked response
        return self._format_chunked_results(
            chunks=relevant_chunks,
            source_url=source_url,
            page_metadata=page_metadata,
            total_content_size=len(markdown_content)
        )

    def _format_chunked_results(self, chunks: List[Dict[str, Any]],
                                source_url: str,
                                page_metadata: Dict[str, Any],
                                total_content_size: int) -> str:
        """
        Format chunked results for display.

        Args:
            chunks: List of relevant chunks
            source_url: Source URL
            page_metadata: Page metadata
            total_content_size: Total size of original content

        Returns:
            Formatted string
        """
        lines = []

        # Header
        lines.append(f"Successfully scraped and analyzed content from: {source_url}")
        lines.append(f"Original content size: {total_content_size // 4} tokens (~{total_content_size} chars)")
        lines.append(f"Showing {len(chunks)} most relevant section(s):\n")

        # Page info
        if page_metadata.get('title'):
            lines.append(f"Title: {page_metadata['title']}")
        if page_metadata.get('description'):
            lines.append(f"Description: {page_metadata['description']}")
        lines.append("")

        # Show each relevant chunk
        for i, chunk in enumerate(chunks, 1):
            similarity = chunk.get('similarity_score', 0.0)
            chunk.get('section', 'Section')
            hierarchy = chunk.get('hierarchy', [])
            position = chunk.get('position', 0)
            total_chunks = chunk.get('total_chunks', 1)

            lines.append("=" * 70)
            lines.append(f"RELEVANT SECTION {i}/{len(chunks)} "
                        f"(Relevance: {similarity:.1%}, "
                        f"Part {position + 1}/{total_chunks})")
            lines.append(f"Path: {' > '.join(hierarchy)}")
            lines.append("=" * 70)
            lines.append("")
            lines.append(chunk['content'])
            lines.append("")

        # Footer
        lines.append("=" * 70)
        lines.append(f"Note: Showing top {len(chunks)} relevant sections out of {chunks[0].get('total_chunks', '?')} total sections.")
        lines.append("The full content has been cached for follow-up queries.")
        lines.append("=" * 70)

        return '\n'.join(lines)

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
