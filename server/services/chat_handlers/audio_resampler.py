"""
Audio Resampler for PersonaPlex Integration

Handles sample rate conversion between ORBIT clients (typically 24kHz)
and PersonaPlex (32kHz native).

Uses efficient numpy-based linear interpolation for low-latency resampling.
For higher quality, can be upgraded to use scipy.signal.resample or librosa.
"""

import logging
from typing import Optional
import struct

logger = logging.getLogger(__name__)

# Try to import numpy for efficient resampling
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("numpy not available, using fallback resampler (slower)")


class AudioResampler:
    """
    Resamples audio between ORBIT (24kHz) and PersonaPlex (32kHz).

    This class handles bidirectional sample rate conversion for real-time
    audio streaming between ORBIT clients and PersonaPlex.

    Attributes:
        orbit_rate: ORBIT client sample rate (default: 24000 Hz)
        personaplex_rate: PersonaPlex native sample rate (default: 32000 Hz)
        dtype: Audio data type (default: float32)
    """

    def __init__(
        self,
        orbit_rate: int = 24000,
        personaplex_rate: int = 32000,
        dtype: str = "float32"
    ):
        """
        Initialize the resampler.

        Args:
            orbit_rate: ORBIT client sample rate in Hz
            personaplex_rate: PersonaPlex sample rate in Hz
            dtype: Audio data type ('float32', 'int16')
        """
        self.orbit_rate = orbit_rate
        self.personaplex_rate = personaplex_rate
        self.dtype = dtype

        # Resampling ratios
        self.orbit_to_pp_ratio = personaplex_rate / orbit_rate  # 32000/24000 = 1.333...
        self.pp_to_orbit_ratio = orbit_rate / personaplex_rate  # 24000/32000 = 0.75

        logger.debug(
            f"AudioResampler initialized: {orbit_rate}Hz <-> {personaplex_rate}Hz"
        )

    def resample_to_personaplex(self, audio: bytes) -> bytes:
        """
        Resample audio from ORBIT rate to PersonaPlex rate.

        Args:
            audio: Audio bytes at ORBIT sample rate

        Returns:
            Audio bytes at PersonaPlex sample rate
        """
        return self._resample(
            audio,
            self.orbit_rate,
            self.personaplex_rate
        )

    def resample_to_orbit(self, audio: bytes) -> bytes:
        """
        Resample audio from PersonaPlex rate to ORBIT rate.

        Args:
            audio: Audio bytes at PersonaPlex sample rate

        Returns:
            Audio bytes at ORBIT sample rate
        """
        return self._resample(
            audio,
            self.personaplex_rate,
            self.orbit_rate
        )

    def _resample(self, audio: bytes, src_rate: int, dst_rate: int) -> bytes:
        """
        Perform resampling using linear interpolation.

        Args:
            audio: Input audio bytes
            src_rate: Source sample rate
            dst_rate: Destination sample rate

        Returns:
            Resampled audio bytes
        """
        if src_rate == dst_rate:
            return audio

        if not audio:
            return audio

        if HAS_NUMPY:
            return self._resample_numpy(audio, src_rate, dst_rate)
        else:
            return self._resample_fallback(audio, src_rate, dst_rate)

    def _resample_numpy(self, audio: bytes, src_rate: int, dst_rate: int) -> bytes:
        """
        Resample using numpy linear interpolation.

        Args:
            audio: Input audio bytes
            src_rate: Source sample rate
            dst_rate: Destination sample rate

        Returns:
            Resampled audio bytes
        """
        # Convert bytes to numpy array
        if self.dtype == "float32":
            # Ensure buffer is aligned to 4-byte boundaries (float32 size)
            sample_size = 4
            aligned_len = (len(audio) // sample_size) * sample_size
            if aligned_len == 0:
                return audio
            if aligned_len < len(audio):
                logger.debug(f"Truncating {len(audio) - aligned_len} bytes for float32 alignment")
                audio = audio[:aligned_len]
            samples = np.frombuffer(audio, dtype=np.float32)
        else:  # int16
            # Ensure buffer is aligned to 2-byte boundaries (int16 size)
            sample_size = 2
            aligned_len = (len(audio) // sample_size) * sample_size
            if aligned_len == 0:
                return audio
            if aligned_len < len(audio):
                audio = audio[:aligned_len]
            samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

        if len(samples) == 0:
            return audio

        # Calculate output length
        output_length = int(len(samples) * dst_rate / src_rate)

        if output_length == 0:
            return b''

        # Linear interpolation
        x_old = np.linspace(0, 1, len(samples), endpoint=False)
        x_new = np.linspace(0, 1, output_length, endpoint=False)
        resampled = np.interp(x_new, x_old, samples)

        # Convert back to bytes
        if self.dtype == "float32":
            return resampled.astype(np.float32).tobytes()
        else:  # int16
            return (resampled * 32768.0).clip(-32768, 32767).astype(np.int16).tobytes()

    def _resample_fallback(self, audio: bytes, src_rate: int, dst_rate: int) -> bytes:
        """
        Resample using pure Python (slower, fallback when numpy unavailable).

        Args:
            audio: Input audio bytes
            src_rate: Source sample rate
            dst_rate: Destination sample rate

        Returns:
            Resampled audio bytes
        """
        # Determine sample size and format
        if self.dtype == "float32":
            sample_size = 4
            fmt = 'f'
        else:  # int16
            sample_size = 2
            fmt = 'h'

        num_samples = len(audio) // sample_size
        if num_samples == 0:
            return audio

        # Unpack samples
        samples = struct.unpack(f'{num_samples}{fmt}', audio)

        # Calculate output length
        output_length = int(num_samples * dst_rate / src_rate)
        if output_length == 0:
            return b''

        # Linear interpolation
        resampled = []
        ratio = (num_samples - 1) / (output_length - 1) if output_length > 1 else 0

        for i in range(output_length):
            pos = i * ratio
            idx = int(pos)
            frac = pos - idx

            if idx + 1 < num_samples:
                value = samples[idx] * (1 - frac) + samples[idx + 1] * frac
            else:
                value = samples[idx]

            resampled.append(value)

        # Pack back to bytes
        return struct.pack(f'{len(resampled)}{fmt}', *resampled)

    def convert_int16_to_float32(self, audio: bytes) -> bytes:
        """
        Convert int16 audio to float32.

        Args:
            audio: Audio bytes in int16 format

        Returns:
            Audio bytes in float32 format
        """
        if HAS_NUMPY:
            samples = np.frombuffer(audio, dtype=np.int16)
            float_samples = samples.astype(np.float32) / 32768.0
            return float_samples.tobytes()
        else:
            num_samples = len(audio) // 2
            samples = struct.unpack(f'{num_samples}h', audio)
            float_samples = [s / 32768.0 for s in samples]
            return struct.pack(f'{len(float_samples)}f', *float_samples)

    def convert_float32_to_int16(self, audio: bytes) -> bytes:
        """
        Convert float32 audio to int16.

        Args:
            audio: Audio bytes in float32 format

        Returns:
            Audio bytes in int16 format
        """
        if HAS_NUMPY:
            samples = np.frombuffer(audio, dtype=np.float32)
            int_samples = (samples * 32768.0).clip(-32768, 32767).astype(np.int16)
            return int_samples.tobytes()
        else:
            num_samples = len(audio) // 4
            samples = struct.unpack(f'{num_samples}f', audio)
            int_samples = [max(-32768, min(32767, int(s * 32768.0))) for s in samples]
            return struct.pack(f'{len(int_samples)}h', *int_samples)


class StreamingResampler:
    """
    Streaming resampler that handles fractional samples across chunks.

    For real-time streaming, this class maintains state between chunks
    to ensure smooth audio without clicks or pops at chunk boundaries.
    """

    def __init__(
        self,
        src_rate: int,
        dst_rate: int,
        dtype: str = "float32"
    ):
        """
        Initialize the streaming resampler.

        Args:
            src_rate: Source sample rate
            dst_rate: Destination sample rate
            dtype: Audio data type
        """
        self.src_rate = src_rate
        self.dst_rate = dst_rate
        self.dtype = dtype

        # Fractional sample accumulator
        self._fractional_position = 0.0

        # Last sample for interpolation across chunk boundaries
        self._last_sample: Optional[float] = None

        self._resampler = AudioResampler(
            orbit_rate=src_rate,
            personaplex_rate=dst_rate,
            dtype=dtype
        )

    def process(self, audio: bytes) -> bytes:
        """
        Process an audio chunk with state preservation.

        Args:
            audio: Input audio chunk

        Returns:
            Resampled audio chunk
        """
        # For now, use the basic resampler
        # A more sophisticated implementation would track fractional positions
        return self._resampler._resample(audio, self.src_rate, self.dst_rate)

    def reset(self):
        """Reset the streaming state."""
        self._fractional_position = 0.0
        self._last_sample = None
