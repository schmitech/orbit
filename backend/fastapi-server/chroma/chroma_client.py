"""
ChromaDB client for retrieving relevant documents
"""

import asyncio
import logging
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logger = logging.getLogger(__name__)

# Thread pool for blocking I/O operations
thread_pool = ThreadPoolExecutor(max_workers=10)


class ChromaRetriever:
    """Handles retrieval of relevant documents from ChromaDB"""
    
    def __init__(self, collection, embeddings, config):
        self.collection = collection
        self.embeddings = embeddings
        self.config = config
        
        # Use thresholds from config or fall back to defaults
        self.confidence_threshold = float(config['chroma'].get('confidence_threshold', 0.85))
        
        # If relevance_threshold exists in config, use it directly
        if 'relevance_threshold' in config['chroma']:
            self.relevance_threshold = float(config['chroma']['relevance_threshold'])
        else:
            # Otherwise, calculate it based on confidence_threshold
            self.relevance_threshold = self.confidence_threshold - 0.15
        
        logger.info(f"ChromaRetriever initialized with confidence threshold: {self.confidence_threshold}, relevance threshold: {self.relevance_threshold}")
    
    async def get_relevant_context(self, query: str, n_results: int = 5):
        """Retrieve relevant context for a query"""
        try:
            # Generate embedding for query using thread pool to avoid blocking
            query_embedding = await asyncio.get_event_loop().run_in_executor(
                thread_pool, 
                self.embeddings.embed_query, 
                query
            )
            
            # Query the collection in thread pool
            results = await asyncio.get_event_loop().run_in_executor(
                thread_pool,
                lambda: self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"]
                )
            )
            
            # Format results
            formatted_results = []
            if results['metadatas'] and len(results['metadatas'][0]) > 0:
                for i, (doc, metadata, distance) in enumerate(zip(
                    results['documents'][0], 
                    results['metadatas'][0],
                    results['distances'][0]
                )):
                    similarity = 1 - distance
                    
                    if 'question' in metadata and 'answer' in metadata:
                        # Calculate relevance score with keyword matching
                        score = similarity
                        query_terms = query.lower().split()
                        question_text = metadata.get('question', '').lower()
                        answer_text = metadata.get('answer', '').lower()
                        
                        # Boost score for term matches
                        for term in query_terms:
                            if len(term) > 3:  # Only consider significant terms
                                if term in question_text:
                                    score += 0.05  # Boost for question matches
                                if term in answer_text:
                                    score += 0.03  # Smaller boost for answer matches
                        
                        formatted_results.append({
                            "question": metadata['question'],
                            "answer": metadata['answer'],
                            "similarity": similarity,
                            "score": score,
                            "confidence": similarity  # For direct answer checks
                        })
                    else:
                        # Calculate score for general content
                        score = similarity
                        query_terms = query.lower().split()
                        content = doc.lower()
                        
                        # Boost score for content matches
                        for term in query_terms:
                            if len(term) > 3 and term in content:
                                score += 0.02
                        
                        formatted_results.append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity": similarity,
                            "score": score
                        })
            
            # Sort by calculated score (most relevant first)
            formatted_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            # Filter by threshold
            formatted_results = [r for r in formatted_results if r["similarity"] >= self.relevance_threshold]
            
            return formatted_results
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []
    
    def get_direct_answer(self, results):
        """Check if we have a high-confidence direct answer from metadata"""
        if not results:
            return None
        
        best_match = results[0]
        if 'question' in best_match and 'answer' in best_match and 'confidence' in best_match:
            confidence = best_match['confidence']
            if confidence >= self.confidence_threshold:
                return best_match['answer']
        
        return None