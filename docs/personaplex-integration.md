# PersonaPlex-7B Integration Technical Specification

## Overview

This document describes the integration of NVIDIA's PersonaPlex-7B full-duplex speech-to-speech model into ORBIT's audio adapter system. PersonaPlex enables real-time voice conversations where the AI can listen and speak simultaneously, supporting natural human conversational dynamics including backchannels, interruptions, and overlapping speech.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [System Requirements](#system-requirements)
3. [Deployment Options](#deployment-options)
4. [Configuration Guide](#configuration-guide)
5. [API Reference](#api-reference)
6. [Adapter Configuration](#adapter-configuration)
7. [Client Integration](#client-integration)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### Traditional vs Full-Duplex Voice

**Traditional Cascade (existing ORBIT voice adapters):**
```
User Audio → STT → LLM → TTS → AI Audio
     ↓         ↓     ↓     ↓
   [wait]   [wait] [wait] [wait]
```
- Turn-based: User speaks, then AI responds
- Higher latency: Multiple model invocations
- No interruption support without explicit handling

**PersonaPlex Full-Duplex:**
```
User Audio ←→ PersonaPlex ←→ AI Audio
              (unified model)
```
- Simultaneous: AI listens while speaking
- Lower latency: Single model handles everything
- Natural dynamics: Backchannels ("mm-hmm"), interruptions, overlap

### Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         ORBIT Server                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐    ┌─────────────────────────────┐    │
│  │   voice_routes.py   │    │  PersonaPlexWebSocketHandler │    │
│  │  /ws/voice/{adapter}│───▶│  - Protocol translation      │    │
│  └─────────────────────┘    │  - Sample rate conversion    │    │
│                              │  - Session management        │    │
│                              └──────────────┬──────────────┘    │
│                                             │                    │
│  ┌──────────────────────────────────────────┴──────────────┐    │
│  │                  PersonaPlexService                      │    │
│  │  ┌─────────────────────┐  ┌─────────────────────────┐   │    │
│  │  │  Proxy Mode         │  │  Embedded Mode          │   │    │
│  │  │  (Remote GPU)       │  │  (Local GPU)            │   │    │
│  │  └──────────┬──────────┘  └──────────┬──────────────┘   │    │
│  └─────────────┼─────────────────────────┼─────────────────┘    │
└────────────────┼─────────────────────────┼──────────────────────┘
                 │                         │
                 ▼                         ▼
    ┌────────────────────┐    ┌────────────────────────────┐
    │  PersonaPlex GPU   │    │  Local GPU (same machine)  │
    │  Server (Remote)   │    │  - Mimi codec              │
    │  - wss://host:8998 │    │  - PersonaPlex LM          │
    └────────────────────┘    │  - Voice embeddings        │
                              └────────────────────────────┘
```

---

## System Requirements

### ORBIT Server Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.10+ | 3.11+ |
| RAM | 4 GB | 8 GB |
| CPU | 2 cores | 4+ cores |

### PersonaPlex GPU Server Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | NVIDIA with 16GB VRAM | NVIDIA A100/H100 |
| CUDA | 12.0+ | 12.4+ |
| RAM | 32 GB | 64 GB |
| Storage | 50 GB | 100 GB (for model cache) |

**Tested GPU Configurations:**
- NVIDIA A100 (40GB/80GB) - Recommended for production
- NVIDIA H100 - Best performance
- NVIDIA RTX 4090 (24GB) - Development/small deployments
- NVIDIA RTX 3090 (24GB) - Development only

### Python Dependencies

```bash
# Required for ORBIT PersonaPlex integration
pip install aiohttp>=3.10.0      # WebSocket client for proxy mode
pip install sphn>=0.1.0          # Opus audio codec
pip install numpy>=1.26.0        # Audio processing

# Required for embedded mode (running model locally)
pip install torch>=2.2.0         # PyTorch
pip install huggingface_hub>=0.24.0  # Model download
pip install sentencepiece>=0.2.0 # Text tokenization

# Required for PersonaPlex server
pip install moshi               # PersonaPlex inference package
```

### System Dependencies

```bash
# Ubuntu/Debian
sudo apt install libopus-dev

# macOS
brew install opus

# Fedora/RHEL
sudo dnf install opus-devel
```

---

## Deployment Options

### Option 1: Proxy Mode (Recommended for Production)

In proxy mode, ORBIT connects to a separate PersonaPlex server. This is recommended because:
- GPU resources can be shared across multiple ORBIT instances
- PersonaPlex server can be scaled independently
- ORBIT server doesn't need GPU access

```
┌──────────────┐         ┌──────────────────────┐
│ ORBIT Server │  WSS    │ PersonaPlex Server   │
│ (No GPU)     │────────▶│ (GPU Required)       │
│ Port 3000    │         │ Port 8998            │
└──────────────┘         └──────────────────────┘
```

#### Step 1: Deploy PersonaPlex Server

**Using Docker (Recommended):**

```bash
# Clone PersonaPlex
cd /path/to/orbit/personaplex

# Create .env file with HuggingFace token
echo "HF_TOKEN=your_huggingface_token" > .env

# Build and run with Docker Compose
docker-compose up --build
docker-compose up -d
```

**Manual Deployment:**

```bash
# Install PersonaPlex
cd /path/to/orbit/personaplex/moshi
pip install -e .

# Download models (requires HF_TOKEN)
export HF_TOKEN=your_huggingface_token

# Start server with SSL
python -m moshi.server \
  --host 0.0.0.0 \
  --port 8998 \
  --ssl /path/to/ssl/certs

# Or without SSL (development only)
python -m moshi.server \
  --host 0.0.0.0 \
  --port 8998
```

#### Step 2: Configure ORBIT for Proxy Mode

Edit `config/personaplex.yaml`:

```yaml
personaplex:
  enabled: true
  mode: "proxy"

  proxy:
    server_url: "wss://your-gpu-server:8998/api/chat"
    ssl_verify: true  # Set to false for self-signed certs
    connection_timeout: 30
    reconnect_attempts: 3
```

#### Step 3: Start ORBIT Server

```bash
cd /path/to/orbit/server
python main.py
```

---

### Option 2: Embedded Mode (Single Server)

In embedded mode, PersonaPlex runs in the same process as ORBIT. This requires:
- GPU on the same machine as ORBIT
- Sufficient VRAM (16GB+)
- All PersonaPlex dependencies installed

```
┌────────────────────────────────────┐
│         ORBIT Server               │
│  ┌──────────────────────────────┐  │
│  │ PersonaPlex (Embedded)       │  │
│  │ - Uses local GPU             │  │
│  │ - Lowest latency             │  │
│  └──────────────────────────────┘  │
│              GPU                    │
└────────────────────────────────────┘
```

#### Step 1: Install Dependencies

```bash
# Install ORBIT with PersonaPlex support
cd /path/to/orbit/server
pip install -r requirements.txt

# Install PersonaPlex package
cd /path/to/orbit/personaplex/moshi
pip install -e .

# Set HuggingFace token
export HF_TOKEN=your_huggingface_token
```

#### Step 2: Configure ORBIT for Embedded Mode

Edit `config/personaplex.yaml`:

```yaml
personaplex:
  enabled: true
  mode: "embedded"

  embedded:
    hf_repo: "nvidia/personaplex-7b-v1"
    device: "cuda"
    cpu_offload: false  # Set true for low-VRAM systems
    warmup_on_start: true
```

#### Step 3: Start ORBIT Server

```bash
cd /path/to/orbit/server
python main.py
```

The first startup will download the model (~15GB) from HuggingFace.

---

## Configuration Guide

### Main Configuration File

**Location:** `config/personaplex.yaml`

```yaml
personaplex:
  # Master enable/disable switch
  enabled: true

  # Deployment mode: "proxy" or "embedded"
  mode: "proxy"

  # ==========================================================
  # Embedded Mode Settings
  # ==========================================================
  embedded:
    # HuggingFace model repository
    hf_repo: "nvidia/personaplex-7b-v1"

    # GPU device
    device: "cuda"  # or "cuda:0", "cuda:1", etc.

    # Enable CPU offload for systems with limited VRAM
    # Trades speed for memory - model partially runs on CPU
    cpu_offload: false

    # Path to voice prompt embeddings
    # null = auto-download from HuggingFace
    voice_prompt_dir: null

    # Warm up model on startup
    # Recommended for production to avoid first-request latency
    warmup_on_start: true
    warmup_iterations: 4

  # ==========================================================
  # Proxy Mode Settings
  # ==========================================================
  proxy:
    # PersonaPlex server WebSocket URL
    server_url: "wss://localhost:8998/api/chat"

    # SSL certificate verification
    # Set to false for self-signed certificates (dev only)
    ssl_verify: true

    # Connection settings
    connection_timeout: 30      # seconds
    reconnect_attempts: 3
    reconnect_delay: 1.0        # seconds between retries

  # ==========================================================
  # Audio Settings
  # ==========================================================
  audio:
    # PersonaPlex native sample rate (do not change)
    sample_rate: 32000

    # Frame rate (80ms frames)
    frame_rate: 12.5

    # Enable Opus codec for efficient streaming
    opus_enabled: true

  # ==========================================================
  # Default Persona Settings
  # ==========================================================
  defaults:
    # Default voice embedding
    voice_prompt: "NATF2.pt"

    # Default system prompt (empty = no default)
    text_prompt: ""

    # Generation parameters
    temperature: 0.8       # Audio generation temperature
    temperature_text: 0.7  # Text generation temperature
    top_k: 250             # Audio top-k sampling
    top_k_text: 25         # Text top-k sampling

  # ==========================================================
  # Session Management
  # ==========================================================
  session:
    # Maximum session duration
    max_duration: 3600  # 1 hour

    # Idle timeout before auto-close
    idle_timeout: 300   # 5 minutes

    # Maximum concurrent sessions (embedded mode)
    max_concurrent_sessions: 4
```

### Available Voices

PersonaPlex includes 16 pre-trained voice embeddings:

| Category | Voice ID | Description |
|----------|----------|-------------|
| Natural Female | NATF0.pt | Clear, professional |
| Natural Female | NATF1.pt | Warm, friendly |
| Natural Female | NATF2.pt | Bright, upbeat |
| Natural Female | NATF3.pt | Calm, soothing |
| Natural Male | NATM0.pt | Clear, professional |
| Natural Male | NATM1.pt | Warm, friendly |
| Natural Male | NATM2.pt | Deep, authoritative |
| Natural Male | NATM3.pt | Calm, steady |
| Variety Female | VARF0-4.pt | Expressive, dynamic voices |
| Variety Male | VARM0-4.pt | Expressive, dynamic voices |

---

## API Reference

### WebSocket Endpoint

```
ws://{host}:{port}/ws/voice/{adapter_name}
```

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `session_id` | No | Session ID for conversation history |
| `user_id` | No | User ID for tracking |
| `api_key` | No* | API key if adapter requires authentication |

*Required if adapter has `requires_api_key_validation: true`

**Example:**
```
ws://localhost:3000/ws/voice/personaplex-assistant?session_id=abc123
```

### Message Protocol

#### Client → Server Messages

**Audio Chunk:**
```json
{
  "type": "audio_chunk",
  "data": "<base64_encoded_pcm_audio>",
  "format": "pcm"
}
```

**Interrupt:**
```json
{
  "type": "interrupt"
}
```

**Ping:**
```json
{
  "type": "ping"
}
```

**End Session:**
```json
{
  "type": "end"
}
```

#### Server → Client Messages

**Connection Established:**
```json
{
  "type": "connected",
  "adapter": "personaplex-assistant",
  "session_id": "abc123",
  "mode": "full_duplex",
  "audio_format": "pcm",
  "sample_rate": 24000,
  "capabilities": {
    "full_duplex": true,
    "interruption": true,
    "backchannels": true
  }
}
```

**Audio Response:**
```json
{
  "type": "audio_chunk",
  "data": "<base64_encoded_pcm_audio>",
  "format": "pcm",
  "sample_rate": 24000,
  "chunk_index": 0
}
```

**Transcription (optional):**
```json
{
  "type": "transcription",
  "text": "Hello",
  "partial": true
}
```

**Interrupted:**
```json
{
  "type": "interrupted",
  "reason": "user_request"
}
```

**Error:**
```json
{
  "type": "error",
  "message": "Error description"
}
```

**Pong:**
```json
{
  "type": "pong"
}
```

### REST Endpoints

**Get Voice Service Status:**
```
GET /voice/status
```

**Response:**
```json
{
  "available": true,
  "global_audio_enabled": true,
  "adapters": [
    {
      "name": "personaplex-assistant",
      "type": "speech_to_speech",
      "enabled": true,
      "full_duplex": true,
      "mode": "speech_to_speech",
      "voice": "NATF2.pt"
    }
  ],
  "websocket_endpoint": "/ws/voice/{adapter_name}"
}
```

---

## Adapter Configuration

### Pre-configured Adapters

ORBIT includes several pre-configured PersonaPlex adapters in `config/adapters/personaplex.yaml`:

| Adapter Name | Voice | Use Case |
|--------------|-------|----------|
| `personaplex-assistant` | NATF2.pt | General-purpose helpful assistant |
| `personaplex-customer-service` | NATM1.pt | Customer support agent |
| `personaplex-language-tutor` | NATF1.pt | Language learning conversations |
| `personaplex-chat` | VARF2.pt | Casual conversation companion |
| `personaplex-interview-coach` | NATM2.pt | Job interview practice |
| `personaplex-storyteller` | VARM1.pt | Interactive storytelling |

### Creating Custom Adapters

Add to `config/adapters/personaplex.yaml`:

```yaml
adapters:
  - name: "my-custom-persona"
    enabled: true
    type: "speech_to_speech"
    datasource: "none"
    adapter: "personaplex"
    implementation: "ai_services.implementations.speech_to_speech.PersonaPlexService"

    capabilities:
      retrieval_behavior: "none"
      supports_realtime_audio: true
      supports_full_duplex: true
      supports_interruption: true
      supports_backchannels: true
      requires_api_key_validation: false

    persona:
      voice_prompt: "NATM0.pt"  # Choose from available voices
      text_prompt: |
        You are a knowledgeable science teacher named Dr. Chen. You explain
        complex scientific concepts in simple, engaging terms. Use analogies
        and examples from everyday life. Be encouraging when students ask
        questions, no matter how basic.

    config:
      websocket_enabled: true
      max_session_duration_seconds: 3600
      ping_interval_seconds: 30
      audio_chunk_size_ms: 80
      orbit_sample_rate: 24000
      personaplex_sample_rate: 32000
```

---

## Client Integration

### Python Client Example

```python
import asyncio
import json
import base64
import websockets
import pyaudio

class PersonaPlexClient:
    def __init__(self, url: str):
        self.url = url
        self.audio = pyaudio.PyAudio()
        self.sample_rate = 24000
        self.chunk_size = 2400  # 100ms at 24kHz

    async def connect(self):
        async with websockets.connect(self.url) as ws:
            # Wait for connection confirmation
            msg = await ws.recv()
            data = json.loads(msg)
            if data["type"] == "connected":
                print(f"Connected: {data}")

            # Start send/receive tasks
            await asyncio.gather(
                self.send_audio(ws),
                self.receive_audio(ws)
            )

    async def send_audio(self, ws):
        stream = self.audio.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )

        while True:
            audio_data = stream.read(self.chunk_size)
            await ws.send(json.dumps({
                "type": "audio_chunk",
                "data": base64.b64encode(audio_data).decode(),
                "format": "pcm"
            }))
            await asyncio.sleep(0.01)

    async def receive_audio(self, ws):
        stream = self.audio.open(
            format=pyaudio.paFloat32,
            channels=1,
            rate=self.sample_rate,
            output=True,
            frames_per_buffer=self.chunk_size
        )

        async for msg in ws:
            data = json.loads(msg)
            if data["type"] == "audio_chunk":
                audio = base64.b64decode(data["data"])
                stream.write(audio)

# Usage
client = PersonaPlexClient(
    "ws://localhost:3000/ws/voice/personaplex-assistant"
)
asyncio.run(client.connect())
```

### JavaScript/Browser Client Example

```javascript
class PersonaPlexClient {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.audioContext = new AudioContext({ sampleRate: 24000 });
  }

  async connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'connected') {
        console.log('Connected:', data);
        this.startMicrophone();
      } else if (data.type === 'audio_chunk') {
        this.playAudio(data.data);
      }
    };
  }

  async startMicrophone() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = this.audioContext.createMediaStreamSource(stream);
    const processor = this.audioContext.createScriptProcessor(2400, 1, 1);

    processor.onaudioprocess = (e) => {
      const audioData = e.inputBuffer.getChannelData(0);
      const base64 = this.float32ToBase64(audioData);

      this.ws.send(JSON.stringify({
        type: 'audio_chunk',
        data: base64,
        format: 'pcm'
      }));
    };

    source.connect(processor);
    processor.connect(this.audioContext.destination);
  }

  float32ToBase64(float32Array) {
    const bytes = new Uint8Array(float32Array.buffer);
    return btoa(String.fromCharCode(...bytes));
  }

  playAudio(base64Data) {
    const bytes = Uint8Array.from(atob(base64Data), c => c.charCodeAt(0));
    const float32 = new Float32Array(bytes.buffer);

    const buffer = this.audioContext.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);

    const source = this.audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioContext.destination);
    source.start();
  }
}

