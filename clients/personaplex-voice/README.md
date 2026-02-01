# ORBIT PersonaPlex Voice Client

A simple full-duplex voice client for the ORBIT PersonaPlex adapter. This client enables real-time voice conversations where you can speak and listen simultaneously.

## Features

- **Full-duplex audio**: Speak and listen at the same time
- **Real-time visualization**: See audio levels for both your voice and AI responses
- **Transcription display**: View live text transcription of the conversation
- **Interruption support**: Click to interrupt the AI mid-speech
- **Simple UI**: Minimal interface focused on voice interaction

## Prerequisites

1. **ORBIT server** running with PersonaPlex adapter enabled
2. **PersonaPlex GPU server** (either embedded or proxy mode)
3. **Modern browser** with microphone support (Chrome, Firefox, Edge)

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

Then open http://localhost:5174 in your browser.

## Configuration

Before connecting, configure:

| Field | Description | Example |
|-------|-------------|---------|
| **Server URL** | ORBIT WebSocket endpoint | `ws://localhost:3000` |
| **Adapter Name** | PersonaPlex adapter name | `personaplex-assistant` |
| **API Key** | ORBIT API key (optional) | `personaplex` |

## Usage

1. Click **Connect** to start the conversation
2. Allow microphone access when prompted
3. Start speaking - the AI will respond in real-time
4. Click **Interrupt** to stop the AI mid-sentence
5. Click **Disconnect** to end the session

## Protocol

This client uses the ORBIT PersonaPlex JSON protocol over WebSocket:

### Client → Server

```json
{"type": "audio_chunk", "data": "<base64_pcm_float32>", "format": "pcm"}
{"type": "interrupt"}
{"type": "ping"}
{"type": "end"}
```

### Server → Client

```json
{"type": "connected", "adapter": "...", "session_id": "...", "mode": "full_duplex", ...}
{"type": "audio_chunk", "data": "<base64_pcm>", "format": "pcm", "sample_rate": 24000, ...}
{"type": "transcription", "text": "...", "partial": true}
{"type": "interrupted", "reason": "user_request"}
{"type": "pong"}
{"type": "error", "message": "..."}
```

## Audio Format

- **Sample Rate**: 24kHz (ORBIT handles resampling to/from PersonaPlex's 32kHz)
- **Channels**: Mono
- **Format**: Float32 PCM, base64-encoded
- **Chunk Duration**: 80ms

## Troubleshooting

### "Microphone access denied"
- Ensure you're using HTTPS or localhost
- Check browser permissions

### "Connection error"
- Verify ORBIT server is running
- Check the PersonaPlex adapter is enabled
- Ensure PersonaPlex GPU server is accessible

### No audio playback
- Check browser autoplay policies (may need user interaction first)
- Verify audio device is selected in browser settings

## Development

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Browser                          │
│  ┌─────────────┐      ┌─────────────────────────┐   │
│  │ Microphone  │─────▶│  ScriptProcessor        │   │
│  └─────────────┘      │  (capture 24kHz PCM)    │   │
│                       └───────────┬─────────────┘   │
│                                   │                 │
│                                   ▼                 │
│                       ┌─────────────────────────┐   │
│                       │  WebSocket Client       │   │
│                       │  (JSON + base64 audio)  │   │
│                       └───────────┬─────────────┘   │
│                                   │                 │
│                                   ▼                 │
│                       ┌─────────────────────────┐   │
│                       │  Audio Playback Queue   │   │
│                       │  (BufferSource nodes)   │   │
│                       └───────────┬─────────────┘   │
│                                   │                 │
│                                   ▼                 │
│                       ┌─────────────────────────┐   │
│                       │  Speakers               │   │
│                       └─────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                            │
                            ▼ WebSocket
┌─────────────────────────────────────────────────────┐
│                    ORBIT Server                     │
│  ┌─────────────────────────────────────────────┐   │
│  │  PersonaPlexWebSocketHandler                │   │
│  │  - JSON/base64 ←→ binary/Opus translation   │   │
│  │  - Sample rate: 24kHz ←→ 32kHz              │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                            │
                            ▼ WebSocket (binary)
┌─────────────────────────────────────────────────────┐
│                 PersonaPlex Server                  │
│  ┌─────────────────────────────────────────────┐   │
│  │  Speech-to-Speech Model (PersonaPlex-7B)    │   │
│  │  - Full-duplex conversation                 │   │
│  │  - Native: 32kHz Opus                       │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## License

Part of the ORBIT project.
