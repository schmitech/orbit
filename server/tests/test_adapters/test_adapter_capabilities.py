"""
Unit tests for adapter capabilities system
"""

import pytest
import sys
import os
from unittest.mock import Mock

# Add the server directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from adapters.capabilities import (
    AdapterCapabilities,
    AdapterCapabilityRegistry,
    RetrievalBehavior,
    FormattingStyle
)


class TestAdapterCapabilities:
    """Test AdapterCapabilities class"""

    def test_for_passthrough_no_file_retrieval(self):
        """Test passthrough capabilities without file retrieval"""
        capabilities = AdapterCapabilities.for_passthrough(supports_file_retrieval=False)

        assert capabilities.retrieval_behavior == RetrievalBehavior.NONE
        assert capabilities.formatting_style == FormattingStyle.STANDARD
        assert capabilities.supports_file_ids is False
        assert capabilities.supports_session_tracking is False

    def test_for_passthrough_with_file_retrieval(self):
        """Test passthrough capabilities with file retrieval (multimodal)"""
        capabilities = AdapterCapabilities.for_passthrough(supports_file_retrieval=True)

        assert capabilities.retrieval_behavior == RetrievalBehavior.CONDITIONAL
        assert capabilities.formatting_style == FormattingStyle.CLEAN
        assert capabilities.supports_file_ids is True
        assert capabilities.supports_session_tracking is True
        assert capabilities.requires_api_key_validation is True
        assert capabilities.skip_when_no_files is True

    def test_for_file_adapter(self):
        """Test file adapter capabilities"""
        capabilities = AdapterCapabilities.for_file_adapter()

        assert capabilities.retrieval_behavior == RetrievalBehavior.ALWAYS
        assert capabilities.formatting_style == FormattingStyle.CLEAN
        assert capabilities.supports_file_ids is True
        assert capabilities.requires_api_key_validation is True

    def test_for_standard_retriever(self):
        """Test standard retriever capabilities"""
        capabilities = AdapterCapabilities.for_standard_retriever()

        assert capabilities.retrieval_behavior == RetrievalBehavior.ALWAYS
        assert capabilities.formatting_style == FormattingStyle.STANDARD
        assert capabilities.supports_file_ids is False

    def test_from_config(self):
        """Test creating capabilities from config"""
        config = {
            'capabilities': {
                'retrieval_behavior': 'conditional',
                'formatting_style': 'clean',
                'supports_file_ids': True,
                'supports_session_tracking': True,
                'requires_api_key_validation': True,
                'skip_when_no_files': True,
                'required_parameters': ['param1'],
                'optional_parameters': ['param2', 'param3']
            }
        }

        capabilities = AdapterCapabilities.from_config(config)

        assert capabilities.retrieval_behavior == RetrievalBehavior.CONDITIONAL
        assert capabilities.formatting_style == FormattingStyle.CLEAN
        assert capabilities.supports_file_ids is True
        assert capabilities.supports_session_tracking is True
        assert capabilities.requires_api_key_validation is True
        assert capabilities.skip_when_no_files is True
        assert capabilities.required_parameters == ['param1']
        assert capabilities.optional_parameters == ['param2', 'param3']

    def test_should_retrieve_none(self):
        """Test should_retrieve with NONE behavior"""
        capabilities = AdapterCapabilities(retrieval_behavior=RetrievalBehavior.NONE)
        context = Mock(file_ids=[])

        assert capabilities.should_retrieve(context) is False

    def test_should_retrieve_always(self):
        """Test should_retrieve with ALWAYS behavior"""
        capabilities = AdapterCapabilities(retrieval_behavior=RetrievalBehavior.ALWAYS)
        context = Mock(file_ids=[])

        assert capabilities.should_retrieve(context) is True

    def test_should_retrieve_conditional_with_files(self):
        """Test should_retrieve with CONDITIONAL behavior and files present"""
        capabilities = AdapterCapabilities(
            retrieval_behavior=RetrievalBehavior.CONDITIONAL,
            skip_when_no_files=True
        )
        context = Mock(file_ids=['file1', 'file2'])

        assert capabilities.should_retrieve(context) is True

    def test_should_retrieve_conditional_without_files(self):
        """Test should_retrieve with CONDITIONAL behavior and no files"""
        capabilities = AdapterCapabilities(
            retrieval_behavior=RetrievalBehavior.CONDITIONAL,
            skip_when_no_files=True
        )
        context = Mock(file_ids=[])

        assert capabilities.should_retrieve(context) is False

    def test_build_retriever_kwargs_minimal(self):
        """Test building retriever kwargs with minimal capabilities"""
        capabilities = AdapterCapabilities(
            supports_file_ids=False,
            supports_session_tracking=False,
            requires_api_key_validation=False
        )
        context = Mock(
            file_ids=['file1'],
            api_key='key123',
            session_id='session456'
        )

        kwargs = capabilities.build_retriever_kwargs(context)

        # Should be empty since no capabilities enabled
        assert kwargs == {}

    def test_build_retriever_kwargs_full(self):
        """Test building retriever kwargs with full capabilities"""
        capabilities = AdapterCapabilities(
            supports_file_ids=True,
            supports_session_tracking=True,
            requires_api_key_validation=True
        )
        context = Mock(
            file_ids=['file1', 'file2'],
            api_key='key123',
            session_id='session456'
        )

        kwargs = capabilities.build_retriever_kwargs(context)

        assert kwargs['file_ids'] == ['file1', 'file2']
        assert kwargs['api_key'] == 'key123'
        assert kwargs['session_id'] == 'session456'

    def test_build_retriever_kwargs_optional_parameters(self):
        """Test building retriever kwargs with optional parameters"""
        capabilities = AdapterCapabilities(
            optional_parameters=['custom_param1', 'custom_param2']
        )
        context = Mock(
            custom_param1='value1',
            custom_param2='value2',
            custom_param3='value3'  # Not in optional_parameters
        )

        kwargs = capabilities.build_retriever_kwargs(context)

        assert kwargs['custom_param1'] == 'value1'
        assert kwargs['custom_param2'] == 'value2'
        assert 'custom_param3' not in kwargs


