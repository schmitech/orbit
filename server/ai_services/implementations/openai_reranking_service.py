"""
OpenAI reranking service implementation using unified architecture.

Uses OpenAI's GPT models for reranking via prompt engineering.
This approach leverages the language understanding capabilities of GPT models
to assess document relevance.
"""

from typing import Dict, Any, List, Optional
import asyncio
import json

from ..providers import OpenAIBaseService
from ..services import RerankingService


class OpenAIRerankingService(RerankingService, OpenAIBaseService):
    """
    OpenAI reranking service using GPT models with prompt engineering.

    Features:
    - Leverages powerful language understanding
    - Good for complex queries
    - Supports all OpenAI models
    - Uses JSON mode for structured output

    This implementation uses the chat completion API with a specialized
    prompt to score document relevance.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI reranking service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes
        OpenAIBaseService.__init__(self, config, RerankingService.service_type)
        RerankingService.__init__(self, config, "openai")

        # Get reranking-specific configuration
        provider_config = self._extract_provider_config()

        # Use fast, cost-effective model by default
        if not self.model:
            self.model = provider_config.get('model', 'gpt-4o-mini')

        self.temperature = provider_config.get('temperature', 0.0)
        self.max_tokens = provider_config.get('max_tokens', 10)

    async def initialize(self) -> bool:
        """
        Initialize the OpenAI reranking service.

        Returns:
            True if initialization was successful, False otherwise
        """
        return await OpenAIBaseService.initialize(self)

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        _skip_init_check: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using GPT models via prompt engineering.

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
                raise ValueError("Failed to initialize OpenAI reranking service")

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

            self.logger.debug(f"Reranked {len(documents)} -> {len(all_results)} documents")
            return all_results

        except Exception as e:
            self.logger.error(f"Error in OpenAI reranking: {str(e)}")
            raise

    async def _score_batch(
        self,
        query: str,
        documents: List[str],
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Score a batch of documents using GPT.

        Args:
            query: The query text
            documents: Batch of documents to score
            offset: Index offset for this batch

        Returns:
            List of scored documents
        """
        # Create prompt for scoring
        prompt = self._create_scoring_prompt(query, documents)

        # Call OpenAI API
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a relevance scoring system. Score documents based on their relevance to the query."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens * len(documents),
            response_format={"type": "json_object"}
        )

        # Parse response
        content = response.choices[0].message.content
        try:
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

        except (json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"Failed to parse OpenAI response: {str(e)}")
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
            f"{i}. {doc[:200]}..." if len(doc) > 200 else f"{i}. {doc}"
            for i, doc in enumerate(documents)
        ])

        prompt = f"""Query: {query}

Documents:
{docs_formatted}

Rate each document's relevance to the query on a scale of 0.0 to 1.0, where:
- 1.0 = Highly relevant, directly answers the query
- 0.5 = Somewhat relevant, contains related information
- 0.0 = Not relevant, unrelated to the query

Return your scores as a JSON object with a "scores" array containing {len(documents)} numbers.
Example format: {{"scores": [0.9, 0.7, 0.3, ...]}}"""

        return prompt

    async def verify_connection(self) -> bool:
        """
        Verify the connection to OpenAI's API.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            test_query = "test"
            test_docs = ["test document"]

            # Skip init check to avoid infinite recursion during initialization
            results = await self.rerank(test_query, test_docs, top_n=1, _skip_init_check=True)

            if results and len(results) > 0:
                self.logger.info("Successfully verified OpenAI reranking connection")
                return True
            else:
                self.logger.error("Received empty results from OpenAI")
                return False

        except Exception as e:
            self.logger.error(f"Failed to verify OpenAI reranking connection: {str(e)}")
            return False
