"""
Ollama reranker service implementation.
"""

import logging
import aiohttp
import json
from typing import List, Dict, Any, Optional
import asyncio

from rerankers.base import RerankerService


class OllamaReranker(RerankerService):
    """
    Implementation of the reranker service for Ollama.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama reranker service.
        
        Args:
            config: Configuration dictionary for Ollama
        """
        super().__init__(config)
        self.logger = logging.getLogger(__name__)
        self.base_url = config.get('base_url', 'http://localhost:11434')
        self.model = config.get('model', 'xitao/bge-reranker-v2-m3:')
        self.temperature = config.get('temperature', 0.0)
        self.batch_size = config.get('batch_size', 5)
        self.session = None
        self._session_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initializing = False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an aiohttp client session.
        Uses a lock to prevent multiple session creations.
        
        Returns:
            An aiohttp ClientSession
        """
        async with self._session_lock:
            if self.session is None or self.session.closed:
                # Configure TCP connector with limits
                connector = aiohttp.TCPConnector(
                    limit=10,  # Limit total number of connections
                    limit_per_host=5,  # Limit connections per host
                    ttl_dns_cache=300,  # Cache DNS results for 5 minutes
                )
                timeout = aiohttp.ClientTimeout(total=30)  # 30 seconds total timeout
                self.session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
                )
            return self.session
    
    async def initialize(self) -> bool:
        """
        Initialize the Ollama reranker service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        # If already initialized, return immediately
        if self.initialized:
            return True
            
        # Use a lock to prevent concurrent initializations
        async with self._init_lock:
            # Double-check that it's not initialized after acquiring the lock
            if self.initialized:
                return True
                
            # Check if we're already in the process of initializing
            if self._initializing:
                self.logger.debug("Already initializing, waiting for completion")
                return self.initialized
                
            self._initializing = True
            
            try:
                # Check if the model is available
                if await self.verify_connection():
                    self.logger.info(f"Initialized Ollama reranker service with model {self.model}")
                    self.initialized = True
                    return True
                return False
            except Exception as e:
                self.logger.error(f"Failed to initialize Ollama reranker service: {str(e)}")
                await self.close()
                return False
            finally:
                self._initializing = False
    
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
        
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/generate"
            
            # Create a simpler prompt for scoring
            prompt = f"""Query: {query}

Documents to score:
{json.dumps(documents, indent=2)}

Score each document's relevance to the query from 0.0 to 1.0. Return only a JSON array of numbers.
Example: [0.8, 0.3, 0.9]

Scores:"""
            
            payload = {
                "model": self.model,
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
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/tags"
            
            self.logger.info(f"Verifying connection to Ollama at {self.base_url}")
            
            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to connect to Ollama: {response.status}")
                    return False
                
                data = await response.json()
                
                # Check if our model is in the list, considering :latest tag
                models = [model.get('name') for model in data.get('models', [])]
                
                self.logger.info(f"Available models in Ollama: {models}")
                
                model_found = any(
                    m.startswith(self.model) or  # Exact match or starts with our model name
                    m.split(':')[0] == self.model  # Match base name without tag
                    for m in models
                )
                
                if not model_found:
                    self.logger.warning(f"Reranker model {self.model} not found in Ollama. Available models: {models}")
                    # Try to generate a test reranking anyway
                    try:
                        url = f"{self.base_url}/api/rerank"
                        payload = {
                            "model": self.model,
                            "query": "test query",
                            "documents": ["test document"],
                            "temperature": self.temperature
                        }
                        
                        self.logger.info(f"Testing reranking with model {self.model}")
                        
                        async with session.post(url, json=payload) as rerank_response:
                            if rerank_response.status != 200:
                                error_text = await rerank_response.text()
                                self.logger.error(f"Error from Ollama: {error_text}")
                                return False
                            
                            # Verify we get valid results
                            data = await rerank_response.json()
                            results = data.get('results', [])
                            
                            if not results or len(results) == 0:
                                self.logger.error("Received empty reranking results from Ollama")
                                return False
                                
                            self.logger.info("Successfully generated test reranking")
                            return True
                    except Exception as e:
                        self.logger.error(f"Failed to generate test reranking: {str(e)}")
                        return False
                
                self.logger.info(f"Successfully verified connection to Ollama with model {self.model}")
                return True
        except Exception as e:
            self.logger.error(f"Error verifying connection to Ollama: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the reranker service and release any resources.
        """
        try:
            if self.session and not self.session.closed:
                await self.session.close()
        except Exception as e:
            self.logger.error(f"Error closing Ollama reranker service session: {str(e)}")
        finally:
            self.session = None
            self.initialized = False
            self._initializing = False