#!/usr/bin/env python3
"""
Test vision service implementations and registration.

This module tests the vision service functionality including:
- Vision service registration
- Provider implementations (OpenAI, Gemini, Anthropic)
- Image analysis, description, OCR, and object detection
- Multimodal inference
- Error handling
"""

import pytest
import sys
import os
from typing import Dict, Any
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO
from PIL import Image

# Get the absolute path to the server directory (parent of tests)
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add server directory to Python path
sys.path.append(server_dir)

from ai_services.registry import register_vision_services
from ai_services.factory import AIServiceFactory


class TestVisionServiceRegistration:
    """Test cases for vision service registration."""

    @pytest.fixture(autouse=True)
    def reset_factory(self):
        """Reset the factory before each test to ensure clean state."""
        # Clear the factory's internal registry before each test
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        # Reset the registration flag
        import ai_services.registry as registry_module
        registry_module._services_registered = False
        yield
        # Clean up after test
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        registry_module._services_registered = False

    @pytest.fixture
    def enabled_providers_config(self) -> Dict[str, Any]:
        """Create a config with all vision providers enabled."""
        return {
            "vision": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-openai-key",
                    "model": "gpt-4o",
                    "temperature": 0.0,
                    "max_tokens": 1000
                },
                "gemini": {
                    "enabled": True,
                    "api_key": "test-gemini-key",
                    "model": "gemini-2.0-flash-exp",
                    "temperature": 0.0,
                    "max_tokens": 1000
                },
                "anthropic": {
                    "enabled": True,
                    "api_key": "test-anthropic-key",
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.0,
                    "max_tokens": 1000
                }
            }
        }

    @pytest.fixture
    def partial_enabled_config(self) -> Dict[str, Any]:
        """Create a config with only some vision providers enabled."""
        return {
            "vision": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-openai-key",
                    "model": "gpt-4o"
                },
                "gemini": {
                    "enabled": False,
                    "api_key": "test-gemini-key"
                },
                "anthropic": {
                    "enabled": True,
                    "api_key": "test-anthropic-key",
                    "model": "claude-3-5-sonnet-20241022"
                }
            }
        }

    def test_register_all_vision_providers(self, enabled_providers_config):
        """Test that all vision providers are registered when enabled."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            # Create a mock module with mock service classes
            mock_module = MagicMock()
            mock_module.OpenAIVisionService = MagicMock()
            mock_module.GeminiVisionService = MagicMock()
            mock_module.AnthropicVisionService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                # For other imports, use the real import
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config
            register_vision_services(enabled_providers_config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            vision_providers = available_services.get('vision', [])

            # Verify that all providers are registered
            assert 'openai' in vision_providers
            assert 'gemini' in vision_providers
            assert 'anthropic' in vision_providers

    def test_register_partial_vision_providers(self, partial_enabled_config):
        """Test that only enabled vision providers are registered."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIVisionService = MagicMock()
            mock_module.AnthropicVisionService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services with config
            register_vision_services(partial_enabled_config)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            vision_providers = available_services.get('vision', [])

            # Verify that only enabled providers are registered
            assert 'openai' in vision_providers
            assert 'anthropic' in vision_providers
            assert 'gemini' not in vision_providers

    def test_register_without_config(self):
        """Test that providers are registered when no config is provided."""
        # Mock the import to prevent actual module loading
        with patch('builtins.__import__') as mock_import:
            mock_module = MagicMock()
            mock_module.OpenAIVisionService = MagicMock()
            mock_module.GeminiVisionService = MagicMock()
            mock_module.AnthropicVisionService = MagicMock()

            # Configure mock_import to return our mock module for ai_services.implementations
            def side_effect(name, *args, **kwargs):
                if 'ai_services.implementations' in name:
                    return mock_module
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = side_effect

            # Register services without config (backward compatibility)
            register_vision_services(None)

            # Get registered services
            available_services = AIServiceFactory.list_available_services()
            vision_providers = available_services.get('vision', [])

            # When no config is provided, all providers should be attempted
            assert 'openai' in vision_providers
            assert 'gemini' in vision_providers
            assert 'anthropic' in vision_providers


