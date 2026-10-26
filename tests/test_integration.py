"""End-to-End integration test for live SDR streaming."""

import time
import unittest
from PyQt5 import QtWidgets, QtCore
from ui.main_window import MainWindow


class TestLiveStreamingE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create single QApplication instance for tests
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def test_live_streaming_pipeline(self):
        window = MainWindow()

        # 1. Start SDR
        window._on_start_stop(True)
        self.assertTrue(window.device._is_streaming)

        # 2. Let it run for 1.5 seconds, pumping Qt events
        start_t = time.time()
        while time.time() - start_t < 1.5:
            self.app.processEvents()
            time.sleep(0.02)

        # Check that we received I/Q samples and computed FFT
        self.assertTrue(hasattr(window, "_latest_iq"))
        self.assertIsNotNone(window._latest_iq)
        self.assertGreater(len(window._latest_iq), 0)

        # 3. Test changing frequency
        window.controls_widget.set_frequency_mhz(433.92)
        self.assertEqual(window.device.center_freq, 433.92e6)

        # Let it stream at 433.92 MHz
        start_t = time.time()
        while time.time() - start_t < 0.5:
            self.app.processEvents()
            time.sleep(0.02)

        # 4. Stop SDR
        window._on_start_stop(False)
        self.assertFalse(window.device._is_streaming)
        window.close()


if __name__ == "__main__":
    unittest.main()
