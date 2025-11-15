# Audio Client Integration Summary

This document summarizes the changes made to support audio services in the client-side code.

## Changes Made

### 1. API Client (`clients/node-api/api.ts`)

**Updated Interfaces:**
- `ChatRequest`: Added optional audio parameters:
  - `audio_input?: string` - Base64-encoded audio data for STT
  - `audio_format?: string` - Audio format (mp3, wav, etc.)
  - `language?: string` - Language code for STT
  - `return_audio?: boolean` - Whether to return audio response
  - `tts_voice?: string` - Voice for TTS
  - `source_language?: string` - Source language for translation
  - `target_language?: string` - Target language for translation

- `ChatResponse`: Added audio response fields:
  - `audio?: string` - Base64-encoded audio data (TTS response)
  - `audio_format?: string` - Audio format

- `StreamResponse`: Added audio fields:
  - `audio?: string` - Base64-encoded audio data
  - `audioFormat?: string` - Audio format

**Updated Methods:**
- `createChatRequest()`: Now accepts all audio parameters
- `streamChat()`: Extended to accept audio parameters and return audio in responses
- Legacy `streamChat()` function: Updated signature to match

### 2. Chat App API Loader (`clients/chat-app/src/api/loader.ts`)

**Updated Interfaces:**
- `StreamResponse`: Added `audio` and `audioFormat` fields
- `ApiClient.streamChat()`: Extended signature to accept audio parameters
- `ApiFunctions.streamChat()`: Updated to match new signature

### 3. Chat App Types (`clients/chat-app/src/types/index.ts`)

**Updated Interfaces:**
- `Message`: Added optional audio fields:
  - `audio?: string` - Base64-encoded audio data
  - `audioFormat?: string` - Audio format

### 4. Chat Store (`clients/chat-app/src/stores/chatStore.ts`)

**Updated Functionality:**
- `sendMessage()`: Now handles audio responses from the API
- Audio data is stored with assistant messages when received
- Audio is extracted from streaming responses and attached to messages

## Usage

### Sending Audio Input

To send audio input for transcription:

```typescript
// Record audio and convert to base64
const audioBlob = await recordAudio();
const audioBase64 = await blobToBase64(audioBlob);

// Send with audio input
for await (const response of api.streamChat(
  '', // Empty message when using audio_input
  true,
  undefined, // fileIds
  audioBase64, // audioInput
  'wav', // audioFormat
  'en-US' // language
)) {
  // Handle response
}
```

### Receiving Audio Output

To receive audio responses (TTS):

```typescript
for await (const response of api.streamChat(
  'Hello, how are you?',
  true,
  undefined, // fileIds
  undefined, // audioInput
  undefined, // audioFormat
  undefined, // language
  true, // returnAudio
  'alloy' // ttsVoice
)) {
  if (response.audio) {
    // Play audio response
    playAudio(response.audio, response.audioFormat);
  }
}
```

## Next Steps for Full Implementation

### 1. Audio Recording Component
Create a component to record audio from the microphone:

```typescript
// Example: clients/chat-app/src/components/AudioRecorder.tsx
export function AudioRecorder({ onAudioRecorded }: { onAudioRecorded: (audio: string) => void }) {
  // Use MediaRecorder API to record audio
  // Convert to base64 and call onAudioRecorded
}
```

### 2. Audio Playback Component
Create a component to play audio responses:

```typescript
// Example: clients/chat-app/src/components/AudioPlayer.tsx
export function AudioPlayer({ audio, format }: { audio: string; format?: string }) {
  // Decode base64 audio and play using HTML5 Audio API
}
```

### 3. Message Input Updates
Update `MessageInput.tsx` to:
- Add audio recording button
- Support sending audio input
- Show audio recording status

### 4. Message Display Updates
Update `Message.tsx` to:
- Display audio player for messages with audio
- Show play/pause controls
- Handle audio format conversion

### 5. Settings Integration
Add audio settings to `Settings.tsx`:
- Enable/disable audio input
- Enable/disable audio output
- Select default TTS voice
- Select default language

## Testing

To test the audio integration:

1. **Test Audio Input (STT)**:
   - Record audio using browser MediaRecorder API
   - Convert to base64
   - Send via `streamChat()` with `audio_input` parameter
   - Verify text response is correct transcription

2. **Test Audio Output (TTS)**:
   - Send text message with `return_audio: true`
   - Verify audio data is received in response
   - Decode base64 and play audio
   - Verify audio quality and voice match

3. **Test Audio File Transcription**:
   - Upload audio file via file upload
   - Verify file is transcribed and stored
   - Query transcribed content
   - Verify retrieval works correctly

## Notes

- Audio data is base64-encoded for transmission
- Audio format should match provider capabilities
- Language codes follow ISO 639-1 format (e.g., "en-US", "fr-FR")
- TTS voice options are provider-specific
- Audio responses are optional and only returned when `return_audio: true`