class TestVisionServiceHelpers:
    """Test vision service helper methods."""

    @pytest.fixture
    def sample_image(self):
        """Create a sample PIL image for testing."""
        img = Image.new('RGB', (100, 100), color='red')
        return img

    @pytest.fixture
    def sample_image_bytes(self, sample_image):
        """Create sample image bytes for testing."""
        buf = BytesIO()
        sample_image.save(buf, format='PNG')
        return buf.getvalue()

    def test_prepare_image_from_bytes(self, sample_image_bytes):
        """Test preparing image from bytes."""
        from ai_services.services.vision_service import VisionService

        # Create a minimal mock implementation with all required methods
        config = {"api_key": "test"}

        class TestVisionService(VisionService):
            async def analyze_image(self, image, prompt=None): pass
            async def describe_image(self, image): pass
            async def extract_text_from_image(self, image): pass
            async def detect_objects(self, image): pass
            async def multimodal_inference(self, image, text_prompt, **kwargs): pass
            async def initialize(self): pass
            async def close(self): pass
            async def verify_connection(self): return True

        service = TestVisionService(config, "test")

        result = service._prepare_image(sample_image_bytes)
        assert isinstance(result, bytes)
        assert result == sample_image_bytes

    def test_prepare_image_from_pil(self, sample_image):
        """Test preparing image from PIL Image."""
        from ai_services.services.vision_service import VisionService

        # Create a minimal mock implementation with all required methods
        config = {"api_key": "test"}

        class TestVisionService(VisionService):
            async def analyze_image(self, image, prompt=None): pass
            async def describe_image(self, image): pass
            async def extract_text_from_image(self, image): pass
            async def detect_objects(self, image): pass
            async def multimodal_inference(self, image, text_prompt, **kwargs): pass
            async def initialize(self): pass
            async def close(self): pass
            async def verify_connection(self): return True

        service = TestVisionService(config, "test")

        result = service._prepare_image(sample_image)
        assert isinstance(result, bytes)

    def test_image_to_base64(self, sample_image_bytes):
        """Test converting image to base64."""
        from ai_services.services.vision_service import VisionService
        import base64

        # Create a minimal mock implementation with all required methods
        config = {"api_key": "test"}

        class TestVisionService(VisionService):
            async def analyze_image(self, image, prompt=None): pass
            async def describe_image(self, image): pass
            async def extract_text_from_image(self, image): pass
            async def detect_objects(self, image): pass
            async def multimodal_inference(self, image, text_prompt, **kwargs): pass
            async def initialize(self): pass
            async def close(self): pass
            async def verify_connection(self): return True

        service = TestVisionService(config, "test")

        result = service._image_to_base64(sample_image_bytes)
        assert isinstance(result, str)

        # Verify it's valid base64
        decoded = base64.b64decode(result)
        assert decoded == sample_image_bytes


