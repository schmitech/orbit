# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev        # Start Vite dev server with HMR
npm run build      # TypeScript check + Vite build → dist/
npm run lint       # ESLint (zero warnings policy)
npm run preview    # Serve the production build locally
npm test           # Run Node test suite (tests/**/*.test.js)
```

Running the full app (after build):
```bash
node bin/orbitchat.js --config orbitchat.yaml --open
```

## Architecture

OrbitChat is a full-stack chat client: a React SPA bundled by Vite served by a thin Express proxy server (`bin/orbitchat.js`). The proxy is the security boundary — API keys never reach the browser.

### Request flow

```
Browser → Express proxy (bin/orbitchat.js)
              ↓ injects X-API-Key from VITE_ADAPTER_KEYS env
          ORBIT backend server
```

The frontend sends an `X-Adapter-Name` header (not a secret). The proxy looks up the real key and injects it server-side before forwarding to the backend.

### State management

There are two tiers:

- **React Context** — `ChatContext`, `ThemeContext`, `SettingsContext`, `AgentHomeNavContext` — used for app-wide UI state.
- **Zustand** — `chatStore.ts` (the main streaming chat state machine), `loginPromptStore.ts`.

### Key files

| File | Role |
|------|------|
| `src/App.tsx` | Root: stacks all providers, decides home vs. chat layout |
| `src/apiClient.ts` | All backend calls (streaming SSE, files, threads, feedback, models) |
| `src/stores/chatStore.ts` | Core chat state machine — streaming, threading, feedback |
| `src/hooks/useChatAgentSelection.ts` | Adapter selection, conversation setup, file-upload state |
| `src/hooks/useVoice.ts` | STT recording + TTS playback |
| `src/utils/runtimeConfig.ts` | Reads config from `window.ORBIT_CHAT_CONFIG` or Vite's `define()` |
| `vite-plugin-orbitchat-config.ts` | Reads `orbitchat.yaml`, injects via Vite `define()`, generates sitemap |
| `bin/orbitchat.js` | Express server: static serving, rate limiting, API proxy |

### Chat streaming

Responses arrive as SSE (Server-Sent Events / JSON lines). `apiClient.ts → streamChat()` handles the reader loop. The `chatStore` manages partial content accumulation and the `request_id` used to cancel in-flight requests via `stopChat()`.

### Configuration

Runtime config comes from `orbitchat.yaml`. The Vite plugin reads it at build time and injects it via `define()`; the Express server reads it at startup and merges adapter keys from the `VITE_ADAPTER_KEYS` env var (JSON object: `{ adapterName: "key" }`).

### Authentication

Auth0 is optional. `src/auth/` wraps the Auth0 React SDK and exposes `useIsAuthenticated`, token retrieval, and a stable user ID. Rate limits differ for guests vs. authenticated users (configured in `orbitchat.yaml`).

## Conventions

- **No secrets in the browser.** API keys live only in the Express proxy via environment variables.
- **Adapter-based routing.** Each conversation targets one adapter; `X-Adapter-Name` header selects it.
- **Session IDs.** Each conversation gets a UUID session ID used for history and feedback endpoints.
- **TypeScript strict mode.** All new code must pass `tsc` without errors.
- **ESLint zero-warnings.** `npm run lint` must exit clean.
- **Component size.** `Message.tsx` and `MessageInput.tsx` are intentionally large (rich rendering + complex state). Keep new components focused.
