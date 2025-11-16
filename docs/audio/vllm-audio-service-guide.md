# vLLM Audio Service Guide

This guide covers setting up and using vLLM to serve audio models like Orpheus TTS with the Orbit platform.

## Overview

The vLLM Audio Service enables high-quality text-to-speech using models like Orpheus TTS served via vLLM's OpenAI-compatible API. Orpheus generates audio tokens that are decoded using the SNAC (Scalable Neural Audio Codec) decoder.

## Prerequisites

- Python 3.8+
- CUDA-capable GPU (recommended) or CPU (slower)
- vLLM installed: `pip install vllm`
- SNAC codec: `pip install snac torch numpy` (included in Orbit's default dependencies)
- FlashInfer (optional but recommended for better performance): `pip install git+https://github.com/flashinfer-ai/flashinfer.git`

## Starting the vLLM Server

### Installing FlashInfer (Recommended)

FlashInfer provides 20-40% faster token generation and better throughput for concurrent requests. Install it before starting vLLM:

```bash
# Install FlashInfer from source (recommended method)
pip install git+https://github.com/flashinfer-ai/flashinfer.git

# Verify installation - restart vLLM and check logs for FlashInfer availability
# You should NOT see: "FlashInfer is not available. Falling back to PyTorch-native implementation"
```

**Requirements:**
- CUDA 11.8+ or 12.1+
- Compatible NVIDIA GPU (compute capability 7.0+)
- CUDA toolkit installed

**Benefits:**
- Faster attention computation
- Better GPU utilization
- Lower latency per request
- Improved throughput for parallel requests

### Basic Command

```bash
vllm serve canopylabs/orpheus-3b-0.1-ft --dtype auto --max-model-len 4096
```

**Note:** This basic command processes requests sequentially (one at a time). For streaming audio, use the optimized command below.

### Optimized Command for GPU (Recommended)

This is the recommended command for production use with FP8 quantization and parallel processing:

```bash
vllm serve canopylabs/orpheus-3b-0.1-ft \
  --dtype auto \
  --quantization fp8 \
  --enable-chunked-prefill \
  --max_model_len 4096 \
  --gpu-memory-utilization 0.85 \
  --max-num-seqs 8
```

**Key Parameters Explained:**
- `--dtype auto`: Automatically selects optimal data type
- `--quantization fp8`: FP8 quantization reduces memory by ~50% while maintaining quality
- `--enable-chunked-prefill`: Optimizes long prompt processing (better for streaming)
- `--max_model_len 4096`: Matches Orpheus model's context window
- `--gpu-memory-utilization 0.85`: Uses 85% of GPU memory (balance between performance and stability)
- `--max-num-seqs 8`: **CRITICAL** - Enables parallel processing of 8 concurrent requests (default is 1, causing sequential delays)

**Tuning `--max-num-seqs` based on GPU memory:**
- 8GB GPU: `--max-num-seqs 4`
- 16GB GPU: `--max-num-seqs 8` (recommended)
- 24GB+ GPU: `--max-num-seqs 12`

**Note:** Without `--max-num-seqs`, vLLM processes requests sequentially, causing 10+ second delays between audio chunks. This parameter is essential for streaming audio performance.

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
    # vLLM-specific optimizations
    max_concurrent_requests: 4  # Match vLLM server's --max-num-seqs (or lower)
    request_queue_size: 10
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

1. **Install FlashInfer** (Critical for performance):
   ```bash
   pip install git+https://github.com/flashinfer-ai/flashinfer.git
   ```
   Provides 20-40% faster token generation and better concurrent request handling.

2. **Enable Parallel Processing** (MOST IMPORTANT):
   ```bash
   --max-num-seqs 8
   ```
   **This is critical!** Without this, vLLM processes requests sequentially, causing 10+ second delays between audio chunks. With FP8 quantization, you can typically run 8-12 concurrent sequences.

3. **Use FP8 Quantization**:
   ```bash
   --quantization fp8
   ```
   Reduces memory usage by ~50% while maintaining quality, allowing more concurrent requests.

4. **Enable Chunked Prefill**:
   ```bash
   --enable-chunked-prefill
   ```
   Optimizes long prompt processing, especially beneficial for streaming scenarios.

5. **Optimize GPU Memory Utilization**:
   ```bash
   --gpu-memory-utilization 0.85
   ```
   Balance between performance (0.9) and stability (0.7). 0.85 is recommended for production.

6. **Tensor Parallelism** (multi-GPU):
   ```bash
   --tensor-parallel-size 2
   ```
   Distributes model across multiple GPUs for larger models or higher throughput.

### Monitoring vLLM Performance

Check GPU utilization and memory:
```bash
watch -n 1 nvidia-smi
```

Monitor vLLM logs for:
- Average generation throughput (tokens/s)
- Number of running/waiting requests
- GPU KV cache usage
- Prefix cache hit rate

If you see OOM (Out of Memory) errors:
- Reduce `--max-num-seqs`
- Lower `--gpu-memory-utilization` to 0.7
- Ensure FP8 quantization is enabled

### Orbit Configuration Optimization

1. **Parallel Audio Generation**: The streaming handler automatically matches vLLM's `max_concurrent_requests` setting
   - Generates multiple audio chunks in parallel
   - Reduces lag between chunks significantly
   - Configured in `streaming_handler.py` (auto-detected from config)

2. **Sentence Batching**: Sentences are batched (default: 3) to reduce TTS API calls
   - Located in `streaming_handler.py`
   - Reduces number of requests to vLLM
   - Balances latency vs. API call overhead

3. **Early Remaining Audio Generation**: Remaining audio starts generating immediately when stream ends
   - Non-blocking background generation
   - Eliminates 10+ second delays for final audio chunks
   - Automatically handled by streaming handler

4. **Timeout Tuning**: Adjust based on your hardware
   - CPU: 45-60 seconds per batch
   - GPU with FlashInfer: 5-15 seconds per batch
   - GPU without FlashInfer: 10-20 seconds per batch

5. **Max Tokens**: Keep conservative (1200) to avoid context overflow
   - Orpheus generates ~7 tokens per audio frame
   - Longer text = more tokens needed
   - With FP8 quantization, you have more headroom

6. **Temperature**: Lower values (0.4-0.6) for consistent output
   - Higher values may introduce variability
   - Default 0.6 works well for most use cases

7. **HTTP Connection Pooling**: Optimized for high concurrency
   - 50 keepalive connections
   - 200 max connections
   - 600s connection reuse
   - Automatic retry with exponential backoff

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

**Without FlashInfer:**
- First load: 2-5 seconds
- Per sentence: 3-8 seconds
- Per 3-sentence batch: 10-20 seconds

**With FlashInfer (Recommended):**
- First load: 2-5 seconds
- Per sentence: 2-5 seconds (20-40% faster)
- Per 3-sentence batch: 6-12 seconds
- Parallel processing (8 concurrent): Near-linear scaling

**With Optimized Settings (FP8 + FlashInfer + max-num-seqs 8):**
- Parallel chunks: 8 concurrent requests
- Average latency per chunk: 3-8 seconds
- Total throughput: 8-16 chunks per minute
- Lag between chunks: <1 second (vs. 10+ seconds sequential)

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
- [ ] **`--max-num-seqs` is set (critical for parallel processing)**
- [ ] FlashInfer installed (check logs for "FlashInfer is not available" warning)
- [ ] `max_tokens` is not too high (keep under 1500)
- [ ] Correct voice name (Orpheus voices, not OpenAI)
- [ ] SNAC dependencies installed (`snac`, `torch`, `numpy`)
- [ ] Sufficient timeout for your hardware
- [ ] Audio provider set to "vllm" in sound config
- [ ] `max_concurrent_requests` in config matches vLLM's `--max-num-seqs`

## Performance Troubleshooting

### Sequential Processing (10+ second delays)

**Symptoms:** Audio chunks arrive one at a time with long delays

**Causes:**
1. Missing `--max-num-seqs` parameter (default is 1)
2. GPU memory too low for concurrent requests
3. vLLM server overloaded

**Solutions:**
1. Add `--max-num-seqs 8` to vLLM command
2. Enable FP8 quantization to reduce memory
3. Monitor GPU memory: `watch -n 1 nvidia-smi`
4. Reduce `--max-num-seqs` if OOM errors occur

### FlashInfer Not Available

**Warning:** "FlashInfer is not available. Falling back to PyTorch-native implementation"

**Solution:**
```bash
pip install git+https://github.com/flashinfer-ai/flashinfer.git
# Restart vLLM server
```

**Note:** If installation fails, vLLM will still work but be 20-40% slower. Check CUDA version compatibility.

## Additional Resources

- [vLLM Documentation](https://docs.vllm.ai/)
- [Orpheus TTS Model](https://huggingface.co/canopylabs/orpheus-3b-0.1-ft)
- [SNAC Codec](https://github.com/hubertsiuzdak/snac)
- [FlashInfer GitHub](https://github.com/flashinfer-ai/flashinfer)

## Quick Start Summary

1. **Install FlashInfer** (recommended):
   ```bash
   pip install git+https://github.com/flashinfer-ai/flashinfer.git
   ```

2. **Start vLLM with optimized settings**:
   ```bash
   vllm serve canopylabs/orpheus-3b-0.1-ft \
     --dtype auto \
     --quantization fp8 \
     --enable-chunked-prefill \
     --max_model_len 4096 \
     --gpu-memory-utilization 0.85 \
     --max-num-seqs 8
   ```

3. **Configure Orbit** (`config/sound.yaml`):
   ```yaml
   sounds:
     vllm:
       max_concurrent_requests: 4  # Match or lower than --max-num-seqs
   ```

4. **Monitor performance**: Check vLLM logs and `nvidia-smi` for GPU utilization

**Expected Results:**
- Parallel audio generation (no sequential delays)
- 3-8 second latency per chunk
- Smooth streaming with minimal gaps
- 20-40% faster with FlashInfer
