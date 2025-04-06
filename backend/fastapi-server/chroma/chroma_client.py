"""
ChromaDB client for retrieving relevant documents
"""

import asyncio
import logging
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool for blocking I/O operations
thread_pool = ThreadPoolExecutor(max_workers=10)


class ChromaRetriever:
    """Handles retrieval of relevant documents from ChromaDB"""
    
    def __init__(self, collection, embeddings, config):
        self.collection = collection
        self.embeddings = embeddings
        self.config = config
        
        self.confidence_threshold = float(config['chroma'].get('confidence_threshold', 0.85))
        self.relevance_threshold = float(config['chroma'].get('relevance_threshold', self.confidence_threshold - 0.15))
        
        logger.info(f"ChromaRetriever initialized with confidence threshold: {self.confidence_threshold}, relevance threshold: {self.relevance_threshold}")
    
    async def get_relevant_context(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant context for a query"""
        try:
            loop = asyncio.get_running_loop()
            query_embedding = await loop.run_in_executor(thread_pool, self.embeddings.embed_query, query)
            
            results = await loop.run_in_executor(
                thread_pool,
                lambda: self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"]
                )
            )
            
            formatted_results = []
            metadatas = results.get('metadatas', [])
            documents = results.get('documents', [])
            distances = results.get('distances', [])
            
            if metadatas and metadatas[0]:
                query_lower = query.lower()
                query_terms = [term for term in query_lower.split() if len(term) > 3]
                for doc, metadata, distance in zip(documents[0], metadatas[0], distances[0]):
                    similarity = 1 - distance
                    if 'question' in metadata and 'answer' in metadata:
                        score = similarity
                        question_text = metadata.get('question', '').lower()
                        answer_text = metadata.get('answer', '').lower()
                        for term in query_terms:
                            if term in question_text:
                                score += 0.05
                            if term in answer_text:
                                score += 0.03
                        formatted_results.append({
                            "question": metadata['question'],
                            "answer": metadata['answer'],
                            "similarity": similarity,
                            "score": score,
                            "confidence": similarity  # For direct answer checks
                        })
                    else:
                        score = similarity
                        content = doc.lower()
                        for term in query_terms:
                            if term in content:
                                score += 0.02
                        formatted_results.append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity": similarity,
                            "score": score
                        })
            
            formatted_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            filtered_results = [r for r in formatted_results if r["similarity"] >= self.relevance_threshold]
            return filtered_results
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}", exc_info=True)
            return []
    
    def get_direct_answer(self, results: List[Dict[str, Any]]):
        """Check if we have a high-confidence direct answer from metadata"""
        if not results:
            return None
        
        best_match = results[0]
        if 'question' in best_match and 'answer' in best_match and 'confidence' in best_match:
            if best_match['confidence'] >= self.confidence_threshold:
                return best_match['answer']
        
        return None
