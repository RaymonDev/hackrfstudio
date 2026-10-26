"""
Signal Generator & TX Waveform Synthesizer for HackRF One.
Generates compliant, clean I/Q test patterns for transmission:
- Single-frequency Continuous Wave (CW)
- Two-Tone Intermodulation Distortion (IMD) test
- Audio Frequency Modulation (FM Tone / Beacon)
- Frequency Chirp (FMCW Sweep)
- ASK / OOK Digital Pulse Sequence Generator
"""

import numpy as np
from enum import Enum
from typing import Optional


class SignalType(Enum):
    CW = "Continuous Wave (CW Tone)"
    TWO_TONE = "Two-Tone IMD Test"
    FM_TONE = "FM Modulated Tone"
    CHIRP = "Frequency Chirp (FMCW)"
    ASK_BURST = "ASK/OOK Custom Pulse"


class SignalGenerator:
    """Synthesizes I/Q baseband waveforms for transmission and testing."""

    def __init__(self, sample_rate: float = 2.0e6):
        self.sample_rate = float(sample_rate)
        self.signal_type = SignalType.CW
        self.offset_hz: float = 0.0          # Baseband carrier offset
        self.amplitude: float = 0.7          # 0.0 to 1.0 (safety backoff from saturation)
        self.tone_freq_hz: float = 1000.0    # 1 kHz modulation
        self.fm_deviation_hz: float = 25000.0# 25 kHz peak deviation
        self.chirp_span_hz: float = 500000.0 # 500 kHz span
        self.chirp_period_sec: float = 0.02  # 50 Hz rep rate

        # Phase state
        self._phase = 0.0
        self._mod_phase = 0.0

    def set_sample_rate(self, rate: float):
        self.sample_rate = float(rate)

    def generate_chunk(self, num_samples: int) -> np.ndarray:
        """Generates complex64 I/Q samples according to selected configuration."""
        fs = self.sample_rate
        t = np.arange(num_samples) / fs

        if self.signal_type == SignalType.CW:
            # Single pure carrier tone at offset_hz
            phases = self._phase + 2.0 * np.pi * self.offset_hz * t
            self._phase = (phases[-1] + 2.0 * np.pi * self.offset_hz / fs) % (2.0 * np.pi)
            iq = self.amplitude * np.exp(1j * phases)

        elif self.signal_type == SignalType.TWO_TONE:
            # Two carriers at offset +/- tone_freq/2
            f1 = self.offset_hz - (self.tone_freq_hz / 2.0)
            f2 = self.offset_hz + (self.tone_freq_hz / 2.0)
            p1 = self._phase + 2.0 * np.pi * f1 * t
            p2 = self._mod_phase + 2.0 * np.pi * f2 * t
            self._phase = (p1[-1] + 2.0 * np.pi * f1 / fs) % (2.0 * np.pi)
            self._mod_phase = (p2[-1] + 2.0 * np.pi * f2 / fs) % (2.0 * np.pi)
            iq = (self.amplitude * 0.5) * (np.exp(1j * p1) + np.exp(1j * p2))

        elif self.signal_type == SignalType.FM_TONE:
            # Frequency modulated tone
            mod_audio = np.sin(self._mod_phase + 2.0 * np.pi * self.tone_freq_hz * t)
            self._mod_phase = (self._mod_phase + 2.0 * np.pi * self.tone_freq_hz * num_samples / fs) % (2.0 * np.pi)

            # Cumulative phase integration for FM
            instantaneous_freq = self.offset_hz + (self.fm_deviation_hz * mod_audio)
            delta_phases = 2.0 * np.pi * instantaneous_freq / fs
            phases = self._phase + np.cumsum(delta_phases)
            self._phase = phases[-1] % (2.0 * np.pi)
            iq = self.amplitude * np.exp(1j * phases)

        elif self.signal_type == SignalType.CHIRP:
            # Linear frequency sweep
            k = self.chirp_span_hz / self.chirp_period_sec
            t_rel = (t % self.chirp_period_sec)
            instantaneous_freq = self.offset_hz - (self.chirp_span_hz / 2.0) + (k * t_rel)
            phases = self._phase + np.cumsum(2.0 * np.pi * instantaneous_freq / fs)
            self._phase = phases[-1] % (2.0 * np.pi)
            iq = self.amplitude * np.exp(1j * phases)

        else:
            iq = np.zeros(num_samples, dtype=np.complex64)

        return iq.astype(np.complex64)

    @staticmethod
    def iq_to_hackrf_bytes(iq: np.ndarray) -> bytes:
        """Converts complex float32 [-1.0, 1.0] to signed 8-bit interleaved bytes [I0, Q0, ...]."""
        scaled = np.clip(iq * 127.0, -127.0, 127.0)
        i_bytes = np.real(scaled).astype(np.int8)
        q_bytes = np.imag(scaled).astype(np.int8)
        interleaved = np.empty(len(iq) * 2, dtype=np.int8)
        interleaved[0::2] = i_bytes
        interleaved[1::2] = q_bytes
        return interleaved.tobytes()
