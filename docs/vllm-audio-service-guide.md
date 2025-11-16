# vLLM Audio Service Guide

This guide covers setting up and using vLLM to serve audio models like Orpheus TTS with the Orbit platform.

## Overview

The vLLM Audio Service enables high-quality text-to-speech using models like Orpheus TTS served via vLLM's OpenAI-compatible API. Orpheus generates audio tokens that are decoded using the SNAC (Scalable Neural Audio Codec) decoder.

## Prerequisites

- Python 3.8+
- CUDA-capable GPU (recommended) or CPU (slower)
- vLLM installed: `pip install vllm`
- SNAC codec: `pip install snac torch numpy` (included in Orbit's default dependencies)

## Starting the vLLM Server

### Basic Command

```bash
vllm serve canopylabs/orpheus-3b-0.1-ft --dtype auto --max-model-len 4096
```

### Optimized Command for GPU

```bash
vllm serve canopylabs/orpheus-3b-0.1-ft \
  --dtype auto \
  --quantization fp8 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.9 \
  --max-num-seqs 8 \
  --enable-prefix-caching
```

### CPU-Only Serving (Slower)

```bash
vllm serve canopylabs/orpheus-3b-0.1-ft \
  --dtype float32 \
  --max-model-len 4096 \
  --device cpu
```

### Remote Server

To serve on a specific host/port:

```bash
vllm serve canopylabs/orpheus-3b-0.1-ft \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype auto \
  --max-model-len 4096
```

## Orbit Configuration

Configure the vLLM audio service in `config/sound.yaml`:

```yaml
sound:
  provider: "vllm"  # Set vLLM as the default audio provider
  enabled: true

sounds:
  vllm:
    enabled: true
    host: "localhost"  # vLLM server host (or remote IP)
    port: 8000         # vLLM server port
    # TTS Configuration
    tts_model: "canopylabs/orpheus-3b-0.1-ft"
    tts_voice: "tara"  # Options: tara, leah, jess, leo, dan, mia, zac, zoe
    tts_format: "wav"
    # STT Configuration (if serving STT model)
    stt_model: null
    # Generation Parameters
    temperature: 0.6
    top_p: 0.95
    max_tokens: 1200  # Keep low for 4096 context window
    repetition_penalty: 1.1
    stream: false
    # Timeout Configuration
    timeout:
      connect: 15000   # 15 seconds
      total: 120000    # 2 minutes
    # Retry Configuration
    retry:
      enabled: true
      max_retries: 3
      initial_wait_ms: 1000
      max_wait_ms: 30000
      exponential_base: 2
```

## Orpheus Voice Options

Orpheus TTS supports the following voices:
- **tara** - Default female voice
- **leah** - Female voice
- **jess** - Female voice
- **mia** - Female voice
- **zoe** - Female voice
- **leo** - Male voice
- **dan** - Male voice
- **zac** - Male voice

## How It Works

1. **Text Input**: User sends text to convert to speech
2. **Prompt Construction**: Text is formatted as `voice: text` with special tokens
3. **Token Generation**: Orpheus generates audio tokens (`<custom_token_XXXXX>`)
4. **SNAC Decoding**: Audio tokens are decoded to PCM audio using SNAC codec
5. **WAV Wrapping**: PCM audio is wrapped in WAV format (24kHz, 16-bit mono)

## Troubleshooting

### Context Length Overflow (400 Error)

**Error**: "This model's maximum context length is 4096 tokens"

**Solution**: Reduce `max_tokens` in config. The default 1200 leaves room for input prompt tokens.

```yaml
max_tokens: 1200  # Conservative for 4096 context window
```

### TTS Generation Timeout

**Error**: "TTS generation timeout for sentence, skipping audio chunk"

**Solution**: Increase timeout in streaming handler (already set to 45s for batched sentences). For CPU inference, expect 10-30+ seconds per audio chunk.

### No Audio Output

**Error**: "TTS response does not contain audio tokens"

**Causes**:
1. Model not generating audio tokens - ensure `skip_special_tokens: False` is set (handled internally)
2. Wrong API endpoint - service uses completions API, not chat completions
3. Model not loaded correctly on vLLM server

**Verify with**:
```bash
curl http://localhost:8000/v1/models
```

### Voice Not Working

**Error**: "Voice 'alloy' is not a valid Orpheus voice"

**Solution**: Use Orpheus-specific voices (tara, leah, etc.). OpenAI voices (alloy, echo, etc.) are automatically mapped to the configured default.

### SNAC Model Loading Slow

**Issue**: First audio generation takes extra time

**Solution**: SNAC model is cached globally after first load. Subsequent requests reuse the cached model. For GPU acceleration:

```yaml
# In advanced config (if supported)
snac_device: "cuda"  # Use GPU for SNAC decoding
```

### Audio Quality Issues

**Symptoms**: Distorted, choppy, or cut-off audio

**Solutions**:
1. Ensure full audio is being decoded (not sliced)
2. Check sample rate matches (24kHz for SNAC)
3. Verify PCM format (16-bit signed integer)

## Optimization Tips

### vLLM Server Optimization

1. **Use FP8 Quantization** (if supported):
   ```bash
   --quantization fp8
   ```
   Reduces memory usage while maintaining quality.

2. **Increase GPU Memory Utilization**:
   ```bash
   --gpu-memory-utilization 0.9
   ```
   Uses more GPU memory for better performance.

3. **Enable Prefix Caching**:
   ```bash
   --enable-prefix-caching
   ```
   Caches common prefixes for faster inference.

4. **Batch Multiple Requests**:
   ```bash
   --max-num-seqs 8
   ```
   Processes multiple requests concurrently.

5. **Tensor Parallelism** (multi-GPU):
   ```bash
   --tensor-parallel-size 2
   ```
   Distributes model across GPUs.

### Orbit Configuration Optimization

1. **Sentence Batching**: Sentences are batched (default: 3) to reduce TTS API calls
   - Located in `streaming_handler.py`
   - Reduces delays between audio chunks

2. **Timeout Tuning**: Adjust based on your hardware
   - CPU: 45-60 seconds per batch
   - GPU: 15-30 seconds per batch

3. **Max Tokens**: Keep conservative (1200) to avoid context overflow
   - Orpheus generates ~7 tokens per audio frame
   - Longer text = more tokens needed

4. **Temperature**: Lower values (0.4-0.6) for consistent output
   - Higher values may introduce variability

### SNAC Decoding Optimization

1. **GPU Decoding**: Set `snac_device: "cuda"` for faster decoding
2. **Model Caching**: SNAC model is cached globally after first load
3. **Batch Size**: Larger batches amortize model loading overhead

## Performance Expectations

### CPU (Apple M1/Intel)
- First load: 5-10 seconds (SNAC model)
- Per sentence: 10-30 seconds
- Per 3-sentence batch: 30-60 seconds

### GPU (NVIDIA with CUDA)
- First load: 2-5 seconds
- Per sentence: 3-8 seconds
- Per 3-sentence batch: 10-20 seconds

### Remote Server
- Add network latency (~100-500ms)
- Audio data transfer time (depends on size)

## API Usage

### Direct API Call

```bash
curl -X POST http://localhost:3001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, how are you today?",
    "adapter": "your-adapter",
    "return_audio": true,
    "tts_voice": "tara"
  }'
```

### Streaming with Audio

```bash
curl -X POST http://localhost:3001/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me a short story",
    "adapter": "your-adapter",
    "stream": true,
    "return_audio": true,
    "tts_voice": "tara"
  }'
```

## Logs and Debugging

Enable verbose logging in `config/config.yaml`:

```yaml
general:
  verbose: true
```

This enables detailed logs including:
- SNAC model loading status
- Audio token extraction counts
- PCM audio byte sizes
- Streaming chunk information

## Common Issues Checklist

- [ ] vLLM server is running and accessible
- [ ] Model is loaded (check `/v1/models` endpoint)
- [ ] `max_tokens` is not too high (keep under 1500)
- [ ] Correct voice name (Orpheus voices, not OpenAI)
- [ ] SNAC dependencies installed (`snac`, `torch`, `numpy`)
- [ ] Sufficient timeout for your hardware
- [ ] Audio provider set to "vllm" in sound config

## Additional Resources

- [vLLM Documentation](https://docs.vllm.ai/)
- [Orpheus TTS Model](https://huggingface.co/canopylabs/orpheus-3b-0.1-ft)
- [SNAC Codec](https://github.com/hubertsiuzdak/snac)
