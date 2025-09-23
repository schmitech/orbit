import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.passthrough.conversational.conversational_adapter import ConversationalAdapter
from inference.pipeline.base import ProcessingContext
from inference.pipeline.service_container import ServiceContainer
from inference.pipeline.steps.context_retrieval import ContextRetrievalStep
from retrievers.adapters.registry import ADAPTER_REGISTRY
import retrievers.adapters.domain_adapters  # noqa: F401 - ensure registrations run


def test_conversational_adapter_registered():
    adapter_info = ADAPTER_REGISTRY.get('passthrough', 'none', 'conversational')
    assert adapter_info is not None

    adapter_instance = ADAPTER_REGISTRY.create('passthrough', 'none', 'conversational')
    assert isinstance(adapter_instance, ConversationalAdapter)


class _DummyAdapterManager:
    def __init__(self, adapter_config):
        self._adapter_config = adapter_config

    def get_adapter_config(self, adapter_name):
        return self._adapter_config


def test_context_retrieval_skip_for_passthrough_adapter():
    container = ServiceContainer()
    container.register_singleton('config', {'general': {'inference_only': False}})
    container.register_singleton('adapter_manager', _DummyAdapterManager({'type': 'passthrough'}))

    step = ContextRetrievalStep(container)
    context = ProcessingContext(adapter_name='conversational-passthrough')

    assert not step.should_execute(context)


def test_context_retrieval_runs_for_retriever_adapter():
    container = ServiceContainer()
    container.register_singleton('config', {'general': {'inference_only': False}})
    container.register_singleton('adapter_manager', _DummyAdapterManager({'type': 'retriever'}))

    step = ContextRetrievalStep(container)
    context = ProcessingContext(adapter_name='qa-sql')

    assert step.should_execute(context)