class TestOpenAIVisionService:
    """Test OpenAI vision service implementation."""

    @pytest.fixture
    def openai_config(self):
        """Create OpenAI vision service config."""
        return {
            "api_key": "test-openai-key",
            "model": "gpt-4o",
            "temperature": 0.0,
            "max_tokens": 1000
        }

    @pytest.fixture
    def sample_image_bytes(self):
        """Create sample image bytes for testing."""
        img = Image.new('RGB', (100, 100), color='blue')
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    @pytest.mark.asyncio
    async def test_analyze_image(self, openai_config, sample_image_bytes):
        """Test OpenAI analyze_image method."""
        from ai_services.implementations.vision.openai_vision_service import OpenAIVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is a test image showing a blue square."

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(OpenAIVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = OpenAIVisionService(openai_config)
            service.client = mock_client
            service.initialized = True

            # Test analyze_image
            result = await service.analyze_image(sample_image_bytes)

            assert isinstance(result, str)
            assert "test image" in result.lower()

            # Verify the client was called correctly
            mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_describe_image(self, openai_config, sample_image_bytes):
        """Test OpenAI describe_image method."""
        from ai_services.implementations.vision.openai_vision_service import OpenAIVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A blue square on white background."

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(OpenAIVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = OpenAIVisionService(openai_config)
            service.client = mock_client
            service.initialized = True

            # Test describe_image
            result = await service.describe_image(sample_image_bytes)

            assert isinstance(result, str)
            assert "blue" in result.lower() or "square" in result.lower()

    @pytest.mark.asyncio
    async def test_extract_text_from_image(self, openai_config, sample_image_bytes):
        """Test OpenAI extract_text_from_image method."""
        from ai_services.implementations.vision.openai_vision_service import OpenAIVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Sample Text\nLine 2"

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(OpenAIVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = OpenAIVisionService(openai_config)
            service.client = mock_client
            service.initialized = True

            # Test extract_text_from_image
            result = await service.extract_text_from_image(sample_image_bytes)

            assert isinstance(result, str)
            assert "Sample Text" in result

    @pytest.mark.asyncio
    async def test_multimodal_inference(self, openai_config, sample_image_bytes):
        """Test OpenAI multimodal_inference method."""
        from ai_services.implementations.vision.openai_vision_service import OpenAIVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The image shows a blue square, which is commonly used in design."

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(OpenAIVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = OpenAIVisionService(openai_config)
            service.client = mock_client
            service.initialized = True

            # Test multimodal_inference
            result = await service.multimodal_inference(
                sample_image_bytes,
                "What does this image show and what is it commonly used for?"
            )

            assert isinstance(result, str)
            assert len(result) > 0


class TestGeminiVisionService:
    """Test Gemini vision service implementation."""

    @pytest.fixture
    def gemini_config(self):
        """Create Gemini vision service config."""
        return {
            "api_key": "test-gemini-key",
            "model": "gemini-2.0-flash-exp",
            "temperature": 0.0,
            "max_tokens": 1000,
            "transport": "rest"
        }

    @pytest.fixture
    def sample_image_bytes(self):
        """Create sample image bytes for testing."""
        img = Image.new('RGB', (100, 100), color='green')
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    @pytest.mark.asyncio
    async def test_analyze_image(self, gemini_config, sample_image_bytes):
        """Test Gemini analyze_image method."""
        from ai_services.implementations.vision.gemini_vision_service import GeminiVisionService

        # Patch the API key resolution
        with patch.object(GeminiVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = GeminiVisionService(gemini_config)
            service.initialized = True

            # Mock google.generativeai and asyncio.to_thread (REST transport uses to_thread)
            with patch('google.generativeai') as mock_genai, \
                 patch('asyncio.to_thread') as mock_to_thread:
                
                mock_model = MagicMock()
                mock_response = MagicMock()
                
                # Create proper mock structure for response.candidates[0].content.parts[0].text
                mock_part = MagicMock()
                mock_part.text = "This image shows a green square."
                
                mock_content = MagicMock()
                mock_content.parts = [mock_part]
                
                mock_candidate = MagicMock()
                mock_candidate.content = mock_content
                
                mock_response.candidates = [mock_candidate]

                # asyncio.to_thread is an async function, so use AsyncMock
                mock_to_thread.return_value = mock_response
                
                mock_genai.GenerativeModel.return_value = mock_model
                mock_genai.configure = MagicMock()

                # Test analyze_image
                result = await service.analyze_image(sample_image_bytes)

                assert isinstance(result, str)
                assert "green" in result.lower() or "square" in result.lower()

    @pytest.mark.asyncio
    async def test_describe_image(self, gemini_config, sample_image_bytes):
        """Test Gemini describe_image method."""
        from ai_services.implementations.vision.gemini_vision_service import GeminiVisionService

        # Patch the API key resolution
        with patch.object(GeminiVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = GeminiVisionService(gemini_config)
            service.initialized = True

            # Mock google.generativeai and asyncio.to_thread (REST transport uses to_thread)
            with patch('google.generativeai') as mock_genai, \
                 patch('asyncio.to_thread') as mock_to_thread:
                
                mock_model = MagicMock()
                mock_response = MagicMock()
                
                # Create proper mock structure for response.candidates[0].content.parts[0].text
                mock_part = MagicMock()
                mock_part.text = "A solid green square."
                
                mock_content = MagicMock()
                mock_content.parts = [mock_part]
                
                mock_candidate = MagicMock()
                mock_candidate.content = mock_content
                
                mock_response.candidates = [mock_candidate]

                # asyncio.to_thread is an async function, so use AsyncMock
                mock_to_thread.return_value = mock_response
                
                mock_genai.GenerativeModel.return_value = mock_model
                mock_genai.configure = MagicMock()

                # Test describe_image
                result = await service.describe_image(sample_image_bytes)

                assert isinstance(result, str)
                assert len(result) > 0

    @pytest.mark.asyncio
    async def test_multimodal_inference_with_rest(self, gemini_config, sample_image_bytes):
        """Test Gemini multimodal_inference with REST transport."""
        from ai_services.implementations.vision.gemini_vision_service import GeminiVisionService

        # Create service with REST transport
        gemini_config['transport'] = 'rest'

        # Patch the API key resolution
        with patch.object(GeminiVisionService, '_resolve_api_key', return_value='test-key'):
            service = GeminiVisionService(gemini_config)
            service.initialized = True

            # Mock google.generativeai and asyncio.to_thread
            with patch('google.generativeai') as mock_genai, \
                 patch('asyncio.to_thread') as mock_to_thread:

                mock_model = MagicMock()
                mock_response = MagicMock()
                
                # Create proper mock structure for response.candidates[0].content.parts[0].text
                mock_part = MagicMock()
                mock_part.text = "Green square for testing."
                
                mock_content = MagicMock()
                mock_content.parts = [mock_part]
                
                mock_candidate = MagicMock()
                mock_candidate.content = mock_content
                
                mock_response.candidates = [mock_candidate]

                # asyncio.to_thread is an async function, so use AsyncMock
                mock_to_thread.return_value = mock_response
                
                mock_genai.GenerativeModel.return_value = mock_model
                mock_genai.GenerationConfig = MagicMock()
                mock_genai.configure = MagicMock()

                # Test multimodal_inference
                result = await service.multimodal_inference(
                    sample_image_bytes,
                    "What color is this square?"
                )

                assert isinstance(result, str)
                assert len(result) > 0


class TestAnthropicVisionService:
    """Test Anthropic vision service implementation."""

    @pytest.fixture
    def anthropic_config(self):
        """Create Anthropic vision service config."""
        return {
            "api_key": "test-anthropic-key",
            "model": "claude-3-5-sonnet-20241022",
            "temperature": 0.0,
            "max_tokens": 1000
        }

    @pytest.fixture
    def sample_image_bytes(self):
        """Create sample image bytes for testing."""
        img = Image.new('RGB', (100, 100), color='red')
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()

    @pytest.mark.asyncio
    async def test_analyze_image(self, anthropic_config, sample_image_bytes):
        """Test Anthropic analyze_image method."""
        from ai_services.implementations.vision.anthropic_vision_service import AnthropicVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "This image shows a red square."

        mock_client.messages.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(AnthropicVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = AnthropicVisionService(anthropic_config)
            service.client = mock_client
            service.initialized = True

            # Test analyze_image
            result = await service.analyze_image(sample_image_bytes)

            assert isinstance(result, str)
            assert "red" in result.lower() or "square" in result.lower()

            # Verify the client was called correctly
            mock_client.messages.create.assert_called_once()
            call_args = mock_client.messages.create.call_args
            # Model should be one of the valid Claude models
            assert call_args.kwargs['model'] in ['claude-3-5-sonnet-20241022', 'claude-sonnet-4-20250514']
            assert call_args.kwargs['max_tokens'] == 1000
            assert call_args.kwargs['temperature'] == 0.0

    @pytest.mark.asyncio
    async def test_describe_image(self, anthropic_config, sample_image_bytes):
        """Test Anthropic describe_image method."""
        from ai_services.implementations.vision.anthropic_vision_service import AnthropicVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "A solid red square on white background."

        mock_client.messages.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(AnthropicVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = AnthropicVisionService(anthropic_config)
            service.client = mock_client
            service.initialized = True

            # Test describe_image
            result = await service.describe_image(sample_image_bytes)

            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_extract_text_from_image(self, anthropic_config, sample_image_bytes):
        """Test Anthropic extract_text_from_image method."""
        from ai_services.implementations.vision.anthropic_vision_service import AnthropicVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Test Document\nPage 1"

        mock_client.messages.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(AnthropicVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = AnthropicVisionService(anthropic_config)
            service.client = mock_client
            service.initialized = True

            # Test extract_text_from_image
            result = await service.extract_text_from_image(sample_image_bytes)

            assert isinstance(result, str)
            assert "Test Document" in result

    @pytest.mark.asyncio
    async def test_multimodal_inference(self, anthropic_config, sample_image_bytes):
        """Test Anthropic multimodal_inference method."""
        from ai_services.implementations.vision.anthropic_vision_service import AnthropicVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "The square is red, which often signifies importance or urgency."

        mock_client.messages.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(AnthropicVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = AnthropicVisionService(anthropic_config)
            service.client = mock_client
            service.initialized = True

            # Test multimodal_inference
            result = await service.multimodal_inference(
                sample_image_bytes,
                "What color is the square and what does it signify?",
                max_tokens=500
            )

            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_detect_objects(self, anthropic_config, sample_image_bytes):
        """Test Anthropic detect_objects method."""
        from ai_services.implementations.vision.anthropic_vision_service import AnthropicVisionService

        # Create mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "1. Red square in the center\n2. White background"

        mock_client.messages.create = AsyncMock(return_value=mock_response)

        # Patch the API key resolution
        with patch.object(AnthropicVisionService, '_resolve_api_key', return_value='test-key'):
            # Create service
            service = AnthropicVisionService(anthropic_config)
            service.client = mock_client
            service.initialized = True

            # Test detect_objects
            result = await service.detect_objects(sample_image_bytes)

            assert isinstance(result, list)
            assert len(result) > 0
            # Check structure of returned objects
            for obj in result:
                assert 'label' in obj
                assert 'confidence' in obj
                assert 'bbox' in obj


class TestVisionServiceErrorHandling:
    """Test error handling in vision services."""

    @pytest.fixture
    def openai_config(self):
        """Create OpenAI vision service config."""
        return {
            "api_key": "test-key",
            "model": "gpt-4o",
            "temperature": 0.0,
            "max_tokens": 1000
        }

    @pytest.mark.asyncio
    async def test_invalid_image_format(self, openai_config):
        """Test handling of invalid image format."""
        from ai_services.implementations.vision.openai_vision_service import OpenAIVisionService

        # Patch the API key resolution
        with patch.object(OpenAIVisionService, '_resolve_api_key', return_value='test-key'):
            service = OpenAIVisionService(openai_config)
            service.initialized = True

            # Test with invalid image data
            with pytest.raises(Exception):
                # Pass an invalid object type
                await service.analyze_image(123)

    @pytest.mark.asyncio
    async def test_api_error_handling(self, openai_config):
        """Test handling of API errors."""
        from ai_services.implementations.vision.openai_vision_service import OpenAIVisionService

        # Create mock client that raises an error
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        # Patch the API key resolution
        with patch.object(OpenAIVisionService, '_resolve_api_key', return_value='test-key'):
            service = OpenAIVisionService(openai_config)
            service.client = mock_client
            service.initialized = True

            # Test that error is raised
            with pytest.raises(Exception):
                await service.analyze_image(b"fake_image_bytes")


class TestVisionResult:
    """Test VisionResult helper class."""

    def test_vision_result_creation(self):
        """Test creating a VisionResult object."""
        from ai_services.services.vision_service import VisionResult

        result = VisionResult(
            content="Main analysis content",
            extracted_text="Extracted text from image",
            detected_objects=[{"label": "car", "confidence": 0.9}],
            description="Image description",
            provider="openai",
            metadata={"model": "gpt-4o"}
        )

        assert result.content == "Main analysis content"
        assert result.extracted_text == "Extracted text from image"
        assert len(result.detected_objects) == 1
        assert result.description == "Image description"
        assert result.provider == "openai"
        assert result.metadata["model"] == "gpt-4o"

    def test_vision_result_to_dict(self):
        """Test converting VisionResult to dictionary."""
        from ai_services.services.vision_service import VisionResult

        result = VisionResult(
            content="Test content",
            provider="anthropic"
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict['content'] == "Test content"
        assert result_dict['provider'] == "anthropic"
        assert result_dict['extracted_text'] is None
        assert result_dict['detected_objects'] == []

    def test_vision_result_str(self):
        """Test VisionResult string representation."""
        from ai_services.services.vision_service import VisionResult

        result = VisionResult(content="String representation test")

        assert str(result) == "String representation test"


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
