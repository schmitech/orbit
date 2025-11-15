# Whisper Integration Guide

This guide explains how to use OpenAI's open-source Whisper for local, offline speech-to-text in ORBIT.

## What is Whisper?

**Whisper** is OpenAI's automatic speech recognition (ASR) model released as open-source:
- GitHub: https://github.com/openai/whisper
- **Runs locally** on your machine (CPU or GPU)
- **Completely free** - no API costs
- **Offline capability** - works without internet
- **99 languages** supported with high accuracy
- **Multiple model sizes** for different use cases

## Whisper vs OpenAI Whisper API

You now have **THREE ways** to use Whisper in ORBIT:

| Feature | Local Whisper | OpenAI API | Ollama |
|---------|--------------|------------|---------|
| **Cost** | Free | $0.006/min | Free |
| **Privacy** | 100% local | Cloud | 100% local |
| **Internet** | Not required | Required | Not required |
| **Speed** | Depends on GPU | Fast | Depends on GPU |
| **Accuracy** | Same models | Large-v3 | Same models |
| **Languages** | 99 | 99 | 99 |
| **Setup** | `pip install` | API key | Ollama install |
| **Best for** | Privacy, offline | Production, quick setup | Experimental |

## Installation

### Option 1: Basic Installation (CPU only)

```bash
pip install openai-whisper
```

This works on any machine but is slower (CPU-only).

### Option 2: GPU Acceleration (NVIDIA GPUs)

For **much faster** transcription with NVIDIA GPUs:

```bash
# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install Whisper
pip install openai-whisper
```

Replace `cu118` with your CUDA version (11.8, 12.1, etc.).

### Option 3: Latest Whisper (from source)

```bash
pip install git+https://github.com/openai/whisper.git
```

Gets the latest improvements and bug fixes.

### Dependencies

Whisper also requires **FFmpeg** for audio processing:

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from: https://ffmpeg.org/download.html

## Model Sizes

Whisper offers 5 model sizes with different trade-offs:

| Model | Size | Speed | VRAM | Quality | Best For |
|-------|------|-------|------|---------|----------|
| `tiny` | 39M | 32x faster | ~1GB | ⭐⭐ | Quick testing |
| `base` | 74M | 16x faster | ~1GB | ⭐⭐⭐ | **General use** |
| `small` | 244M | 6x faster | ~2GB | ⭐⭐⭐⭐ | **Recommended** |
| `medium` | 769M | 2x faster | ~5GB | ⭐⭐⭐⭐⭐ | High quality |
| `large-v3` | 1550M | 1x (baseline) | ~10GB | ⭐⭐⭐⭐⭐⭐ | Best accuracy |

**Recommendation:**
- **Development**: Use `base` for quick iteration
- **Production**: Use `small` for best balance of speed/accuracy
- **High accuracy**: Use `large-v3` if you have GPU

Models are automatically downloaded on first use and cached in `~/.cache/whisper/`.

## Configuration

### Global Configuration (config/sound.yaml)

```yaml
sounds:
  whisper:
    enabled: true
    model_size: "base"  # tiny, base, small, medium, large-v3
    device: "auto"      # auto, cpu, cuda
    language: null      # null = auto-detect, or "en", "es", "fr", etc.
    task: "transcribe"  # transcribe or translate (to English)
```

### Adapter Configuration

#### Example 1: Local Voice Chat (STT only)

```yaml
- name: "local-voice-chat"
  enabled: true
  type: "passthrough"
  datasource: "none"
  adapter: "conversational"
  implementation: "implementations.passthrough.conversational.ConversationalImplementation"

  # Use Whisper for STT
  audio_provider: "whisper"

  config:
    stt_model_size: "base"  # Fast and accurate
    stt_device: "auto"      # Use GPU if available
    stt_language: null      # Auto-detect language
    audio_input_enabled: true
```

#### Example 2: Audio File Transcription

