"""
Moderators package for handling content moderation with different providers.
"""

from .base import ModeratorService, ModeratorFactory, ModerationResult, ModerationCategory
from .openai import OpenAIModerator
from .anthropic import AnthropicModerator
from .ollama import OllamaModerator

# Register available moderators with the factory
ModeratorFactory.register('openai', OpenAIModerator)
ModeratorFactory.register('anthropic', AnthropicModerator)
ModeratorFactory.register('ollama', OllamaModerator)

__all__ = ['ModeratorService', 'ModeratorFactory', 'ModerationResult', 'ModerationCategory', 
           'OpenAIModerator', 'AnthropicModerator', 'OllamaModerator']