class TestAdapterCapabilityRegistry:
    """Test AdapterCapabilityRegistry class"""

    def test_register_and_get(self):
        """Test registering and getting capabilities"""
        registry = AdapterCapabilityRegistry()
        capabilities = AdapterCapabilities.for_file_adapter()

        registry.register('test-adapter', capabilities)

        retrieved = registry.get('test-adapter')
        assert retrieved == capabilities

    def test_get_nonexistent(self):
        """Test getting non-existent adapter"""
        registry = AdapterCapabilityRegistry()

        result = registry.get('nonexistent-adapter')
        assert result is None

    def test_register_from_config(self):
        """Test registering from config"""
        registry = AdapterCapabilityRegistry()
        config = {
            'capabilities': {
                'retrieval_behavior': 'always',
                'formatting_style': 'standard'
            }
        }

        registry.register_from_config('test-adapter', config)

        capabilities = registry.get('test-adapter')
        assert capabilities.retrieval_behavior == RetrievalBehavior.ALWAYS
        assert capabilities.formatting_style == FormattingStyle.STANDARD

    def test_has_adapter(self):
        """Test has_adapter method"""
        registry = AdapterCapabilityRegistry()
        capabilities = AdapterCapabilities.for_file_adapter()

        assert registry.has_adapter('test-adapter') is False

        registry.register('test-adapter', capabilities)

        assert registry.has_adapter('test-adapter') is True