```yaml
- name: "whisper-transcription"
  enabled: true
  type: "retriever"
  datasource: "none"
  adapter: "file"
  implementation: "retrievers.implementations.file.file_retriever.FileVectorRetriever"

  # Use Whisper for transcribing uploaded audio files
  audio_provider: "whisper"
  embedding_provider: "openai"

  config:
    storage_backend: "filesystem"
    storage_root: "./uploads"
    max_file_size: 104857600  # 100MB for audio files

    # Whisper configuration
    enable_audio_transcription: true
    stt_model_size: "small"  # Higher quality for file transcription
    transcription_language: null  # Auto-detect

    # Supported audio formats
    supported_types:
      - "audio/wav"
      - "audio/mpeg"
      - "audio/mp3"
      - "audio/ogg"
      - "audio/flac"
      - "audio/webm"
```

#### Example 3: Hybrid (Whisper STT + OpenAI TTS)

For complete voice chat with local STT and cloud TTS:

```yaml
- name: "hybrid-voice-chat"
  enabled: true
  type: "passthrough"
  datasource: "none"
  adapter: "conversational"

  # Use Whisper for free local STT
  audio_provider: "whisper"

  # BUT: For TTS, we need a different provider since Whisper doesn't support TTS
  # This would require code changes to support separate STT/TTS providers
  # For now, use voice-chat adapter with OpenAI for both STT and TTS
```

**Note:** Currently, adapters use a single `audio_provider`. To mix Whisper STT with OpenAI TTS, you'd need to extend the adapter to support separate `stt_provider` and `tts_provider` configurations.

## Usage

### From Python (Direct API)

```python
from server.ai_services import AIServiceFactory, ServiceType

# Create Whisper service
config = {
    'sounds': {
        'whisper': {
            'model_size': 'base',
            'device': 'auto',
            'language': None  # Auto-detect
        }
    }
}

whisper_service = AIServiceFactory.create_service(
    ServiceType.AUDIO,
    'whisper',
    config
)

await whisper_service.initialize()

# Transcribe audio
with open('audio.mp3', 'rb') as f:
    audio_data = f.read()

text = await whisper_service.speech_to_text(
    audio_data,
    language='en'  # Optional: specify language for better accuracy
)

print(f"Transcription: {text}")
```

### From Client API

```typescript
// Record audio (browser)
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
const mediaRecorder = new MediaRecorder(stream);
const chunks: Blob[] = [];

mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
mediaRecorder.onstop = async () => {
  const audioBlob = new Blob(chunks, { type: 'audio/webm' });
  const audioBase64 = await blobToBase64(audioBlob);

  // Send to Whisper-enabled adapter
  for await (const response of api.streamChat(
    '',  // Empty message when using audio_input
    true,
    undefined,  // fileIds
    audioBase64,  // audioInput
    'webm',  // audioFormat
    'en'  // language (optional)
  )) {
    console.log(response.text);
  }
};

mediaRecorder.start();
setTimeout(() => mediaRecorder.stop(), 5000);  // Record for 5 seconds
```

## Advanced Features

### 1. Language Detection

Whisper can auto-detect the language:

```python
# Auto-detect (language=None)
text = await whisper_service.speech_to_text(audio_data, language=None)

# Or specify for better accuracy
text = await whisper_service.speech_to_text(audio_data, language='es')  # Spanish
```

Supported languages: https://github.com/openai/whisper#available-models-and-languages

### 2. Translation to English

Whisper can translate any language TO English:

```python
# Transcribe French audio to French text
text_fr = await whisper_service.transcribe(audio_data, language='fr')

# Translate French audio to English text
text_en = await whisper_service.translate(audio_data, source_language='fr')
```

**Important:** Whisper can only translate **to** English, not from English to other languages.

### 3. Word-Level Timestamps

```python
# Get word-level timestamps
result = whisper_service.model.transcribe(
    audio_path,
    word_timestamps=True
)

for segment in result['segments']:
    for word in segment['words']:
        print(f"{word['word']}: {word['start']:.2f}s - {word['end']:.2f}s")
```

