"""Unit tests for I/Q recording and file playback."""

import os
import tempfile
import unittest
import numpy as np
from recording.iq_file import IQRecorder, IQPlayer, FileFormat


class TestFileIO(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.temp_dir):
            try:
                os.remove(os.path.join(self.temp_dir, f))
            except Exception:
                pass
        try:
            os.rmdir(self.temp_dir)
        except Exception:
            pass

    def test_record_and_play_hackrf_int8(self):
        rec_path = os.path.join(self.temp_dir, "test_cap.c8")
        recorder = IQRecorder()
        sample_rate = 2e6
        center_freq = 100e6

        recorder.start_recording(rec_path, FileFormat.HACKRF_INT8, center_freq, sample_rate)

        # Generate test chunk
        test_chunk = (0.5 * np.ones(1024) + 1j * 0.5 * np.ones(1024)).astype(np.complex64)
        recorder.write_chunk(test_chunk)
        info = recorder.stop_recording()

        self.assertTrue(os.path.isfile(rec_path))
        self.assertEqual(info["bytes_written"], 1024 * 2)  # 2 bytes per complex sample

        # Test sidecar metadata JSON
        meta_path = rec_path + ".json"
        self.assertTrue(os.path.isfile(meta_path))

        # Test player loading
        player = IQPlayer()
        loaded = player.load_file(rec_path)
        self.assertTrue(loaded)
        self.assertEqual(player.center_freq, center_freq)
        self.assertEqual(player.sample_rate, sample_rate)

    def test_record_float32(self):
        rec_path = os.path.join(self.temp_dir, "test_cap.cf32")
        recorder = IQRecorder()
        recorder.start_recording(rec_path, FileFormat.FLOAT32, 433.92e6, 2e6)

        chunk = (np.random.normal(0, 0.5, 512) + 1j * np.random.normal(0, 0.5, 512)).astype(np.complex64)
        recorder.write_chunk(chunk)
        info = recorder.stop_recording()

        self.assertTrue(os.path.isfile(rec_path))
        self.assertEqual(info["bytes_written"], 512 * 8)  # 8 bytes per complex64 sample


if __name__ == "__main__":
    unittest.main()
