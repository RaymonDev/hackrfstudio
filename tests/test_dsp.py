"""Unit tests for DSP algorithms, demodulators, and filters."""

import unittest
import numpy as np
from dsp.fft_processor import FFTProcessor
from dsp.demodulator import SDRDemodulator, DemodMode
from dsp.filter import frequency_shift, DeemphasisFilter, LowPassFilter, DCBlocker


class TestDSP(unittest.TestCase):

    def test_fft_processor(self):
        fft_proc = FFTProcessor(fft_size=1024, window_name="Hann")
        sample_rate = 2.0e6
        center_freq = 100.0e6

        # Test carrier at +200 kHz offset
        t = np.arange(2048) / sample_rate
        test_signal = (np.exp(1j * 2.0 * np.pi * 200e3 * t)).astype(np.complex64)

        freqs, power_db, peak_db = fft_proc.process(test_signal, center_freq, sample_rate)

        self.assertEqual(len(freqs), 1024)
        self.assertEqual(len(power_db), 1024)
        # Verify peak is near 100.2 MHz
        peak_idx = np.argmax(power_db)
        peak_freq = freqs[peak_idx]
        self.assertAlmostEqual(peak_freq, 100.2, delta=0.01)

    def test_frequency_shift(self):
        sample_rate = 1.0e6
        t = np.arange(1000) / sample_rate
        carrier = np.exp(1j * 2.0 * np.pi * 100e3 * t).astype(np.complex64)

        # Shift down by 100 kHz -> should be DC (0 Hz)
        shifted, _ = frequency_shift(carrier, 100e3, sample_rate)
        # Phase difference between adjacent samples should be ~0
        phase_diffs = np.angle(shifted[1:] * np.conj(shifted[:-1]))
        self.assertAlmostEqual(float(np.mean(phase_diffs)), 0.0, delta=0.05)

    def test_am_demodulation(self):
        demod = SDRDemodulator(sample_rate=1.0e6, mode=DemodMode.AM)
        demod.set_squelch(-100.0)  # Open squelch
        t = np.arange(65536) / 1.0e6
        audio_freq = 1000.0  # 1 kHz audio tone

        # AM signal: (1 + 0.8 * sin(2*pi*fa*t))
        envelope = 1.0 + 0.8 * np.sin(2.0 * np.pi * audio_freq * t)
        iq = (envelope + 0j).astype(np.complex64)

        audio, rssi = demod.demodulate(iq)
        self.assertGreater(len(audio), 0)
        self.assertTrue(demod.squelch_open)
        self.assertGreater(rssi, -40.0)

    def test_wfm_demodulation(self):
        demod = SDRDemodulator(sample_rate=2.0e6, mode=DemodMode.WFM)
        demod.set_squelch(-100.0)
        t = np.arange(65536) / 2.0e6
        audio_freq = 440.0  # 440 Hz tone

        # FM: exp(j * integral(kf * audio))
        phase = (75000.0 / audio_freq) * np.sin(2.0 * np.pi * audio_freq * t)
        iq = np.exp(1j * phase).astype(np.complex64)

        audio, rssi = demod.demodulate(iq)
        self.assertGreater(len(audio), 0)
        self.assertTrue(demod.squelch_open)

    def test_deemphasis_filter(self):
        deemph = DeemphasisFilter(sample_rate=48000, tau=50e-6)
        # Test impulse response is decaying
        impulse = np.zeros(100, dtype=np.float32)
        impulse[0] = 1.0
        response = deemph.process(impulse)
        self.assertGreater(response[0], response[1])
        self.assertGreater(response[1], response[2])

    def test_dc_blocker(self):
        dc_block = DCBlocker(alpha=0.99)
        # Constant DC signal of 5.0 across 1000 samples
        dc_signal = np.full(1000, 5.0, dtype=np.float32)
        out = dc_block.process(dc_signal)
        # Output should decay toward 0.0 (0.99^1000 * 5.0 < 0.001)
        self.assertLess(abs(out[-1]), 0.01)


if __name__ == "__main__":
    unittest.main()
