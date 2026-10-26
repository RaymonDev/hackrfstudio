"""
Multi-Mode SDR Demodulation Engine.
Supports:
- WFM (Wideband FM Broadcast Radio with 50/75us de-emphasis)
- NFM (Narrowband FM Walkie-Talkies / Marine / Ham)
- AM (Aviation Airband / Shortwave Envelope Detector)
- USB / LSB (Single Sideband HF/VHF Voice)
- CW (Continuous Wave / Morse with 700 Hz BFO)
"""

import numpy as np
from enum import Enum
from scipy import signal
from typing import Tuple, Optional
from .filter import frequency_shift, DeemphasisFilter, LowPassFilter, DCBlocker


class DemodMode(Enum):
    WFM = "WFM (Wideband FM)"
    NFM = "NFM (Narrowband FM)"
    AM = "AM (Airband / Aviation)"
    USB = "USB (Upper Sideband)"
    LSB = "LSB (Lower Sideband)"
    CW = "CW (Morse Code)"
    RAW = "RAW (No Demod)"


class SDRDemodulator:
    """Real-time demodulator processing I/Q chunks into speaker-ready PCM audio."""

    AUDIO_RATE = 48000  # 48 kHz standard audio rate

    def __init__(self, sample_rate: float = 2.0e6, mode: DemodMode = DemodMode.WFM):
        self.sample_rate = float(sample_rate)
        self.mode = mode
        self.channel_offset_hz: float = 0.0  # Offset from LO center frequency

        # Squelch & Gain
        self.squelch_threshold_db: float = -70.0  # dBFS
        self.squelch_open: bool = False
        self.audio_gain: float = 1.0
        self.agc_enabled: bool = True
        self._agc_peak: float = 0.1

        # Phase tracking state for smooth inter-chunk processing
        self._mixer_phase = 0.0
        self._last_sample = 0.0 + 0.0j
        self._bfo_phase = 0.0

        # Filters
        self._deemphasis = DeemphasisFilter(sample_rate=self.AUDIO_RATE, tau=50e-6)
        self._dc_blocker = DCBlocker()
        self._audio_lpf = LowPassFilter(cutoff_hz=15000.0, sample_rate=self.AUDIO_RATE)

    def set_mode(self, mode: DemodMode):
        self.mode = mode
        # Adjust audio filter according to mode
        if mode == DemodMode.WFM:
            self._audio_lpf.set_cutoff(16000.0)
        elif mode == DemodMode.NFM:
            self._audio_lpf.set_cutoff(4000.0)
        elif mode == DemodMode.AM:
            self._audio_lpf.set_cutoff(4500.0)
        elif mode in (DemodMode.USB, DemodMode.LSB):
            self._audio_lpf.set_cutoff(3000.0)
        elif mode == DemodMode.CW:
            self._audio_lpf.set_cutoff(1000.0)

    def set_sample_rate(self, rate: float):
        self.sample_rate = float(rate)

    def set_channel_offset(self, offset_hz: float):
        self.channel_offset_hz = float(offset_hz)

    def set_squelch(self, threshold_db: float):
        self.squelch_threshold_db = float(threshold_db)

    def set_volume(self, volume_pct: float):
        # 0.0 to 1.0
        self.audio_gain = max(0.0, min(2.0, float(volume_pct)))

    def demodulate(self, iq_chunk: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Demodulates an I/Q chunk into 48 kHz mono float32 audio [-1.0, 1.0].
        Returns (audio_samples, current_rssi_db).
        """
        if len(iq_chunk) == 0:
            return np.zeros(0, dtype=np.float32), -100.0

        # 1. Frequency Translation to selected channel
        shifted_iq, self._mixer_phase = frequency_shift(
            iq_chunk, self.channel_offset_hz, self.sample_rate, self._mixer_phase
        )

        # 2. RSSI (Signal strength in dBFS)
        mean_power = np.mean(np.abs(shifted_iq) ** 2)
        rssi_db = float(10.0 * np.log10(max(mean_power, 1e-12)))

        # Squelch check
        self.squelch_open = (rssi_db >= self.squelch_threshold_db)

        # Calculate decimation factor from RF sample rate down to intermediate/audio rate
        # Target intermediate baseband rate: ~192 kHz for WFM, ~48 kHz for NFM/AM
        intermediate_rate = 192000 if self.mode == DemodMode.WFM else 48000
        decimation = max(1, int(round(self.sample_rate / intermediate_rate)))
        actual_intermediate_rate = self.sample_rate / decimation

        # Decimate I/Q to intermediate rate
        iq_baseband = shifted_iq[::decimation]

        if not self.squelch_open:
            # Muted by squelch - return silence matching expected audio duration
            expected_audio_len = int(len(iq_chunk) * (self.AUDIO_RATE / self.sample_rate))
            return np.zeros(expected_audio_len, dtype=np.float32), rssi_db

        # 3. Demodulation Algorithm
        if self.mode == DemodMode.WFM:
            audio = self._demod_fm(iq_baseband)
            # Resample intermediate rate to 48 kHz
            audio = signal.resample_poly(audio, up=self.AUDIO_RATE, down=int(actual_intermediate_rate))
            audio = self._deemphasis.process(audio)
            audio = self._audio_lpf.process(audio)

        elif self.mode == DemodMode.NFM:
            audio = self._demod_fm(iq_baseband)
            if int(actual_intermediate_rate) != self.AUDIO_RATE:
                audio = signal.resample_poly(audio, up=self.AUDIO_RATE, down=int(actual_intermediate_rate))
            audio = self._audio_lpf.process(audio)

        elif self.mode == DemodMode.AM:
            # Envelope detector: |s[n]|
            audio = np.abs(iq_baseband).astype(np.float32)
            audio = self._dc_blocker.process(audio)
            if int(actual_intermediate_rate) != self.AUDIO_RATE:
                audio = signal.resample_poly(audio, up=self.AUDIO_RATE, down=int(actual_intermediate_rate))
            audio = self._audio_lpf.process(audio)

        elif self.mode == DemodMode.USB:
            # Upper Sideband
            audio = np.real(iq_baseband).astype(np.float32)
            if int(actual_intermediate_rate) != self.AUDIO_RATE:
                audio = signal.resample_poly(audio, up=self.AUDIO_RATE, down=int(actual_intermediate_rate))
            audio = self._audio_lpf.process(audio)

        elif self.mode == DemodMode.LSB:
            # Lower Sideband
            audio = np.imag(iq_baseband).astype(np.float32)
            if int(actual_intermediate_rate) != self.AUDIO_RATE:
                audio = signal.resample_poly(audio, up=self.AUDIO_RATE, down=int(actual_intermediate_rate))
            audio = self._audio_lpf.process(audio)

        elif self.mode == DemodMode.CW:
            # Inject 700 Hz BFO tone
            t = np.arange(len(iq_baseband)) / actual_intermediate_rate
            bfo = np.cos(2.0 * np.pi * 700.0 * t + self._bfo_phase)
            self._bfo_phase = (self._bfo_phase + 2.0 * np.pi * 700.0 * len(t) / actual_intermediate_rate) % (2.0 * np.pi)
            audio = (np.real(iq_baseband) * bfo).astype(np.float32)
            if int(actual_intermediate_rate) != self.AUDIO_RATE:
                audio = signal.resample_poly(audio, up=self.AUDIO_RATE, down=int(actual_intermediate_rate))
            audio = self._audio_lpf.process(audio)

        else:
            audio = np.real(iq_baseband).astype(np.float32)

        # 4. AGC and Output Gain
        if self.agc_enabled and len(audio) > 0:
            peak = np.max(np.abs(audio))
            if peak > 1e-4:
                # Smooth peak tracking
                self._agc_peak = 0.95 * self._agc_peak + 0.05 * peak
                audio = audio / max(0.01, self._agc_peak) * 0.7

        audio = np.clip(audio * self.audio_gain, -1.0, 1.0).astype(np.float32)
        return audio, rssi_db

    def _demod_fm(self, iq: np.ndarray) -> np.ndarray:
        """Quadrature phase discriminator: d(theta) / dt = angle(s[n] * conj(s[n-1]))."""
        if len(iq) < 2:
            return np.zeros(len(iq), dtype=np.float32)

        # Prepend last sample from previous chunk for smooth phase continuity
        extended = np.empty(len(iq) + 1, dtype=np.complex64)
        extended[0] = self._last_sample
        extended[1:] = iq
        self._last_sample = iq[-1]

        # Phase difference
        product = extended[1:] * np.conj(extended[:-1])
        phase_diff = np.angle(product)
        return phase_diff.astype(np.float32)
