# ORBIT CLI Test Suite

This directory contains comprehensive tests for the ORBIT CLI tool, organized into unit tests and integration tests.

## Test Structure

```
tests/
├── __init__.py                    # Test package initialization
├── conftest.py                    # Shared pytest fixtures
├── pytest.ini                    # pytest configuration
├── README.md                      # This file
├── integration/
│   └── test_cli_integration.py    # End-to-end CLI integration tests
└── unit/
    ├── test_api/                  # API client tests
    │   ├── test_base_client.py    # Base API client tests
    │   ├── test_decorators.py     # API decorator tests
    │   └── test_endpoints/        # Individual endpoint tests
    │       ├── test_auth.py       # Authentication API tests
    │       ├── test_keys.py       # API key management tests
    │       ├── test_prompts.py    # Prompt management tests
    │       └── test_users.py      # User management tests
    ├── test_commands/             # Command module tests
    │   └── test_server_commands.py
    ├── test_config/               # Configuration tests
    │   ├── test_defaults.py       # Default configuration tests
    │   ├── test_manager.py        # Configuration manager tests
    │   └── test_validator.py      # Configuration validation tests
    └── test_server/               # Server management tests
        ├── test_controller.py     # Server controller tests
        └── test_process_manager.py
```

## Running Tests

### Prerequisites

Ensure you have the development dependencies installed:

```bash
pip install -e ".[dev]"
```

### Running All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=orbit_cli --cov-report=html
```

### Running Specific Test Types

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only API tests
pytest -m api

# Run only configuration tests
pytest -m config
```

## Test Categories and Markers

The tests are organized using pytest markers:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests that may require external dependencies
- `@pytest.mark.slow` - Tests that take longer to run
- `@pytest.mark.network` - Tests requiring network connectivity
- `@pytest.mark.auth` - Tests requiring authentication
- `@pytest.mark.admin` - Tests requiring admin privileges
- `@pytest.mark.server` - Tests requiring a running server
- `@pytest.mark.cli` - Tests for CLI functionality
- `@pytest.mark.api` - Tests for API functionality
- `@pytest.mark.config` - Tests for configuration management

## Test Fixtures

### Shared Fixtures (conftest.py)

#### Configuration Fixtures
- `temp_dir` - Temporary directory for test files
- `temp_config_dir` - Temporary configuration directory
- `mock_config_manager` - Mock configuration manager
- `sample_config` - Sample configuration data

#### API Fixtures
- `mock_api_manager` - Mock API manager
- `mock_base_client` - Mock base API client
- `mock_api_response` - Mock successful API response
- `mock_failed_api_response` - Mock failed API response

#### Server Fixtures
- `mock_server_controller` - Mock server controller

#### Output Fixtures
- `mock_formatter` - Mock output formatter

#### Sample Data Fixtures
- `sample_api_key` / `sample_api_key_data` - Sample API key data
- `sample_user` / `sample_user_data` - Sample user data
- `sample_prompt` / `sample_prompt_data` - Sample prompt data

## Adjustments Made

### 1. Fixed Import Issues

**Problem**: Tests were importing `BaseClient` but the actual class is `BaseAPIClient`.

**Solution**: Updated all imports and references:
```python
# Before
from orbit_cli.api.base_client import BaseClient

# After  
from orbit_cli.api.base_client import BaseAPIClient
```

### 2. Added Missing Fixtures

**Problem**: Tests referenced `mock_api_response` and `mock_failed_api_response` fixtures that didn't exist.

**Solution**: Added comprehensive mock response fixtures in `conftest.py`.

### 3. Updated Test Methods

**Problem**: Test methods were using outdated API patterns.

**Solution**: Updated tests to match the actual `BaseAPIClient` implementation:
- Changed constructor calls to require `server_url` parameter
- Updated method signatures to use `json_data` instead of `data`
- Fixed assertions to match actual class properties

### 4. Added pytest Configuration

**Problem**: Tests used markers but no pytest configuration existed.

**Solution**: Added comprehensive `pytest.ini` with test discovery patterns, marker definitions, and logging configuration.

## Writing New Tests

### Unit Test Template

```python
import pytest
from unittest.mock import Mock, patch

from orbit_cli.module import ClassUnderTest

class TestClassUnderTest:
    """Test cases for ClassUnderTest."""
    
    @pytest.mark.unit
    def test_method_success(self, fixture_name):
        """Test successful method execution."""
        # Arrange
        instance = ClassUnderTest()
        
        # Act
        result = instance.method()
        
        # Assert
        assert result == expected_value
```

## Best Practices

1. **Use descriptive test names** that explain what is being tested
2. **Follow the Arrange-Act-Assert pattern**
3. **Mock external dependencies** to keep tests isolated
4. **Use appropriate markers** to categorize tests
5. **Write both positive and negative test cases** 