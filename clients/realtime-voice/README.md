# ORBIT Realtime Voice Bridge (test client)

Minimal browser client for ORBIT's real-time speech-to-speech (STS) adapters: microphone → ORBIT WebSocket → whichever STS provider the adapter is configured for. The client speaks one generic ORBIT wire protocol and doesn't care which provider is behind it — point `VITE_ADAPTER_NAME` at any of:

- **`open-ai-real-time-voice-chat`** → [OpenAI Realtime API](https://developers.openai.com/api/docs/guides/realtime)
- **`gemini-live-voice-chat`** → [Gemini Live API](https://ai.google.dev/gemini-api/docs/live-api)
- **`open-ai-real-time-translation`** → OpenAI Realtime speech-to-speech translation

All three (and any future STS adapter) are defined in `config/adapters/audio.yaml`.

- Uses **PCM16 mono 24 kHz** base64 chunks on the wire both ways — the server resamples to whatever the active provider actually needs.
- **API key is optional** if your ORBIT adapter does not require `api_key` on the WebSocket.

## Prerequisites

1. ORBIT server running.
2. `config/adapters.yaml` imports **`adapters/audio.yaml`**.
3. Your chosen adapter (e.g. `open-ai-real-time-voice-chat` or `gemini-live-voice-chat`) enabled in `audio.yaml`.
4. The matching provider credential set for the ORBIT server process — **`OPENAI_API_KEY`** for OpenAI Realtime adapters, **`GOOGLE_API_KEY`** (or `GEMINI_API_KEY`) for Gemini Live.

## Quick start

```bash
cd clients/realtime-voice
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
| `VITE_ADAPTER_NAME` | Server adapter id — any STS adapter, e.g. `open-ai-real-time-voice-chat` or `gemini-live-voice-chat` (no default; must be set, or entered in the UI with `VITE_DISPLAY_SETTINGS=true`) |
| `VITE_API_KEY` | Optional; if set, validates via `/admin/api-keys/.../status` and may bind adapter from the key |
| `VITE_DISPLAY_SETTINGS` | `true` to show URL / adapter / key fields in the UI |

## Protocol

ORBIT JSON messages used by this client:

- **Client → server:** `audio_chunk` (base64 **PCM16 LE**), `ping`, `interrupt`
- **Server → client:** `connected` (carries `mode`/`realtime_model` — the UI reads these into the Provider / Model readout), `audio_chunk` (PCM16), `transcription`, `assistant_transcript_delta`, `done`, `error`, `pong`

## UI

The panel shows a duplex signal strip — **IN** (your mic) above, **OUT** (the model's reply) below, sharing one scrolling timeline — so you can see both sides of the conversation moving in real time, regardless of which provider is connected. The Provider / Model readout above it is populated from the server's `connected` event, not hardcoded to any one backend.

## Production build

```bash
npm run build
npm run preview   # serves dist/
```

## Troubleshooting

### Voice sounds sped up (chipmunk) or cuts off mid-sentence

The client resamples the provider's **24 kHz** PCM reply to your `AudioContext`’s **native sample rate** (often 48 kHz) *before* the playback worklet so duration and pitch stay correct.

If replies still sound truncated, on the server adapter set **`realtime_interrupt_response: false`** (OpenAI Realtime adapters only; default in `audio.yaml`) so server VAD does not cancel the model when it thinks you started talking. You can also raise **`vad_silence_duration_ms`** so turns wait longer after you pause.

## License

Part of the ORBIT project.
