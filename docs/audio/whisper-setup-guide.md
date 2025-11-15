# Whisper Setup & Usage Guide

A practical guide to enabling and using local Whisper for speech-to-text in ORBIT adapters.

## Quick Start (5 Minutes)

### Step 1: Install Whisper

```bash
# Option A: Install with torch profile (recommended)
./install/install.sh --profile torch

# Option B: Manual installation
pip install openai-whisper

# Also install FFmpeg (required for audio processing)
# Ubuntu/Debian:
sudo apt install ffmpeg

# macOS:
brew install ffmpeg

# Windows: Download from https://ffmpeg.org/download.html
```

### Step 2: Enable Whisper in Config

Edit `config/sound.yaml`:

```yaml
sounds:
  whisper:
    enabled: true
    model_size: "base"  # Start with base for development
    device: "auto"      # Auto-detect GPU/CPU
    language: null      # Auto-detect language
```

### Step 3: Create an Adapter

**Option A: Use the Pre-configured Adapter**

The `local-voice-chat` adapter is already configured in `config/adapters.yaml`:

```yaml
- name: "local-voice-chat"
  audio_provider: "whisper"
```

Create an API key for this adapter:

```bash
# Create API key
python utils/setup/create_api_key.py \
  --client-name "whisper-test" \
  --adapter "local-voice-chat"
```

**Option B: Create Your Own Adapter**

