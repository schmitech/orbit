# ElevenLabs Audio Service Usage Guide

This guide explains how to use the ElevenLabs audio service for high-quality text-to-speech.

## Overview

ElevenLabs provides industry-leading natural-sounding text-to-speech with:
- **Natural voices** - Highly realistic voice synthesis
- **Multilingual support** - Support for 29+ languages
- **Voice cloning** - Create custom voices
- **Advanced controls** - Fine-tune stability, clarity, and style

**Note**: ElevenLabs is a TTS-only service. For speech-to-text, use OpenAI, Google, or Ollama.

## Configuration

### Environment Variable
```bash
export ELEVENLABS_API_KEY="your-api-key-here"
```

### Config File (config/sound.yaml)
```yaml
sound:
  provider: "elevenlabs"  # Set as default provider
  enabled: true

sounds:
  elevenlabs:
    enabled: true
    api_key: ${ELEVENLABS_API_KEY}  # Or hardcode (not recommended)
    api_base: "https://api.elevenlabs.io/v1"

    # TTS Configuration
    tts_model: "eleven_multilingual_v2"  # Available models:
                                         # - eleven_monolingual_v1 (English only, fast)
                                         # - eleven_multilingual_v1 (29 languages)
                                         # - eleven_multilingual_v2 (Best quality)
                                         # - eleven_turbo_v2 (Fastest, good quality)

    tts_voice: "EXAVITQu4vr4xnSDxMaL"  # Sarah (default)
                                       # Get voice IDs from list_voices()

    tts_format: "mp3_44100_128"  # Output formats:
                                  # - mp3_44100_128 (balanced)
                                  # - mp3_44100_192 (higher quality)
                                  # - pcm_16000, pcm_22050, pcm_24000, pcm_44100 (uncompressed)
                                  # - ulaw_8000 (phone quality)

    # Voice Settings
    tts_stability: 0.5            # 0.0-1.0 (lower = more variable/expressive)
    tts_similarity_boost: 0.75    # 0.0-1.0 (higher = clearer, closer to training)
    tts_style: 0.0                # 0.0-1.0 (style exaggeration, v2 models only)
    tts_use_speaker_boost: true   # Enhanced voice quality
```

## Usage Examples

### Basic Text-to-Speech

```python
from ai_services.implementations.elevenlabs_audio_service import ElevenLabsAudioService

# Initialize service
config = {
    "sounds": {
        "elevenlabs": {
            "enabled": True,
            "api_key": "your-api-key"
        }
    }
}

service = ElevenLabsAudioService(config)
await service.initialize()

# Convert text to speech
audio_data = await service.text_to_speech("Hello, world!")

# Save to file
with open("output.mp3", "wb") as f:
    f.write(audio_data)

# Clean up
await service.close()
```

### Custom Voice Settings

```python
# More expressive voice (lower stability)
audio = await service.text_to_speech(
    "This is expressive speech!",
    stability=0.3,
    similarity_boost=0.8,
    style=0.5  # Only for v2 models
)

# More stable, consistent voice
audio = await service.text_to_speech(
    "This is stable speech.",
    stability=0.8,
    similarity_boost=0.6
)
```

### Using Different Voices

```python
# List available voices
voices = await service.list_voices()
for voice in voices['voices']:
    print(f"{voice['name']}: {voice['voice_id']}")

# Get detailed voice information
voice_info = await service.get_voice_info("EXAVITQu4vr4xnSDxMaL")
print(f"Voice: {voice_info['name']}")
print(f"Description: {voice_info.get('description', 'N/A')}")

# Use specific voice
audio = await service.text_to_speech(
    "Hello from a different voice!",
    voice="21m00Tcm4TlvDq8ikWAM"  # Rachel
)
```

### Different Output Formats

```python
# High-quality MP3
audio_hq = await service.text_to_speech(
    "High quality audio",
    format="mp3_44100_192"
)

# Uncompressed PCM (44.1kHz)
audio_pcm = await service.text_to_speech(
    "Uncompressed audio",
    format="pcm_44100"
)

# Phone quality for smaller file size
audio_phone = await service.text_to_speech(
    "Phone quality",
    format="ulaw_8000"
)
```

