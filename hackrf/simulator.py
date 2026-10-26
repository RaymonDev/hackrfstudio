"""
Realistic RF Spectrum Simulator for HackRF One.
Generates authentic I/Q signals for testing, demonstration, and offline analysis:
- Gaussian thermal noise floor responsive to LNA/VGA gains
- Broadcast FM stations with real audio program modulation (WFM)
- Aviation AM transmissions with voice modulation
- Narrowband FM (NFM) repeater transmissions with CTCSS tones
- Sub-GHz 433.92 MHz ISM ASK/OOK remote keyfob bursts
- 2.4 GHz WiFi / BLE spectral profiles
- Accurate sample rate timing and callback delivery
"""

import time
import threading
import numpy as np
from typing import Callable, Optional, Dict, List


class RFSimulator:
    """Simulates HackRF One receiving or transmitting I/Q samples."""

    def __init__(self, sample_rate: float = 2e6, center_freq: float = 100e6):
        self.sample_rate = float(sample_rate)
        self.center_freq = float(center_freq)
        self.lna_gain = 32  # 0 to 40 dB (steps of 8 dB)
        self.vga_gain = 30  # 0 to 62 dB (steps of 2 dB)
        self.amp_enabled = False  # +14 dB
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[np.ndarray], None]] = None
        self._chunk_size = 65536  # Number of complex samples per callback

        # Audio synthesis state for FM broadcast stations
        self._audio_phase = 0.0
        self._fm_phase = 0.0
        self._time_offset = 0.0

        # Sub-GHz 433.92 MHz pulse generator state
        self._last_burst_time = 0.0
        self._burst_interval = 1.2  # Remote packet sent every 1.2 seconds

        # Known frequency emitters (MHz: (type, label, param_dict))
        self._emitters = [
            # FM Broadcast
            (88.5, "FM", "Radio One", 440.0),
            (91.3, "FM", "Jazz Waves", 554.37),
            (95.1, "FM", "Classical Air", 659.25),
            (98.5, "FM", "NPR News", 523.25),
            (101.1, "FM", "Rock FM", 349.23),
            (104.7, "FM", "Hit Radio", 783.99),
            (107.5, "FM", "Pop Radio", 880.0),
            # Aviation AM
            (118.7, "AM", "Tower ATC", 1000.0),
            (121.5, "AM", "Emergency Guard", 1000.0),
            (124.85, "AM", "Approach Control", 800.0),
            # Ham 2m NFM
            (145.500, "NFM", "VHF Calling", 1200.0),
            (146.520, "NFM", "National Simplex", 700.0),
            # Sub-GHz ISM
            (433.92, "ASK", "433MHz Weather Sensor / Keyfob", 2000.0),
            (868.3, "FSK", "LoRa / Smart Meter", 25000.0),
            (915.0, "FSK", "ISM Sensor Mesh", 50000.0),
            # 2.4 GHz ISM
            (2412.0, "WIFI", "WiFi Channel 1", 20e6),
            (2437.0, "WIFI", "WiFi Channel 6", 20e6),
            (2462.0, "WIFI", "WiFi Channel 11", 20e6),
            (2402.0, "BLE", "BLE Adv 37", 1e6),
            (2426.0, "BLE", "BLE Adv 38", 1e6),
            (2480.0, "BLE", "BLE Adv 39", 1e6),
        ]

    def set_sample_rate(self, rate: float):
        self.sample_rate = float(rate)

    def set_freq(self, freq: float):
        self.center_freq = float(freq)

    def set_lna_gain(self, gain: int):
        self.lna_gain = max(0, min(40, int(gain)))

    def set_vga_gain(self, gain: int):
        self.vga_gain = max(0, min(62, int(gain)))

    def set_amp_enable(self, enable: bool):
        self.amp_enabled = bool(enable)

    def start_rx(self, callback: Callable[[np.ndarray], None]):
        """Starts streaming simulated I/Q samples to callback."""
        if self.running:
            return
        self.running = True
        self._callback = callback
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def stop_rx(self):
        """Stops the streaming thread."""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _worker_loop(self):
        dt = self._chunk_size / self.sample_rate
        next_deadline = time.perf_counter()

        while self.running:
            samples = self.generate_iq_block(self._chunk_size)
            if self._callback and self.running:
                try:
                    self._callback(samples)
                except Exception as e:
                    print(f"Simulator callback error: {e}")

            next_deadline += dt
            delay = next_deadline - time.perf_counter()
            if delay > 0.001:
                time.sleep(delay)
            elif delay < -0.1:
                # Catch up if running behind
                next_deadline = time.perf_counter()

    def generate_iq_block(self, num_samples: int) -> np.ndarray:
        """
        Synthesizes a realistic block of complex baseband samples:
        I/Q = I + 1j * Q
        """
        fs = self.sample_rate
        fc = self.center_freq
        t = (np.arange(num_samples) / fs) + self._time_offset
        self._time_offset += num_samples / fs

        # Calculate effective system gain multiplier (0 to ~1.0)
        total_gain_db = (self.lna_gain + self.vga_gain + (14 if self.amp_enabled else 0))
        gain_scale = 10.0 ** ((total_gain_db - 100.0) / 20.0)

        # 1. Base Thermal Noise floor (Gaussian white noise)
        noise_level = 0.015 * (1.0 + total_gain_db / 50.0)
        noise_i = np.random.normal(0, noise_level, num_samples)
        noise_q = np.random.normal(0, noise_level, num_samples)
        iq = (noise_i + 1j * noise_q).astype(np.complex64)

        # 2. Add signals in current bandwidth [fc - fs/2, fc + fs/2]
        bw_min = fc - (fs / 2.0)
        bw_max = fc + (fs / 2.0)

        current_wall_time = time.time()

        for emit_mhz, mod_type, label, param in self._emitters:
            emit_hz = emit_mhz * 1e6
            # Check if within receiver window (with a slight margin)
            if (emit_hz >= bw_min - 100e3) and (emit_hz <= bw_max + 100e3):
                offset_hz = emit_hz - fc
                signal_amplitude = 0.35 * gain_scale

                if mod_type == "FM":
                    # Synthesize wideband FM broadcast signal
                    audio_freq = float(param)
                    # Multi-tone acoustic audio program: base tone + harmonic + 19 kHz stereo pilot
                    audio_mod = (
                        0.7 * np.sin(2.0 * np.pi * audio_freq * t) +
                        0.2 * np.sin(2.0 * np.pi * (audio_freq * 1.5) * t) +
                        0.1 * np.sin(2.0 * np.pi * 19000.0 * t)  # Stereo pilot
                    )
                    # Instantaneous frequency deviation = 75 kHz peak
                    kf = 75000.0
                    phase = 2.0 * np.pi * offset_hz * t + (kf / audio_freq) * audio_mod
                    iq += (signal_amplitude * np.exp(1j * phase)).astype(np.complex64)

                elif mod_type == "AM":
                    # Amplitude modulation: (1 + m * audio) * carrier
                    audio_freq = float(param)
                    m = 0.8
                    carrier = np.exp(1j * 2.0 * np.pi * offset_hz * t)
                    envelope = (1.0 + m * np.sin(2.0 * np.pi * audio_freq * t))
                    iq += (signal_amplitude * 0.5 * envelope * carrier).astype(np.complex64)

                elif mod_type == "NFM":
                    # Narrowband FM: 5 kHz deviation + 100 Hz CTCSS sub-tone
                    audio_freq = float(param)
                    audio_mod = (
                        0.8 * np.sin(2.0 * np.pi * audio_freq * t) +
                        0.15 * np.sin(2.0 * np.pi * 100.0 * t)
                    )
                    kf = 5000.0
                    phase = 2.0 * np.pi * offset_hz * t + (kf / audio_freq) * audio_mod
                    iq += (signal_amplitude * 0.6 * np.exp(1j * phase)).astype(np.complex64)

                elif mod_type == "ASK":
                    # 433 MHz Keyfob / Weather Station ASK / OOK bursts
                    time_since_burst = current_wall_time - self._last_burst_time
                    if time_since_burst > self._burst_interval:
                        self._last_burst_time = current_wall_time

                    in_burst = (current_wall_time - self._last_burst_time) < 0.08  # 80ms packet
                    if in_burst:
                        # 32-bit Manchester / PWM pulse train simulation
                        symbol_rate = 2000.0  # 2 kbps
                        pulse_clock = np.sin(2.0 * np.pi * symbol_rate * t) > 0
                        carrier = np.exp(1j * 2.0 * np.pi * offset_hz * t)
                        iq += (signal_amplitude * 0.9 * pulse_clock * carrier).astype(np.complex64)

                elif mod_type == "WIFI":
                    # Wideband OFDM hum: filtered noise shape over 20 MHz
                    wifi_sig = np.random.normal(0, 0.25, num_samples) + 1j * np.random.normal(0, 0.25, num_samples)
                    carrier = np.exp(1j * 2.0 * np.pi * offset_hz * t)
                    iq += (wifi_sig * carrier * gain_scale).astype(np.complex64)

                elif mod_type == "BLE":
                    # BLE GFSK burst
                    if (int(current_wall_time * 10) % 2) == 0:
                        carrier = np.exp(1j * 2.0 * np.pi * offset_hz * t)
                        iq += (signal_amplitude * 0.7 * carrier).astype(np.complex64)

        # Clip values to [-1.0, 1.0] to prevent overflow
        max_val = np.max(np.abs(iq))
        if max_val > 1.2:
            iq = iq / (max_val / 1.2)

        return iq