// Usage
const client = new PersonaPlexClient(
  'ws://localhost:3000/ws/voice/personaplex-assistant'
);
client.connect();
```

---

## Troubleshooting

### Common Issues

#### 1. Cannot access PersonaPlex UI from browser / Server not reachable externally

**Cause:** The Moshi server defaults to `--host localhost`, binding only to the container's internal IP (e.g., `172.18.0.2`) instead of all interfaces.

**Solution:**

Update both the Dockerfile and docker-compose.yaml to bind to `0.0.0.0`:

**Dockerfile** - Update the CMD:
```dockerfile
CMD ["/app/moshi/.venv/bin/python", "-m", "moshi.server", "--host", "0.0.0.0", "--ssl", "/app/ssl"]
```

**docker-compose.yaml** - Make port binding explicit:
```yaml
ports:
  - "0.0.0.0:8998:8998"
```

Then rebuild and restart:
```bash
docker-compose down
docker-compose up --build -d
```

After this change, you can connect via:
| Location | URL |
|----------|-----|
| Same machine | `https://localhost:8998` |
| Another machine (LAN/AWS) | `https://<host-ip>:8998` |

> **Note:** If using a self-signed certificate, your browser will show a security warning. You can proceed past it to access the Web UI.

#### 2. "PersonaPlex service unavailable"

