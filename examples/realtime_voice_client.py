"""
Real-Time Voice Chat WebSocket Client Example

This example demonstrates how to connect to the Orbit real-time voice chat
WebSocket endpoint and have a bidirectional audio conversation with AI.

Requirements:
    pip install websockets pyaudio

Basic Usage:
    # Connect to local server (no API key required by default)
    python realtime_voice_client.py

    # Connect with session ID for conversation history
    python realtime_voice_client.py --session-id my-session

    # Connect with custom adapter
    python realtime_voice_client.py --adapter real-time-voice-chat

    # Connect with API key (if required by adapter configuration)
    python realtime_voice_client.py --api-key your_api_key_here

    # Full example with all options
    python realtime_voice_client.py \
        --host localhost \
        --port 3000 \
        --adapter real-time-voice-chat \
        --session-id my-conversation \
        --api-key your_api_key_here

Command-Line Arguments:
    --host          Server hostname (default: localhost)
    --port          Server port (default: 3000)
    --adapter       Adapter name to use (default: real-time-voice-chat)
    --session-id    Session ID for conversation history (optional)
    --api-key       API key for authentication (optional, required if adapter
                    has requires_api_key_validation: true)

Environment Setup:
    1. Ensure the Orbit server is running:
       cd server && python main.py

    2. Verify the real-time-voice-chat adapter is enabled in:
       config/adapters/audio.yaml

    3. Ensure you have a working microphone and speakers

    4. If API key is required, obtain it from your Orbit server admin

Features:
    - Real-time bidirectional audio streaming via WebSocket
    - Automatic speech-to-text transcription
    - Text-to-speech audio playback
    - Interruption support (speak while AI is talking)
    - Session management for conversation history
    - Connection status monitoring

Controls:
    - Speak into your microphone to send audio to the AI
    - Listen for AI responses through your speakers
    - Press Ctrl+C to disconnect and exit

Notes:
    - Audio format: 16-bit PCM, mono, 24kHz sample rate
    - Default audio chunk size: 100ms (2400 samples)
    - The client automatically handles audio encoding/decoding
    - Interruption is automatic when you speak while AI is responding
"""

import asyncio
import json
import base64
import argparse
from typing import Optional
import wave
import io
import struct

try:
    import websockets
    import pyaudio
except ImportError:
    print("Please install required packages: pip install websockets pyaudio")
    exit(1)


