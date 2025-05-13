"""
Insights Adapter for City Data
==============================

This adapter connects to the QAChromaRetriever and InsightsEngine to provide 
enhanced responses that include analytical insights based on metadata fields.
The LLM will generate answers directly from metadata.

Usage:
    from utils.insights_adapter import InsightsAdapter
    
    # Initialize the adapter
    adapter = InsightsAdapter(config)
    await adapter.initialize()
    
    # Use in conjuction with a retriever
    context_items = await retriever.get_relevant_context(query)
    enhanced_response = await adapter.generate_insights_response(context_items, query)
"""

import logging
import json
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class InsightsAdapter:
    """Adapter that enhances QA retrieval with analytical insights from metadata."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the InsightsAdapter.
        
        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self.insights_engine = None
        self.llm_service = None
    
    async def initialize(self) -> bool:
        """Initialize required services."""
        try:
            # Import only when needed to avoid circular imports
            from utils.insights_engine import InsightsEngine
            from llm.base import LLMServiceFactory
            
            # Initialize insights engine
            self.insights_engine = InsightsEngine(self.config)
            engine_init = await self.insights_engine.initialize()
            
            # Get LLM configuration
            llm_provider = self.config.get('inference', {}).get('provider', 'ollama')
            
            # Create LLM service for final response generation
            self.llm_service = LLMServiceFactory.create_llm_service(self.config, llm_provider)
            llm_init = await self.llm_service.initialize()
            
            logger.info(f"InsightsAdapter initialized successfully")
            return engine_init and llm_init
        except Exception as e:
            logger.error(f"Failed to initialize InsightsAdapter: {str(e)}")
            return False
    
    async def close(self) -> None:
        """Close any open services."""
        if self.insights_engine:
            await self.insights_engine.close()
        if self.llm_service:
            await self.llm_service.close()
    
    async def generate_insights_response(self, 
                                  context_items: List[Dict[str, Any]], 
                                  query: str) -> Dict[str, Any]:
        """
        Generate a response with analytical insights based on the context items.
        
        Args:
            context_items: List of context items from the retriever
            query: The original user query
            
        Returns:
            Dictionary containing the enhanced response with insights
        """
        if not context_items:
            return {"answer": "I don't have enough information to answer that question."}
        
        # Generate insights directly from the context items and metadata
        # This will now contain both the answer and insights
        insights_result = await self.insights_engine.generate_insights(context_items, query)
        
        # If insights generation failed, return an error
        if insights_result.get("insights") is None:
            return {"answer": "I couldn't find a specific answer to your question."}
        
        # Return the complete response that includes both the answer and insights
        return {
            "answer": insights_result.get("insights", ""),
            "supporting_data": insights_result.get("supporting_data")
        }
    
    def extract_department_insights(self, context_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract department-specific insights from context items.
        
        Args:
            context_items: List of context items from the retriever
            
        Returns:
            Dictionary with department statistics
        """
        departments = {}
        
        for item in context_items:
            metadata = item.get("metadata", {})
            dept = metadata.get("department")
            
            if not dept:
                continue
                
            if dept not in departments:
                departments[dept] = {
                    "count": 0,
                    "avg_response_time": None,
                    "total_costs": 0,
                    "services": []
                }
            
            departments[dept]["count"] += 1
            departments[dept]["services"].append(metadata.get("question", ""))
            
            # Process response time
            if "response_time" in metadata:
                try:
                    response_time = float(metadata["response_time"])
                    if departments[dept]["avg_response_time"] is None:
                        departments[dept]["avg_response_time"] = response_time
                    else:
                        # Update running average
                        current_avg = departments[dept]["avg_response_time"]
                        current_count = departments[dept]["count"] - 1
                        departments[dept]["avg_response_time"] = (current_avg * current_count + response_time) / departments[dept]["count"]
                except (ValueError, TypeError):
                    pass
            
            # Process costs
            if "cost" in metadata:
                try:
                    # Extract numeric value from cost string (e.g., "$25" -> 25)
                    cost_str = metadata["cost"]
                    cost_value = float(re.sub(r'[^\d.]', '', cost_str))
                    departments[dept]["total_costs"] += cost_value
                except (ValueError, TypeError):
                    pass
        
        return departments
    
    def calculate_budget_allocation(self, context_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate budget allocation insights from context items.
        
        Args:
            context_items: List of context items from the retriever
            
        Returns:
            Dictionary with budget allocation insights
        """
        # Extract department budgets or costs
        department_data = {}
        total_budget = 0
        budget_items = 0
        
        for item in context_items:
            metadata = item.get("metadata", {})
            dept = metadata.get("department")
            
            if not dept:
                continue
                
            if dept not in department_data:
                department_data[dept] = {
                    "budget": 0,
                    "revenue": 0,
                    "costs": []
                }
            
            # Process budget amount
            if "budget_amount" in metadata:
                try:
                    # Extract numeric value from budget string
                    budget_str = metadata["budget_amount"]
                    budget_value = float(re.sub(r'[^\d.]', '', budget_str))
                    department_data[dept]["budget"] = budget_value
                    total_budget += budget_value
                    budget_items += 1
                except (ValueError, TypeError):
                    pass
            
            # Process revenue
            if "annual_revenue" in metadata:
                try:
                    revenue_str = metadata["annual_revenue"]
                    revenue_value = float(re.sub(r'[^\d.]', '', revenue_str))
                    department_data[dept]["revenue"] += revenue_value
                except (ValueError, TypeError):
                    pass
            
            # Process service costs
            if "service_cost" in metadata:
                try:
                    cost_str = metadata["service_cost"]
                    cost_value = float(re.sub(r'[^\d.]', '', cost_str))
                    department_data[dept]["costs"].append({
                        "service": metadata.get("question", ""),
                        "cost": cost_value
                    })
                except (ValueError, TypeError):
                    pass
        
        return {
            "department_data": department_data,
            "total_budget": total_budget,
            "departments_with_budget": budget_items
        }
    
    def analyze_service_metrics(self, context_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze service metrics from context items.
        
        Args:
            context_items: List of context items from the retriever
            
        Returns:
            Dictionary with service metrics insights
        """
        metrics = {
            "online_services": [],
            "avg_response_time": 0,
            "response_time_count": 0,
            "seasonal_services": {},
            "high_priority_services": []
        }
        
        for item in context_items:
            metadata = item.get("metadata", {})
            
            # Track online services
            if "online_completion_rate" in metadata:
                try:
                    completion_rate = float(metadata["online_completion_rate"])
                    if completion_rate > 0:
                        metrics["online_services"].append({
                            "service": metadata.get("question", ""),
                            "completion_rate": completion_rate,
                            "department": metadata.get("department", "")
                        })
                except (ValueError, TypeError):
                    pass
            
            # Track response times
            if "response_time" in metadata:
                try:
                    response_time = float(metadata["response_time"])
                    metrics["avg_response_time"] = (metrics["avg_response_time"] * metrics["response_time_count"] + response_time) / (metrics["response_time_count"] + 1)
                    metrics["response_time_count"] += 1
                except (ValueError, TypeError):
                    pass
            
            # Track seasonal services
            if "timeframe" in metadata:
                timeframe = metadata["timeframe"]
                if timeframe not in ["annual", "monthly", "as needed"]:
                    if timeframe not in metrics["seasonal_services"]:
                        metrics["seasonal_services"][timeframe] = []
                    metrics["seasonal_services"][timeframe].append(metadata.get("question", ""))
            
            # Track high priority services
            if metadata.get("priority") == "high":
                metrics["high_priority_services"].append({
                    "service": metadata.get("question", ""),
                    "department": metadata.get("department", ""),
                    "response_time": metadata.get("response_time", "unknown")
                })
        
        return metrics 