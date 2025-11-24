#!/usr/bin/env python3
"""Quick microphone test to check if audio is being captured."""

import pyaudio
import struct
import time

# Audio capture constants
RATE = 24000
FRAMES_PER_BUFFER = 2400
CALIBRATION_TIME = 0.5  # seconds to measure background noise
MIN_SPEECH_THRESHOLD = 0.0002  # fallback threshold when room noise is minimal
THRESHOLD_MARGIN = 0.0001  # absolute extra margin above the measured noise floor
SPEECH_MULTIPLIER = 2.5  # how far above noise floor input must be to count as speech

def test_microphone():
    """Test if microphone is capturing audio."""
    print("Testing microphone for 5 seconds...")
    print("Please speak into your microphone!\n")

    audio = pyaudio.PyAudio()

    # List audio devices
    print("Available audio devices:")
    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            print(f"  [{i}] {info['name']} (Input channels: {info['maxInputChannels']})")
    print()

    # Find Yeti microphone or ask user
    yeti_device = None
    for i in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(i)
        if 'yeti' in info['name'].lower() and info['maxInputChannels'] > 0:
            yeti_device = i
            break

    if yeti_device is not None:
        device_info = audio.get_device_info_by_index(yeti_device)
        print(f"Using: [{yeti_device}] {device_info['name']}")
        channels = min(2, device_info['maxInputChannels'])  # Use stereo if available
    else:
        # Ask user to select device
        device_input = input("Enter device index to use (or press Enter for default): ").strip()
        if device_input:
            yeti_device = int(device_input)
            device_info = audio.get_device_info_by_index(yeti_device)
            channels = min(2, device_info['maxInputChannels'])
            print(f"Using: [{yeti_device}] {device_info['name']}")
        else:
            yeti_device = None
            channels = 1
            print("Using default microphone")

    print(f"Channels: {channels}")
    print()

    # Open microphone
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=channels,
        rate=RATE,
        input=True,
        input_device_index=yeti_device,
        frames_per_buffer=FRAMES_PER_BUFFER
    )

    print("Recording... stay quiet for a moment while we measure background noise.")
    print("Once calibration finishes, keep speaking so we can detect audio!\n")

    start_time = time.time()
    max_amplitude = 0
    chunk_count = 0
    speech_chunks = 0

    chunk_duration = FRAMES_PER_BUFFER / RATE
    calibration_chunks = max(5, int(CALIBRATION_TIME / chunk_duration))
    calibration_values = []
    noise_floor = 0.0
    calibrated = False

    try:
        while time.time() - start_time < 5:
            data = stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)

            # Calculate amplitude (works for both mono and stereo)
            num_samples = len(data) // 2  # 16-bit = 2 bytes per sample
            samples = struct.unpack(f'{num_samples}h', data)

            # For stereo, convert to mono by averaging channels
            if channels == 2:
                # Separate left and right channels
                left = samples[0::2]
                right = samples[1::2]
                # Average them
                mono_samples = [(l + r) // 2 for l, r in zip(left, right)]
                samples = mono_samples

            rms = (sum(s*s for s in samples) / len(samples)) ** 0.5
            normalized_rms = rms / 32767.0
            peak_level = max(abs(s) for s in samples) / 32767.0
            signal_level = max(normalized_rms, peak_level)

            chunk_count += 1
            max_amplitude = max(max_amplitude, signal_level)

            if not calibrated:
                calibration_values.append(normalized_rms)

                if len(calibration_values) >= calibration_chunks:
                    noise_floor = max(
                        MIN_SPEECH_THRESHOLD,
                        sum(calibration_values) / len(calibration_values)
                    )
                    calibrated = True
                    print(f"  Calibration complete. Noise floor: {noise_floor:.4f}")
                    print("  Keep speaking so we can detect audio!\n")
                continue

            speech_threshold = max(
                MIN_SPEECH_THRESHOLD,
                noise_floor * SPEECH_MULTIPLIER + THRESHOLD_MARGIN
            )

            if signal_level > speech_threshold:
                speech_chunks += 1
                print(f"  Speech detected! Amplitude: {signal_level:.4f}")
            else:
                # Slowly adapt the noise floor downward when things stay quiet
                noise_floor = 0.98 * noise_floor + 0.02 * normalized_rms

    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()

    print(f"\nResults:")
    print(f"  Total chunks: {chunk_count}")
    print(f"  Speech chunks detected: {speech_chunks}")
    print(f"  Max amplitude: {max_amplitude:.6f}")
    if calibrated:
        print(f"  Final noise floor: {noise_floor:.6f}")

    if speech_chunks == 0:
        print("\n⚠️  WARNING: No speech detected!")
        print("  Possible issues:")
        print("    - Microphone is muted")
        print("    - Wrong microphone selected")
        print("    - Microphone permissions not granted")
        print("    - You didn't speak loud enough")
        if max_amplitude < 0.0005:
            print("  Observed signal stayed extremely low; double-check OS microphone permissions.")
    else:
        print(f"\n✓ Microphone is working! Detected speech in {speech_chunks}/{chunk_count} chunks")

if __name__ == "__main__":
    test_microphone()