See [Creating a New Adapter](#creating-a-new-adapter) below.

### Step 4: Test It

```python
# Test script: test_whisper.py
import asyncio
from server.ai_services import AIServiceFactory, ServiceType

async def test_whisper():
    # Load config
    from server.utils.config_loader import load_config
    config = load_config()

    # Create Whisper service
    whisper = AIServiceFactory.create_service(
        ServiceType.AUDIO,
        'whisper',
        config
    )

    await whisper.initialize()
    print(f"✅ Whisper initialized with model: {whisper.model_size}")
    print(f"✅ Using device: {whisper.model.device}")

    # Test with audio file
    with open('test_audio.mp3', 'rb') as f:
        audio_data = f.read()

    text = await whisper.speech_to_text(audio_data)
    print(f"📝 Transcription: {text}")

    await whisper.cleanup()

asyncio.run(test_whisper())
```

Run the test:

```bash
python test_whisper.py
```

---

## Creating a New Adapter

### Example 1: Simple Voice Chat (STT Only)

Create a new adapter in `config/adapters.yaml`:

```yaml
- name: "my-voice-chat"
  enabled: true
  type: "passthrough"
  datasource: "none"
  adapter: "conversational"
  implementation: "implementations.passthrough.conversational.ConversationalImplementation"

  # Use Whisper for speech-to-text
  inference_provider: "ollama_cloud"
  model: "gpt-oss:120b"
  audio_provider: "whisper"  # ← Local Whisper for STT

  capabilities:
    retrieval_behavior: "none"
    formatting_style: "standard"
    supports_file_ids: false
    supports_session_tracking: true
    requires_api_key_validation: false
    optional_parameters:
      - "audio_input"      # Accept base64-encoded audio
      - "audio_format"     # Audio format (mp3, wav, etc.)
      - "language"         # Language code (optional)
      - "session_id"

  config:
    # Whisper-specific settings
    stt_model_size: "base"   # Options: tiny, base, small, medium, large-v3
    stt_device: "auto"       # Options: auto, cpu, cuda
    stt_language: null       # null = auto-detect, or "en", "es", etc.

    # Audio input
    audio_input_enabled: true
    audio_output_enabled: false  # Whisper doesn't support TTS
    return_text: true
```

**Create API Key:**

```bash
python utils/setup/create_api_key.py \
  --client-name "my-app" \
  --adapter "my-voice-chat"
```

### Example 2: Audio File Transcription

For transcribing uploaded audio files:

```yaml
- name: "whisper-file-transcription"
  enabled: true
  type: "retriever"
  datasource: "none"
  adapter: "file"
  implementation: "retrievers.implementations.file.file_retriever.FileVectorRetriever"

  # Use Whisper for transcription
  audio_provider: "whisper"
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

  config:
    # Storage configuration
    storage_backend: "filesystem"
    storage_root: "./uploads"
    max_file_size: 104857600  # 100MB for audio files

    # Whisper transcription
    enable_audio_transcription: true
    stt_model_size: "small"  # Higher quality for file transcription
    stt_device: "auto"
    transcription_language: null  # Auto-detect

    # Supported audio formats
    supported_types:
      - "audio/wav"
      - "audio/mpeg"
      - "audio/mp3"
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

### Example 3: Hybrid (Whisper STT + OpenAI TTS)

**Note:** Currently, adapters use a single `audio_provider`. To use Whisper for STT and OpenAI for TTS, you'll need separate adapters or extend the implementation.

**Workaround: Use Two Adapters**

```yaml
# Adapter 1: Input processing (Whisper STT)
- name: "voice-input"
  audio_provider: "whisper"
  config:
    audio_input_enabled: true
    audio_output_enabled: false

# Adapter 2: Output generation (OpenAI TTS)
- name: "voice-output"
  audio_provider: "openai"
  config:
    audio_input_enabled: false
    audio_output_enabled: true
    return_audio: true
    tts_voice: "alloy"
```

---

## Configuration Reference

### Global Configuration (config/sound.yaml)

```yaml
sounds:
  whisper:
    enabled: true

    # Model Selection
    # tiny: Fastest, least accurate (~1GB VRAM)
    # base: Good for development (~1GB VRAM) ← RECOMMENDED for testing
    # small: Production balance (~2GB VRAM) ← RECOMMENDED for production
    # medium: High quality (~5GB VRAM)
    # large-v3: Best accuracy (~10GB VRAM)
    model_size: "base"

    # Device Selection
    # auto: Use GPU if available, otherwise CPU
    # cpu: Force CPU (slower)
    # cuda: Force NVIDIA GPU (faster)
    device: "auto"

    # Compute Type
    # default: Standard precision
    # int8: 8-bit quantization (faster, less VRAM, slight quality loss)
    # float16: Half precision (faster on GPU)
    compute_type: "default"

    # Language Detection
    # null: Auto-detect language (recommended)
    # "en": Force English
    # "es": Force Spanish
    # etc. (99 languages supported)
    language: null

    # Task Type
    # transcribe: Convert speech to text in original language
    # translate: Convert speech to English text
    task: "transcribe"

    # Timeouts (local processing)
    timeout:
      connect: 5000
      total: 300000  # 5 minutes for long audio files

    retry:
      enabled: false
      max_retries: 1
```

### Per-Adapter Override

Override global settings in your adapter:

```yaml
audio_provider: "whisper"
config:
  stt_model_size: "small"      # Override global model_size
  stt_device: "cuda"           # Force GPU usage
  stt_language: "en"           # Force English detection
  stt_task: "translate"        # Translate to English
```

---

## Model Selection Guide

Choose the right model for your use case:

| Use Case | Model | Why |
|----------|-------|-----|
| **Development/Testing** | `base` | Fast iteration, good enough accuracy |
| **Production (CPU)** | `small` | Best CPU performance/accuracy balance |
| **Production (GPU)** | `small` or `medium` | Fast with high accuracy |
| **High Accuracy** | `large-v3` | Best results, slower |
| **Quick Demos** | `tiny` | Fastest, acceptable for demos |
| **Multilingual** | `small`+ | Better language detection |
| **Noisy Audio** | `medium`+ | Better at handling background noise |

**Performance Expectations:**

| Model | CPU (1 min audio) | GPU (1 min audio) |
|-------|------------------|------------------|
| tiny | ~30 sec | ~1 sec |
| base | ~60 sec | ~3 sec |
| small | ~3 min | ~8 sec |
| medium | ~10 min | ~15 sec |
| large-v3 | ~25 min | ~30 sec |

*Note: Times are approximate and vary by hardware*

---

## Usage Examples

### 1. Using the API Client (Browser)

```typescript
// clients/chat-app/src/example-whisper-usage.ts

// Record audio from microphone
async function recordAndTranscribe() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mediaRecorder = new MediaRecorder(stream);
  const chunks: Blob[] = [];

  mediaRecorder.ondataavailable = (e) => chunks.push(e.data);

  mediaRecorder.onstop = async () => {
    // Convert to base64
    const audioBlob = new Blob(chunks, { type: 'audio/webm' });
    const reader = new FileReader();

    reader.onloadend = async () => {
      const base64Audio = (reader.result as string).split(',')[1];

      // Send to Whisper adapter
      const api = await getApi();
      for await (const response of api.streamChat(
        '',  // Empty text message
        true,
        undefined,  // fileIds
        base64Audio,  // audio_input
        'webm',  // audio_format
        'en'  // language (optional)
      )) {
        console.log('Transcription:', response.text);
      }
    };

    reader.readAsDataURL(audioBlob);
  };

  // Record for 5 seconds
  mediaRecorder.start();
  setTimeout(() => {
    mediaRecorder.stop();
    stream.getTracks().forEach(track => track.stop());
  }, 5000);
}

