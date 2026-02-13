# ORBIT Mobile Chat

A native-feeling iOS chat app for the [ORBIT](https://github.com/schmitech/orbit) server, built with React Native (Expo). It provides a ChatGPT-style experience with a conversation list, real-time streaming chat, markdown rendering, and light/dark theming.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Screens](#screens)
- [Key Concepts](#key-concepts)
- [Testing on a Physical Device](#testing-on-a-physical-device)
- [Publishing to the App Store](#publishing-to-the-app-store)
- [Troubleshooting](#troubleshooting)
- [Feature Roadmap](#feature-roadmap)

---

## Prerequisites

Before you begin, make sure you have the following installed:

| Tool | Version | How to install |
|------|---------|----------------|
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) or `brew install node` |
| **npm** | 9+ | Comes with Node.js |
| **Xcode** | 15+ | Mac App Store (required for iOS Simulator) |
| **Xcode Command Line Tools** | — | `xcode-select --install` |
| **iOS Simulator** | iOS 17+ | Open Xcode > Settings > Platforms > download an iOS runtime |
| **Watchman** (optional) | — | `brew install watchman` (improves file watching performance) |

You also need access to a running **ORBIT server** and a valid **API key**.

---

## Quick Start

```bash
# 1. Navigate to the project directory
cd orbit-mobile

# 2. Install dependencies
npm install

# 3. Create your environment file
cp .env.example .env

# 4. Edit .env with your ORBIT server details
#    EXPO_PUBLIC_ORBIT_HOST=https://your-orbit-server.example.com
#    EXPO_PUBLIC_ORBIT_API_KEY=your-api-key-here

# 5. Open the iOS Simulator manually first
open -a Simulator

# 6. Start the Expo dev server
npx expo start --tunnel --clean

# 7. Press 'i' to open in iOS Simulator
```

> **macOS permissions note:** If pressing `i` throws an error like `"Not authorized to send Apple events to System Events"`, your terminal doesn't have Automation permission to launch the Simulator. To fix this, go to **System Settings > Privacy & Security > Automation**, find your terminal app (Terminal, iTerm2, or VS Code), and enable the toggle for **System Events**. Alternatively, just open the Simulator manually first with `open -a Simulator` (step 5 above) before starting Expo — this avoids the permission issue entirely.

---

## Configuration

The app requires two environment variables to connect to your ORBIT server. These are injected at build time via Expo's `EXPO_PUBLIC_*` convention.

### Setting up the `.env` file

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
# The base URL of your ORBIT server (no trailing slash)
EXPO_PUBLIC_ORBIT_HOST=https://your-orbit-server.example.com

# Your ORBIT API key
EXPO_PUBLIC_ORBIT_API_KEY=your-api-key-here

# Enable text-to-speech audio output (requires server-side TTS support)
EXPO_PUBLIC_ENABLE_AUDIO_OUTPUT=false
```

### How config injection works

The `src/config/env.ts` module reads these variables via `process.env.EXPO_PUBLIC_*`. Expo inlines them at build time, so they are baked into the JavaScript bundle. The app will throw a descriptive error on launch if either variable is missing.

### Important notes on environment variables

- **Changes to `.env` require a restart.** After editing `.env`, stop the dev server (`Ctrl+C`) and run `npx expo start` again. Metro does not hot-reload environment variables.
- **The `.env` file is gitignored.** It will not be committed to version control. This is intentional — never commit API keys.
- **For CI/CD builds**, set `EXPO_PUBLIC_ORBIT_HOST`, `EXPO_PUBLIC_ORBIT_API_KEY`, and `EXPO_PUBLIC_ENABLE_AUDIO_OUTPUT` as pipeline secrets (e.g., GitHub Actions secrets or EAS Build secrets).

---

## Running the App

### Development (Expo Go or Dev Client)

```bash
# Start the Metro bundler
npx expo start

# Then press one of:
#   i — open in iOS Simulator
#   a — open on Android emulator (if configured)
#   w — open in web browser
```

### Development Build (native)

If you need native modules not supported by Expo Go, create a development build:

```bash
# Generate native iOS project and run on simulator
npx expo run:ios

# Or for a physical device (requires Apple Developer account)
npx expo run:ios --device
```

### Production Build

```bash
# Using EAS Build (recommended for distribution)
npx eas build --platform ios

# Or export a static bundle for self-hosting
npx expo export --platform ios
```

### Available npm scripts

| Command | Description |
|---------|-------------|
| `npm start` | Start the Expo dev server |
| `npm run ios` | Start and open in iOS Simulator |
| `npm run android` | Start and open on Android emulator |
| `npm run web` | Start and open in browser |

---

## Project Structure

```
orbit-mobile/
├── app/                                # Expo Router file-based routing
│   ├── _layout.tsx                     # Root stack navigator, hydration, gesture setup
│   ├── (tabs)/                         # Tab navigator group
│   │   ├── _layout.tsx                 # Tab bar config (Chats + Settings tabs)
│   │   ├── index.tsx                   # Conversations list screen
│   │   └── settings.tsx                # Settings screen
│   └── chat/
│       └── [id].tsx                    # Chat view screen (dynamic route)
├── src/
│   ├── api/
│   │   ├── client.ts                   # Singleton ApiClient wrapper
│   │   └── orbitApi.ts                 # ORBIT API client (local copy from node-api)
│   ├── components/
│   │   ├── ChatBubble.tsx              # User/assistant message bubble
│   │   ├── ChatInput.tsx               # Bottom input bar with send/stop/mic/speaker buttons
│   │   ├── ConversationCard.tsx        # Conversation list item
│   │   ├── EmptyState.tsx              # Empty state placeholder
│   │   ├── MarkdownContent.tsx         # Markdown renderer for assistant messages
│   │   ├── StreamingCursor.tsx         # Animated bouncing dots during streaming
│   │   └── SwipeableRow.tsx            # Swipe-to-delete wrapper
│   ├── config/
│   │   ├── constants.ts                # App-wide constants (timings, limits, keys)
│   │   └── env.ts                      # Environment variable loader
│   ├── hooks/
│   │   ├── useTheme.ts                 # Theme management hook (light/dark/system)
│   │   └── useVoice.ts                 # Speech-to-text hook (expo-speech-recognition)
│   ├── stores/
│   │   ├── chatStore.ts                # Zustand state store (conversations, streaming, audio)
│   │   └── themeStore.ts               # Zustand theme persistence store
│   ├── theme/
│   │   └── colors.ts                   # Light and dark color palettes
│   ├── types/
│   │   └── index.ts                    # TypeScript interfaces (Message, Conversation, etc.)
│   └── utils/
│       ├── audioPlayer.ts              # Audio chunk streaming manager (TTS playback)
│       ├── session.ts                  # ID generators for sessions and messages
│       └── storage.ts                  # AsyncStorage persistence helpers
├── assets/                             # App icon, splash screen images
├── app.json                            # Expo configuration
├── package.json                        # Dependencies and scripts
├── tsconfig.json                       # TypeScript configuration
├── .env.example                        # Environment variable template
└── .gitignore
```

---

## Architecture

### Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Framework** | Expo SDK 54 + React Native 0.81 | Cross-platform native app |
| **Routing** | Expo Router 6 | File-based navigation (stack + tabs) |
| **State** | Zustand 5 | Lightweight state management |
| **Persistence** | AsyncStorage | Local conversation storage |
| **Lists** | FlashList 2 | High-performance virtualized lists |
| **Animations** | Reanimated 4 | Streaming cursor animation |
| **Gestures** | Gesture Handler 2 | Swipe-to-delete |
| **Markdown** | react-native-markdown-display | Rich text rendering in chat |
| **Audio Playback** | expo-audio | TTS audio chunk streaming and playback |
| **Speech Recognition** | expo-speech-recognition | Voice input (speech-to-text) |
| **File System** | expo-file-system | Temp file management for audio chunks |
| **API Client** | `@schmitech/chatbot-api` (local copy) | SSE streaming, all ORBIT endpoints |

### Data Flow

```
User types message
        │
        v
  ChatInput.tsx ──onSend──> chatStore.sendMessage()
                                    │
                       ┌────────────┤
                       v            v
              Add user message   Create empty assistant
              to conversation    message (isStreaming: true)
                                    │
                                    v
                          ApiClient.streamChat()
                          (SSE over fetch + ReadableStream)
                                    │
                            ┌───────┴───────┐
                            v               v
                      Text chunks      Done signal
                            │               │
                            v               v
                   appendToLastMessage()  Flush buffer,
                   (batched at 32ms)     set isStreaming: false,
                            │            persist to AsyncStorage
                            v
                      React re-render
                      (ChatBubble updates)
```

### API Client

The file `src/api/orbitApi.ts` is a local copy of the ORBIT TypeScript API client (`@schmitech/chatbot-api` v2.1.6). It is zero-dependency, using only the Fetch API and `ReadableStream` for SSE streaming. The Node.js-specific connection pooling code has been removed for React Native compatibility.

The singleton wrapper in `src/api/client.ts` creates a single `ApiClient` instance configured from the environment variables. Key methods used by the app:

| Method | Purpose |
|--------|---------|
| `streamChat()` | Async generator yielding SSE chunks (text, audio_chunk, request_id, done) |
| `stopChat(sessionId, requestId)` | Server-side cancellation of an active stream |
| `validateApiKey()` | Checks if the API key is valid and active |
| `getAdapterInfo()` | Returns adapter name, model, and client name |
| `setSessionId()` | Sets the session ID for conversation isolation |

---

## Screens

### 1. Conversations List (Chats tab)

The home screen showing all conversations sorted by most recent activity.

- **New chat:** Tap the blue "+" floating action button in the bottom-right corner
- **Open chat:** Tap any conversation to resume it
- **Delete chat:** Swipe a conversation to the left to reveal the delete button. A confirmation alert will appear before deletion.
- **Empty state:** When there are no conversations, a placeholder message is shown

Each conversation card displays:
- Conversation title (first message, truncated to 50 characters)
- Relative timestamp ("Just now", "5m ago", "2h ago", "3d ago")
- Preview of the last message (truncated to 80 characters)
- Model name, if available

### 2. Chat View

The main chat interface where you interact with the ORBIT server.

- **Send a message:** Type in the bottom input bar and tap the blue arrow button
- **Voice input:** Tap the microphone button to dictate a message using speech-to-text. The mic icon turns red while listening. Speech is transcribed and placed in the text input field. After 2 seconds of silence, recognition stops automatically.
- **Audio output (TTS):** When `EXPO_PUBLIC_ENABLE_AUDIO_OUTPUT=true`, a speaker toggle button appears to the left of the text input. Tap it to enable/disable audio responses per conversation. When enabled, the server streams audio chunks that play in real-time as the text response arrives.
- **Stop generation:** While the assistant is responding, the send button becomes a red stop button. Tap it to cancel the response. This sends both a local abort signal and a server-side cancellation request. Audio playback also stops.
- **Streaming:** Assistant responses appear incrementally as they are received from the server. Animated bouncing dots indicate streaming is in progress.
- **Markdown:** Assistant responses render markdown including headings, bold/italic, code blocks (with syntax highlighting), lists, tables, blockquotes, and links.
- **Copy message:** Long-press on any assistant message to copy its content to the clipboard.
- **Keyboard handling:** The input bar moves up smoothly when the keyboard appears (iOS `KeyboardAvoidingView`).
- **Auto-scroll:** The message list automatically scrolls to the bottom when new content arrives.

### 3. Settings

App configuration and status information.

- **Connection status:** Shows a green or red dot indicating whether the ORBIT server is reachable. Tap to re-check. When connected, displays the client name, adapter name, and model.
- **Appearance:** Toggle between Light, Dark, and System theme. The selection is persisted across app launches.
- **Audio:** Shows availability of text-to-speech (controlled by `EXPO_PUBLIC_ENABLE_AUDIO_OUTPUT`) and voice input (always available).
- **Data:** Shows the total number of conversations. "Clear All Conversations" deletes all local data after confirmation.
- **Version:** Displays the app version from `app.json`.

---

## Key Concepts

### Conversations and Sessions

Each conversation has a unique `sessionId` that is sent to the ORBIT server with every request. This allows the server to maintain per-conversation chat history. Session IDs are generated locally in the format `mobile-{timestamp}-{random}`.

Conversations are stored entirely on-device using AsyncStorage. They persist across app restarts. There is no cloud sync — deleting the app deletes all conversations.

### Streaming Buffer

The SSE stream from the ORBIT server can deliver text chunks very rapidly (sometimes multiple per millisecond). Updating React state on every chunk would cause render storms and UI jank.

The store implements a **32ms batching buffer** (matching the web app's approach at ~30fps). Incoming text chunks are accumulated in a buffer and flushed to state at most once every 32ms. When streaming ends, any remaining buffered content is flushed immediately.

### Stop Generation

When the user taps the stop button, two things happen simultaneously:

1. **Local abort:** The `AbortController` signal aborts the active `fetch` request, immediately stopping data flow.
2. **Server-side cancel:** A `POST /v1/chat/stop` request is sent with the `session_id` and `request_id` (captured from the first SSE chunk), telling the server to stop generating.

### Theme System

The app supports three theme modes:

- **System** (default) — follows the device's appearance setting
- **Light** — always light
- **Dark** — always dark

Theme preference is persisted to AsyncStorage. The `useTheme()` hook provides the current color palette to all components. Colors are defined in `src/theme/colors.ts` using iOS-native conventions.

### Audio Output (Text-to-Speech)

When `EXPO_PUBLIC_ENABLE_AUDIO_OUTPUT=true` is set, the app supports real-time TTS audio playback, matching the orbitchat web app's audio functionality.

**How it works:**

1. The user enables audio via the speaker toggle in the chat input bar (per-conversation setting)
2. When sending a message, the store passes `returnAudio: true` and optional `ttsVoice` to the streaming API
3. The server includes `audio_chunk` events in the SSE stream alongside text chunks
4. The `AudioStreamManager` (`src/utils/audioPlayer.ts`) receives chunks, writes them as temporary files, and plays them sequentially using `expo-audio`
5. Chunks are ordered by `chunk_index` and played back in real-time as they arrive
6. Temporary audio files are cleaned up after playback

**Supported audio formats:** MP3, WAV, Opus, OGG, WebM, AAC (depends on server configuration).

### Voice Input (Speech-to-Text)

Voice input uses the device's native speech recognition via `expo-speech-recognition`. **Note:** This requires a native dev build (`npx expo run:ios`) — it will not work in Expo Go. The mic button is automatically hidden when the native module is unavailable.

**How it works:**

1. The user taps the microphone button in the chat input bar
2. The app requests microphone and speech recognition permissions (first time only)
3. Speech is transcribed in real-time using iOS on-device speech recognition
4. Interim results are displayed as they are recognized; final results are appended to the text input
5. After 2 seconds of silence, recognition stops automatically
6. The user can then edit the transcribed text before sending

The `useVoice` hook (`src/hooks/useVoice.ts`) manages the speech recognition lifecycle and provides `startListening`, `stopListening`, and `isListening` state.

---

## Testing on a Physical Device

You can run the app on your iPhone during development without an Apple Developer account.

### Using Expo Go (easiest)

1. Install **Expo Go** from the App Store on your iPhone
2. Start the dev server in tunnel mode:
   ```bash
   npx expo start --tunnel
   ```
3. Scan the QR code displayed in the terminal with your iPhone camera
4. The app opens in Expo Go — no cables or Xcode required

Tunnel mode routes through Expo's servers, so your phone and computer don't need to be on the same Wi-Fi network.

### Using a Development Build (for native module testing)

If you need native modules not available in Expo Go (e.g., `expo-speech-recognition` for voice input), create a dev build directly on your device:

1. Connect your iPhone to your Mac via USB
2. Open the project in Xcode: `open ios/orbit-mobile.xcworkspace` (run `npx expo prebuild` first if the `ios/` folder doesn't exist)
3. In Xcode, select your iPhone as the build target
4. You may need to configure signing: go to **Signing & Capabilities** and select your personal team
5. Build and run (Cmd+R)

Alternatively, use the Expo CLI:

```bash
npx expo run:ios --device
```

This will list connected devices and let you pick one. The native build only needs to happen once (or when native dependencies change). For subsequent JS/TS code changes, just run `npx expo start` and the app on your device will hot-reload.

### Important: Connecting to Metro on a physical device

After installing a dev build on your iPhone, the app needs to connect to the Metro bundler running on your Mac to load the JavaScript bundle. If you see the error **"No script URL provided"**, it means the app can't find Metro.

**Solution — start Metro in tunnel mode before opening the app:**

```bash
npx expo start --tunnel
```

Tunnel mode routes through Expo's servers, so your phone and Mac don't need to be on the same Wi-Fi network. Once Metro is running, open the app on your iPhone and it will connect automatically.

> **Tip:** If the app still doesn't connect, shake your phone to open the React Native dev menu, tap **"Change Bundle Location"**, and enter your Mac's local IP and port (e.g., `192.168.1.100:8081`).

### Trusting the developer profile

The first time you install a dev build on your iPhone, iOS may block the app from launching with an "untrusted developer" error. To fix this:

1. On your iPhone, go to **Settings > General > VPN & Device Management**
2. Tap your developer certificate under "Developer App"
3. Tap **Trust** and confirm

The app will launch normally after this one-time step.

---

## Publishing to the App Store

This section walks through the complete process of shipping the app to the Apple App Store so users can download it.

### Prerequisites for App Store distribution

| Requirement | Details |
|-------------|---------|
| **Apple Developer Account** | Enroll at [developer.apple.com](https://developer.apple.com/programs/) ($99/year) |
| **EAS CLI** | Install globally: `npm install -g eas-cli` |
| **Expo account** | Sign up free at [expo.dev](https://expo.dev/signup) and log in: `eas login` |
| **App icon** | 1024x1024px PNG with no transparency (place in `assets/icon.png`) |
| **App Store Connect** | Create your app listing at [appstoreconnect.apple.com](https://appstoreconnect.apple.com) |

### Step 1: Configure EAS Build

Run the following command in the project root to generate an `eas.json` configuration file:

```bash
eas build:configure
```

This creates `eas.json`. Edit it to include a production profile:

```json
{
  "cli": {
    "version": ">= 3.0.0"
  },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal"
    },
    "preview": {
      "distribution": "internal",
      "ios": {
        "simulator": false
      }
    },
    "production": {
      "ios": {
        "autoIncrement": true
      }
    }
  },
  "submit": {
    "production": {
      "ios": {
        "appleId": "your-apple-id@example.com",
        "ascAppId": "your-app-store-connect-app-id",
        "appleTeamId": "YOUR_TEAM_ID"
      }
    }
  }
}
```

Replace the placeholder values:
- `appleId` — the email you use to sign in to App Store Connect
- `ascAppId` — your app's numeric ID from App Store Connect (found under App Information > General Information > Apple ID)
- `appleTeamId` — your 10-character team ID (found at [developer.apple.com/account](https://developer.apple.com/account) under Membership Details)

### Step 2: Set environment variables for production

Your `.env` file is only used locally. For EAS Build, set your environment variables as EAS secrets:

```bash
eas secret:create --name EXPO_PUBLIC_ORBIT_HOST --value "https://your-production-orbit-server.com" --scope project
eas secret:create --name EXPO_PUBLIC_ORBIT_API_KEY --value "your-production-api-key" --scope project
```

These secrets are injected at build time and are never visible in logs or build artifacts.

### Step 3: Update `app.json` for production

Before your first submission, verify these fields in `app.json`:

```json
{
  "expo": {
    "name": "ORBIT Chat",
    "slug": "orbit-mobile",
    "version": "1.0.0",
    "ios": {
      "supportsTablet": true,
      "bundleIdentifier": "com.yourcompany.orbit-chat",
      "buildNumber": "1",
      "infoPlist": {
        "NSCameraUsageDescription": "Used to scan QR codes for configuration",
        "ITSAppUsesNonExemptEncryption": false
      }
    }
  }
}
```

Key fields:
- `bundleIdentifier` — must match what you registered in App Store Connect (e.g., `com.yourcompany.orbit-chat`). Change this from the default `com.orbit.chat` to your own.
- `version` — the user-facing version string (e.g., `1.0.0`). Increment this for each new App Store release.
- `buildNumber` — Apple's internal build number. EAS auto-increments this if `autoIncrement: true` is set in `eas.json`.
- `ITSAppUsesNonExemptEncryption: false` — avoids the export compliance prompt on every TestFlight upload (set to `true` only if you use custom encryption beyond standard HTTPS).

### Step 4: Create the App Store listing

1. Go to [App Store Connect](https://appstoreconnect.apple.com)
2. Click **My Apps > "+" > New App**
3. Fill in:
   - **Platform:** iOS
   - **Name:** ORBIT Chat (or your chosen name)
   - **Primary language:** English (U.S.)
   - **Bundle ID:** Select the bundle ID you registered (must match `bundleIdentifier` in `app.json`)
   - **SKU:** A unique ID of your choice (e.g., `orbit-chat-ios`)
4. Save. You'll fill in screenshots, description, and review information later.

### Step 5: Build for production

```bash
eas build --platform ios --profile production
```

This command:
- Uploads your project to EAS Build servers
- Compiles a native `.ipa` file signed for App Store distribution
- Manages provisioning profiles and certificates automatically (EAS prompts you to log in to your Apple Developer account on first run)

The build takes 10-20 minutes. You'll get a URL to track progress and download the artifact.

### Step 6: Submit to the App Store

Once the build completes, submit it directly from the CLI:

```bash
eas submit --platform ios --latest
```

This uploads the latest build to App Store Connect. Alternatively, specify a build ID:

```bash
eas submit --platform ios --id your-build-id
```

Or combine build and submit in a single command:

```bash
eas build --platform ios --profile production --auto-submit
```

### Step 7: TestFlight (beta testing)

After submission, the build appears in App Store Connect under **TestFlight** within a few minutes. Apple runs an automated review on TestFlight builds (usually takes 10-30 minutes).

1. Go to **App Store Connect > Your App > TestFlight**
2. Under **Internal Testing**, click **"+"** to create a test group
3. Add testers by email (up to 100 internal testers)
4. Testers receive an email invite to install the app via the TestFlight app on their iPhone

For external beta testing (up to 10,000 testers), submit the build for Beta App Review under the **External Testing** tab.

### Step 8: Submit for App Store Review

When you're ready to go public:

1. Go to **App Store Connect > Your App > App Store tab**
2. Under the current version, fill in:
   - **Screenshots:** At minimum, iPhone 6.7" (1290x2796px) and 6.5" (1284x2778px). Take these in the Simulator via `Cmd+S`.
   - **Description:** What the app does
   - **Keywords:** Comma-separated search terms
   - **Support URL:** A link to your support page or GitHub repo
   - **Privacy Policy URL:** Required for all apps
3. Under **Build**, click **"+"** and select the build you submitted
4. Answer the review questions (content rights, advertising, etc.)
5. Click **Submit for Review**

Apple's review typically takes 24-48 hours. You'll receive an email when the app is approved (or if changes are requested).

### Step 9: Release

After approval, you can choose to release:
- **Immediately** — the app goes live on the App Store
- **On a specific date** — schedule the release
- **Manually** — hold until you click "Release This Version"

### Updating the app after release

For subsequent releases:

```bash
# 1. Increment the version in app.json (e.g., 1.0.0 → 1.1.0)

# 2. Build
eas build --platform ios --profile production

# 3. Submit
eas submit --platform ios --latest

# 4. In App Store Connect, create a new version, attach the build, and submit for review
```

For minor JavaScript-only updates (no native code changes), you can use **EAS Update** to push over-the-air updates without going through App Store Review:

```bash
npx eas-cli update --branch production --message "Fix streaming bug"
```

Users receive the update the next time they open the app. This is ideal for bug fixes and small improvements.

### Summary of commands

| Step | Command |
|------|---------|
| Configure EAS | `eas build:configure` |
| Set production secrets | `eas secret:create --name EXPO_PUBLIC_ORBIT_HOST --value "..." --scope project` |
| Build for App Store | `eas build --platform ios --profile production` |
| Submit to App Store Connect | `eas submit --platform ios --latest` |
| Build + submit in one step | `eas build --platform ios --profile production --auto-submit` |
| Push OTA update | `npx eas-cli update --branch production --message "description"` |

---

## Troubleshooting

### "EXPO_PUBLIC_ORBIT_HOST is not set"

You haven't created the `.env` file, or it is empty. Copy the example and fill in your values:

```bash
cp .env.example .env
# Then edit .env with your server URL and API key
```

After editing, restart the dev server (`Ctrl+C` then `npx expo start`).

### Settings screen shows "Disconnected"

- Verify that the ORBIT server is running and accessible from your machine.
- Check that `EXPO_PUBLIC_ORBIT_HOST` in `.env` is the correct URL (include the protocol, e.g., `https://`).
- Check that `EXPO_PUBLIC_ORBIT_API_KEY` is a valid, active API key on that server.
- If the server uses a self-signed certificate, the iOS Simulator may reject it. Use HTTP for local development or install the CA certificate in the simulator.

### Metro bundler errors on start

```bash
# Clear Metro's cache and restart
npx expo start --clear
```

### Dependency resolution errors during `npm install`

Some packages have peer dependency conflicts with React 19. Use the legacy resolution flag:

```bash
npm install --legacy-peer-deps
```

### "Cannot find module 'react-native-worklets/plugin'"

This Babel plugin is required by `react-native-reanimated`. Install it:

```bash
npx expo install react-native-worklets
```

### Messages are not streaming (response appears all at once)

The ORBIT server may be returning non-streaming responses. Verify that your server supports SSE streaming on `POST /v1/chat` with `Accept: text/event-stream`. The app requests `stream: true` by default.

### Build fails with "No bundle URL present"

This usually means Metro crashed. Check the terminal for errors, then:

```bash
# Kill any lingering Metro processes
lsof -ti:8081 | xargs kill -9 2>/dev/null

# Restart
npx expo start --clear
```

---

## Feature Roadmap

### V1 (current)
- Conversation list with create/delete
- Real-time SSE streaming chat
- Stop generation (local + server-side)
- Markdown rendering (headings, code, lists, tables)
- Light/dark/system theme
- Conversation persistence (AsyncStorage)
- Connection status and adapter info in Settings
- Copy assistant messages to clipboard
- Voice input (speech-to-text via on-device recognition)
- Audio output (text-to-speech with streaming audio chunk playback)
- Per-conversation audio settings

### V1.1 (planned)
- QR code / deep link configuration (no `.env` needed)
- Share messages
- Haptic feedback on interactions
- Error retry UI with tap-to-retry
- TTS voice selection (alloy, echo, fable, onyx, nova, shimmer)

### V2 (planned)
- Multi-adapter support (switch models mid-conversation)
- File uploads
- Autocomplete suggestions
- iPad layout optimization

### V3 (planned)
- Conversation threading
- Push notifications
- Android release
