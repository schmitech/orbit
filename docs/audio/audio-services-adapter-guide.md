# Audio Services Adapter Guide

This guide explains how to use the new audio service capabilities (TTS and STT) in adapters, similar to how `vision_provider` is used for image processing.

## Overview

Audio services provide:
- **Text-to-Speech (TTS)**: Convert text responses to audio
- **Speech-to-Text (STT)**: Convert audio input to text
- **Transcription**: Transcribe audio files
- **Translation**: Translate audio between languages

## Configuration Pattern

Similar to `vision_provider`, you can configure `audio_provider` (or `sound_provider`) in adapters:

```yaml
audio_provider: "openai"  # Options: openai, google, ollama, elevenlabs
```

## Use Cases

### 1. Enhanced Multimodal Adapter (Extend Existing)

Extend `simple-chat-with-files` to support audio file transcription:

```yaml
  - name: "simple-chat-with-files-audio"
    enabled: true
    type: "passthrough"
    datasource: "none"
    adapter: "multimodal"
    implementation: "implementations.passthrough.multimodal.MultimodalImplementation"
    
    # Provider overrides
    inference_provider: "ollama_cloud"
    model: "gpt-oss:120b"
    embedding_provider: "openai"
    vision_provider: "gemini"           # For image files
    audio_provider: "openai"            # For audio file transcription
    
    capabilities:
      retrieval_behavior: "conditional"
      formatting_style: "clean"
      supports_file_ids: true
      supports_session_tracking: true
      requires_api_key_validation: true
      skip_when_no_files: true
      optional_parameters:
        - "file_ids"
        - "api_key"
        - "session_id"
    
    config:
      storage_backend: "filesystem"
      storage_root: "./uploads"
      max_file_size: 52428800
      
      # Audio processing settings
      enable_audio_transcription: true  # Enable audio file transcription
      audio_transcription_language: null  # Auto-detect, or specify "en-US", "fr-FR", etc.
      
      chunking_strategy: "recursive"
      chunk_size: 1000
      chunk_overlap: 200
      
      vector_store: "chroma"
      collection_prefix: "files_"
      
      confidence_threshold: 0.3
      max_results: 5
      return_results: 3
```

### 2. Voice Chat Adapter (Voice Input/Output)

Create a voice-enabled chat adapter that accepts audio input and returns audio responses:

```yaml
  - name: "voice-chat"
    enabled: true
    type: "passthrough"
    datasource: "none"
    adapter: "conversational"
    implementation: "implementations.passthrough.conversational.ConversationalImplementation"
    
    # Provider overrides
    inference_provider: "ollama_cloud"
    model: "gpt-oss:120b"
    audio_provider: "openai"  # For both STT and TTS
    
    # Voice settings
    audio_input_enabled: true   # Accept audio input
    audio_output_enabled: true  # Return audio responses
    tts_voice: "alloy"          # OpenAI voice: alloy, echo, fable, onyx, nova, shimmer
    tts_format: "mp3"           # Output format: mp3, opus, aac, flac
    
    capabilities:
      retrieval_behavior: "none"
      formatting_style: "standard"
      supports_file_ids: false
      supports_session_tracking: true
      requires_api_key_validation: false
      optional_parameters:
        - "audio_input"      # Base64-encoded audio data
        - "audio_format"    # Input audio format (mp3, wav, etc.)
        - "language"        # Language code for STT
        - "session_id"
    
    config:
      # Audio processing
      stt_language: "en-US"     # Default language for speech-to-text
      tts_voice: "alloy"        # Default voice for text-to-speech
      tts_format: "mp3"         # Default output format
      
      # Response settings
      return_text: true         # Also return text alongside audio
      return_audio: true        # Return audio response
```

### 3. Audio Transcription Adapter

Specialized adapter for transcribing audio files:

