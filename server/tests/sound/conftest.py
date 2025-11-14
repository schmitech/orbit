"""
Pytest configuration for audio service tests.

This module provides shared fixtures and configuration for all audio service tests.
"""

import pytest
import os


@pytest.fixture(scope="session", autouse=True)
def set_test_env_vars():
    """
    Set test environment variables for all audio service tests.

    This fixture automatically runs for all tests in the sound/ directory
    and sets fake API keys to prevent validation errors during testing.
    """
    # Store original values to restore after tests
    original_env = {}

    test_env_vars = {
        "OPENAI_API_KEY": "test-openai-key-12345",
        "ANTHROPIC_API_KEY": "test-anthropic-key-12345",
        "COHERE_API_KEY": "test-cohere-key-12345",
        "GOOGLE_API_KEY": "test-google-key-12345",
        "ELEVENLABS_API_KEY": "test-elevenlabs-key-12345",
    }

    # Save original values and set test values
    for key, value in test_env_vars.items():
        if key in os.environ:
            original_env[key] = os.environ[key]
        os.environ[key] = value

    yield

    # Restore original environment variables
    for key in test_env_vars.keys():
        if key in original_env:
            os.environ[key] = original_env[key]
        else:
            os.environ.pop(key, None)


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration for each test."""
    import logging
    # Suppress debug logs during tests for cleaner output
    logging.getLogger('ai_services').setLevel(logging.WARNING)
    yield
    # Reset to default
    logging.getLogger('ai_services').setLevel(logging.INFO)
