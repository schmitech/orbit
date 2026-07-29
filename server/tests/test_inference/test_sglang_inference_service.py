"""Unit tests for the OpenAI-compatible SGLang inference service."""

from types import SimpleNamespace
from unittest.mock import patch

from ai_services.implementations.inference.sglang_inference_service import SGLangInferenceService


class _Completions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


class _Stream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        self.iterator = iter(self.chunks)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration:
            raise StopAsyncIteration


def _choice(content=None, *, tool_calls=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def _stream_chunk(content):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


def _service(responses):
    service = object.__new__(SGLangInferenceService)
    service.initialized = True
    service.model = "Qwen/Qwen2.5-1.5B-Instruct"
    service.temperature = 0.1
    service.max_tokens = 128
    service.top_p = 0.8
    service.top_k = 20
    service.repetition_penalty = 1.0
    service.presence_penalty = 0.0
    service.frequency_penalty = 0.0
    service.stop_tokens = ["<eos>"]
    completions = _Completions(responses)
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return service, completions


class TestSGLangInferenceService:
    def test_uses_host_port_and_allows_unauthenticated_server(self):
        class FakeHttpClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        with patch("ai_services.providers.openai_compatible_base.httpx.AsyncClient", FakeHttpClient), \
             patch("ai_services.providers.openai_compatible_base.AsyncOpenAI", return_value=object()):
            service = SGLangInferenceService({
                "inference": {"sglang": {"host": "sglang.internal", "port": 31000, "model": "test"}}
            })
        assert str(service.base_url).rstrip("/") == "http://sglang.internal:31000/v1"
        assert service.api_key == "not-needed"

    async def test_generate_forwards_standard_sampling_parameters(self):
        service, completions = _service([_choice("hello")])
        result = await service.generate("hi", temperature=0.3)

        assert result == "hello"
        assert completions.calls == [{
            "model": "Qwen/Qwen2.5-1.5B-Instruct",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.3,
            "max_tokens": 128,
            "top_p": 0.8,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "top_k": 20,
            "repetition_penalty": 1.0,
            "stop": ["<eos>"],
        }]

    async def test_stream_and_batch_preserve_output_order(self):
        stream = _Stream([_stream_chunk("hel"), _stream_chunk(None), _stream_chunk("lo")])
        service, completions = _service([stream, _choice("first"), _choice("second")])

        chunks = [chunk async for chunk in service.generate_stream("hello")]
        batch = await service.batch_generate(["one", "two"])

        assert chunks == ["hel", "lo"]
        assert batch == ["first", "second"]
        assert completions.calls[0]["stream"] is True

    async def test_normalizes_native_tool_calls(self):
        function = SimpleNamespace(name="get_weather", arguments='{"city": "Toronto"}')
        call = SimpleNamespace(id="call_1", function=function)
        service, completions = _service([_choice(None, tool_calls=[call], finish_reason="tool_calls")])
        tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]

        result = await service.generate_with_tools([{"role": "user", "content": "weather"}], tools)

        assert result.text is None
        assert result.finish_reason == "tool_calls"
        assert result.tool_calls == [{"id": "call_1", "name": "get_weather", "arguments": {"city": "Toronto"}}]
        assert result.assistant_message["tool_calls"][0]["function"]["arguments"] == '{"city": "Toronto"}'
        assert completions.calls[0]["tools"] == tools
        assert completions.calls[0]["tool_choice"] == "auto"