```yaml
  - name: "audio-transcription"
    enabled: true
    type: "retriever"
    datasource: "none"
    adapter: "file"
    implementation: "retrievers.implementations.file.file_retriever.FileVectorRetriever"
    
    # Provider overrides
    audio_provider: "openai"    # Use OpenAI Whisper for transcription
    embedding_provider: "openai"
    
    capabilities:
      retrieval_behavior: "conditional"
      formatting_style: "clean"
      supports_file_ids: true
      supports_session_tracking: false
      requires_api_key_validation: true
      skip_when_no_files: true
      optional_parameters:
        - "file_ids"
        - "api_key"
        - "transcription_language"  # Optional: specify language
    
    config:
      storage_backend: "filesystem"
      storage_root: "./uploads"
      max_file_size: 104857600  # 100MB for audio files
      
      # Audio-specific settings
      enable_audio_transcription: true
      transcription_language: null  # Auto-detect, or "en-US", "fr-FR", etc.
      transcription_format: "text"   # Return format: "text", "json", "srt", "vtt"
      
      # Supported audio formats
      supported_audio_types:
        - "audio/wav"
        - "audio/mpeg"
        - "audio/mp3"
        - "audio/mp4"
        - "audio/ogg"
        - "audio/flac"
        - "audio/webm"
      
      # Vector store for transcribed text
      vector_store: "chroma"
      collection_prefix: "audio_transcriptions_"
      
      chunking_strategy: "recursive"
      chunk_size: 2000  # Larger chunks for transcriptions
      chunk_overlap: 200
      
      confidence_threshold: 0.3
      max_results: 10
      return_results: 5
```

### 4. Multilingual Voice Assistant

Voice assistant with translation capabilities:

```yaml
  - name: "multilingual-voice-assistant"
    enabled: true
    type: "passthrough"
    datasource: "none"
    adapter: "conversational"
    implementation: "implementations.passthrough.conversational.ConversationalImplementation"
    
    # Provider overrides
    inference_provider: "ollama_cloud"
    model: "gpt-oss:120b"
    audio_provider: "google"  # Google supports many languages
    
    capabilities:
      retrieval_behavior: "none"
      formatting_style: "standard"
      supports_file_ids: false
      supports_session_tracking: true
      requires_api_key_validation: false
      optional_parameters:
        - "audio_input"
        - "source_language"    # Language of input audio
        - "target_language"    # Language for output audio
        - "session_id"
    
    config:
      # Language settings
      default_source_language: "auto"  # Auto-detect input language
      default_target_language: "en-US" # Default output language
      
      # Google TTS settings (multilingual)
      tts_model: "neural2"              # Google TTS model
      tts_voice: "en-US-Neural2-A"      # Default voice
      tts_language_code: "en-US"
      tts_audio_encoding: "MP3"
      
      # Google STT settings
      stt_model: "latest_long"
      stt_language_code: "en-US"
      stt_sample_rate: 16000
      stt_encoding: "LINEAR16"
      
      # Audio I/O
      audio_input_enabled: true
      audio_output_enabled: true
      return_text: true
      return_audio: true
```

### 5. ElevenLabs High-Quality Voice Adapter

Use ElevenLabs for premium voice quality:

```yaml
  - name: "premium-voice-chat"
    enabled: true
    type: "passthrough"
    datasource: "none"
    adapter: "conversational"
    implementation: "implementations.passthrough.conversational.ConversationalImplementation"
    
    # Provider overrides
    inference_provider: "ollama_cloud"
    model: "gpt-oss:120b"
    audio_provider: "elevenlabs"  # High-quality TTS
    # Note: ElevenLabs is TTS-only, use OpenAI for STT
    audio_stt_provider: "openai"  # Separate STT provider
    
    capabilities:
      retrieval_behavior: "none"
      formatting_style: "standard"
      supports_file_ids: false
      supports_session_tracking: true
      requires_api_key_validation: false
      optional_parameters:
        - "audio_input"
        - "voice_id"           # ElevenLabs voice ID
        - "session_id"
    
    config:
      # ElevenLabs TTS settings
      tts_model: "eleven_multilingual_v2"
      tts_voice: "EXAVITQu4vr4xnSDxMaL"  # Default voice (Sarah)
      tts_format: "mp3_44100_128"
      tts_stability: 0.5
      tts_similarity_boost: 0.75
      tts_style: 0.0
      tts_use_speaker_boost: true
      
      # OpenAI STT settings (for input)
      stt_provider: "openai"
      stt_model: "whisper-1"
      stt_language: null  # Auto-detect
      
      # Audio I/O
      audio_input_enabled: true
      audio_output_enabled: true
      return_text: true
      return_audio: true
```

