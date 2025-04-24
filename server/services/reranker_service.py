"""
Reranker Service
================

A service that provides reranking functionality for retrieved documents using LLMs.
It acts as a cross-encoder to score query-document pairs for higher precision retrieval.
"""

import logging
import aiohttp
import asyncio
from typing import Dict, Any, List, Tuple

from config.config_manager import _is_true_value

# Configure logging
logger = logging.getLogger(__name__)


class RerankerService:
    """Handles document reranking using LLM models"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the RerankerService
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        
        # Get reranker configuration
        reranker_config = config.get('reranker', {})
        
        # Load settings
        self.enabled = _is_true_value(reranker_config.get('enabled', False))
        
        # Get provider information - use resolved_provider and resolved_model 
        # that were set by _resolve_provider_configs
        self.provider = reranker_config.get('resolved_provider', 'ollama')
        self.model = reranker_config.get('resolved_model', 'gemma3:1b')
        
        # Get provider-specific configuration
        provider_config = config.get('inference', {}).get(self.provider, {})
        self.base_url = provider_config.get('base_url', 'http://localhost:11434')
        
        if provider_config:
            logger.info(f"Reranker service using provider: {self.provider}")
            logger.info(f"Reranker service using base URL: {self.base_url}")
        else:
            # Fallback to legacy config for backward compatibility
            self.base_url = config.get('ollama', {}).get('base_url', 'http://localhost:11434')
            logger.warning(f"Using legacy config for reranker service: {self.base_url}")
        
        # Other reranker parameters
        self.batch_size = reranker_config.get('batch_size', 5)
        self.temperature = reranker_config.get('temperature', 0.0)  # Use deterministic scoring
        self.top_n = reranker_config.get('top_n', 3)  # Number of documents to return after reranking
        
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
        self.session = None
        
        if self.verbose:
            logger.info(f"Reranker service initialized: enabled={self.enabled}, provider={self.provider}, model={self.model}")
            logger.info(f"Batch size: {self.batch_size}, Top N: {self.top_n}")

    async def initialize(self):
        """Initialize the aiohttp session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout for reranking
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def _score_document(self, query: str, document: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
        """
        Score a single document based on relevance to the query
        
        Args:
            query: The user query
            document: The document to score
            
        Returns:
            Tuple[Dict[str, Any], float]: Document and relevance score
        """
        try:
            # Construct document text based on its type
            if "question" in document and "answer" in document:
                doc_text = f"Question: {document['question']}\nAnswer: {document['answer']}"
            elif "content" in document:
                doc_text = document['content']
            else:
                doc_text = str(document)
            
            # Create a prompt for the reranker
            prompt = f"""Rate the relevance of the following document to the query on a scale from 0 to 10, 
where 0 means completely irrelevant and 10 means perfectly relevant.
Return only a number (0-10) without any explanations.

QUERY: {query}

DOCUMENT: {doc_text}

RELEVANCE SCORE (0-10):"""

            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": self.temperature,
                "top_p": 1.0,
                "top_k": 1,
                "num_predict": 5,
                "stream": False
            }

            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Reranking failed with status {response.status}")
                    return document, document.get("confidence", 0)
                
                data = await response.json()
                score_text = data.get("response", "").strip()
                
                # Extract numeric score
                try:
                    # Handle different response formats
                    score_text = ''.join(c for c in score_text if c.isdigit() or c == '.')
                    score = float(score_text)
                    
                    # Normalize to 0-1 range
                    normalized_score = min(1.0, max(0.0, score / 10.0))
                    
                    if self.verbose:
                        logger.info(f"Reranked document with score: {normalized_score:.4f}")
                    
                    return document, normalized_score
                except ValueError:
                    logger.warning(f"Failed to parse reranker score: {score_text}")
                    return document, document.get("confidence", 0)

        except Exception as e:
            logger.error(f"Error in reranking document: {str(e)}")
            return document, document.get("confidence", 0)

    async def rerank(self, query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rerank a list of documents based on relevance to the query
        
        Args:
            query: The user query
            documents: List of documents to rerank
            
        Returns:
            List[Dict[str, Any]]: Reranked list of documents
        """
        if not self.enabled or not documents:
            return documents
        
        try:
            await self.initialize()
            
            if self.verbose:
                logger.info(f"Reranking {len(documents)} documents using {self.provider}:{self.model}")
            
            # Process documents in batches to avoid overloading the server
            scored_documents = []
            
            # Create tasks for scoring all documents
            tasks = [self._score_document(query, doc) for doc in documents]
            
            # Process all documents
            results = await asyncio.gather(*tasks)
            
            # Sort by score
            scored_documents = sorted(results, key=lambda x: x[1], reverse=True)
            
            # Log results if verbose
            if self.verbose:
                logger.info("Reranking results:")
                for i, (doc, score) in enumerate(scored_documents[:self.top_n]):
                    logger.info(f"  {i+1}. Score: {score:.4f}")
            
            # Return only the documents, not the scores
            reranked_docs = [doc for doc, _ in scored_documents[:self.top_n]]
            
            # Update confidence scores based on reranking
            for i, doc in enumerate(reranked_docs):
                doc["confidence"] = scored_documents[i][1]
            
            return reranked_docs

        except Exception as e:
            logger.error(f"Error in reranking: {str(e)}")
            return documents  # Return original documents if reranking fails