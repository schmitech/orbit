# ORBIT OpenAI Realtime Voice (test client)

Minimal browser client for the **`open-ai-real-time-voice-chat`** adapter: microphone → ORBIT WebSocket → [OpenAI Realtime API](https://developers.openai.com/api/docs/guides/realtime).

This mirrors **`clients/personaplex-voice`**, but:

- Uses **PCM16 mono 24 kHz** base64 chunks (OpenAI Realtime wire format), not float32.
- **API key is optional** if your ORBIT adapter does not require `api_key` on the WebSocket.
- Default adapter name: **`open-ai-real-time-voice-chat`**.

## Prerequisites

1. ORBIT server running.
2. `config/adapters.yaml` imports **`adapters/audio.yaml`**.
3. Adapter **`open-ai-real-time-voice-chat`** enabled in `audio.yaml`.
4. **`OPENAI_API_KEY`** set for the ORBIT server process.

## Quick start

```bash
cd clients/openai-realtime-voice
cp .env.example .env.local   # optional
npm install
npm run dev
```

Open **http://localhost:5175** (Vite default for this app).

Or: `chmod +x run.sh && ./run.sh`

## Configuration

| Env variable | Purpose |
|--------------|---------|
| `VITE_ORBIT_SERVER_URL` | WebSocket base, e.g. `ws://localhost:3000` |
| `VITE_ORBIT_API_URL` | HTTP base for admin validation (if different from WS host) |
| `VITE_ADAPTER_NAME` | Server adapter id (default: `open-ai-real-time-voice-chat`) |
| `VITE_API_KEY` | Optional; if set, validates via `/admin/api-keys/.../status` and may bind adapter from the key |
| `VITE_DISPLAY_SETTINGS` | `true` to show URL / adapter / key fields in the UI |

## Protocol

Same ORBIT JSON messages as `real-time-voice-chat` / PersonaPlex voice UI:

- **Client → server:** `audio_chunk` (base64 **PCM16 LE**), `ping`, `interrupt`
- **Server → client:** `connected`, `audio_chunk` (PCM16), `transcription`, `assistant_transcript_delta`, `done`, `error`, `pong`

## Production build

```bash
npm run build
npm run preview   # serves dist/
```

## Troubleshooting

### Voice sounds sped up (chipmunk) or cuts off mid-sentence

The client resamples OpenAI’s **24 kHz** PCM to your `AudioContext`’s **native sample rate** (often 48 kHz) *before* the playback worklet so duration and pitch stay correct.

If replies still sound truncated, on the server adapter set **`realtime_interrupt_response: false`** (default in `audio.yaml` for this adapter) so server VAD does not cancel the model when it thinks you started talking. You can also raise **`vad_silence_duration_ms`** so turns wait longer after you pause.

## License

Part of the ORBIT project.
