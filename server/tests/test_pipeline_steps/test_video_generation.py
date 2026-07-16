"""
Tests for VideoGenerationStep (server/inference/pipeline/steps/video_generation.py).

Mirrors test_image_generation.py — same generation-memory contract, different
media type and service hook (generate_video / get_video_service).
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

_CONFIG_PATH = os.path.join(SERVER_DIR, '..', 'config', 'rewriters-prompts.yaml')
with open(_CONFIG_PATH) as f:
    TEST_CONFIG = yaml.safe_load(f)


def _make_container(adapter_type="video_generation", llm_provider=None, video_service=None,
                     thread_dataset_service=None, video_provider="xai"):
    adapter_manager = MagicMock()
    adapter_manager.get_adapter_config.return_value = {
        "type": adapter_type,
        "video_provider": video_provider,
        "rewrite_provider": None,
    }
    adapter_manager.get_overridden_provider = AsyncMock(return_value=None)
    adapter_manager.get_video_service = AsyncMock(return_value=video_service or _default_video_service())

    known = {"adapter_manager": adapter_manager, "llm_provider": llm_provider, "config": TEST_CONFIG}
    if thread_dataset_service is not None:
        known["thread_dataset_service"] = thread_dataset_service

    container = MagicMock()
    container.has.side_effect = lambda key: key in known and known[key] is not None
    container.get.side_effect = lambda key: known.get(key)
    container.get_or_none.side_effect = lambda key: known.get(key)
    return container


def _default_video_service():
    service = MagicMock()
    service.generate_video = AsyncMock(return_value={"video_bytes": b"fakevideobytes", "format": "mp4"})
    return service


def _make_memory_service(stored=None):
    store = {}
    if stored:
        store.update(stored)

    service = MagicMock()
    service.enabled = True
    service._generate_dataset_key = MagicMock(side_effect=lambda thread_id: f"thread_dataset:{thread_id}")

    async def get_dataset(key):
        return store.get(key)

    async def store_dataset(thread_id, query_context, raw_results):
        key = service._generate_dataset_key(thread_id)
        store[key] = (query_context, raw_results)
        return key

    service.get_dataset = AsyncMock(side_effect=get_dataset)
    service.store_dataset = AsyncMock(side_effect=store_dataset)
    return service


# ---------------------------------------------------------------------------
# should_execute
# ---------------------------------------------------------------------------

class TestVideoGenerationStepShouldExecute:
    def setup_method(self):
        from inference.pipeline.steps.video_generation import VideoGenerationStep
        self.StepClass = VideoGenerationStep

    def test_executes_for_video_generation_adapter(self):
        from inference.pipeline.base import ProcessingContext
        container = _make_container(adapter_type="video_generation")
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="video-generator")
        assert step.should_execute(ctx) is True

    def test_skips_for_image_generation_adapter(self):
        from inference.pipeline.base import ProcessingContext
        container = _make_container(adapter_type="image_generation")
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="image-generator")
        assert step.should_execute(ctx) is False

    def test_skips_when_blocked(self):
        from inference.pipeline.base import ProcessingContext
        container = _make_container(adapter_type="video_generation")
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="video-generator", is_blocked=True)
        assert step.should_execute(ctx) is False

    def test_does_not_support_streaming(self):
        step = self.StepClass(_make_container())
        assert step.supports_streaming() is False


# ---------------------------------------------------------------------------
# process()
# ---------------------------------------------------------------------------

class TestVideoGenerationStepProcess:
    def setup_method(self):
        from inference.pipeline.steps.video_generation import VideoGenerationStep
        self.StepClass = VideoGenerationStep

    @pytest.mark.asyncio
    async def test_process_sets_context_fields_without_rewrite(self):
        from inference.pipeline.base import ProcessingContext

        container = _make_container()
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="video-generator", message="a dog running in a forest")
        result = await step.process(ctx)

        assert result.error is None
        assert result.video is not None
        assert result.video_format == "mp4"
        assert result.video_revised_prompt == "a dog running in a forest"
        assert result.response == "a dog running in a forest"

    @pytest.mark.asyncio
    async def test_process_rewrites_using_conversation_history(self):
        from inference.pipeline.base import ProcessingContext

        captured = {}

        async def capture_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return "a golden retriever puppy bounding through a sunlit forest, camera tracking alongside"

        llm_provider = MagicMock()
        llm_provider.generate = capture_generate
        container = _make_container(llm_provider=llm_provider)

        step = self.StepClass(container)
        ctx = ProcessingContext(
            adapter_name="video-generator",
            message="make a video of a dog",
            context_messages=[{"role": "user", "content": "I love golden retrievers"}],
        )
        result = await step.process(ctx)

        assert result.error is None
        assert "golden retriever" in captured["prompt"]
        assert result.video_revised_prompt == "a golden retriever puppy bounding through a sunlit forest, camera tracking alongside"

    @pytest.mark.asyncio
    async def test_process_folds_previous_generation_memory_into_rewrite(self):
        from inference.pipeline.base import ProcessingContext

        captured = {}

        async def capture_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return "a fluffy dog wearing a miniature space suit bounding across a lunar landscape"

        llm_provider = MagicMock()
        llm_provider.generate = capture_generate
        memory_service = _make_memory_service()
        container = _make_container(llm_provider=llm_provider, thread_dataset_service=memory_service)

        step = self.StepClass(container)

        first_ctx = ProcessingContext(
            adapter_name="video-generator", message="a dog running in a forest", session_id="sess-1",
        )
        await step.process(first_ctx)
        assert first_ctx.video_revised_prompt

        second_ctx = ProcessingContext(
            adapter_name="video-generator", message="make the dog wear a space suit", session_id="sess-1",
        )
        result = await step.process(second_ctx)

        assert result.error is None
        assert first_ctx.video_revised_prompt in captured["prompt"]
        assert "space suit" in captured["prompt"]

    @pytest.mark.asyncio
    async def test_process_stores_generation_memory_after_success(self):
        from inference.pipeline.base import ProcessingContext

        memory_service = _make_memory_service()
        container = _make_container(thread_dataset_service=memory_service)
        step = self.StepClass(container)

        ctx = ProcessingContext(adapter_name="video-generator", message="a cat on a skateboard", session_id="sess-9")
        result = await step.process(ctx)

        assert result.error is None
        memory_service.store_dataset.assert_awaited_once()
        _, kwargs = memory_service.store_dataset.call_args
        assert kwargs["query_context"] == {"prompt": result.video_revised_prompt}

    @pytest.mark.asyncio
    async def test_process_does_not_store_memory_without_session_id(self):
        from inference.pipeline.base import ProcessingContext

        memory_service = _make_memory_service()
        container = _make_container(thread_dataset_service=memory_service)
        step = self.StepClass(container)

        ctx = ProcessingContext(adapter_name="video-generator", message="a cat on a skateboard")
        await step.process(ctx)

        memory_service.store_dataset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_error_when_no_video_service(self):
        from inference.pipeline.base import ProcessingContext

        adapter_manager = MagicMock()
        adapter_manager.get_adapter_config.return_value = {"type": "video_generation", "video_provider": None}
        adapter_manager.get_video_service = AsyncMock(return_value=None)
        container = MagicMock()
        container.has.side_effect = lambda k: k in ("adapter_manager", "config")
        container.get.side_effect = lambda k: adapter_manager if k == "adapter_manager" else TEST_CONFIG
        container.get_or_none.side_effect = lambda k: TEST_CONFIG if k == "config" else None

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="video-generator", message="a dog")
        result = await step.process(ctx)

        assert result.error is not None
