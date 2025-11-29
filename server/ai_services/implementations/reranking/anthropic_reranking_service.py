"""
Anthropic reranking service implementation using unified architecture.

Uses Anthropic's Claude models for reranking via prompt engineering.
Claude excels at instruction following and nuanced relevance judgments.
"""

import logging
from typing import Dict, Any, List, Optional
import asyncio
import json

from ...providers import AnthropicBaseService
from ...services import RerankingService

logger = logging.getLogger(__name__)


class AnthropicRerankingService(RerankingService, AnthropicBaseService):
    """
    Anthropic reranking service using Claude models with prompt engineering.

    Features:
    - Excellent instruction following
    - Nuanced relevance judgments
    - Fast Haiku model available
    - Structured JSON output

    This implementation uses the messages API with a specialized
    prompt to score document relevance.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Anthropic reranking service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes
        AnthropicBaseService.__init__(self, config, RerankingService.service_type)
        RerankingService.__init__(self, config, "anthropic")

        # Get reranking-specific configuration
        provider_config = self._extract_provider_config()

        # Use fast Haiku model by default for cost-effectiveness
        if not self.model:
            self.model = provider_config.get('model', 'claude-3-haiku-20240307')

        self.temperature = provider_config.get('temperature', 0.0)
        self.max_tokens = provider_config.get('max_tokens', 100)

    async def initialize(self) -> bool:
        """
        Initialize the Anthropic reranking service.

        Returns:
            True if initialization was successful, False otherwise
        """
        return await AnthropicBaseService.initialize(self)

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        _skip_init_check: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using Claude models via prompt engineering.

        Args:
            query: The query text
            documents: List of document texts to rerank
            top_n: Number of top results to return (if None, returns all)
            _skip_init_check: Internal flag to skip initialization check (used during verify_connection)

        Returns:
            List of dictionaries containing reranked documents with scores.
        """
        if not _skip_init_check and not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Anthropic reranking service")

        if not documents:
            return []

        # Use top_n from parameter, or fall back to config default
        if top_n is None:
            top_n = self.top_n_default

        try:
            # Score documents in batches to avoid token limits
            batch_size = self.batch_size
            all_results = []

            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i + batch_size]
                batch_scores = await self._score_batch(query, batch_docs, i)
                all_results.extend(batch_scores)

            # Sort by score descending
            all_results.sort(key=lambda x: x['score'], reverse=True)

            # Apply top_n if specified
            if top_n is not None:
                all_results = all_results[:top_n]

            logger.debug(f"Reranked {len(documents)} -> {len(all_results)} documents")
            return all_results

        except Exception as e:
            logger.error(f"Error in Anthropic reranking: {str(e)}")
            raise

    async def _score_batch(
        self,
        query: str,
        documents: List[str],
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Score a batch of documents using Claude.

        Args:
            query: The query text
            documents: Batch of documents to score
            offset: Index offset for this batch

        Returns:
            List of scored documents
        """
        # Create prompt for scoring
        prompt = self._create_scoring_prompt(query, documents)

        # Call Anthropic API
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Parse response
        content = response.content[0].text
        try:
            # Extract JSON from response (Claude might include explanation)
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                scores_data = json.loads(json_str)
            else:
                scores_data = json.loads(content)

            scores = scores_data.get('scores', [])

            # Normalize scores to 0-1 range if needed
            if scores and max(scores) > 1.0:
                max_score = max(scores)
                scores = [s / max_score for s in scores]

            # Create results
            results = []
            for idx, (doc, score) in enumerate(zip(documents, scores)):
                results.append({
                    'index': offset + idx,
                    'text': doc,
                    'score': float(score)
                })

            return results

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse Anthropic response: {str(e)}")
            logger.error(f"Response content: {content}")
            # Fallback: return documents with neutral scores
            return [
                {
                    'index': offset + idx,
                    'text': doc,
                    'score': 0.5
                }
                for idx, doc in enumerate(documents)
            ]

    def _create_scoring_prompt(self, query: str, documents: List[str]) -> str:
        """
        Create a prompt for document scoring.

        Args:
            query: The query text
            documents: List of documents to score

        Returns:
            Formatted prompt string
        """
        docs_formatted = "\n".join([
            f"Document {i}: {doc[:200]}..." if len(doc) > 200 else f"Document {i}: {doc}"
            for i, doc in enumerate(documents)
        ])

        prompt = f"""You are a relevance scoring system. Your task is to rate how relevant each document is to the given query.

Query: {query}

{docs_formatted}

Rate each document's relevance to the query on a scale of 0.0 to 1.0:
- 1.0 = Highly relevant, directly answers the query
- 0.5 = Somewhat relevant, contains related information
- 0.0 = Not relevant, unrelated to the query

Provide your scores as a JSON object with a "scores" array containing exactly {len(documents)} numbers, one for each document in order.

Example format:
{{
  "scores": [0.9, 0.7, 0.3]
}}

Only output the JSON, no other text."""

        return prompt

    async def verify_connection(self) -> bool:
        """
        Verify the connection to Anthropic's API.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            test_query = "test"
            test_docs = ["test document"]

            # Skip init check to avoid infinite recursion during initialization
            results = await self.rerank(test_query, test_docs, top_n=1, _skip_init_check=True)

            if results and len(results) > 0:
                logger.info("Successfully verified Anthropic reranking connection")
                return True
            else:
                logger.error("Received empty results from Anthropic")
                return False

        except Exception as e:
            logger.error(f"Failed to verify Anthropic reranking connection: {str(e)}")
            return False
