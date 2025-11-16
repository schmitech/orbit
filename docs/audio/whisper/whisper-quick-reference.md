# Whisper Quick Reference

One-page reference for using Whisper in ORBIT.

## Installation

```bash
# Option 1: With torch profile (recommended)
./install/install.sh --profile torch

# Option 2: Manual
pip install openai-whisper
sudo apt install ffmpeg  # or brew install ffmpeg
```

## Model Selection

| Model | Speed | VRAM | Use Case |
|-------|-------|------|----------|
| `tiny` | 32x | ~1GB | Quick demos |
| `base` | 16x | ~1GB | **Development** ⭐ |
| `small` | 6x | ~2GB | **Production** ⭐ |
| `medium` | 2x | ~5GB | High quality |
| `large-v3` | 1x | ~10GB | Best accuracy |

## Basic Adapter Configuration

```yaml
- name: "my-whisper-adapter"
  enabled: true
  type: "passthrough"
  adapter: "conversational"
  audio_provider: "whisper"  # ← Use Whisper

  config:
    stt_model_size: "base"   # Model choice
    stt_device: "auto"       # auto/cpu/cuda
    stt_language: null       # null = auto-detect
    audio_input_enabled: true
```

## Global Configuration

```yaml
# config/sound.yaml
sounds:
  whisper:
    enabled: true
    model_size: "base"
    device: "auto"
    language: null
```

## Usage Examples

### Python

```python
from server.ai_services import AIServiceFactory, ServiceType
from server.utils.config_loader import load_config

config = load_config()
whisper = AIServiceFactory.create_service(ServiceType.AUDIO, 'whisper', config)
await whisper.initialize()

# Transcribe
with open('audio.mp3', 'rb') as f:
    text = await whisper.speech_to_text(f.read())

print(text)
```

### TypeScript (Browser)

```typescript
// Record audio
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
const mediaRecorder = new MediaRecorder(stream);
const chunks: Blob[] = [];

mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
mediaRecorder.onstop = async () => {
  const blob = new Blob(chunks, { type: 'audio/webm' });
  const base64 = await blobToBase64(blob);

  // Send to Whisper adapter
  for await (const response of api.streamChat(
    '', true, undefined,
    base64,  // audio_input
    'webm',  // audio_format
    'en'     // language (optional)
  )) {
    console.log(response.text);
  }
};

mediaRecorder.start();
setTimeout(() => mediaRecorder.stop(), 5000);
```

## GPU Acceleration

```bash
# Install PyTorch with CUDA
pip install torch --index-url https://download.pytorch.org/whl/cu118

# Force GPU in config
sounds:
  whisper:
    device: "cuda"
```

**Performance:** 20x faster on GPU vs CPU

## Common Issues

| Issue | Solution |
|-------|----------|
| "No module named whisper" | `pip install openai-whisper` |
| "CUDA out of memory" | Use smaller model or `device: "cpu"` |
| Slow transcription | Enable GPU or use `tiny`/`base` model |
| Poor accuracy | Use larger model (`medium`/`large-v3`) |
| "FFmpeg not found" | `sudo apt install ffmpeg` |

## Supported Languages

99 languages including: English, Spanish, French, German, Italian, Portuguese, Dutch, Russian, Arabic, Chinese, Japanese, Korean, Hindi, and more.

**Auto-detection:** `language: null`
**Specific language:** `language: "en"` (faster, more accurate)

## Translation

Whisper can translate any language **to English only**:

```python
# Translate French audio → English text
text = await whisper.translate(audio_data, source_language='fr')
```

## API Comparison

| Feature | Whisper (Local) | OpenAI API |
|---------|----------------|------------|
| Cost | **FREE** | $0.006/min |
| Privacy | **Local** | Cloud |
| Internet | **Not needed** | Required |
| Setup | `pip install` | API key |
| Speed (GPU) | Fast | Fast |
| Speed (CPU) | Slow | Fast |

## Key Points

✅ Free, local, offline speech-to-text
✅ 99 languages with auto-detection
✅ 5 model sizes for different needs
✅ GPU acceleration supported
✅ Same accuracy as OpenAI API
❌ STT only (no TTS)
❌ Can only translate to English

## Resources

- Setup Guide: `docs/whisper-setup-guide.md`
- Technical Guide: `docs/whisper-integration-guide.md`
- Audio Adapters: `docs/audio-services-adapter-guide.md`
- GitHub: https://github.com/openai/whisper
