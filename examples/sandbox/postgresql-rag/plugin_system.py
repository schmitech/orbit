#!/usr/bin/env python3
"""
Plugin System for RAG Architecture
==================================

This module provides a plugin architecture for extending RAG system functionality
with pre-processing, post-processing, and response enhancement capabilities.
"""

import logging
from typing import Protocol, runtime_checkable, Dict, List, Any, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PluginPriority(Enum):
    """Plugin execution priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class PluginContext:
    """Context information passed to plugins"""
    user_query: str
    template_id: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    similarity_score: Optional[float] = None
    execution_time_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


@runtime_checkable
class RAGPlugin(Protocol):
    """Plugin interface for extending RAG functionality"""
    
    def get_name(self) -> str:
        """Return the plugin name"""
        ...
    
    def get_version(self) -> str:
        """Return the plugin version"""
        ...
    
    def get_priority(self) -> PluginPriority:
        """Return the plugin execution priority"""
        ...
    
    def is_enabled(self) -> bool:
        """Check if the plugin is enabled"""
        ...
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Modify query before processing"""
        ...
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Transform results after query execution"""
        ...
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Enhance the generated response"""
        ...
    
    def validate_template(self, template: Dict, context: PluginContext) -> bool:
        """Validate if a template should be used"""
        ...
    
    def extract_parameters(self, query: str, template: Dict, context: PluginContext) -> Dict[str, Any]:
        """Extract or modify parameters"""
        ...


class BaseRAGPlugin(ABC):
    """Base class for RAG plugins with default implementations"""
    
    def __init__(self, name: str, version: str = "1.0.0", priority: PluginPriority = PluginPriority.NORMAL):
        self._name = name
        self._version = version
        self._priority = priority
        self._enabled = True
    
    def get_name(self) -> str:
        return self._name
    
    def get_version(self) -> str:
        return self._version
    
    def get_priority(self) -> PluginPriority:
        return self._priority
    
    def is_enabled(self) -> bool:
        return self._enabled
    
    def enable(self):
        """Enable the plugin"""
        self._enabled = True
        logger.info(f"Plugin {self._name} enabled")
    
    def disable(self):
        """Disable the plugin"""
        self._enabled = False
        logger.info(f"Plugin {self._name} disabled")
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Default implementation - return query unchanged"""
        return query
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Default implementation - return results unchanged"""
        return results
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Default implementation - return response unchanged"""
        return response
    
    def validate_template(self, template: Dict, context: PluginContext) -> bool:
        """Default implementation - always return True"""
        return True
    
    def extract_parameters(self, query: str, template: Dict, context: PluginContext) -> Dict[str, Any]:
        """Default implementation - return empty dict"""
        return {}


class QueryNormalizationPlugin(BaseRAGPlugin):
    """Plugin for normalizing and cleaning user queries"""
    
    def __init__(self):
        super().__init__("QueryNormalization", "1.0.0", PluginPriority.HIGH)
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Normalize query text"""
        if not query:
            return query
        
        # Remove extra whitespace
        normalized = " ".join(query.split())
        
        # Convert to lowercase for better matching
        normalized = normalized.lower()
        
        # Remove common punctuation that might interfere with matching
        import re
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = " ".join(normalized.split())
        
        logger.debug(f"Query normalized: '{query}' -> '{normalized}'")
        return normalized





