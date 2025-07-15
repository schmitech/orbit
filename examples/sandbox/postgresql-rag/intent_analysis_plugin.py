#!/usr/bin/env python3
"""
Intent Analysis Plugin for RAG System
=====================================

This plugin performs structured analysis of user queries to extract intent,
entities, and qualifiers for improved template matching.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from plugin_system import BaseRAGPlugin, PluginContext, PluginPriority

logger = logging.getLogger(__name__)


class IntentAnalysisPlugin(BaseRAGPlugin):
    """Plugin for analyzing user query intent and extracting structured information"""
    
    def __init__(self, inference_client):
        super().__init__("IntentAnalysis", "1.0.0", PluginPriority.HIGH)
        self.inference_client = inference_client
        
        # Define intent categories
        self.intent_categories = {
            "find_list": ["show", "find", "list", "get", "display", "pull up", "bring up"],
            "calculate_summary": ["total", "sum", "calculate", "how much", "lifetime", "summary"],
            "rank_list": ["top", "best", "highest", "most", "biggest", "largest"],
            "search_find": ["search", "look for", "find by", "who has", "customer with"],
            "filter_by": ["filter", "only", "just", "specific", "particular"],
            "compare_data": ["compare", "versus", "vs", "difference"]
        }
        
        # Define entity categories
        self.entity_categories = {
            "customer": ["customer", "client", "buyer", "user", "person"],
            "order": ["order", "purchase", "transaction", "sale", "buy"],
            "amount": ["amount", "total", "value", "price", "cost", "revenue"],
            "status": ["status", "state", "condition", "stage"],
            "payment_method": ["payment", "pay", "method", "credit card", "paypal"],
            "location": ["city", "country", "location", "place", "region"],
            "time": ["date", "time", "period", "when", "recent", "last"]
        }
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Analyze query intent and store structured information in context"""
        if not query or not query.strip():
            return query
        
        try:
            # Perform intent analysis
            intent_analysis = self._analyze_intent(query)
            
            # Store analysis in context metadata
            if context.metadata is None:
                context.metadata = {}
            context.metadata['intent_analysis'] = intent_analysis
            
            logger.debug(f"Intent analysis for '{query}': {intent_analysis}")
            
        except Exception as e:
            logger.error(f"Intent analysis failed for query '{query}': {e}")
            # Don't fail the query, just log the error
        
        return query  # Return original query unchanged
    
    def _analyze_intent(self, query: str) -> Dict[str, Any]:
        """Analyze the intent of a user query"""
        # First try rule-based analysis
        rule_based_analysis = self._rule_based_analysis(query)
        
        # Then enhance with LLM analysis
        llm_analysis = self._llm_analysis(query)
        
        # Merge the analyses
        combined_analysis = self._merge_analyses(rule_based_analysis, llm_analysis)
        
        return combined_analysis
    
    def _rule_based_analysis(self, query: str) -> Dict[str, Any]:
        """Perform rule-based intent analysis"""
        query_lower = query.lower()
        
        # Determine primary intent
        intent = "find_list"  # Default
        for intent_type, keywords in self.intent_categories.items():
            for keyword in keywords:
                if keyword in query_lower:
                    intent = intent_type
                    break
            if intent != "find_list":
                break
        
        # Determine primary entity with better logic
        primary_entity = "order"  # Default
        
        # Check for specific patterns first
        if "customer" in query_lower and any(word in query_lower for word in ["lifetime", "value", "total", "summary"]):
            primary_entity = "customer"
        elif "customer" in query_lower and any(word in query_lower for word in ["order", "buy", "purchase", "transaction"]):
            primary_entity = "order"
        elif "top" in query_lower and "customer" in query_lower:
            primary_entity = "customer"
        elif "payment" in query_lower or "pay" in query_lower:
            primary_entity = "payment_method"
        elif "status" in query_lower or any(status in query_lower for status in ["pending", "delivered", "shipped", "cancelled"]):
            primary_entity = "status"
        elif "amount" in query_lower or "value" in query_lower or "price" in query_lower:
            primary_entity = "amount"
        elif "city" in query_lower or "country" in query_lower or "location" in query_lower:
            primary_entity = "location"
        else:
            # Fallback to keyword matching
            for entity_type, keywords in self.entity_categories.items():
                for keyword in keywords:
                    if keyword in query_lower:
                        primary_entity = entity_type
                        break
                if primary_entity != "order":
                    break
        
        # Extract qualifiers
        qualifiers = []
        if "recent" in query_lower or "last" in query_lower:
            qualifiers.append("recent")
        if "top" in query_lower or "best" in query_lower:
            qualifiers.append("top")
        if "high" in query_lower or "expensive" in query_lower or "over" in query_lower:
            qualifiers.append("high_value")
        if "low" in query_lower or "cheap" in query_lower or "under" in query_lower:
            qualifiers.append("low_value")
        if "specific" in query_lower or "particular" in query_lower:
            qualifiers.append("specific")
        if "international" in query_lower or "abroad" in query_lower:
            qualifiers.append("international")
        if "lifetime" in query_lower or "total" in query_lower:
            qualifiers.append("lifetime")
        if "summary" in query_lower or "overview" in query_lower:
            qualifiers.append("summary")
        
        # Extract mentioned parameters
        mentioned_parameters = self._extract_mentioned_parameters(query)
        
        return {
            "intent": intent,
            "primary_entity": primary_entity,
            "qualifiers": qualifiers,
            "mentioned_parameters": mentioned_parameters,
            "confidence": 0.7  # Medium confidence for rule-based
        }
    
    def _llm_analysis(self, query: str) -> Dict[str, Any]:
        """Perform LLM-based intent analysis"""
        try:
            prompt = self._create_analysis_prompt(query)
            response_text = self.inference_client.generate_response(prompt, temperature=0.1)
            
            # Check if response is empty or error message
            if not response_text or response_text.strip() == "":
                logger.warning("LLM returned empty response")
                raise ValueError("Empty response from LLM")
            
            # Check if response contains error message
            if "error" in response_text.lower() or "sorry" in response_text.lower():
                logger.warning(f"LLM returned error message: {response_text}")
                raise ValueError("LLM returned error message")
            
            # Try to extract JSON from response
            response_text = response_text.strip()
            
            # Remove any markdown formatting
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Parse JSON response
            analysis_result = json.loads(response_text)
            
            # Validate the response structure
            if not isinstance(analysis_result, dict):
                raise ValueError("LLM response is not a valid JSON object")
            
            # Ensure required fields exist with proper defaults
            required_fields = {
                "intent": "find_list",
                "primary_entity": "order", 
                "qualifiers": [],
                "mentioned_parameters": {}
            }
            
            for field, default_value in required_fields.items():
                if field not in analysis_result:
                    analysis_result[field] = default_value
                elif analysis_result[field] is None:
                    analysis_result[field] = default_value
            
            # Validate field types
            if not isinstance(analysis_result["qualifiers"], list):
                analysis_result["qualifiers"] = []
            if not isinstance(analysis_result["mentioned_parameters"], dict):
                analysis_result["mentioned_parameters"] = {}
            
            # Add confidence score
            analysis_result["confidence"] = 0.9  # High confidence for LLM-based
            
            return analysis_result
            
        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}")
            # Return empty analysis on failure
            return {
                "intent": "find_list",
                "primary_entity": "order",
                "qualifiers": [],
                "mentioned_parameters": {},
                "confidence": 0.3  # Low confidence due to failure
            }
    
    def _create_analysis_prompt(self, query: str) -> str:
        """Create the prompt for LLM intent analysis"""
        return f"""Analyze the user's database query and extract the following information.
Respond ONLY with a valid JSON object.

User Query: "{query}"

Available intent categories:
- "find_list": Show me, find, list, get, display items
- "calculate_summary": Total, sum, calculate, how much, lifetime value
- "rank_list": Top, best, highest, most, biggest customers/orders
- "search_find": Search for, find by, who has, customer with
- "filter_by": Filter, only, just, specific, particular criteria
- "compare_data": Compare, versus, difference between

Available entity categories:
- "customer": Customer, client, buyer, user, person
- "order": Order, purchase, transaction, sale, buy
- "amount": Amount, total, value, price, cost, revenue
- "status": Status, state, condition, stage
- "payment_method": Payment, pay, method, credit card, paypal
- "location": City, country, location, place, region
- "time": Date, time, period, when, recent, last

JSON Response Format:
{{
  "intent": "intent_category",
  "primary_entity": "entity_category",
  "qualifiers": ["list", "of", "descriptive", "keywords"],
  "mentioned_parameters": {{
    "parameter_name": "extracted_value"
  }}
}}

Examples:
- "Show me recent orders for customer 123" → {{"intent": "find_list", "primary_entity": "order", "qualifiers": ["recent", "specific_customer"], "mentioned_parameters": {{"customer_id": "123"}}}}
- "What's the total revenue from customer 456" → {{"intent": "calculate_summary", "primary_entity": "customer", "qualifiers": ["total", "revenue"], "mentioned_parameters": {{"customer_id": "456"}}}}
- "Who are our top 10 customers" → {{"intent": "rank_list", "primary_entity": "customer", "qualifiers": ["top", "ranking"], "mentioned_parameters": {{"limit": "10"}}}}

JSON Response:"""
    
    def _extract_mentioned_parameters(self, query: str) -> Dict[str, Any]:
        """Extract mentioned parameters from the query"""
        parameters = {}
        query_lower = query.lower()
        
        # Extract customer ID
        import re
        customer_match = re.search(r'customer\s+(\d+)', query_lower)
        if customer_match:
            parameters["customer_id"] = customer_match.group(1)
        
        # Extract amounts (but avoid customer IDs)
        amount_pattern = r'\$(\d+(?:\.\d{2})?)'  # Only match amounts with $ symbol
        amount_matches = re.findall(amount_pattern, query)
        if amount_matches:
            if "over" in query_lower or "above" in query_lower or "more than" in query_lower:
                parameters["min_amount"] = float(amount_matches[0])
            elif "under" in query_lower or "below" in query_lower or "less than" in query_lower:
                parameters["max_amount"] = float(amount_matches[0])
            elif "between" in query_lower and len(amount_matches) >= 2:
                parameters["min_amount"] = float(amount_matches[0])
                parameters["max_amount"] = float(amount_matches[1])
            else:
                parameters["amount"] = float(amount_matches[0])
        
        # Also extract amounts without $ but only in specific contexts
        if "over" in query_lower or "above" in query_lower or "more than" in query_lower:
            amount_match = re.search(r'(\d+(?:\.\d{2})?)(?:\s*dollars?)?', query_lower)
            if amount_match and "customer" not in query_lower[:amount_match.start()]:
                parameters["min_amount"] = float(amount_match.group(1))
        elif "under" in query_lower or "below" in query_lower or "less than" in query_lower:
            amount_match = re.search(r'(\d+(?:\.\d{2})?)(?:\s*dollars?)?', query_lower)
            if amount_match and "customer" not in query_lower[:amount_match.start()]:
                parameters["max_amount"] = float(amount_match.group(1))
        
        # Extract time periods
        if "last week" in query_lower:
            parameters["days_back"] = 7
        elif "last month" in query_lower:
            parameters["days_back"] = 30
        elif "last year" in query_lower:
            parameters["days_back"] = 365
        elif "yesterday" in query_lower:
            parameters["days_back"] = 1
        elif "today" in query_lower:
            parameters["days_back"] = 0
        
        # Extract limits
        limit_match = re.search(r'top\s+(\d+)', query_lower)
        if limit_match:
            parameters["limit"] = int(limit_match.group(1))
        
        # Extract status
        statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
        for status in statuses:
            if status in query_lower:
                parameters["status"] = status
                break
        
        # Extract payment method
        payment_methods = {
            'credit_card': ['credit card', 'credit'],
            'debit_card': ['debit card', 'debit'],
            'paypal': ['paypal', 'pay pal'],
            'bank_transfer': ['bank transfer', 'bank', 'transfer'],
            'cash': ['cash']
        }
        for method, keywords in payment_methods.items():
            for keyword in keywords:
                if keyword in query_lower:
                    parameters["payment_method"] = method
                    break
            if "payment_method" in parameters:
                break
        
        return parameters
    
    def _merge_analyses(self, rule_based: Dict[str, Any], llm_based: Dict[str, Any]) -> Dict[str, Any]:
        """Merge rule-based and LLM-based analyses"""
        # Use LLM analysis as primary if confidence is high
        if llm_based.get("confidence", 0) > 0.8:
            primary_analysis = llm_based
            secondary_analysis = rule_based
            analysis_method = "llm_primary"
        else:
            primary_analysis = rule_based
            secondary_analysis = llm_based
            analysis_method = "rule_primary"
        
        # Merge qualifiers
        all_qualifiers = list(set(primary_analysis.get("qualifiers", []) + 
                                 secondary_analysis.get("qualifiers", [])))
        
        # Merge mentioned parameters (rule-based takes precedence for parameters)
        all_parameters = rule_based.get("mentioned_parameters", {}).copy()
        llm_parameters = llm_based.get("mentioned_parameters", {})
        
        # Only add LLM parameters if they don't conflict with rule-based
        for key, value in llm_parameters.items():
            if key not in all_parameters or all_parameters[key] is None:
                all_parameters[key] = value
        
        # Use primary analysis for intent and entity
        merged_analysis = {
            "intent": primary_analysis.get("intent", "find_list"),
            "primary_entity": primary_analysis.get("primary_entity", "order"),
            "qualifiers": all_qualifiers,
            "mentioned_parameters": all_parameters,
            "confidence": max(primary_analysis.get("confidence", 0), 
                            secondary_analysis.get("confidence", 0)),
            "analysis_method": analysis_method
        }
        
        return merged_analysis
    
    def validate_template(self, template: Dict, context: PluginContext) -> bool:
        """Validate template using intent analysis"""
        intent_analysis = context.metadata.get('intent_analysis')
        if not intent_analysis:
            return True  # No analysis available, accept template
        
        template_tags = template.get('semantic_tags', {})
        
        # Check if template has semantic tags
        if not template_tags:
            return True  # No semantic tags, accept template
        
        # Check action/intent match
        template_action = template_tags.get('action')
        user_intent = intent_analysis.get('intent')
        
        if template_action and user_intent:
            # Map intents to actions
            intent_to_action = {
                "find_list": "find_list",
                "calculate_summary": "calculate_summary", 
                "rank_list": "rank_list",
                "search_find": "search_find",
                "filter_by": "find_list",
                "compare_data": "find_list"
            }
            
            expected_action = intent_to_action.get(user_intent)
            if expected_action and template_action != expected_action:
                logger.debug(f"Template action '{template_action}' doesn't match user intent '{user_intent}'")
                return False
        
        # Check primary entity match
        template_entity = template_tags.get('primary_entity')
        user_entity = intent_analysis.get('primary_entity')
        
        if template_entity and user_entity and template_entity != user_entity:
            logger.debug(f"Template entity '{template_entity}' doesn't match user entity '{user_entity}'")
            return False
        
        return True 