## Implementation Notes

### 1. File Processing Integration

To enable audio file transcription in file processing, you'll need to:

1. **Update File Processing Service** to detect audio files and use audio service for transcription
2. **Add audio_provider configuration** similar to vision_provider
3. **Store transcriptions** in the vector store for retrieval

Example integration point:
```python
# In file_processing_service.py
if mime_type.startswith('audio/'):
    audio_provider = await self._get_audio_provider_for_api_key(api_key)
    transcription = await audio_service.transcribe(file_data, language=language)
    # Store transcription as text chunks
```

### 2. API Endpoint Extensions

Extend chat endpoints to support audio:

```python
# In chat routes
@router.post("/v1/chat")
async def chat(
    message: Optional[str] = None,
    audio_input: Optional[str] = None,  # Base64 audio
    audio_format: Optional[str] = None,
    return_audio: bool = False,
    ...
):
    # Convert audio to text if provided
    if audio_input:
        audio_data = base64.b64decode(audio_input)
        message = await audio_service.speech_to_text(
            audio_data, 
            language=language
        )
    
    # Get text response
    response = await chat_service.chat(message, ...)
    
    # Convert to audio if requested
    if return_audio:
        audio_response = await audio_service.text_to_speech(
            response,
            voice=voice,
            format=format
        )
        return {
            "text": response,
            "audio": base64.b64encode(audio_response).decode(),
            "audio_format": format
        }
    
    return {"text": response}
```

### 3. Adapter Implementation

In your adapter implementation, access audio services:

```python
from server.ai_services import AIServiceFactory, ServiceType

class YourAdapter:
    def __init__(self, config):
        self.config = config
        self.audio_provider = config.get('audio_provider', 'openai')
    
    async def process_audio_input(self, audio_data: bytes):
        # Get audio service
        audio_service = AIServiceFactory.create_service(
            ServiceType.AUDIO,
            self.audio_provider,
            self.config
        )
        await audio_service.initialize()
        
        # Transcribe
        text = await audio_service.speech_to_text(audio_data)
        return text
    
    async def generate_audio_response(self, text: str):
        # Get audio service
        audio_service = AIServiceFactory.create_service(
            ServiceType.AUDIO,
            self.audio_provider,
            self.config
        )
        await audio_service.initialize()
        
        # Generate speech
        audio = await audio_service.text_to_speech(
            text,
            voice=self.config.get('tts_voice', 'alloy'),
            format=self.config.get('tts_format', 'mp3')
        )
        return audio
```

## Supported Audio Providers

| Provider | STT | TTS | Languages | Notes |
|----------|-----|-----|-----------|-------|
| OpenAI | ✅ Whisper | ✅ TTS-1 | 50+ | High quality, fast |
| Google | ✅ Speech-to-Text | ✅ Text-to-Speech | 100+ | Multilingual, neural voices |
| Ollama | ✅ Whisper | ✅ Piper/Kokoro | Limited | Local, free |
| ElevenLabs | ❌ | ✅ Premium TTS | 20+ | High-quality voices, voice cloning |
| Anthropic | ❌ | ❌ | - | Placeholder (not yet supported) |
| Cohere | ❌ | ❌ | - | Placeholder (not yet supported) |

## TTS Content Sanitization

When LLM responses contain tables, charts, code blocks, and other markdown formatting, TTS can produce awkward speech like "pipe column one pipe column two pipe" for tables. The TTS system includes built-in content sanitization to handle this.

### Configuration

In `config/tts.yaml`:

