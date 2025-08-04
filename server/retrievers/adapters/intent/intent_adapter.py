"""
Intent adapter for SQL datasources that translates natural language queries to SQL
"""

import yaml
import logging
from typing import Dict, Any, List, Optional, Union
import os
from pathlib import Path

from retrievers.adapters.domain_adapters import DocumentAdapter, DocumentAdapterFactory

# Configure logging
logger = logging.getLogger(__name__)

# Register with the factory
DocumentAdapterFactory.register_adapter("intent", lambda **kwargs: IntentAdapter(**kwargs))
logger.info("Registered IntentAdapter as 'intent'")


class IntentAdapter(DocumentAdapter):
    """
    Adapter that manages domain-specific knowledge for the intent retriever.
    This component loads domain configuration and template libraries needed
    for text-to-SQL translation.
    """
    
    def __init__(self, 
                 domain_config_path: Optional[str] = None,
                 template_library_path: Optional[Union[str, List[str]]] = None,
                 confidence_threshold: float = 0.75,
                 verbose: bool = False,
                 config: Dict[str, Any] = None,
                 **kwargs):
        """
        Initialize the intent adapter.
        
        Args:
            domain_config_path: Path to domain configuration YAML file
            template_library_path: Path to SQL template library YAML file
            confidence_threshold: Minimum confidence score for template matching
            verbose: Whether to enable verbose logging
            config: Optional configuration dictionary
            **kwargs: Additional keyword arguments
        """
        self.confidence_threshold = confidence_threshold
        self.verbose = verbose
        self.config = config or {}
        
        # Load domain configuration
        self.domain_config = None
        self.template_library = None
        
        # Try to get paths from config if not provided directly
        if not domain_config_path and config:
            domain_config_path = config.get('domain_config_path')
        if not template_library_path and config:
            template_library_path = config.get('template_library_path')
            
        # Load configurations
        if domain_config_path:
            self.domain_config = self._load_yaml_config(domain_config_path, "domain configuration")
        if template_library_path:
            # Support both single path and list of paths
            if isinstance(template_library_path, list):
                self.template_library = self._load_multiple_template_libraries(template_library_path)
            else:
                self.template_library = self._load_yaml_config(template_library_path, "template library")
            
        logger.info(f"IntentAdapter initialized with confidence_threshold={confidence_threshold}")
        if self.domain_config:
            logger.info(f"Loaded domain: {self.domain_config.get('domain_name', 'Unknown')}")
        if self.template_library:
            template_count = len(self.template_library.get('templates', {}))
            logger.info(f"Loaded {template_count} SQL templates")
    
    def _load_yaml_config(self, path: str, config_type: str) -> Optional[Dict[str, Any]]:
        """
        Load a YAML configuration file.
        
        Args:
            path: Path to the YAML file
            config_type: Type of configuration for error messages
            
        Returns:
            Loaded configuration dictionary or None if error
        """
        try:
            # Handle relative paths from the project root
            if not os.path.isabs(path):
                # Assume relative paths are from the project root
                project_root = Path(__file__).parent.parent.parent.parent.parent
                full_path = project_root / path
            else:
                full_path = Path(path)
                
            if not full_path.exists():
                logger.warning(f"{config_type} file not found at: {full_path}")
                return None
                
            with open(full_path, 'r') as f:
                config = yaml.safe_load(f)
                
            if self.verbose:
                logger.info(f"Loaded {config_type} from: {full_path}")
                
            return config
            
        except Exception as e:
            logger.error(f"Error loading {config_type}: {str(e)}")
            return None
    
    def _load_multiple_template_libraries(self, paths: List[str]) -> Dict[str, Any]:
        """
        Load and merge multiple template library files.
        
        Args:
            paths: List of paths to template library files
            
        Returns:
            Merged template library dictionary
        """
        merged_library = {"templates": []}
        total_loaded = 0
        
        for path in paths:
            library = self._load_yaml_config(path, f"template library from {path}")
            if library and "templates" in library:
                templates = library["templates"]
                # Handle both list and dict formats
                if isinstance(templates, list):
                    merged_library["templates"].extend(templates)
                    total_loaded += len(templates)
                elif isinstance(templates, dict):
                    # Convert dict to list format
                    for template in templates.values():
                        merged_library["templates"].append(template)
                        total_loaded += 1
                    
        logger.info(f"Loaded {total_loaded} total SQL templates from {len(paths)} files")
        return merged_library
    
    def get_domain_config(self) -> Optional[Dict[str, Any]]:
        """Get the loaded domain configuration."""
        return self.domain_config
    
    def get_template_library(self) -> Optional[Dict[str, Any]]:
        """Get the loaded template library."""
        return self.template_library
    
    def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific template by ID.
        
        Args:
            template_id: The template identifier
            
        Returns:
            Template dictionary or None if not found
        """
        if not self.template_library:
            return None
            
        templates = self.template_library.get('templates', {})
        
        # Handle both dictionary and list formats
        if isinstance(templates, dict):
            # Check if template_id is a direct key
            if template_id in templates:
                return templates[template_id]
            # Otherwise search through values for matching id
            for template in templates.values():
                if isinstance(template, dict) and template.get('id') == template_id:
                    return template
        elif isinstance(templates, list):
            # Search through list for matching id
            for template in templates:
                if isinstance(template, dict) and template.get('id') == template_id:
                    return template
        
        return None
    
    def get_all_templates(self) -> List[Dict[str, Any]]:
        """
        Get all templates from the library.
        
        Returns:
            List of template dictionaries
        """
        if not self.template_library:
            return []
            
        templates = self.template_library.get('templates', {})
        
        # Handle both dictionary and list formats
        if isinstance(templates, dict):
            # Convert dictionary to list of values
            return list(templates.values())
        elif isinstance(templates, list):
            # Already a list
            return templates
        else:
            return []
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format SQL query results into a structured document.
        
        Args:
            raw_doc: The raw document text (SQL results as string)
            metadata: Additional metadata about the results
            
        Returns:
            A formatted context item
        """
        if self.verbose:
            logger.info(f"IntentAdapter.format_document called with metadata keys: {list(metadata.keys())}")
            
        # Create the base item
        item = {
            "raw_document": raw_doc,
            "metadata": metadata.copy(),
        }
        
        # Add intent-specific metadata
        if 'template_id' in metadata:
            item['template_id'] = metadata['template_id']
        if 'query_intent' in metadata:
            item['query_intent'] = metadata['query_intent']
        if 'parameters_used' in metadata:
            item['parameters'] = metadata['parameters_used']
            
        # Format results based on the result type
        if 'results' in metadata and isinstance(metadata['results'], list):
            # Format as a structured result set
            results = metadata['results']
            if results:
                # Create a summary of the results
                result_count = len(results)
                if result_count == 1:
                    item['content'] = self._format_single_result(results[0])
                else:
                    item['content'] = self._format_multiple_results(results)
                item['result_count'] = result_count
            else:
                item['content'] = "No results found for the query."
                item['result_count'] = 0
        else:
            # Use raw document as content
            item['content'] = raw_doc
            
        return item
    
    def _format_single_result(self, result: Dict[str, Any]) -> str:
        """Format a single result into readable text."""
        lines = []
        for key, value in result.items():
            if value is not None:
                # Format the key to be more readable
                formatted_key = key.replace('_', ' ').title()
                lines.append(f"{formatted_key}: {value}")
        return '\n'.join(lines)
    
    def _format_multiple_results(self, results: List[Dict[str, Any]]) -> str:
        """Format multiple results into readable text."""
        if not results:
            return "No results"
            
        # Create a summary showing the first few results
        lines = [f"Found {len(results)} results:"]
        
        # Show up to 5 results
        for i, result in enumerate(results[:5]):
            lines.append(f"\nResult {i+1}:")
            lines.append(self._format_single_result(result))
            
        if len(results) > 5:
            lines.append(f"\n... and {len(results) - 5} more results")
            
        return '\n'.join(lines)
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Extract a direct answer from the SQL results if available.
        
        Args:
            context: List of context items
            
        Returns:
            A direct answer if found, otherwise None
        """
        if not context:
            return None
            
        first_result = context[0]
        
        # Check if we have high confidence results
        if first_result.get("confidence", 0) >= self.confidence_threshold:
            return first_result.get('content', None)
        
        return None
    
    def apply_domain_specific_filtering(self, 
                                      context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]:
        """
        Apply intent-specific filtering/ranking.
        
        Args:
            context_items: List of context items to filter
            query: The original user query
            
        Returns:
            Filtered list of context items
        """
        # Filter out items below confidence threshold
        filtered = [
            item for item in context_items 
            if item.get("confidence", 0) >= self.confidence_threshold
        ]
        
        # Sort by confidence score
        filtered.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        return filtered
    
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Compatibility method to match retriever's expected interface.
        """
        return self.apply_domain_specific_filtering(context_items, query)


