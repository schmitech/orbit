"""
Ollama reranker service implementation.
"""

import logging
import json
from typing import List, Dict, Any, Optional
import asyncio

from rerankers.base import RerankerService
from utils.ollama_utils import OllamaBaseService


class OllamaReranker(RerankerService, OllamaBaseService):
    """
    Implementation of the reranker service for Ollama.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama reranker service.
        
        Args:
            config: Configuration dictionary for Ollama
        """
        RerankerService.__init__(self, config)
        OllamaBaseService.__init__(self, config, 'rerankers')
        
        # Additional reranker-specific config
        reranker_config = config.get('rerankers', {}).get('ollama', {})
        self.batch_size = reranker_config.get('batch_size', 5)
    
    async def rerank(self, query: str, documents: List[str], top_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Rerank documents based on their relevance to the query.
        
        Args:
            query: The query text
            documents: List of document texts to rerank
            top_n: Number of top results to return (if None, returns all)
            
        Returns:
            List of dictionaries containing reranked documents with scores
        """
        if not self.initialized:
            if not await self.initialize():
                self.logger.error("Failed to initialize reranker service before reranking")
                raise ValueError("Failed to initialize reranker service")
        
        async def _rerank():
            session = await self.session_manager.get_session()
            url = f"{self.config.base_url}/api/generate"
            
            # Create a simpler prompt for scoring
            prompt = f"""Query: {query}

Documents to score:
{json.dumps(documents, indent=2)}

Score each document's relevance to the query from 0.0 to 1.0. Return only a JSON array of numbers.
Example: [0.8, 0.3, 0.9]

Scores:"""
            
            payload = {
                "model": self.config.model,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.0,  # Use 0 temperature for consistent scoring
                "num_predict": 256,  # We only need a small response
                "stop": ["\n", "}", "]"]  # Stop at the end of the array
            }
            
            self.logger.debug(f"Sending reranking request to {url} for query: {query[:50]}...")
            
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error from Ollama: {error_text}")
                    raise ValueError(f"Failed to rerank documents: {error_text}")
                
                data = await response.json()
                response_text = data.get('response', '').strip()
                
                try:
                    # Clean up the response text to ensure it's valid JSON
                    response_text = response_text.strip()
                    if not response_text.startswith('['):
                        response_text = '[' + response_text
                    if not response_text.endswith(']'):
                        response_text = response_text + ']'
                    
                    # Parse the scores from the response
                    scores = json.loads(response_text)
                    if not isinstance(scores, list) or len(scores) != len(documents):
                        raise ValueError(f"Invalid scores format. Expected {len(documents)} scores, got {len(scores) if isinstance(scores, list) else 'non-list'}")
                    
                    # Format results
                    reranked_docs = []
                    for idx, (doc, score) in enumerate(zip(documents, scores)):
                        reranked_docs.append({
                            'document': doc,
                            'score': float(score),
                            'rank': idx + 1
                        })
                    
                    # Sort by score in descending order
                    reranked_docs.sort(key=lambda x: x['score'], reverse=True)
                    
                    # Apply top_n if specified
                    if top_n is not None:
                        reranked_docs = reranked_docs[:top_n]
                    
                    self.logger.debug(f"Successfully reranked {len(reranked_docs)} documents")
                    return reranked_docs
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse scores from response: {str(e)}")
                    self.logger.error(f"Raw response: {response_text}")
                    raise ValueError(f"Failed to parse reranking scores: {str(e)}")
        
        try:
            return await self.retry_handler.execute_with_retry(_rerank)
        except Exception as e:
            self.logger.error(f"Error reranking documents with Ollama: {str(e)}")
            # Re-raise the exception to be handled by the caller
            raise
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Ollama reranker service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        # First use the base verifier
        if not await self.connection_verifier.verify_connection():
            # If model not found, try the reranking API anyway
            try:
                async def _test_rerank():
                    session = await self.session_manager.get_session()
                    url = f"{self.config.base_url}/api/rerank"
                    payload = {
                        "model": self.config.model,
                        "query": "test query",
                        "documents": ["test document"],
                        "temperature": self.config.temperature
                    }
                    
                    self.logger.info(f"Testing reranking with model {self.config.model}")
                    
                    async with session.post(url, json=payload) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            self.logger.error(f"Error from Ollama: {error_text}")
                            return False
                        
                        # Verify we get valid results
                        data = await response.json()
                        results = data.get('results', [])
                        
                        if not results or len(results) == 0:
                            self.logger.error("Received empty reranking results from Ollama")
                            return False
                            
                        self.logger.info("Successfully generated test reranking")
                        return True
                
                return await self.retry_handler.execute_with_retry(_test_rerank)
            except Exception as e:
                self.logger.error(f"Failed to generate test reranking: {str(e)}")
                return False
        
        return True
    
    async def close(self) -> None:
        """
        Close the reranker service and release any resources.
        """
        await OllamaBaseService.close(self)