**Cause:** PersonaPlex service not initialized or server unreachable.

**Solution:**
- Check `config/personaplex.yaml` has `enabled: true`
- For proxy mode: Verify PersonaPlex server is running and accessible
- For embedded mode: Ensure GPU is available and CUDA is installed
- Check logs for initialization errors

#### 3. "Connection refused" in proxy mode

**Cause:** PersonaPlex server not running or wrong URL.

**Solution:**
```bash
# Check if server is running
curl -k https://your-server:8998/health

# Check firewall allows port 8998
sudo ufw allow 8998

# Verify URL in config
cat config/personaplex.yaml | grep server_url
```

#### 4. "Out of memory" in embedded mode

**Cause:** Insufficient GPU VRAM.

**Solution:**
```yaml
# Enable CPU offload in config/personaplex.yaml
embedded:
  cpu_offload: true
```

Or use a smaller batch size / reduce concurrent sessions:
```yaml
session:
  max_concurrent_sessions: 2
```

#### 5. Audio quality issues

**Cause:** Sample rate mismatch or codec issues.

**Solution:**
- Ensure client sends audio at 24kHz sample rate
- Verify Opus codec is installed: `pip install sphn`
- Check audio format is float32 PCM

#### 6. High latency

**Cause:** Network latency or server overload.