// Usage
recordAndTranscribe();
```

### 2. Upload Audio File

```typescript
async function transcribeAudioFile(file: File) {
  const api = await getApi();

  // Upload file
  const uploadResult = await api.uploadFile(file);
  console.log('File uploaded:', uploadResult.file_id);

  // Whisper will automatically transcribe audio files
  // Query the transcribed content
  const results = await api.queryFile(
    uploadResult.file_id,
    'What was discussed?',
    10
  );

  console.log('Transcription results:', results);
}

// Usage
const audioFile = document.querySelector<HTMLInputElement>('#audio-upload').files[0];
transcribeAudioFile(audioFile);
```

### 3. Python Script

```python
# scripts/transcribe_audio.py
import asyncio
import sys
from server.ai_services import AIServiceFactory, ServiceType
from server.utils.config_loader import load_config

async def transcribe_file(audio_path: str, language: str = None):
    # Load config
    config = load_config()

    # Create Whisper service
    whisper = AIServiceFactory.create_service(
        ServiceType.AUDIO,
        'whisper',
        config
    )

    await whisper.initialize()

    # Read audio file
    with open(audio_path, 'rb') as f:
        audio_data = f.read()

    # Transcribe
    print(f"Transcribing {audio_path}...")
    text = await whisper.speech_to_text(audio_data, language=language)

    print(f"\nTranscription:\n{text}")

    await whisper.cleanup()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python transcribe_audio.py <audio_file> [language]")
        sys.exit(1)

    audio_path = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else None

    asyncio.run(transcribe_file(audio_path, language))
```

Run it:

```bash
python scripts/transcribe_audio.py recording.mp3
# Or with language specified:
python scripts/transcribe_audio.py recording.mp3 es
```

### 4. Batch Transcription

```python
# scripts/batch_transcribe.py
import asyncio
from pathlib import Path
from server.ai_services import AIServiceFactory, ServiceType
from server.utils.config_loader import load_config

async def batch_transcribe(audio_dir: str, output_file: str):
    config = load_config()
    whisper = AIServiceFactory.create_service(ServiceType.AUDIO, 'whisper', config)
    await whisper.initialize()

    audio_files = list(Path(audio_dir).glob('*.mp3'))
    results = {}

    for audio_file in audio_files:
        print(f"Processing {audio_file.name}...")

        with open(audio_file, 'rb') as f:
            text = await whisper.speech_to_text(f.read())

        results[audio_file.name] = text

    # Save results
    with open(output_file, 'w') as f:
        for filename, text in results.items():
            f.write(f"=== {filename} ===\n{text}\n\n")

    print(f"✅ Transcribed {len(results)} files to {output_file}")
    await whisper.cleanup()

asyncio.run(batch_transcribe('./audio_files', 'transcriptions.txt'))
```

---

## GPU Acceleration Setup

For **20x faster** transcription:

### NVIDIA GPU (CUDA)

```bash
# 1. Check if you have CUDA-capable GPU
nvidia-smi

# 2. Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# 3. Install Whisper
pip install openai-whisper

# 4. Test GPU usage
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

**Force GPU in config:**

```yaml
sounds:
  whisper:
    device: "cuda"  # Force GPU usage
```

### Apple Silicon (MPS - macOS)

```bash
# Install PyTorch with MPS support
pip install torch torchvision torchaudio

# Whisper will automatically use MPS if available
```

**Config:**

```yaml
sounds:
  whisper:
    device: "auto"  # Auto-detects MPS on Apple Silicon
```

---

## Troubleshooting

### Issue: "ImportError: No module named 'whisper'"

**Solution:**

```bash
# Install Whisper
pip install openai-whisper

# Or with torch profile
./install/install.sh --profile torch
```

### Issue: "CUDA out of memory"

**Solutions:**

1. **Use a smaller model:**

```yaml
whisper:
  model_size: "base"  # Instead of "large-v3"
```

2. **Use CPU:**

```yaml
whisper:
  device: "cpu"
```

3. **Enable quantization:**

```yaml
whisper:
  compute_type: "int8"  # Reduces VRAM usage
```

### Issue: "Transcription is very slow"

