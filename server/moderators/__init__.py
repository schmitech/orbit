"""
Moderators package for content safety and moderation.
"""

# Import the base moderator factory and classes
from .base import ModeratorFactory, ModeratorService

# Define all available moderator classes but import them lazily
__all__ = [
    'ModeratorFactory',
    'ModeratorService',
    'OpenAIModerator',
    'AnthropicModerator', 
    'OllamaModerator'
]

# Map of moderator names to their module paths for lazy loading
_MODERATOR_REGISTRY = {
    'openai': '.openai.OpenAIModerator',
    'anthropic': '.anthropic.AnthropicModerator',
    'ollama': '.ollama.OllamaModerator'
}

def register_moderator(moderator_name):
    """
    Lazily import and register a moderator by name.
    
    Args:
        moderator_name: The name of the moderator to import and register
    
    Returns:
        bool: True if registration was successful, False otherwise
    """
    import logging
    import importlib
    
    logger = logging.getLogger(__name__)
    
    if moderator_name not in _MODERATOR_REGISTRY:
        logger.warning(f"Unknown moderator: {moderator_name}")
        return False
    
    if moderator_name in ModeratorFactory._registry:
        # Already registered
        return True
    
    try:
        # Parse the module path and class name
        module_path, class_name = _MODERATOR_REGISTRY[moderator_name].rsplit('.', 1)
        
        # Import the module relative to this package
        module = importlib.import_module(module_path, package=__name__)
        
        # Get the class from the module
        moderator_class = getattr(module, class_name)
        
        # Register the moderator
        ModeratorFactory.register(moderator_name, moderator_class)
        logger.info(f"Successfully registered moderator: {moderator_name}")
        return True
    except ImportError as e:
        logger.error(f"Failed to import moderator {moderator_name}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error registering moderator {moderator_name}: {str(e)}")
        return False