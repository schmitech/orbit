"""
Passthrough adapter package for non-retrieval adapters.

These adapters don't perform retrieval but provide a consistent interface
for operations like conversational interactions.
"""

from adapters.passthrough.adapter import ConversationalAdapter

__all__ = ['ConversationalAdapter']