```yaml
tts:
  provider: "openai"
  enabled: true

  # Content sanitization for TTS
  sanitize_content: true          # Remove non-speech content before TTS
  announce_skipped_content: true  # Say "[Table displayed]" vs silent removal
```

### What Gets Sanitized

| Content Type | Behavior |
|--------------|----------|
| Chart blocks (` ```chart...``` `) | Removed or replaced with "[Chart displayed]" |
| Code blocks (` ```...``` `) | Removed or replaced with "[Code block omitted]" |
| Inline code (`` `code` ``) | Removed silently |
| Markdown tables (`\| col \| col \|`) | Removed or replaced with "[Table displayed]" |
| Images (`![alt](url)`) | Removed silently |
| Links (`[text](url)`) | URL removed, link text kept |
| Raw URLs | Removed silently |
| Headers (`# ## ###`) | Markers removed, text kept |
| Bold/Italic (`**text**`, `*text*`) | Markers removed, text kept |
| Strikethrough (`~~text~~`) | Markers removed, text kept |
| Horizontal rules (`---`) | Removed silently |
| Blockquotes (`> text`) | Markers removed, text kept |
| List markers (`- `, `1. `) | Markers removed, text kept |
| HTML tags | Removed silently |

### Example

**LLM Response:**
```
Here's the quarterly data:

| Quarter | Sales |
|---------|-------|
| Q1      | 45000 |
| Q2      | 52000 |

The trend shows **strong growth** in Q2.
```

**TTS Output (with `announce_skipped_content: true`):**
> "Here's the quarterly data: Table displayed. The trend shows strong growth in Q2."

**TTS Output (with `announce_skipped_content: false`):**
> "Here's the quarterly data: The trend shows strong growth in Q2."

### Adapter-Level Override

You can override sanitization settings per adapter:

```yaml
  - name: "voice-chat"
    enabled: true
    type: "passthrough"
    # ...

    # TTS settings
    tts_provider: "openai"
    tts_sanitize_content: true        # Override global setting
    tts_announce_skipped: false       # Silent removal for this adapter
```

### Implementation Details

The sanitization happens in `AudioHandler._sanitize_for_tts()` (`server/services/chat_handlers/audio_handler.py`):

1. Called after text truncation but before TTS generation
2. Returns `None` if no speakable text remains (skips TTS entirely)
3. Logs the reduction in text size for debugging

```python
# Flow in generate_audio():
processed_text = self._truncate_text(text)      # Apply length limits
processed_text = self._sanitize_for_tts(text)   # Remove non-speech content
audio_data = await audio_service.text_to_speech(processed_text)  # Generate speech
```

## Best Practices

1. **Provider Selection**:
   - Use **OpenAI** for balanced STT/TTS with good quality
   - Use **Google** for multilingual support
   - Use **ElevenLabs** for premium voice quality (TTS only)
   - Use **Ollama** for local/offline processing

2. **Audio Format**:
   - **Input**: Support common formats (mp3, wav, ogg, flac)
   - **Output**: Use mp3 for compatibility, opus for smaller size

3. **Language Handling**:
   - Auto-detect language when possible
   - Allow explicit language specification for accuracy
   - Support language translation workflows

4. **Performance**:
   - Cache transcriptions for repeated audio files
   - Use streaming for long audio files
   - Consider async processing for large files

5. **Error Handling**:
   - Handle unsupported audio formats gracefully
   - Provide fallback to text-only mode
   - Log audio processing errors for debugging

## Example: Extending simple-chat-with-files

To add audio support to the existing `simple-chat-with-files` adapter, simply add:

```yaml
audio_provider: "openai"  # Add this line
```

And update the supported file types in the config:

```yaml
supported_types:
  # ... existing types ...
  - "audio/wav"
  - "audio/mpeg"
  - "audio/mp3"
  - "audio/ogg"
  - "audio/flac"
```

The file processing service will automatically transcribe audio files using the configured audio provider, and the transcribed text will be stored in the vector store for retrieval, just like other document types.