### Using Different Models

```python
# Fastest (Turbo v2)
audio_fast = await service.text_to_speech(
    "Fast generation",
    model="eleven_turbo_v2"
)

# Best quality (Multilingual v2)
audio_best = await service.text_to_speech(
    "Best quality",
    model="eleven_multilingual_v2"
)

# English only (Monolingual v1)
audio_en = await service.text_to_speech(
    "English only",
    model="eleven_monolingual_v1"
)
```

## Popular Voices

ElevenLabs provides several pre-made voices. Here are some popular ones:

| Voice Name | Voice ID | Description |
|------------|----------|-------------|
| Sarah | EXAVITQu4vr4xnSDxMaL | Soft, youthful female |
| Rachel | 21m00Tcm4TlvDq8ikWAM | Calm, young female |
| Domi | AZnzlk1XvdvUeBnXmlld | Strong, authoritative female |
| Bella | EXAVITQu4vr4xnSDxMaL | Soft, pleasant female |
| Antoni | ErXwobaYiN019PkySvjV | Well-rounded male |
| Elli | MF3mGyEYCl7XYWbV9V6O | Emotional female |
| Josh | TxGEqnHWrfWFTfGW9XjX | Young, energetic male |
| Arnold | VR6AewLTigWG4xSOukaG | Crisp, confident male |
| Adam | pNInz6obpgDQGcFmaJgB | Deep, authoritative male |
| Sam | yoZ06aMxZJJ28mfd3POQ | Dynamic, raspy male |

Use `await service.list_voices()` to see all available voices in your account.

## Voice Settings Guide

### Stability (0.0 - 1.0)
- **Low (0.0-0.3)**: More expressive, variable, emotional
- **Medium (0.4-0.6)**: Balanced (default: 0.5)
- **High (0.7-1.0)**: Consistent, stable, monotone

### Similarity Boost (0.0 - 1.0)
- **Low (0.0-0.5)**: More creative, less like original voice
- **Medium (0.5-0.8)**: Balanced (default: 0.75)
- **High (0.8-1.0)**: Very similar to training data, clearest

### Style (0.0 - 1.0) - V2 Models Only
- **Low (0.0)**: Default style (recommended)
- **High (1.0)**: Exaggerated style, more expressive

## Error Handling

```python
try:
    audio = await service.text_to_speech("Test")
except Exception as e:
    print(f"TTS error: {e}")
    # Handle error (rate limit, invalid voice, etc.)

# Check connection
is_connected = await service.verify_connection()
if not is_connected:
    print("Cannot connect to ElevenLabs API")
```

## Limitations

- **TTS only**: No speech-to-text support
- **API costs**: ElevenLabs charges per character
- **Rate limits**: Free tier has character limits per month
- **Internet required**: Cloud service, requires internet connection

## Best Practices

1. **Reuse service instances**: Initialize once, use multiple times
2. **Close when done**: Call `await service.close()` to free resources
3. **Cache audio**: Save generated audio to avoid regenerating
4. **Monitor usage**: Track character usage against your plan limits
5. **Test voices**: Try different voices and settings for your use case
6. **Use turbo for speed**: eleven_turbo_v2 for faster, cost-effective TTS

## Pricing Tiers

ElevenLabs offers several pricing tiers:
- **Free**: 10,000 characters/month
- **Starter**: 30,000 characters/month
- **Creator**: 100,000 characters/month
- **Pro**: 500,000 characters/month
- **Scale**: Custom enterprise pricing

Visit https://elevenlabs.io/pricing for current pricing.

## Resources

- **API Documentation**: https://elevenlabs.io/docs/api-reference
- **Voice Library**: https://elevenlabs.io/voice-library
- **Dashboard**: https://elevenlabs.io/app
- **Discord Community**: https://discord.gg/elevenlabs
