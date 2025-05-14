"""
City Insights Demo
=================

This script demonstrates how to use the enhanced QA system that provides analytical insights
based on city service metadata, with LLM-generated answers.

It performs the following steps:
1. Loads the configuration
2. Initializes the QA Chrome Retriever with the enhanced collection
3. Initializes the Insights Adapter
4. Processes sample queries and displays LLM-generated responses with insights

Usage:
    python city_insights_demo.py [--local] [--collection COLLECTION_NAME]

Example output for a query about parking permits:
    LLM GENERATED ANSWER WITH INSIGHTS:
    The residential parking permit fee is $25 per year through the Transportation
    Department. This service has a popularity rating of 8.5/10, making it one of the most requested
    city services. When compared to other annual permits, the parking permit is one of the more
    affordable options, as similar permits range from $5 to $250 per year. The Transportation
    Department processes approximately 12,000 parking permits annually, generating $300,000 in
    revenue which helps fund road maintenance and traffic management.
"""

import argparse
import asyncio
import logging
import os
import yaml
import sys
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CityInsightsDemo")

# Add necessary paths for imports
project_root = Path(__file__).resolve().parents[1]
server_path = project_root / "server"
sys.path.append(str(project_root))
sys.path.append(str(server_path))

def load_config():
    """Load configuration from the config file"""
    config_path = server_path / "config.yaml"
    return yaml.safe_load(config_path.read_text())

async def run_demo(collection_name, use_local=False, db_path="./chroma_db"):
    """Run the city insights demo"""
    try:
        # Load the configuration
        config = load_config()
        logger.info("Configuration loaded")
        
        # Override Chroma settings if using local database
        if use_local:
            config["datasources"] = config.get("datasources", {})
            config["datasources"]["chroma"] = {
                "use_local": True,
                "db_path": db_path
            }
        
        # Import the retriever and adapter classes
        from server.retrievers.implementations.qa_chroma_retriever import QAChromaRetriever
        from utils.insights_adapter import InsightsAdapter
        
        # Initialize the retriever
        logger.info(f"Initializing QAChromaRetriever with collection: {collection_name}")
        retriever = QAChromaRetriever(config=config)
        await retriever.initialize()
        await retriever.set_collection(collection_name)
        
        # Initialize the insights adapter
        logger.info("Initializing InsightsAdapter")
        adapter = InsightsAdapter(config=config)
        await adapter.initialize()
        
        # Define sample queries that would benefit from insights
        sample_queries = [
            "What is the fee for a residential parking permit?",
            "How can I pay my water bill online?",
            "Where can I find the city's annual budget?",
            "What are the requirements for a food truck license?",
            "How do I report a pothole on my street?",
            "How can I volunteer for city beautification projects?"
        ]
        
        # Process each query
        for query in sample_queries:
            logger.info(f"\n\n=========== QUERY: {query} ===========")
            
            # Get relevant context from the retriever
            context_items = await retriever.get_relevant_context(query, collection_name=collection_name)
            logger.info(f"Retrieved {len(context_items)} context items")
            
            if not context_items:
                logger.warning("No relevant context found for query")
                continue
            
            # Get metadata fields from the top result for display
            sorted_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)
            top_metadata = sorted_items[0].get("metadata", {})
            
            # Generate response with insights
            response_result = await adapter.generate_insights_response(context_items, query)
            
            # Display the LLM-generated answer
            print("\n" + "=" * 80)
            print(f"QUERY: {query}\n")
            
            # Display metadata fields for reference
            print("METADATA FROM TOP RESULT:")
            for key, value in top_metadata.items():
                if key not in ["question", "source", "original_id"]:
                    print(f"  {key}: {value}")
            print()
            
            # Display the LLM-generated answer with insights
            print("LLM-GENERATED ANSWER WITH INSIGHTS:")
            print(response_result.get("answer", "No answer available"))
            print("=" * 80 + "\n")
            
            # Pause between queries for readability
            await asyncio.sleep(1)
        
        # Clean up
        await retriever.close()
        await adapter.close()
        logger.info("Demo completed successfully")
    
    except Exception as e:
        logger.error(f"Error running demo: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

async def main():
    """Main function to parse arguments and run demo"""
    parser = argparse.ArgumentParser(description="Demonstrate city insights capabilities")
    parser.add_argument("--local", action="store_true", help="Use local filesystem Chroma database")
    parser.add_argument("--collection", type=str, default="city_qa_enhanced", help="Name of the Chroma collection to query")
    parser.add_argument("--db-path", type=str, default="./chroma_db", help="Path to local Chroma database")
    
    args = parser.parse_args()
    
    await run_demo(
        collection_name=args.collection,
        use_local=args.local,
        db_path=args.db_path
    )

if __name__ == "__main__":
    asyncio.run(main()) 