"""
Adapter Capabilities System

This module defines a capability-based system for adapters, eliminating
hardcoded adapter type checks in pipeline steps.

Instead of checking if an adapter is "multimodal" or "file-document-qa",
pipeline steps query adapter capabilities to determine behavior.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum


class RetrievalBehavior(Enum):
    """Defines how an adapter retrieves context"""
    NONE = "none"  # No retrieval (pure passthrough)
    ALWAYS = "always"  # Always retrieves context
    CONDITIONAL = "conditional"  # Retrieves based on conditions (e.g., file_ids present)


class FormattingStyle(Enum):
    """Defines how retrieved documents should be formatted"""
    STANDARD = "standard"  # Standard format with citations and confidence
    CLEAN = "clean"  # Clean format without citations (for file/multimodal)
    CUSTOM = "custom"  # Adapter provides custom formatting


@dataclass
class AdapterCapabilities:
    """
    Defines the capabilities and behavioral characteristics of an adapter.

    This allows pipeline steps to query adapter behavior without hardcoded
    type checks or string matching.
    """

    # Core behavior
    retrieval_behavior: RetrievalBehavior = RetrievalBehavior.ALWAYS
    formatting_style: FormattingStyle = FormattingStyle.STANDARD

    # Context retrieval features
    supports_file_ids: bool = False  # Can filter by file_ids
    supports_session_tracking: bool = False  # Needs session_id
    requires_api_key_validation: bool = False  # Needs api_key for ownership validation
    supports_threading: bool = False  # Supports conversation threading on retrieved datasets
    supports_language_filtering: bool = False  # Can filter/boost by detected language
    supports_autocomplete: bool = False  # Provides autocomplete suggestions from nl_examples

    # Additional parameters to pass to get_relevant_context()
    required_parameters: List[str] = field(default_factory=list)
    optional_parameters: List[str] = field(default_factory=list)

    # Execution conditions
    skip_when_no_files: bool = False  # Skip retrieval when file_ids is empty

    # Context formatting options
    context_format: Optional[str] = None  # "markdown_table", "toon", "csv", or None (pipe-separated default)
    context_max_tokens: Optional[int] = None  # Token budget for context trimming
    numeric_precision: Dict[str, Any] = field(default_factory=dict)  # e.g. {"decimal_places": 2}

    # Custom behavior hooks (for advanced use cases)
    custom_should_execute: Optional[Callable[[Any], bool]] = None
    custom_format_context: Optional[Callable[[list, Optional[Dict]], str]] = None

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'AdapterCapabilities':
        """
        Create capabilities from adapter configuration.

        If the 'capabilities' section is missing or incomplete, defaults
        will be used for unspecified values.

        Args:
            config: Adapter configuration dictionary (from adapters.yaml)
                Should contain a 'capabilities' key with capability settings.
                If missing, all capabilities will use defaults.

        Returns:
            AdapterCapabilities instance with values from config or defaults
        """
        capabilities_config = config.get('capabilities', {})

        return cls(
            retrieval_behavior=RetrievalBehavior(
                capabilities_config.get('retrieval_behavior', 'always')
            ),
            formatting_style=FormattingStyle(
                capabilities_config.get('formatting_style', 'standard')
            ),
            supports_file_ids=capabilities_config.get('supports_file_ids', False),
            supports_session_tracking=capabilities_config.get('supports_session_tracking', False),
            requires_api_key_validation=capabilities_config.get('requires_api_key_validation', False),
            supports_threading=capabilities_config.get('supports_threading', False),
            supports_language_filtering=capabilities_config.get('supports_language_filtering', False),
            supports_autocomplete=capabilities_config.get('supports_autocomplete', False),
            required_parameters=capabilities_config.get('required_parameters', []),
            optional_parameters=capabilities_config.get('optional_parameters', []),
            skip_when_no_files=capabilities_config.get('skip_when_no_files', False),
            context_format=capabilities_config.get('context_format'),
            context_max_tokens=capabilities_config.get('context_max_tokens'),
            numeric_precision=capabilities_config.get('numeric_precision', {}),
        )

    @classmethod
    def for_passthrough(cls, supports_file_retrieval: bool = False) -> 'AdapterCapabilities':
        """
        Create capabilities for passthrough adapters.

        Args:
            supports_file_retrieval: Whether this passthrough supports file retrieval

        Returns:
            AdapterCapabilities instance
        """
        if supports_file_retrieval:
            # Multimodal-style: retrieves files conditionally
            return cls(
                retrieval_behavior=RetrievalBehavior.CONDITIONAL,
                formatting_style=FormattingStyle.CLEAN,
                supports_file_ids=True,
                supports_session_tracking=True,
                requires_api_key_validation=True,
                skip_when_no_files=True,
            )
        else:
            # Pure passthrough: no retrieval
            return cls(
                retrieval_behavior=RetrievalBehavior.NONE,
                formatting_style=FormattingStyle.STANDARD,
            )

    @classmethod
    def for_file_adapter(cls) -> 'AdapterCapabilities':
        """Create capabilities for file-based adapters."""
        return cls(
            retrieval_behavior=RetrievalBehavior.ALWAYS,
            formatting_style=FormattingStyle.CLEAN,
            supports_file_ids=True,
            requires_api_key_validation=True,
            optional_parameters=['file_ids', 'api_key'],
        )

    @classmethod
    def for_standard_retriever(cls, adapter_name: Optional[str] = None) -> 'AdapterCapabilities':
        """
        Create capabilities for standard retriever adapters (QA, Intent, etc.).

        Args:
            adapter_name: Optional adapter name to determine threading/autocomplete support
        """
        # Check if adapter supports threading (intent or QA adapters)
        supports_threading = False
        supports_autocomplete = False
        if adapter_name:
            is_intent_or_qa = (
                adapter_name.startswith('intent-') or
                adapter_name.startswith('qa-') or
                'qa' in adapter_name.lower()
            ) and not (
                'conversational' in adapter_name.lower() or
                'multimodal' in adapter_name.lower()
            )
            supports_threading = is_intent_or_qa
            # Intent adapters with templates support autocomplete
            supports_autocomplete = adapter_name.startswith('intent-') or adapter_name.startswith('composite-')

        return cls(
            retrieval_behavior=RetrievalBehavior.ALWAYS,
            formatting_style=FormattingStyle.STANDARD,
            supports_file_ids=False,
            supports_threading=supports_threading,
            supports_autocomplete=supports_autocomplete,
            optional_parameters=['api_key'],
        )

    def should_retrieve(self, context: Any) -> bool:
        """
        Determine if retrieval should occur based on capabilities and context.

        Args:
            context: ProcessingContext instance

        Returns:
            True if retrieval should execute
        """
        # Check retrieval behavior
        if self.retrieval_behavior == RetrievalBehavior.NONE:
            return False

        if self.retrieval_behavior == RetrievalBehavior.ALWAYS:
            return True

        if self.retrieval_behavior == RetrievalBehavior.CONDITIONAL:
            # Check if files are present when required
            if self.skip_when_no_files and not context.file_ids:
                return False
            return True

        return True

    def build_retriever_kwargs(self, context: Any) -> Dict[str, Any]:
        """
        Build keyword arguments for get_relevant_context() based on capabilities.

        Args:
            context: ProcessingContext instance

        Returns:
            Dictionary of kwargs to pass to retriever
        """
        kwargs = {}

        # Add file_ids if supported and present
        if self.supports_file_ids and context.file_ids:
            kwargs['file_ids'] = context.file_ids

        # Add api_key if needed for validation
        if self.requires_api_key_validation and context.api_key:
            kwargs['api_key'] = context.api_key

        # Add session_id if supported
        if self.supports_session_tracking and context.session_id:
            kwargs['session_id'] = context.session_id

        # Add detected_language if language filtering is supported
        if self.supports_language_filtering:
            detected_lang = getattr(context, 'detected_language', None)
            if detected_lang:
                kwargs['detected_language'] = detected_lang

        # Add any required/optional parameters from context
        for param in self.required_parameters + self.optional_parameters:
            value = getattr(context, param, None)
            if value is not None:
                kwargs[param] = value

        return kwargs


class AdapterCapabilityRegistry:
    """
    Registry for adapter capabilities.

    This registry maps adapter names to their capabilities, allowing
    pipeline steps to query capabilities dynamically.
    """

    def __init__(self):
        self._capabilities: Dict[str, AdapterCapabilities] = {}

    def register(self, adapter_name: str, capabilities: AdapterCapabilities) -> None:
        """Register capabilities for an adapter."""
        self._capabilities[adapter_name] = capabilities

    def get(self, adapter_name: str) -> Optional[AdapterCapabilities]:
        """Get capabilities for an adapter."""
        return self._capabilities.get(adapter_name)

    def register_from_config(self, adapter_name: str, config: Dict[str, Any]) -> None:
        """Register capabilities from adapter configuration."""
        capabilities = AdapterCapabilities.from_config(config)
        self.register(adapter_name, capabilities)

    def has_adapter(self, adapter_name: str) -> bool:
        """Check if adapter is registered."""
        return adapter_name in self._capabilities

    def unregister(self, adapter_name: str) -> None:
        """
        Unregister capabilities for an adapter.

        This should be called when an adapter is removed or reloaded
        to ensure capabilities are re-inferred from the new configuration.

        Args:
            adapter_name: Name of the adapter to unregister
        """
        if adapter_name in self._capabilities:
            del self._capabilities[adapter_name]

    def clear(self) -> None:
        """
        Clear all registered capabilities.

        This is useful for testing or when reloading all adapter configurations.
        """
        self._capabilities.clear()

    def get_all_adapter_names(self) -> List[str]:
        """Get list of all registered adapter names."""
        return list(self._capabilities.keys())


# Global registry instance
_global_registry = AdapterCapabilityRegistry()


def get_capability_registry() -> AdapterCapabilityRegistry:
    """Get the global capability registry."""
    return _global_registry
