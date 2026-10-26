"""Unit tests for Protocol Decoder and Signal Generator."""

import unittest
import numpy as np
from dsp.protocol_decoder import ProtocolDecoder
from dsp.signal_gen import SignalGenerator, SignalType


class TestProtocolAndSignalGen(unittest.TestCase):

    def test_signal_generator_cw(self):
        sig_gen = SignalGenerator(sample_rate=2e6)
        sig_gen.signal_type = SignalType.CW
        sig_gen.offset_hz = 50e3
        chunk = sig_gen.generate_chunk(1024)

        self.assertEqual(len(chunk), 1024)
        self.assertEqual(chunk.dtype, np.complex64)
        # Power should be close to amplitude^2
        mean_power = np.mean(np.abs(chunk) ** 2)
        self.assertAlmostEqual(mean_power, 0.7 ** 2, delta=0.05)

    def test_signal_generator_two_tone(self):
        sig_gen = SignalGenerator(sample_rate=2e6)
        sig_gen.signal_type = SignalType.TWO_TONE
        chunk = sig_gen.generate_chunk(1024)
        self.assertEqual(len(chunk), 1024)

    def test_protocol_decoder_pulse_detection(self):
        decoder = ProtocolDecoder(sample_rate=1e6)

        # Synthesize a clear 32-bit OOK pulse train
        # Short pulse: 300 us, Long pulse: 900 us, Gap: 300 us
        samples_per_us = 1  # at 1 MSPS, 1 sample = 1 us
        pulses = []

        # 16 alternating bits
        pattern = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1]
        for bit in pattern:
            high_len = 900 if bit == 1 else 300
            low_len = 400
            pulses.append(np.ones(high_len, dtype=np.complex64) * 0.8)
            pulses.append(np.zeros(low_len, dtype=np.complex64))

        # Long gap at the end to finalize packet
        pulses.append(np.zeros(20000, dtype=np.complex64))

        iq_stream = np.concatenate(pulses)
        packets = decoder.process_iq(iq_stream)

        self.assertGreater(len(packets), 0)
        pkt = packets[0]
        self.assertTrue(pkt.hex_str.startswith("0x"))
        self.assertGreater(len(pkt.binary_str), 8)


if __name__ == "__main__":
    unittest.main()
