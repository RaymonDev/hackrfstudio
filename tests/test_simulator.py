"""Unit tests for RF Spectrum Simulator."""

import unittest
import numpy as np
from hackrf.simulator import RFSimulator


class TestSimulator(unittest.TestCase):

    def setUp(self):
        self.sim = RFSimulator(sample_rate=2e6, center_freq=100e6)

    def test_block_generation(self):
        block = self.sim.generate_iq_block(4096)
        self.assertEqual(len(block), 4096)
        self.assertEqual(block.dtype, np.complex64)
        # Power should be bounded
        mean_power = np.mean(np.abs(block) ** 2)
        self.assertGreater(mean_power, 1e-6)
        self.assertLess(mean_power, 2.0)

    def test_gain_scaling(self):
        # Min gain
        self.sim.set_lna_gain(0)
        self.sim.set_vga_gain(0)
        block_low = self.sim.generate_iq_block(4096)
        power_low = np.mean(np.abs(block_low) ** 2)

        # High gain
        self.sim.set_lna_gain(40)
        self.sim.set_vga_gain(62)
        block_high = self.sim.generate_iq_block(4096)
        power_high = np.mean(np.abs(block_high) ** 2)

        self.assertGreater(power_high, power_low)

    def test_frequency_tuning(self):
        # Tuning to 433.92 MHz ISM
        self.sim.set_freq(433.92e6)
        self.assertEqual(self.sim.center_freq, 433.92e6)
        block = self.sim.generate_iq_block(4096)
        self.assertEqual(len(block), 4096)


if __name__ == "__main__":
    unittest.main()
