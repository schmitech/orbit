"""
Contract test for the typesafe-sdk surface that TypeSafeDecisionService relies on.

The SDK's public API is new; if a minor release changes these names or signatures,
this test fails before the provider breaks at runtime.
"""

import inspect

import pytest

typesafe_sdk = pytest.importorskip("typesafe_sdk")


def test_exports_used_by_the_provider():
    for name in ("AsyncTypeSafeClient", "Choice", "Noul", "Score", "SystemOneResponse", "TypeSafeError"):
        assert hasattr(typesafe_sdk, name), name


def test_async_client_constructor_accepts_config_kwargs():
    params = inspect.signature(typesafe_sdk.AsyncTypeSafeClient.__init__).parameters
    for name in ("api_key", "base_url", "timeout", "model"):
        assert name in params, name


def test_async_client_has_system_one_and_aclose():
    client_cls = typesafe_sdk.AsyncTypeSafeClient
    assert inspect.iscoroutinefunction(client_cls.system_one)
    assert inspect.iscoroutinefunction(client_cls.aclose)
    params = inspect.signature(client_cls.system_one).parameters
    for name in ("state", "questions", "model"):
        assert name in params, name


def test_response_dumps_to_wire_shape():
    response = typesafe_sdk.SystemOneResponse.model_validate({
        "model": "jev-1.13.0",
        "usage": {"input_tokens": 1, "output_tokens": 2},
        "answers": {"refund": {"type": "noul", "noul": 0.9}},
    })
    assert response.model_dump(mode="json") == {
        "model": "jev-1.13.0",
        "usage": {"input_tokens": 1, "output_tokens": 2},
        "answers": {"refund": {"type": "noul", "noul": 0.9}},
    }