**Solutions:**

1. **Use GPU** (see GPU setup above)
2. **Use smaller model:**
   - `tiny` = 32x faster than large
   - `base` = 16x faster than large
3. **Specify language** (skips detection):

```yaml
whisper:
  language: "en"  # Instead of null
```

### Issue: "Poor accuracy / wrong words"

**Solutions:**

1. **Use larger model:**

```yaml
whisper:
  model_size: "medium"  # or "large-v3"
```

2. **Specify correct language:**

```yaml
whisper:
  language: "en"  # or "es", "fr", etc.
```

3. **Improve audio quality:**
   - Record at 16kHz or higher
   - Reduce background noise
   - Use better microphone

### Issue: "FFmpeg not found"

**Solution:**

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from: https://ffmpeg.org/download.html
# Add to PATH
```

---

## Advanced Configuration

### Language-Specific Settings

For better accuracy in specific languages:

```yaml
# Spanish transcription
- name: "whisper-spanish"
  audio_provider: "whisper"
  config:
    stt_model_size: "small"
    stt_language: "es"  # Force Spanish

# Auto-detect Asian languages
- name: "whisper-asian"
  audio_provider: "whisper"
  config:
    stt_model_size: "medium"  # Better for complex scripts
    stt_language: null  # Auto-detect
```

### Translation to English

```yaml
- name: "whisper-translate"
  audio_provider: "whisper"
  config:
    stt_model_size: "small"
    stt_task: "translate"  # Translate any language → English
```

**Note:** Whisper can only translate **to** English, not from English to other languages.

### Word-Level Timestamps

For applications needing precise timing:

```python
# Direct API usage (not through adapter)
result = whisper_service.model.transcribe(
    audio_path,
    word_timestamps=True
)

for segment in result['segments']:
    for word in segment['words']:
        print(f"{word['word']}: {word['start']:.2f}s - {word['end']:.2f}s")
```

---

## Best Practices

### 1. Model Selection by Use Case

```yaml
# Development
stt_model_size: "base"  # Fast iteration

# Production (High Volume)
stt_model_size: "small"  # Best balance

# Production (High Accuracy)
stt_model_size: "large-v3"  # Best quality

# Demos/Prototypes
stt_model_size: "tiny"  # Fastest
```

### 2. Device Selection

```yaml
# Automatic (recommended)
stt_device: "auto"  # Use GPU if available

# Force GPU (if you have one)
stt_device: "cuda"  # Fail if GPU not available

# Force CPU (reliable but slow)
stt_device: "cpu"  # Works everywhere
```

### 3. Language Handling

```yaml
# Unknown language (slower but works)
stt_language: null  # Auto-detect

# Known language (faster, more accurate)
stt_language: "en"  # English
stt_language: "es"  # Spanish
```

### 4. Error Handling

Always handle errors gracefully:

```python
try:
    text = await whisper.speech_to_text(audio_data)
except ImportError:
    # Whisper not installed
    print("Install Whisper: pip install openai-whisper")
except Exception as e:
    # Transcription failed
    print(f"Transcription error: {e}")
```

---

## Next Steps

1. **Start simple** - Use `base` model with `auto` device
2. **Test with sample audio** - Verify it works
3. **Optimize model size** - Based on your hardware
4. **Enable GPU** - For production performance
5. **Create production adapter** - With proper settings
6. **Monitor performance** - Adjust model size as needed

## Resources

- **Whisper GitHub:** https://github.com/openai/whisper
- **Supported Languages:** https://github.com/openai/whisper#available-models-and-languages
- **Model Card:** https://github.com/openai/whisper/blob/main/model-card.md
- **ORBIT Audio Docs:** `docs/audio-services-adapter-guide.md`
- **Technical Guide:** `docs/whisper-integration-guide.md`

---

## Summary

**Quick checklist:**

- [ ] Install: `pip install openai-whisper` or `./install/install.sh --profile torch`
- [ ] Install FFmpeg: `sudo apt install ffmpeg` (or brew/Windows)
- [ ] Enable in config: `sounds.whisper.enabled: true`
- [ ] Choose model: `base` for dev, `small` for prod
- [ ] Create adapter: Set `audio_provider: "whisper"`
- [ ] Create API key: `create_api_key.py --adapter "your-adapter"`
- [ ] Test it: Upload audio or send via API
- [ ] Optimize: Enable GPU for 20x speedup

You're ready to use local, free, offline speech-to-text! 🎉
