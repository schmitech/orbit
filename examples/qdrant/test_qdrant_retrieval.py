#!/usr/bin/env python3
"""
Debug script to test Qdrant retrieval and understand why responses say "I don't have enough information"
even when matching records are found.
"""

import asyncio
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import sys
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the server directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'server'))

async def check_qdrant_data():
    """Check what data exists in Qdrant and test retrieval"""
    
    # Connect to Qdrant
    client = QdrantClient(host="99.79.49.135", port=6333)
    
    # Check collection info
    try:
        collection_info = client.get_collection("csed")
        logger.info(f"Collection 'csed' info:")
        logger.info(f"  - Points count: {collection_info.points_count}")
        logger.info(f"  - Vector size: {collection_info.config.params.vectors.size}")
        logger.info(f"  - Distance metric: {collection_info.config.params.vectors.distance}")
    except Exception as e:
        logger.error(f"Error getting collection info: {e}")
        return
    
    # Retrieve some sample points to see what's in the collection
    try:
        # Scroll through some points to see the data
        points = client.scroll(
            collection_name="csed",
            limit=10,
            with_payload=True,
            with_vectors=False
        )
        
        logger.info("\n=== Sample points from collection ===")
        for i, point in enumerate(points[0]):
            logger.info(f"\nPoint {i+1}:")
            payload = point.payload
            if 'question' in payload:
                logger.info(f"  Question: {payload.get('question', 'N/A')}")
            if 'answer' in payload:
                logger.info(f"  Answer: {payload.get('answer', 'N/A')[:200]}...")
            if 'content' in payload:
                logger.info(f"  Content: {payload.get('content', 'N/A')[:200]}...")
            logger.info(f"  Other fields: {list(payload.keys())}")
            
    except Exception as e:
        logger.error(f"Error scrolling points: {e}")
    
    # Now test a search for directory-related content
    logger.info("\n=== Testing search for 'directory' related content ===")
    
    # We need to create an embedding for the search query
    # For this test, we'll use a simple vector search with a random vector
    # In production, this would be the actual embedding of the query
    
    try:
        # Import the actual system to get embeddings
        from services.embeddings_service import EmbeddingsService
        import yaml
        
        # Load config
        with open('config/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Create embeddings service
        embeddings_service = EmbeddingsService(config)
        await embeddings_service.initialize()
        
        # Test queries
        test_queries = [
            "How to add to the CSED Directory?",
            "CSED Directory",
            "add to directory",
            "directory submission",
            "register business directory"
        ]
        
        for query in test_queries:
            logger.info(f"\n--- Searching for: '{query}' ---")
            
            # Generate embedding
            query_embedding = await embeddings_service.embed_query(query)
            
            if query_embedding:
                # Search Qdrant
                results = client.search(
                    collection_name="csed",
                    query_vector=query_embedding,
                    limit=5,
                    with_payload=True
                )
                
                for j, result in enumerate(results):
                    logger.info(f"\nResult {j+1}:")
                    logger.info(f"  Score: {result.score:.4f}")
                    logger.info(f"  Scaled score (x200): {result.score * 200:.2f}")
                    payload = result.payload
                    if 'question' in payload:
                        logger.info(f"  Question: {payload.get('question', 'N/A')}")
                    if 'answer' in payload:
                        logger.info(f"  Answer: {payload.get('answer', 'N/A')[:200]}...")
                    if 'content' in payload:
                        logger.info(f"  Content: {payload.get('content', 'N/A')[:200]}...")
            else:
                logger.error(f"Failed to generate embedding for query: {query}")
                
    except ImportError as e:
        logger.warning(f"Could not import embeddings service: {e}")
        logger.info("Performing basic search without actual embeddings...")
        
        # Do a basic filter search instead
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            # Search for any points that might contain "directory" in their text
            filter_results = client.scroll(
                collection_name="csed",
                limit=100,
                with_payload=True,
                with_vectors=False
            )
            
            directory_related = []
            for point in filter_results[0]:
                payload = point.payload
                # Check if any field contains "directory"
                for key, value in payload.items():
                    if isinstance(value, str) and 'directory' in value.lower():
                        directory_related.append(point)
                        break
            
            logger.info(f"\n=== Found {len(directory_related)} points containing 'directory' ===")
            for point in directory_related[:5]:  # Show first 5
                payload = point.payload
                logger.info(f"\nPoint ID: {point.id}")
                if 'question' in payload:
                    logger.info(f"  Question: {payload.get('question', 'N/A')}")
                if 'answer' in payload:
                    logger.info(f"  Answer: {payload.get('answer', 'N/A')[:200]}...")
                    
        except Exception as e:
            logger.error(f"Error performing filter search: {e}")

if __name__ == "__main__":
    asyncio.run(check_qdrant_data())