"""
Digital Signal Processing Filters for SDR Demodulation.
Includes decimation, anti-aliasing FIR/IIR, frequency translation,
FM de-emphasis, and DC removal.
"""

import numpy as np
from scipy import signal
from typing import Tuple


def frequency_shift(iq_data: np.ndarray, offset_hz: float, sample_rate: float, phase_start: float = 0.0) -> Tuple[np.ndarray, float]:
    """
    Shifts the center frequency of I/Q samples by offset_hz via complex mixing:
    s_shifted[n] = s[n] * exp(-j * 2*pi * offset * n / fs)
    Returns shifted samples and next phase start.
    """
    if abs(offset_hz) < 1.0:
        return iq_data, phase_start

    num_samples = len(iq_data)
    delta_phase = 2.0 * np.pi * offset_hz / sample_rate
    phases = phase_start - (np.arange(num_samples) * delta_phase)
    mixer = np.exp(1j * phases).astype(np.complex64)
    shifted = iq_data * mixer
    next_phase = (phases[-1] - delta_phase) % (2.0 * np.pi)
    return shifted, next_phase


def decimate_iq(iq_data: np.ndarray, decimation_factor: int) -> np.ndarray:
    """Downsamples I/Q stream by integer decimation_factor with anti-aliasing."""
    if decimation_factor <= 1:
        return iq_data
    # Use scipy.signal.resample_poly or decimate
    # Subsampling with basic anti-aliasing box/filter for speed in real-time
    try:
        # Downsample real and imag parts separately using scipy decimate
        # Using FIR or simple zero-phase filtering
        q_factor = int(decimation_factor)
        # Fast downsampling for high-rate SDR chunks
        return signal.decimate(iq_data, q_factor, ftype="fir", zero_phase=False)
    except Exception:
        return iq_data[::decimation_factor]


class DeemphasisFilter:
    """
    Broadcast FM De-emphasis filter (single-pole IIR).
    World / Europe: 50 microseconds (tau = 50e-6)
    North America: 75 microseconds (tau = 75e-6)
    """

    def __init__(self, sample_rate: float, tau: float = 50e-6):
        self.sample_rate = float(sample_rate)
        self.tau = float(tau)
        self.alpha = float(np.exp(-1.0 / (self.sample_rate * self.tau)))
        self._prev_y = 0.0

    def set_tau(self, tau: float):
        self.tau = float(tau)
        self.alpha = float(np.exp(-1.0 / (self.sample_rate * self.tau)))

    def process(self, audio: np.ndarray) -> np.ndarray:
        """Applies de-emphasis filter to audio stream."""
        # y[n] = (1 - alpha) * x[n] + alpha * y[n-1]
        b = [1.0 - self.alpha]
        a = [1.0, -self.alpha]
        out, zi = signal.lfilter(b, a, audio, zi=[self._prev_y])
        self._prev_y = float(zi[0])
        return out.astype(np.float32)


class LowPassFilter:
    """Configurable Butterworth Low-Pass Filter for Audio & Baseband."""

    def __init__(self, cutoff_hz: float, sample_rate: float, order: int = 5):
        self.cutoff_hz = float(cutoff_hz)
        self.sample_rate = float(sample_rate)
        self.order = order
        self._design_filter()
        self._zi = signal.lfilter_zi(self.b, self.a)

    def _design_filter(self):
        nyquist = 0.5 * self.sample_rate
        norm_cutoff = min(0.99, max(0.01, self.cutoff_hz / nyquist))
        self.b, self.a = signal.butter(self.order, norm_cutoff, btype="low")

    def set_cutoff(self, cutoff_hz: float):
        self.cutoff_hz = float(cutoff_hz)
        self._design_filter()
        self._zi = signal.lfilter_zi(self.b, self.a)

    def process(self, data: np.ndarray) -> np.ndarray:
        out, self._zi = signal.lfilter(self.b, self.a, data, zi=self._zi)
        return out.astype(np.float32)


class DCBlocker:
    """Removes DC offset from demodulated audio signals."""

    def __init__(self, alpha: float = 0.995):
        self.alpha = float(alpha)
        self._prev_x = 0.0
        self._prev_y = 0.0

    def process(self, data: np.ndarray) -> np.ndarray:
        # y[n] = x[n] - x[n-1] + alpha * y[n-1]
        b = [1.0, -1.0]
        a = [1.0, -self.alpha]
        out, zi = signal.lfilter(b, a, data, zi=[self._prev_y])
        self._prev_y = float(zi[0])
        return out.astype(np.float32)