### 4. Temperature Sampling

For better accuracy on difficult audio:

```python
text = await whisper_service.speech_to_text(
    audio_data,
    temperature=0.0  # Deterministic (default)
)

# Or for more varied transcriptions
text = await whisper_service.speech_to_text(
    audio_data,
    temperature=0.8  # More creative
)
```

## Performance Optimization

### GPU Acceleration

**Without GPU (CPU only):**
- Base model: ~1 min for 1 min of audio
- Large-v3: ~5 min for 1 min of audio

**With NVIDIA GPU (CUDA):**
- Base model: ~3 seconds for 1 min of audio (20x faster!)
- Large-v3: ~15 seconds for 1 min of audio

**Check GPU usage:**
```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"Device: {whisper_service.model.device}")
```

### Model Quantization

For lower memory usage with minimal quality loss:

```yaml
sounds:
  whisper:
    compute_type: "int8"  # 8-bit quantization (faster, less VRAM)
```

### Batch Processing

Process multiple audio files efficiently:

```python
audio_files = ['file1.mp3', 'file2.mp3', 'file3.mp3']

for audio_file in audio_files:
    with open(audio_file, 'rb') as f:
        text = await whisper_service.transcribe(f.read())
        print(f"{audio_file}: {text}")
```

## Comparison with Other Providers

### When to Use Local Whisper

✅ **Use Whisper when:**
- Privacy is critical (medical, legal, sensitive data)
- Working offline or in air-gapped environments
- Processing large volumes (API costs add up)
- Need language detection
- Want full control over model and parameters

❌ **Don't use Whisper when:**
- Need TTS (Whisper is STT-only)
- Very limited computing resources (use OpenAI API)
- Need instant results without GPU
- Want zero setup complexity

### Hybrid Approach (Best of Both Worlds)

**Recommended setup:**
- **STT**: Local Whisper (free, private)
- **TTS**: OpenAI API or ElevenLabs (high quality, fast)

This gives you:
- 💰 Zero cost for transcription (Whisper)
- 🔒 Privacy for input audio (stays local)
- 🎵 High-quality voice output (OpenAI/ElevenLabs)
- ⚡ Fast response times (API TTS is faster than local)

## Troubleshooting

### Issue: "Failed to load Whisper model"

**Solution:**
```bash
# Reinstall Whisper
pip uninstall openai-whisper
pip install openai-whisper

# Check FFmpeg
ffmpeg -version
```

### Issue: "CUDA out of memory"

**Solution:** Use a smaller model or CPU:

```yaml
whisper:
  model_size: "base"  # Instead of "large-v3"
  device: "cpu"       # Force CPU if GPU doesn't have enough VRAM
```

### Issue: Slow transcription on CPU

**Solution:** Use GPU or a smaller model:

```yaml
whisper:
  model_size: "tiny"  # Fastest (32x faster than large)
  device: "auto"      # Will use GPU if available
```

### Issue: Poor accuracy

**Solution:**
1. Use a larger model: `small` → `medium` → `large-v3`
2. Specify the language: `language: "en"` instead of `null`
3. Improve audio quality: Record at 16kHz, reduce background noise

## Resources

- **Official Repo:** https://github.com/openai/whisper
- **Model Card:** https://github.com/openai/whisper/blob/main/model-card.md
- **Supported Languages:** https://github.com/openai/whisper#available-models-and-languages
- **Paper:** https://arxiv.org/abs/2212.04356

## Summary

Local Whisper integration gives you:
- ✅ **Free** speech-to-text (no API costs)
- ✅ **Private** (audio never leaves your server)
- ✅ **Offline** (works without internet)
- ✅ **Accurate** (same models as OpenAI API)
- ✅ **Multilingual** (99 languages)
- ✅ **Flexible** (5 model sizes for different needs)

Perfect for privacy-sensitive applications, high-volume transcription, or offline deployments!