**Solution:**
- For proxy mode: Deploy PersonaPlex server closer to ORBIT
- For embedded mode: Ensure GPU is not shared with other processes
- Reduce `audio_chunk_size_ms` for lower latency (at cost of efficiency)

### Debug Logging

Enable debug logging in ORBIT:

```python
# In server/main.py or via environment
import logging
logging.getLogger('services.chat_handlers.personaplex_websocket_handler').setLevel(logging.DEBUG)
logging.getLogger('ai_services.implementations.speech_to_speech').setLevel(logging.DEBUG)
```

### Health Checks

**Check PersonaPlex server health:**
```bash
curl -k https://your-server:8998/health
```

**Check ORBIT voice status:**
```bash
curl http://localhost:3000/voice/status
```

**Test WebSocket connection:**
```bash
# Using websocat
websocat ws://localhost:3000/ws/voice/personaplex-assistant
```

---

## Performance Tuning

### Proxy Mode Optimization

```yaml
proxy:
  # Increase timeout for slow networks
  connection_timeout: 60

  # More reconnect attempts for unstable connections
  reconnect_attempts: 5
  reconnect_delay: 2.0
```

### Embedded Mode Optimization

```yaml
embedded:
  # Reduce warmup for faster startup
  warmup_iterations: 2

  # Use specific GPU
  device: "cuda:0"
```

### Session Limits

```yaml
session:
  # Limit concurrent sessions to prevent OOM
  max_concurrent_sessions: 4

  # Shorter idle timeout to free resources
  idle_timeout: 120
```

---

## Security Considerations

1. **SSL/TLS:** Always use `wss://` in production for PersonaPlex server
2. **API Keys:** Enable `requires_api_key_validation` for public-facing adapters
3. **Network Isolation:** Run PersonaPlex server in private network when possible
4. **Rate Limiting:** Implement connection limits per IP/user
5. **Session Limits:** Configure `max_concurrent_sessions` to prevent resource exhaustion

---

## References

- [PersonaPlex GitHub Repository](https://github.com/nvidia/personaplex)
- [ORBIT Documentation](https://github.com/your-org/orbit)
- [HuggingFace Model Card](https://huggingface.co/nvidia/personaplex-7b-v1)
- [Opus Codec Documentation](https://opus-codec.org/)
