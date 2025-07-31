"""
Simplified plugin system for Intent retriever
"""

import logging
from typing import Protocol, List, Dict, Any, Optional
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
class IntentPluginContext:
    """Context information passed to intent plugins"""
    user_query: str
    template_id: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    similarity_score: Optional[float] = None
    execution_time_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class IntentPlugin(Protocol):
    """Plugin interface for extending Intent retriever functionality"""
    
    def get_name(self) -> str:
        """Return the plugin name"""
        ...
    
    def get_priority(self) -> PluginPriority:
        """Return the plugin execution priority"""
        ...
    
    def is_enabled(self) -> bool:
        """Check if the plugin is enabled"""
        ...
    
    def pre_process_query(self, query: str, context: IntentPluginContext) -> str:
        """Modify query before processing"""
        ...
    
    def post_process_results(self, results: List[Dict], context: IntentPluginContext) -> List[Dict]:
        """Transform results after query execution"""
        ...
    
    def enhance_response(self, response: str, context: IntentPluginContext) -> str:
        """Enhance the generated response"""
        ...


class BaseIntentPlugin(ABC):
    """Base class for Intent plugins with default implementations"""
    
    def __init__(self, name: str, priority: PluginPriority = PluginPriority.NORMAL):
        self._name = name
        self._priority = priority
        self._enabled = True
    
    def get_name(self) -> str:
        return self._name
    
    def get_priority(self) -> PluginPriority:
        return self._priority
    
    def is_enabled(self) -> bool:
        return self._enabled
    
    def enable(self):
        self._enabled = True
    
    def disable(self):
        self._enabled = False
    
    def pre_process_query(self, query: str, context: IntentPluginContext) -> str:
        """Default implementation - return query unchanged"""
        return query
    
    def post_process_results(self, results: List[Dict], context: IntentPluginContext) -> List[Dict]:
        """Default implementation - return results unchanged"""
        return results
    
    def enhance_response(self, response: str, context: IntentPluginContext) -> str:
        """Default implementation - return response unchanged"""
        return response


class IntentPluginManager:
    """Manager for Intent retriever plugins"""
    
    def __init__(self):
        self.plugins: List[IntentPlugin] = []
    
    def register_plugin(self, plugin: IntentPlugin):
        """Register a plugin"""
        self.plugins.append(plugin)
        # Sort by priority
        self.plugins.sort(key=lambda p: p.get_priority().value, reverse=True)
        logger.info(f"Registered Intent plugin: {plugin.get_name()}")
    
    def get_enabled_plugins(self) -> List[IntentPlugin]:
        """Get list of enabled plugins"""
        return [p for p in self.plugins if p.is_enabled()]
    
    def execute_pre_processing(self, query: str, context: IntentPluginContext) -> str:
        """Execute pre-processing plugins"""
        result_query = query
        
        for plugin in self.get_enabled_plugins():
            try:
                result_query = plugin.pre_process_query(result_query, context)
            except Exception as e:
                logger.error(f"Error in plugin {plugin.get_name()} pre_process_query: {e}")
        
        return result_query
    
    def execute_post_processing(self, results: List[Dict], context: IntentPluginContext) -> List[Dict]:
        """Execute post-processing plugins"""
        result_data = results
        
        for plugin in self.get_enabled_plugins():
            try:
                result_data = plugin.post_process_results(result_data, context)
            except Exception as e:
                logger.error(f"Error in plugin {plugin.get_name()} post_process_results: {e}")
        
        return result_data
    
    def execute_response_enhancement(self, response: str, context: IntentPluginContext) -> str:
        """Execute response enhancement plugins"""
        result_response = response
        
        for plugin in self.get_enabled_plugins():
            try:
                result_response = plugin.enhance_response(result_response, context)
            except Exception as e:
                logger.error(f"Error in plugin {plugin.get_name()} enhance_response: {e}")
        
        return result_response


# Example plugins
class QueryNormalizationPlugin(BaseIntentPlugin):
    """Plugin to normalize common query variations"""
    
    def __init__(self):
        super().__init__("Query Normalization", PluginPriority.HIGH)
    
    def pre_process_query(self, query: str, context: IntentPluginContext) -> str:
        """Normalize common query variations"""
        normalized = query.lower().strip()
        
        # Common substitutions
        substitutions = {
            'show me': 'find',
            'get me': 'find',
            'i want': 'find',
            'can you show': 'show',
            'can you get': 'get',
            'please show': 'show',
            'please get': 'get'
        }
        
        for old_phrase, new_phrase in substitutions.items():
            normalized = normalized.replace(old_phrase, new_phrase)
        
        return normalized


class ResultEnrichmentPlugin(BaseIntentPlugin):
    """Plugin to enrich results with additional metadata"""
    
    def __init__(self):
        super().__init__("Result Enrichment", PluginPriority.NORMAL)
    
    def post_process_results(self, results: List[Dict], context: IntentPluginContext) -> List[Dict]:
        """Add enrichment metadata to results"""
        for result in results:
            if 'metadata' not in result:
                result['metadata'] = {}
            
            result['metadata']['processed_by'] = self.get_name()
            result['metadata']['query_similarity'] = context.similarity_score
            result['metadata']['processing_time'] = context.execution_time_ms
        
        return results


class ResponseEnhancementPlugin(BaseIntentPlugin):
    """Plugin to enhance response formatting"""
    
    def __init__(self):
        super().__init__("Response Enhancement", PluginPriority.LOW)
    
    def enhance_response(self, response: str, context: IntentPluginContext) -> str:
        """Add helpful context to responses"""
        if context.template_id:
            enhanced = f"{response}\n\n_Query processed using template: {context.template_id}_"
            if context.similarity_score:
                enhanced += f" _(confidence: {context.similarity_score:.1%})_"
            return enhanced
        
        return response