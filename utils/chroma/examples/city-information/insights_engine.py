"""
Insights Engine for City Data
=============================

This service takes retrieval results from the QA Chroma retriever and performs
analytical reasoning based on the metadata fields to provide additional insights.
The LLM will generate answers using this metadata.

Usage:
    from utils.insights_engine import InsightsEngine
    
    # Initialize the engine
    engine = InsightsEngine()
    
    # Generate insights from context items
    insights = await engine.generate_insights(context_items, query)
"""

import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class InsightsEngine:
    """Generates analytical insights from context items with metadata."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the InsightsEngine.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.llm_service = None  # Will be initialized lazily
    
    async def initialize(self) -> bool:
        """Initialize required services."""
        try:
            # Import here to avoid circular imports
            from llm.base import LLMServiceFactory
            
            # Get LLM configuration - this assumes your config follows the pattern in your codebase
            llm_provider = self.config.get('inference', {}).get('provider', 'ollama')
            
            # Create LLM service
            self.llm_service = LLMServiceFactory.create_llm_service(self.config, llm_provider)
            await self.llm_service.initialize()
            
            logger.info(f"InsightsEngine initialized with {llm_provider} LLM service")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize InsightsEngine: {str(e)}")
            return False
    
    async def close(self) -> None:
        """Close any open services."""
        if self.llm_service:
            await self.llm_service.close()
    
    async def generate_insights(self, 
                         context_items: List[Dict[str, Any]], 
                         query: str) -> Dict[str, Any]:
        """
        Generate insights based on context items and their metadata.
        
        Args:
            context_items: List of context items from QAChromaRetriever
            query: The original user query
            
        Returns:
            Dictionary containing insights and supporting data
        """
        if not context_items:
            return {"insights": None, "reason": "No context items available"}
        
        # Extract metadata from context items
        metadata_list = []
        for item in context_items:
            if "metadata" in item and isinstance(item["metadata"], dict):
                # Extract the metadata fields
                extracted = {
                    "question": item.get("metadata", {}).get("question", ""),
                    "confidence": item.get("confidence", 0),
                }
                
                # Add all metadata fields except internal ones
                for key, value in item.get("metadata", {}).items():
                    if key not in ["question", "source", "original_id"]:
                        extracted[key] = value
                
                metadata_list.append(extracted)
        
        # If no usable metadata, return early
        if not metadata_list:
            return {"insights": None, "reason": "No usable metadata found"}
        
        # Prepare a prompt for the LLM to reason over the data
        system_prompt = """You are an analytical assistant that provides insights and answers based on city data.
You need to both:
1. Generate a direct answer to the user's question
2. Provide insightful observations, calculations, or connections based on the metadata

Focus on numerical trends, comparisons across departments, timeline analysis, or budget implications.
If the metadata contains financial information, perform relevant calculations.
If temporal data is present, analyze seasonal patterns or year-over-year changes.
If resource allocation data exists, suggest optimization opportunities.
Your response should be concise, data-driven, and directly relevant to the user's question."""
        
        # Format the metadata in a structured way for the LLM
        metadata_formatted = json.dumps(metadata_list, indent=2)
        
        user_prompt = f"""User question: {query}

Retrieved information and metadata:
{metadata_formatted}

First, provide a direct answer to the user's question based on the metadata.
Then, provide analytical insights that go beyond the direct answer.
Include any relevant calculations, comparisons, or patterns you observe in the data.
"""
        
        try:
            # Call the LLM to generate insights
            response = await self.llm_service.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,  # Low temperature for analytical reasoning
                max_tokens=500
            )
            
            # Return the generated insights along with the supporting data
            return {
                "insights": response,
                "supporting_data": metadata_list,
                "query": query
            }
        except Exception as e:
            logger.error(f"Error generating insights: {str(e)}")
            return {"insights": None, "reason": f"Error: {str(e)}"}

    @staticmethod
    def extract_metadata(context_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract metadata from context items for analysis.
        This is a utility method that can be used separately from generate_insights.
        
        Args:
            context_items: List of context items from QAChromaRetriever
            
        Returns:
            Dictionary with processed metadata ready for analysis
        """
        result = {
            "departments": {},
            "costs": [],
            "timeframes": [],
            "locations": []
        }
        
        for item in context_items:
            metadata = item.get("metadata", {})
            
            # Track department-specific information
            if dept := metadata.get("department"):
                if dept not in result["departments"]:
                    result["departments"][dept] = {
                        "count": 0,
                        "costs": [],
                        "avg_response_time": []
                    }
                result["departments"][dept]["count"] += 1
                
                if cost := metadata.get("cost"):
                    try:
                        cost_value = float(cost.replace("$", "").replace(",", ""))
                        result["departments"][dept]["costs"].append(cost_value)
                        result["costs"].append(cost_value)
                    except (ValueError, TypeError):
                        pass
                        
                if time := metadata.get("response_time"):
                    try:
                        time_value = float(time)
                        result["departments"][dept]["avg_response_time"].append(time_value)
                    except (ValueError, TypeError):
                        pass
            
            # Track location data
            if location := metadata.get("location"):
                result["locations"].append(location)
                
            # Track timeframe data
            if timeframe := metadata.get("timeframe"):
                result["timeframes"].append(timeframe)
        
        return result 