class ResultFilteringPlugin(BaseRAGPlugin):
    """Plugin for filtering and sorting results"""
    
    def __init__(self, max_results: int = 100):
        super().__init__("ResultFiltering", "1.0.0", PluginPriority.NORMAL)
        self.max_results = max_results
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Filter and limit results"""
        if not results:
            return results
        
        # Limit number of results
        if len(results) > self.max_results:
            results = results[:self.max_results]
            logger.info(f"Limited results to {self.max_results} records")
        
        return results


class DataEnrichmentPlugin(BaseRAGPlugin):
    """Plugin for enriching result data with additional information"""
    
    def __init__(self):
        super().__init__("DataEnrichment", "1.0.0", PluginPriority.LOW)
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Enrich results with additional computed fields"""
        if not results:
            return results
        
        enriched_results = []
        for result in results:
            enriched = result.copy()
            
            # Add computed fields
            if 'total' in result and isinstance(result['total'], (int, float)):
                enriched['total_formatted'] = f"${result['total']:,.2f}"
            
            if 'order_date' in result:
                enriched['days_ago'] = self._calculate_days_ago(result['order_date'])
            
            if 'status' in result:
                enriched['status_icon'] = self._get_status_icon(result['status'])
            
            enriched_results.append(enriched)
        
        return enriched_results
    
    def _calculate_days_ago(self, order_date) -> Optional[int]:
        """Calculate days since order date"""
        try:
            from datetime import datetime
            if isinstance(order_date, str):
                order_date = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
            days_ago = (datetime.now() - order_date).days
            return max(0, days_ago)
        except:
            return None
    
    def _get_status_icon(self, status: str) -> str:
        """Get status icon based on status"""
        icons = {
            'pending': '⏳',
            'processing': '🔄',
            'shipped': '📦',
            'delivered': '✅',
            'cancelled': '❌'
        }
        return icons.get(status.lower(), '❓')


class ResponseEnhancementPlugin(BaseRAGPlugin):
    """Plugin for enhancing generated responses"""
    
    def __init__(self):
        super().__init__("ResponseEnhancement", "1.0.0", PluginPriority.LOW)
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Enhance response with additional context and formatting"""
        if not response:
            return response
        
        enhanced = response
        
        # Add execution time if available
        if context.execution_time_ms:
            enhanced += f"\n\n⏱️ Query executed in {context.execution_time_ms:.2f}ms"
        
        # Add confidence score if available
        if context.similarity_score:
            confidence = "High" if context.similarity_score > 0.8 else "Medium" if context.similarity_score > 0.6 else "Low"
            enhanced += f"\n🎯 Confidence: {confidence} ({context.similarity_score:.1%})"
        
        # Add template info if available
        if context.template_id:
            enhanced += f"\n📋 Template: {context.template_id}"
        
        return enhanced


class SecurityPlugin(BaseRAGPlugin):
    """Plugin for security validation and sanitization"""
    
    def __init__(self):
        super().__init__("Security", "1.0.0", PluginPriority.CRITICAL)
        self.blocked_patterns = [
            r'DROP\s+TABLE',
            r'DELETE\s+FROM',
            r'UPDATE\s+.*\s+SET',
            r'INSERT\s+INTO',
            r'CREATE\s+TABLE',
            r'ALTER\s+TABLE',
            r'EXEC\s*\(',
            r'xp_cmdshell',
            r'UNION\s+SELECT',
            r'OR\s+1\s*=\s*1',
            r'--',
            r'/\*.*\*/'
        ]
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Check for potentially malicious patterns"""
        import re
        
        query_upper = query.upper()
        for pattern in self.blocked_patterns:
            if re.search(pattern, query_upper, re.IGNORECASE):
                logger.warning(f"Blocked potentially malicious query: {query}")
                raise ValueError(f"Query contains blocked pattern: {pattern}")
        
        return query
    
    def validate_template(self, template: Dict, context: PluginContext) -> bool:
        """Validate template for security"""
        # Check if template is approved
        if not template.get('approved', False):
            logger.warning(f"Blocked unapproved template: {template.get('id', 'unknown')}")
            return False
        
        # Check for dangerous SQL patterns
        sql_template = template.get('sql_template', '')
        sql_upper = sql_template.upper()
        
        dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'CREATE', 'ALTER', 'EXEC']
        for keyword in dangerous_keywords:
            if keyword in sql_upper and 'WHERE' not in sql_upper:
                logger.warning(f"Template contains dangerous keyword without WHERE: {template.get('id', 'unknown')}")
                return False
        
        return True


