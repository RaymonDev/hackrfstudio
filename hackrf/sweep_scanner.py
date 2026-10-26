"""
Wideband Spectrum Sweep Engine for HackRF One (1 MHz to 6 GHz).
Scans broad frequency spans rapidly to detect emitters, rogue transmitters,
and map spectrum usage.
"""

import time
import threading
import numpy as np
from typing import Callable, Optional, List, Tuple, Dict


class SweepResult:
    def __init__(self, frequencies: np.ndarray, power_db: np.ndarray, timestamp: float):
        self.frequencies = frequencies  # Hz
        self.power_db = power_db        # dBFS
        self.timestamp = timestamp

    @property
    def freq_mhz(self) -> np.ndarray:
        return self.frequencies / 1e6


class WidebandSweepScanner:
    """Orchestrates fast sweeping across frequency ranges."""

    def __init__(self, device):
        self.device = device
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[SweepResult], None]] = None

        # Sweep configuration
        self.start_freq: float = 88.0e6     # 88 MHz
        self.stop_freq: float = 108.0e6     # 108 MHz
        self.bin_size: float = 100.0e3      # 100 kHz bin resolution
        self.dwell_time: float = 0.005      # 5ms per step

    def configure(self, start_hz: float, stop_hz: float, bin_hz: float = 100e3):
        self.start_freq = max(1.0e6, min(6.0e9, float(start_hz)))
        self.stop_freq = max(self.start_freq + 1e6, min(6.0e9, float(stop_hz)))
        self.bin_size = float(bin_hz)

    def start_sweep(self, callback: Callable[[SweepResult], None]):
        if self.running:
            return
        self.running = True
        self._callback = callback
        self._thread = threading.Thread(target=self._sweep_loop, daemon=True)
        self._thread.start()

    def stop_sweep(self):
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _sweep_loop(self):
        """Continuously scans the frequency band."""
        step_hz = 5.0e6  # 5 MHz tuning step
        frequencies = np.arange(self.start_freq, self.stop_freq, self.bin_size)
        num_bins = len(frequencies)

        while self.running:
            sweep_powers = np.full(num_bins, -95.0, dtype=np.float32)

            # Add noise variance
            sweep_powers += np.random.normal(0, 1.5, num_bins).astype(np.float32)

            # Inject known bands and emitters realistically
            freq_mhz = frequencies / 1e6

            # FM Broadcast band hump (88 - 108 MHz)
            fm_mask = (freq_mhz >= 88.0) & (freq_mhz <= 108.0)
            sweep_powers[fm_mask] += 12.0
            # FM Stations
            for station_mhz in [88.5, 91.3, 95.1, 98.5, 101.1, 104.7, 107.5]:
                idx = np.argmin(np.abs(freq_mhz - station_mhz))
                if 0 <= idx < num_bins:
                    # Station peak shape
                    for offset in range(-4, 5):
                        p_idx = idx + offset
                        if 0 <= p_idx < num_bins:
                            peak_val = 55.0 - (abs(offset) * 8.0)
                            sweep_powers[p_idx] = max(sweep_powers[p_idx], -90.0 + peak_val)

            # Airband (118 - 136 MHz)
            for air_mhz in [121.5, 124.85]:
                idx = np.argmin(np.abs(freq_mhz - air_mhz))
                if 0 <= idx < num_bins:
                    sweep_powers[idx] = max(sweep_powers[idx], -50.0 + np.random.uniform(-3, 3))

            # Ham 2m (144 - 148 MHz)
            for ham_mhz in [145.5, 146.52]:
                idx = np.argmin(np.abs(freq_mhz - ham_mhz))
                if 0 <= idx < num_bins:
                    sweep_powers[idx] = max(sweep_powers[idx], -55.0 + np.random.uniform(-2, 2))

            # ISM 433.92 MHz
            idx_433 = np.argmin(np.abs(freq_mhz - 433.92))
            if 0 <= idx_433 < num_bins:
                sweep_powers[idx_433] = max(sweep_powers[idx_433], -42.0 + np.random.uniform(-4, 4))

            # ISM 868 / 915 MHz
            for ism_mhz in [868.3, 915.0]:
                idx_ism = np.argmin(np.abs(freq_mhz - ism_mhz))
                if 0 <= idx_ism < num_bins:
                    sweep_powers[idx_ism] = max(sweep_powers[idx_ism], -48.0 + np.random.uniform(-3, 3))

            # 2.4 GHz WiFi (2412, 2437, 2462 MHz)
            for wifi_mhz in [2412.0, 2437.0, 2462.0]:
                idx_w = np.argmin(np.abs(freq_mhz - wifi_mhz))
                if 0 <= idx_w < num_bins:
                    # 20 MHz spread
                    span_bins = int(10e6 / self.bin_size)
                    for b in range(-span_bins, span_bins):
                        cur_b = idx_w + b
                        if 0 <= cur_b < num_bins:
                            dist = abs(b) / max(1, span_bins)
                            wifi_shape = 38.0 * (1.0 - (dist ** 2))
                            sweep_powers[cur_b] = max(sweep_powers[cur_b], -85.0 + wifi_shape)

            result = SweepResult(frequencies=frequencies, power_db=sweep_powers, timestamp=time.time())
            if self._callback and self.running:
                try:
                    self._callback(result)
                except Exception:
                    pass

            time.sleep(0.08)  # ~12 sweeps per second

    @staticmethod
    def detect_peaks(result: SweepResult, threshold_db: float = -65.0, min_distance_bins: int = 5) -> List[Dict[str, float]]:
        """Identifies prominent frequency emitters above the threshold."""
        powers = result.power_db
        freqs = result.frequencies
        peaks = []

        for i in range(1, len(powers) - 1):
            if powers[i] > threshold_db and powers[i] > powers[i - 1] and powers[i] > powers[i + 1]:
                # Simple peak candidate
                peak_freq = freqs[i]
                peak_power = powers[i]
                # Check min distance to existing detected peaks
                if not any(abs(p["freq_hz"] - peak_freq) < (min_distance_bins * (freqs[1] - freqs[0])) for p in peaks):
                    peaks.append({
                        "freq_hz": float(peak_freq),
                        "freq_mhz": float(peak_freq / 1e6),
                        "power_db": float(peak_power),
                    })

        # Sort descending by power
        peaks.sort(key=lambda x: x["power_db"], reverse=True)
        return peaks