class RealTimeVoiceClient:
    """WebSocket client for real-time voice conversations with AI."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3000,
        adapter_name: str = "real-time-voice-chat",
        session_id: Optional[str] = None,
        api_key: Optional[str] = None,
        input_device: Optional[int] = None
    ):
        """
        Initialize the voice client.

        Args:
            host: Server host
            port: Server port
            adapter_name: Adapter name to use
            session_id: Optional session ID for conversation history
            api_key: Optional API key for authentication
            input_device: Optional audio input device index
        """
        self.host = host
        self.port = port
        self.adapter_name = adapter_name
        self.session_id = session_id or "test-session"
        self.api_key = api_key

        # Build WebSocket URL with parameters
        params = [f"session_id={self.session_id}"]
        if self.api_key:
            params.append(f"api_key={self.api_key}")

        self.ws_url = f"ws://{host}:{port}/ws/voice/{adapter_name}?{'&'.join(params)}"

        # PyAudio instance
        self.audio = pyaudio.PyAudio()

        # Auto-detect or use specified input device
        self.input_device = input_device
        if self.input_device is None:
            self.input_device = self._find_yeti_microphone()

        # Get device info to determine channels
        if self.input_device is not None:
            device_info = self.audio.get_device_info_by_index(self.input_device)
            self.input_channels = min(2, device_info['maxInputChannels'])  # Stereo if available
            print(f"Using microphone: {device_info['name']} ({self.input_channels} channels)")
        else:
            self.input_channels = 1
            print("Using default microphone (mono)")

        # Audio configuration
        self.audio_format = pyaudio.paInt16  # 16-bit audio
        self.output_channels = 1  # Mono output
        self.rate = 24000  # 24kHz sample rate
        self.chunk_size = 2400  # 100ms at 24kHz
        self.chunk_duration_ms = 100

        # Audio streams
        self.input_stream = None
        self.output_stream = None

        # State
        self.is_connected = False
        self.is_listening = False
        self.is_speaking = False

    def _find_yeti_microphone(self) -> Optional[int]:
        """Find Yeti microphone device index."""
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if 'yeti' in info['name'].lower() and info['maxInputChannels'] > 0:
                return i
        return None

    def open_audio_streams(self):
        """Open microphone input and speaker output streams."""
        # Input stream (microphone) - may be stereo
        self.input_stream = self.audio.open(
            format=self.audio_format,
            channels=self.input_channels,
            rate=self.rate,
            input=True,
            input_device_index=self.input_device,
            frames_per_buffer=self.chunk_size
        )

        # Output stream (speakers) - mono
        self.output_stream = self.audio.open(
            format=self.audio_format,
            channels=self.output_channels,
            rate=self.rate,
            output=True,
            frames_per_buffer=self.chunk_size
        )

        print("✓ Audio streams opened")

    def close_audio_streams(self):
        """Close audio streams."""
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        self.audio.terminate()
        print("✓ Audio streams closed")

    def _stereo_to_mono(self, audio_bytes: bytes) -> bytes:
        """
        Convert stereo audio to mono by averaging channels.

        Args:
            audio_bytes: Stereo audio bytes (16-bit PCM)

        Returns:
            Mono audio bytes (16-bit PCM)
        """
        if self.input_channels == 1:
            return audio_bytes  # Already mono

        # Unpack stereo samples
        num_samples = len(audio_bytes) // 2
        samples = struct.unpack(f'{num_samples}h', audio_bytes)

        # Separate left and right channels
        left = samples[0::2]
        right = samples[1::2]

        # Average channels to create mono
        mono_samples = [(l + r) // 2 for l, r in zip(left, right)]

        # Pack back to bytes
        return struct.pack(f'{len(mono_samples)}h', *mono_samples)

    async def send_audio_chunk(self, websocket, audio_bytes: bytes):
        """
        Send an audio chunk to the server.

        Args:
            websocket: WebSocket connection
            audio_bytes: Raw audio bytes
        """
        # Convert stereo to mono if needed
        audio_mono = self._stereo_to_mono(audio_bytes)

        # Encode to base64
        audio_b64 = base64.b64encode(audio_mono).decode('utf-8')

        # Send message
        message = {
            "type": "audio_chunk",
            "data": audio_b64,
            "format": "wav"
        }

        await websocket.send(json.dumps(message))

    async def send_audio_from_mic(self, websocket):
        """
        Continuously capture audio from microphone and send to server.

        Args:
            websocket: WebSocket connection
        """
        self.is_listening = True
        print("🎤 Listening... (press Ctrl+C to interrupt)")

        try:
            while self.is_listening and self.is_connected:
                # Read audio chunk from microphone in a thread (PyAudio call blocks)
                audio_data = await asyncio.to_thread(
                    self.input_stream.read,
                    self.chunk_size,
                    exception_on_overflow=False
                )

                # Send to server
                await self.send_audio_chunk(websocket, audio_data)

                # Small delay to prevent overwhelming the server
                await asyncio.sleep(0.01)

        except Exception as e:
            print(f"Error capturing audio: {e}")

    async def receive_messages(self, websocket):
        """
        Receive and process messages from server.

        Args:
            websocket: WebSocket connection
        """
        try:
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "connected":
                    print(f"✓ Connected to {data.get('adapter')}")
                    print(f"  Session ID: {data.get('session_id')}")
                    print(f"  Audio format: {data.get('audio_format')}")

                elif msg_type == "transcription":
                    text = data.get("text", "")
                    print(f"📝 You said: {text}")

                elif msg_type == "audio_chunk":
                    # Decode and play audio
                    audio_b64 = data.get("data")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)

                        # Play audio
                        if not self.is_speaking:
                            self.is_speaking = True
                            print("🔊 AI is speaking...")

                        # Writing to PyAudio blocks, so offload to a worker thread
                        await asyncio.to_thread(self.output_stream.write, audio_bytes)

                elif msg_type == "done":
                    if self.is_speaking:
                        self.is_speaking = False
                        print("✓ AI finished speaking")

                elif msg_type == "interrupted":
                    if self.is_speaking:
                        self.is_speaking = False
                    reason = data.get("reason", "unknown")
                    print(f"⏸️  AI interrupted ({reason})")

                elif msg_type == "error":
                    print(f"❌ Error: {data.get('message')}")

                elif msg_type == "pong":
                    pass  # Keepalive response

        except websockets.exceptions.ConnectionClosed:
            print("Connection closed by server")
            self.is_connected = False

    async def send_interrupt(self, websocket):
        """
        Send interrupt signal to stop AI from speaking.

        Args:
            websocket: WebSocket connection
        """
        message = {"type": "interrupt"}
        await websocket.send(json.dumps(message))
        print("⏸️  Interrupted AI")

    async def connect_and_run(self):
        """Connect to WebSocket and start conversation loop."""
        print(f"Connecting to {self.ws_url}...")

        try:
            async with websockets.connect(self.ws_url) as websocket:
                self.is_connected = True
                print("✓ WebSocket connected")

                # Open audio streams
                self.open_audio_streams()

                # Start tasks
                receive_task = asyncio.create_task(self.receive_messages(websocket))
                send_task = asyncio.create_task(self.send_audio_from_mic(websocket))

                # Wait for either task to complete (or Ctrl+C)
                done, pending = await asyncio.wait(
                    [receive_task, send_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel remaining tasks gracefully
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass  # Expected when cancelling tasks

        except KeyboardInterrupt:
            print("\n\n👋 Disconnecting...")
        except Exception as e:
            print(f"❌ Connection error: {e}")
        finally:
            self.is_connected = False
            self.close_audio_streams()
            print("✓ Connection closed")

    def run(self):
        """Run the client."""
        try:
            asyncio.run(self.connect_and_run())
        except KeyboardInterrupt:
            # Suppress the exception - already handled in connect_and_run
            pass


def main():
    """Main entry point."""
    try:
        parser = argparse.ArgumentParser(description="Real-time voice chat client")
        parser.add_argument("--host", default="localhost", help="Server host")
        parser.add_argument("--port", type=int, default=3000, help="Server port")
        parser.add_argument("--adapter", default="real-time-voice-chat", help="Adapter name")
        parser.add_argument("--session-id", help="Session ID for conversation history")
        parser.add_argument("--api-key", help="API key for authentication (optional)")
        parser.add_argument("--input-device", type=int, help="Audio input device index (auto-detects Yeti if not specified)")

        args = parser.parse_args()

        client = RealTimeVoiceClient(
            host=args.host,
            port=args.port,
            adapter_name=args.adapter,
            session_id=args.session_id,
            api_key=args.api_key,
            input_device=args.input_device
        )

        client.run()
    except KeyboardInterrupt:
        # Handle CTRL-C gracefully without showing traceback
        print("\n\n👋 Goodbye!")
        exit(0)


if __name__ == "__main__":
    main()
