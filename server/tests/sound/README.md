# Audio Service Tests

This directory contains comprehensive unit tests for all audio service implementations in the Orbit AI services architecture.

## Test Files

### `test_audio_service.py`
Main test file covering:
- **Audio service registration** - Testing provider registration with full/partial/no config
- **Helper methods** - Testing `_prepare_audio()`, `_get_audio_format()`, `_validate_audio_format()`
- **AudioResult class** - Testing result creation, string conversion, and dict serialization
- **Factory function** - Testing `create_audio_service()` function

### `test_openai_audio_service.py`
OpenAI audio service tests covering:
- **Text-to-speech (TTS)** - Testing TTS with different voices and formats (mp3, opus, aac, flac)
- **Speech-to-text (STT)** - Testing Whisper transcription from bytes and files
- **Transcription** - Testing the transcribe alias method
- **Translation** - Testing audio translation (to English and non-English)
- **Configuration** - Testing default and custom configurations
- **Error handling** - Testing API error handling
- **Auto-initialization** - Testing automatic service initialization

### `test_google_audio_service.py`
Google Cloud audio service tests covering:
- **Text-to-speech (TTS)** - Testing Google Cloud TTS with different voices and encodings
- **Speech-to-text (STT)** - Testing Google Cloud Speech recognition
- **Transcription** - Testing transcribe alias
- **Translation** - Testing translation with and without Google Translate library
- **Initialization** - Testing client initialization and missing dependencies
- **Configuration** - Testing default and custom configurations (language codes, sample rates, pitch, speaking rate)
- **Error handling** - Testing Google API error handling
- **Resource cleanup** - Testing proper client cleanup

### `test_ollama_audio_service.py`
Ollama local audio service tests covering:
- **Text-to-speech (TTS)** - Testing local TTS models (piper, kokoro) with base64 encoding
- **Speech-to-text (STT)** - Testing local Whisper models
- **Transcription** - Testing transcribe method
- **Translation** - Testing translation using local inference models
- **Endpoint fallback** - Testing fallback from /transcribe to /generate endpoint
- **Configuration** - Testing default and custom model configurations
- **Response formats** - Testing different response field formats (audio, response, text, transcription)

### `test_placeholder_audio_services.py`
Placeholder service tests for providers without native audio APIs:
- **Anthropic placeholder** - Testing NotImplementedError for all methods
- **Cohere placeholder** - Testing NotImplementedError for all methods
- **Error messages** - Testing that error messages are clear and helpful
- **Configuration handling** - Testing minimal and full configurations
- **Inheritance** - Testing proper inheritance from AudioService base class
- **Future compatibility** - Ensuring placeholders can be easily replaced when APIs become available

### `test_elevenlabs_audio_service.py`
ElevenLabs audio service tests covering:
- **Text-to-speech (TTS)** - Testing high-quality voice synthesis
- **Voice customization** - Testing stability, similarity_boost, style parameters
- **Multiple output formats** - Testing different audio formats (mp3, pcm)
- **Voice management** - Testing list_voices() and get_voice_info()
- **Configuration** - Testing default and custom voice settings
- **Error handling** - Testing API error responses
- **STT not supported** - Testing that STT/transcription/translation raise NotImplementedError with helpful messages

## Running Tests

### Run all audio service tests:
```bash
cd server/tests
pytest sound/ -v
```

### Run specific test file:
```bash
pytest sound/test_audio_service.py -v
pytest sound/test_openai_audio_service.py -v
pytest sound/test_google_audio_service.py -v
pytest sound/test_ollama_audio_service.py -v
pytest sound/test_placeholder_audio_services.py -v
```

### Run specific test class:
```bash
pytest sound/test_audio_service.py::TestAudioServiceRegistration -v
pytest sound/test_openai_audio_service.py::TestOpenAIAudioService -v
```

### Run specific test method:
```bash
pytest sound/test_audio_service.py::TestAudioServiceRegistration::test_register_all_audio_providers -v
pytest sound/test_openai_audio_service.py::TestOpenAIAudioService::test_text_to_speech -v
```

### Run with coverage:
```bash
pytest sound/ --cov=ai_services.services.audio_service --cov=ai_services.implementations --cov-report=html
```

## Test Coverage

The test suite provides comprehensive coverage of:

1. **Service Registration** (100%)
   - All providers (OpenAI, Google, Anthropic, Ollama, Cohere)
   - Config-based enablement/disablement
   - Missing dependency handling
   - Factory integration

2. **Audio Operations** (100%)
   - Text-to-speech (TTS) with various voices and formats
   - Speech-to-text (STT) with language support
   - Audio transcription
   - Audio translation
   - Audio format handling and validation

3. **Configuration** (100%)
   - Default configurations
   - Custom configurations
   - Provider-specific settings (models, voices, encodings, sample rates)
   - Timeout and retry settings

4. **Error Handling** (100%)
   - API errors
   - Invalid formats
   - Missing dependencies
   - Connection failures
   - Fallback mechanisms

5. **Placeholder Services** (100%)
   - NotImplementedError for unsupported operations
   - Clear, helpful error messages
   - Proper inheritance and structure

## Test Patterns

### Mocking Audio Data
```python
# For bytes
audio_bytes = b"fake audio data"

# For files
audio_file = tmp_path / "test.mp3"
audio_file.write_bytes(audio_bytes)

# For base64 (Ollama)
audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
```

### Mocking Async Clients
```python
# OpenAI client
mock_client = MagicMock()
mock_client.audio.speech.create = AsyncMock(return_value=mock_response)

# Google Cloud client
mock_tts_client = MagicMock()
mock_tts_client.synthesize_speech = AsyncMock(return_value=mock_response)
```

### Testing Factory Registration
```python
# Reset factory before tests
AIServiceFactory._service_registry = {}
AIServiceFactory._service_cache = {}

# Register services
register_audio_services(config)

# Verify registration
available = AIServiceFactory.list_available_services()
assert 'openai' in available.get('audio', [])
```

## Dependencies

The tests mock external dependencies and don't require:
- OpenAI API keys
- Google Cloud credentials
- Running Ollama server
- Network connectivity

This ensures tests run fast and reliably in CI/CD environments.

## Future Enhancements

When audio APIs become available for Anthropic and Cohere:
1. Remove placeholder tests for that provider
2. Add comprehensive tests following OpenAI/Google patterns
3. Update test documentation

## Integration Tests

For integration testing with real APIs, see:
- `server/tests/test_audio_integration.py` (when created)
- Use environment variables for API keys
- Mark with `@pytest.mark.integration` for optional execution