class TestCapabilityInference:
    """Test capability inference from adapter configs"""

    def test_infer_passthrough_conversational(self):
        """Test inferring capabilities for passthrough conversational adapter"""

        # Infer using factory methods directly
        capabilities = AdapterCapabilities.for_passthrough(supports_file_retrieval=False)

        assert capabilities.retrieval_behavior == RetrievalBehavior.NONE
        assert capabilities.formatting_style == FormattingStyle.STANDARD

    def test_infer_passthrough_multimodal(self):
        """Test inferring capabilities for passthrough multimodal adapter"""

        # Infer using factory methods directly
        capabilities = AdapterCapabilities.for_passthrough(supports_file_retrieval=True)

        assert capabilities.retrieval_behavior == RetrievalBehavior.CONDITIONAL
        assert capabilities.formatting_style == FormattingStyle.CLEAN
        assert capabilities.supports_file_ids is True

    def test_infer_file_adapter(self):
        """Test inferring capabilities for file adapter"""

        # Infer using factory methods directly
        capabilities = AdapterCapabilities.for_file_adapter()

        assert capabilities.retrieval_behavior == RetrievalBehavior.ALWAYS
        assert capabilities.formatting_style == FormattingStyle.CLEAN
        assert capabilities.supports_file_ids is True

    def test_infer_standard_retriever(self):
        """Test inferring capabilities for standard retriever"""

        # Infer using factory methods directly
        capabilities = AdapterCapabilities.for_standard_retriever()

        assert capabilities.retrieval_behavior == RetrievalBehavior.ALWAYS
        assert capabilities.formatting_style == FormattingStyle.STANDARD
        assert capabilities.supports_file_ids is False


class TestCapabilityReloading:
    """Test capability registry reload behavior"""

    def test_unregister_adapter(self):
        """Test unregistering an adapter's capabilities"""
        registry = AdapterCapabilityRegistry()
        capabilities = AdapterCapabilities.for_file_adapter()

        # Register
        registry.register('test-adapter', capabilities)
        assert registry.has_adapter('test-adapter')

        # Unregister
        registry.unregister('test-adapter')
        assert not registry.has_adapter('test-adapter')
        assert registry.get('test-adapter') is None

    def test_unregister_nonexistent_adapter(self):
        """Test unregistering a non-existent adapter (should not error)"""
        registry = AdapterCapabilityRegistry()

        # Should not raise an error
        registry.unregister('nonexistent-adapter')

    def test_clear_all_capabilities(self):
        """Test clearing all capabilities from registry"""
        registry = AdapterCapabilityRegistry()

        # Register multiple adapters
        registry.register('adapter1', AdapterCapabilities.for_file_adapter())
        registry.register('adapter2', AdapterCapabilities.for_standard_retriever())
        registry.register('adapter3', AdapterCapabilities.for_passthrough(supports_file_retrieval=True))

        assert len(registry.get_all_adapter_names()) == 3

        # Clear all
        registry.clear()

        assert len(registry.get_all_adapter_names()) == 0
        assert not registry.has_adapter('adapter1')
        assert not registry.has_adapter('adapter2')
        assert not registry.has_adapter('adapter3')

    def test_reregister_after_unregister(self):
        """Test re-registering capabilities after unregistering"""
        registry = AdapterCapabilityRegistry()

        # Register with one set of capabilities
        caps1 = AdapterCapabilities.for_passthrough(supports_file_retrieval=False)
        registry.register('test-adapter', caps1)

        retrieved1 = registry.get('test-adapter')
        assert retrieved1.retrieval_behavior == RetrievalBehavior.NONE

        # Unregister
        registry.unregister('test-adapter')

        # Re-register with different capabilities (simulating reload)
        caps2 = AdapterCapabilities.for_passthrough(supports_file_retrieval=True)
        registry.register('test-adapter', caps2)

        retrieved2 = registry.get('test-adapter')
        assert retrieved2.retrieval_behavior == RetrievalBehavior.CONDITIONAL
        assert retrieved2.supports_file_ids is True

    def test_get_all_adapter_names(self):
        """Test getting all registered adapter names"""
        registry = AdapterCapabilityRegistry()

        # Empty registry
        assert registry.get_all_adapter_names() == []

        # Add some adapters
        registry.register('adapter1', AdapterCapabilities.for_file_adapter())
        registry.register('adapter2', AdapterCapabilities.for_standard_retriever())

        names = registry.get_all_adapter_names()
        assert len(names) == 2
        assert 'adapter1' in names
        assert 'adapter2' in names


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
