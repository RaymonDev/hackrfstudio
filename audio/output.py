"""
Real-Time Audio Output Engine for SDR Demodulation.
Streams audio chunks to speakers with jitter buffering and under-run protection.
"""

import queue
import threading
import numpy as np
from typing import Optional

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except Exception:
    sd = None
    SOUNDDEVICE_AVAILABLE = False


class AudioOutput:
    """Manages real-time low-latency audio playback."""

    SAMPLE_RATE = 48000
    BLOCK_SIZE = 1024

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.muted = False
        self.volume = 1.0  # 0.0 to 1.0
        self._stream: Optional[sd.OutputStream] = None
        self._queue = queue.Queue(maxsize=30)  # ~600ms buffer max
        self.is_active = False

    def start(self) -> bool:
        """Starts the audio output stream."""
        if self.is_active or not SOUNDDEVICE_AVAILABLE:
            return False

        try:
            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.BLOCK_SIZE,
                callback=self._audio_callback
            )
            self._stream.start()
            self.is_active = True
            return True
        except Exception as e:
            print(f"Failed to start audio stream: {e}")
            self.is_active = False
            return False

    def stop(self):
        """Stops the audio output stream."""
        if not self.is_active:
            return

        self.is_active = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        # Clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break

    def write(self, audio_data: np.ndarray):
        """Pushes audio chunk (float32) into the playback queue."""
        if not self.is_active or self.muted:
            return

        if len(audio_data) == 0:
            return

        # Ensure float32 1D
        data = audio_data.astype(np.float32)
        if self.volume != 1.0:
            data = data * self.volume

        try:
            self._queue.put_nowait(data)
        except queue.Full:
            # Drop oldest block if falling behind to maintain low latency
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(data)
            except Exception:
                pass

    def _audio_callback(self, outdata, frames, time_info, status):
        """Sounddevice callback running on the high-priority audio thread."""
        needed = frames
        pos = 0

        while pos < needed:
            if not hasattr(self, "_current_block") or self._current_block is None or len(self._current_block) == 0:
                try:
                    self._current_block = self._queue.get_nowait()
                except queue.Empty:
                    # Buffer under-run: output silence
                    outdata[pos:, 0] = 0.0
                    return

            avail = len(self._current_block)
            take = min(avail, needed - pos)
            outdata[pos:pos + take, 0] = self._current_block[:take]
            self._current_block = self._current_block[take:]
            pos += take

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(2.0, float(volume)))

    def set_mute(self, mute: bool):
        self.muted = bool(mute)