# Register adapter with the global registry for dynamic loading
def register_intent_adapter():
    """Register intent adapter with the global adapter registry"""
    logger.info("Registering intent adapter with global registry...")
    
    try:
        from ..registry import ADAPTER_REGISTRY
        
        # Register for PostgreSQL datasource
        ADAPTER_REGISTRY.register(
            adapter_type="retriever",
            datasource="postgres",
            adapter_name="intent",
            implementation='retrievers.adapters.intent.intent_adapter.IntentAdapter',
            config={
                'confidence_threshold': 0.75,
                'verbose': False
            }
        )
        logger.info("Registered intent adapter for postgres")
        
        # Also register for other SQL datasources that might use intent in the future
        for datasource in ['mysql', 'mssql']:
            ADAPTER_REGISTRY.register(
                adapter_type="retriever",
                datasource=datasource,
                adapter_name="intent",
                implementation='retrievers.adapters.intent.intent_adapter.IntentAdapter',
                config={
                    'confidence_threshold': 0.75,
                    'verbose': False
                }
            )
            logger.info(f"Registered intent adapter for {datasource}")
        
        logger.info("Intent adapter registration complete")
        
    except Exception as e:
        logger.error(f"Failed to register intent adapter: {e}")

# Register when module is imported
register_intent_adapter()