class LoggingPlugin(BaseRAGPlugin):
    """Plugin for comprehensive logging and monitoring"""
    
    def __init__(self):
        super().__init__("Logging", "1.0.0", PluginPriority.LOW)
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Log query processing"""
        logger.info(f"Processing query: '{query}'")
        return query
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Log result processing"""
        logger.info(f"Processed {len(results)} results for template {context.template_id}")
        return results
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Log response generation"""
        logger.info(f"Generated response for template {context.template_id}")
        return response


class PluginManager:
    """Manager for registering and executing plugins"""
    
    def __init__(self):
        self.plugins: List[RAGPlugin] = []
        self.plugin_registry: Dict[str, RAGPlugin] = {}
    
    def register_plugin(self, plugin: RAGPlugin):
        """Register a plugin"""
        if not isinstance(plugin, RAGPlugin):
            raise ValueError(f"Plugin must implement RAGPlugin protocol: {type(plugin)}")
        
        plugin_name = plugin.get_name()
        if plugin_name in self.plugin_registry:
            logger.warning(f"Plugin {plugin_name} already registered, replacing")
        
        self.plugin_registry[plugin_name] = plugin
        self.plugins.append(plugin)
        
        # Sort plugins by priority (highest first)
        self.plugins.sort(key=lambda p: p.get_priority().value, reverse=True)
        
        logger.info(f"Registered plugin: {plugin_name} v{plugin.get_version()}")
    
    def unregister_plugin(self, plugin_name: str):
        """Unregister a plugin by name"""
        if plugin_name in self.plugin_registry:
            plugin = self.plugin_registry[plugin_name]
            self.plugins.remove(plugin)
            del self.plugin_registry[plugin_name]
            logger.info(f"Unregistered plugin: {plugin_name}")
    
    def get_plugin(self, plugin_name: str) -> Optional[RAGPlugin]:
        """Get a plugin by name"""
        return self.plugin_registry.get(plugin_name)
    
    def get_enabled_plugins(self) -> List[RAGPlugin]:
        """Get all enabled plugins"""
        return [p for p in self.plugins if p.is_enabled()]
    
    def execute_pre_processing(self, query: str, context: PluginContext) -> str:
        """Execute all pre-processing plugins"""
        processed_query = query
        for plugin in self.get_enabled_plugins():
            try:
                processed_query = plugin.pre_process_query(processed_query, context)
            except Exception as e:
                logger.error(f"Error in pre-processing plugin {plugin.get_name()}: {e}")
        return processed_query
    
    def execute_post_processing(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Execute all post-processing plugins"""
        processed_results = results
        for plugin in self.get_enabled_plugins():
            try:
                processed_results = plugin.post_process_results(processed_results, context)
            except Exception as e:
                logger.error(f"Error in post-processing plugin {plugin.get_name()}: {e}")
        return processed_results
    
    def execute_response_enhancement(self, response: str, context: PluginContext) -> str:
        """Execute all response enhancement plugins"""
        enhanced_response = response
        for plugin in self.get_enabled_plugins():
            try:
                enhanced_response = plugin.enhance_response(enhanced_response, context)
            except Exception as e:
                logger.error(f"Error in response enhancement plugin {plugin.get_name()}: {e}")
        return enhanced_response
    
    def validate_template_with_plugins(self, template: Dict, context: PluginContext) -> bool:
        """Validate template using all plugins"""
        for plugin in self.get_enabled_plugins():
            try:
                if not plugin.validate_template(template, context):
                    logger.info(f"Template {template.get('id', 'unknown')} rejected by plugin {plugin.get_name()}")
                    return False
            except Exception as e:
                logger.error(f"Error in template validation plugin {plugin.get_name()}: {e}")
                return False
        return True
    
    def extract_parameters_with_plugins(self, query: str, template: Dict, context: PluginContext) -> Dict[str, Any]:
        """Extract parameters using all plugins"""
        extracted_params = {}
        for plugin in self.get_enabled_plugins():
            try:
                plugin_params = plugin.extract_parameters(query, template, context)
                extracted_params.update(plugin_params)
            except Exception as e:
                logger.error(f"Error in parameter extraction plugin {plugin.get_name()}: {e}")
        return extracted_params 