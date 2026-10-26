"""
Raw I/Q Signal File Recorder & Playback Engine.
Supports:
- HackRF Native 8-bit signed interleaved format (.c8 / .bin)
- GNU Radio 32-bit complex float (.cf32)
- Standard 16-bit stereo WAV (Left=I, Right=Q)
- JSON metadata sidecar (center frequency, sample rate, timestamps)
"""

import os
import json
import time
import wave
import threading
import numpy as np
from enum import Enum
from typing import Optional, Callable, Dict, Any


class FileFormat(Enum):
    HACKRF_INT8 = "HackRF Native (8-bit signed I/Q)"
    FLOAT32 = "GNU Radio Complex (Float32 I/Q)"
    WAV16 = "16-bit Stereo PCM WAV (I/Q)"


class IQRecorder:
    """Records real-time I/Q data streams to disk."""

    def __init__(self):
        self.is_recording = False
        self.file_path: Optional[str] = None
        self.file_format = FileFormat.HACKRF_INT8
        self._file_handle = None
        self._wav_handle = None
        self._bytes_written = 0
        self._start_time = 0.0

    def start_recording(self, file_path: str, format: FileFormat, center_freq: float, sample_rate: float):
        """Starts recording I/Q stream to the specified file."""
        if self.is_recording:
            return

        self.file_path = file_path
        self.file_format = format
        self._bytes_written = 0
        self._start_time = time.time()

        if format == FileFormat.WAV16:
            self._wav_handle = wave.open(file_path, "wb")
            self._wav_handle.setnchannels(2)  # Stereo: Left=I, Right=Q
            self._wav_handle.setsampwidth(2)   # 16-bit PCM
            self._wav_handle.setframerate(min(192000, int(sample_rate)))
        else:
            self._file_handle = open(file_path, "wb")

        # Write metadata sidecar JSON
        meta_path = file_path + ".json"
        meta_data = {
            "center_frequency_hz": float(center_freq),
            "sample_rate_hz": float(sample_rate),
            "format": format.name,
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "generator": "HackRF Studio",
        }
        try:
            with open(meta_path, "w") as f:
                json.dump(meta_data, f, indent=2)
        except Exception:
            pass

        self.is_recording = True

    def write_chunk(self, iq_chunk: np.ndarray):
        """Writes an I/Q chunk to file."""
        if not self.is_recording or len(iq_chunk) == 0:
            return

        if self.file_format == FileFormat.HACKRF_INT8:
            scaled = np.clip(iq_chunk * 127.0, -127.0, 127.0)
            interleaved = np.empty(len(iq_chunk) * 2, dtype=np.int8)
            interleaved[0::2] = np.real(scaled).astype(np.int8)
            interleaved[1::2] = np.imag(scaled).astype(np.int8)
            data_bytes = interleaved.tobytes()
            self._file_handle.write(data_bytes)
            self._bytes_written += len(data_bytes)

        elif self.file_format == FileFormat.FLOAT32:
            data_bytes = iq_chunk.astype(np.complex64).tobytes()
            self._file_handle.write(data_bytes)
            self._bytes_written += len(data_bytes)

        elif self.file_format == FileFormat.WAV16:
            scaled = np.clip(iq_chunk * 32767.0, -32767.0, 32767.0)
            interleaved = np.empty(len(iq_chunk) * 2, dtype=np.int16)
            interleaved[0::2] = np.real(scaled).astype(np.int16)
            interleaved[1::2] = np.imag(scaled).astype(np.int16)
            self._wav_handle.writeframes(interleaved.tobytes())
            self._bytes_written += interleaved.nbytes

    def stop_recording(self) -> Dict[str, Any]:
        """Stops recording and closes file handles."""
        if not self.is_recording:
            return {}

        self.is_recording = False
        duration = time.time() - self._start_time

        if self._file_handle:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None

        if self._wav_handle:
            try:
                self._wav_handle.close()
            except Exception:
                pass
            self._wav_handle = None

        return {
            "file_path": self.file_path,
            "duration_sec": duration,
            "bytes_written": self._bytes_written,
            "mb_written": self._bytes_written / (1024 * 1024),
        }

    def get_stats(self) -> Dict[str, Any]:
        duration = time.time() - self._start_time if self.is_recording else 0.0
        return {
            "is_recording": self.is_recording,
            "duration_sec": duration,
            "mb_written": self._bytes_written / (1024 * 1024),
        }


class IQPlayer:
    """Replays captured I/Q files in real-time."""

    def __init__(self):
        self.file_path: Optional[str] = None
        self.sample_rate: float = 2.0e6
        self.center_freq: float = 100.0e6
        self.loop: bool = True
        self.is_playing = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[np.ndarray], None]] = None

    def load_file(self, file_path: str) -> bool:
        """Loads metadata sidecar if available."""
        self.file_path = file_path
        meta_path = file_path + ".json"
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                    self.center_freq = float(meta.get("center_frequency_hz", 100e6))
                    self.sample_rate = float(meta.get("sample_rate_hz", 2e6))
            except Exception:
                pass
        return os.path.isfile(file_path)

    def start_playback(self, callback: Callable[[np.ndarray], None]):
        if self.is_playing or not self.file_path or not os.path.isfile(self.file_path):
            return

        self.is_playing = True
        self._callback = callback
        self._thread = threading.Thread(target=self._play_loop, daemon=True)
        self._thread.start()

    def stop_playback(self):
        self.is_playing = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _play_loop(self):
        chunk_samples = 65536
        dt = chunk_samples / self.sample_rate

        while self.is_playing:
            try:
                with open(self.file_path, "rb") as f:
                    while self.is_playing:
                        # Read chunk of signed 8-bit bytes (HackRF default)
                        raw = f.read(chunk_samples * 2)
                        if not raw:
                            if self.loop:
                                break  # Re-loop to start of file
                            else:
                                self.is_playing = False
                                return

                        raw_np = np.frombuffer(raw, dtype=np.int8).astype(np.float32) / 128.0
                        i_data = raw_np[0::2]
                        q_data = raw_np[1::2]
                        iq_chunk = (i_data + 1j * q_data).astype(np.complex64)

                        t_start = time.perf_counter()
                        if self._callback and self.is_playing:
                            self._callback(iq_chunk)

                        elapsed = time.perf_counter() - t_start
                        sleep_time = dt - elapsed
                        if sleep_time > 0.001:
                            time.sleep(sleep_time)

            except Exception as e:
                print(f"Error during playback: {e}")
                break
