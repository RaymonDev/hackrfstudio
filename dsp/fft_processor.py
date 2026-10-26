"""
High-Performance Spectrum & FFT Processing Engine.
Computes fast complex FFTs with windowing, exponential smoothing,
and peak-hold detection.
"""

import numpy as np
from typing import Tuple, Optional


class FFTProcessor:
    """Computes FFT and power spectrum for real-time SDR visualization."""

    WINDOWS = {
        "Hann": np.hanning,
        "Hamming": np.hamming,
        "Blackman": np.blackman,
        "Rectangular": np.ones,
    }

    def __init__(self, fft_size: int = 2048, window_name: str = "Hann"):
        self.fft_size = int(fft_size)
        self.window_name = window_name
        self._window = self._create_window(self.window_name, self.fft_size)

        # Averaging & peak hold
        self.averaging_alpha = 0.5  # 0.0 (no update) to 1.0 (no smoothing)
        self._smoothed_db: Optional[np.ndarray] = None
        self._peak_hold_db: Optional[np.ndarray] = None
        self.peak_hold_enabled = False

    def set_fft_size(self, size: int):
        if size != self.fft_size and size > 0:
            self.fft_size = int(size)
            self._window = self._create_window(self.window_name, self.fft_size)
            self._smoothed_db = None
            self._peak_hold_db = None

    def set_window(self, window_name: str):
        if window_name in self.WINDOWS:
            self.window_name = window_name
            self._window = self._create_window(self.window_name, self.fft_size)

    def set_averaging(self, alpha: float):
        self.averaging_alpha = max(0.01, min(1.0, float(alpha)))

    def reset_peak_hold(self):
        self._peak_hold_db = None

    def _create_window(self, name: str, size: int) -> np.ndarray:
        func = self.WINDOWS.get(name, np.hanning)
        return func(size).astype(np.float32)

    def process(self, iq_samples: np.ndarray, center_freq: float, sample_rate: float) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
        """
        Processes complex I/Q samples into power spectrum (in dBFS).
        Returns:
            frequencies_mhz: 1D array of frequency points in MHz
            power_db: 1D array of current/smoothed power in dBFS
            peak_db: 1D array of peak-hold power (or None)
        """
        n = self.fft_size
        if len(iq_samples) < n:
            # Pad with zeros if buffer is smaller than fft_size
            padded = np.zeros(n, dtype=np.complex64)
            padded[:len(iq_samples)] = iq_samples
            iq_slice = padded
        else:
            # Use most recent n samples
            iq_slice = iq_samples[-n:]

        # Apply window
        windowed = iq_slice * self._window

        # Fast Fourier Transform & FFT Shift
        fft_result = np.fft.fftshift(np.fft.fft(windowed, n=n))

        # Power spectrum in dBFS (normalized to full scale)
        # Avoid log of zero
        mag_sq = (np.abs(fft_result) / n) ** 2
        power_db = 10.0 * np.log10(np.maximum(mag_sq, 1e-13))

        # Exponential smoothing (averaging)
        if self._smoothed_db is None or len(self._smoothed_db) != n:
            self._smoothed_db = power_db.copy()
        else:
            self._smoothed_db = (self.averaging_alpha * power_db) + ((1.0 - self.averaging_alpha) * self._smoothed_db)

        # Peak hold
        if self.peak_hold_enabled:
            if self._peak_hold_db is None or len(self._peak_hold_db) != n:
                self._peak_hold_db = self._smoothed_db.copy()
            else:
                self._peak_hold_db = np.maximum(self._peak_hold_db, self._smoothed_db)
        else:
            self._peak_hold_db = None

        # Frequency axis in MHz
        freq_step = sample_rate / n
        freq_offsets = (np.arange(n) - (n // 2)) * freq_step
        frequencies_mhz = (center_freq + freq_offsets) / 1e6

        return frequencies_mhz, self._smoothed_db, self._peak_hold_db
