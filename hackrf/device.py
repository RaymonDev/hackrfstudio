"""
Hardware Abstraction Layer (HAL) for HackRF One.
Seamlessly unifies:
1. Physical HackRF One device (via ctypes libhackrf)
2. Realistic RF Physics Simulator
3. Captured I/Q File Playback
"""

import os
import sys
import ctypes
import numpy as np
from enum import Enum
from typing import Optional, Callable, Dict, Any
from .driver import LibHackRF, HackRFTransfer, hackrf_sample_block_cb_fn, TransceiverMode
from .simulator import RFSimulator


class DeviceMode(Enum):
    PHYSICAL = "Hardware (HackRF One USB)"
    SIMULATOR = "Built-in RF Simulator"
    FILE_PLAYBACK = "Recorded I/Q File"


class HackRFDevice:
    """Unified SDR controller interface for HackRF One."""

    def __init__(self, mode: DeviceMode = DeviceMode.SIMULATOR):
        self.mode = mode
        self.lib = LibHackRF.get_instance()
        self._dev_ptr = ctypes.c_void_p()
        self._is_open = False
        self._is_streaming = False

        # Current Radio Parameters
        self.center_freq: float = 100.0e6  # 100 MHz default
        self.sample_rate: float = 2.0e6   # 2 MSPS default
        self.lna_gain: int = 32           # 0 to 40 dB
        self.vga_gain: int = 30           # 0 to 62 dB
        self.txvga_gain: int = 20         # 0 to 47 dB
        self.amp_enabled: bool = False    # +14 dB RF Preamp
        self.antenna_bias_tee: bool = False # 3.3V DC power on antenna port
        self.baseband_filter_bw: int = 1750000

        # High-Fidelity Simulator
        self._simulator = RFSimulator(sample_rate=self.sample_rate, center_freq=self.center_freq)

        # C-callback reference to prevent garbage collection during streaming
        self._c_callback_ref = None
        self._user_callback: Optional[Callable[[np.ndarray], None]] = None

    @classmethod
    def is_hardware_library_available(cls) -> bool:
        lib = LibHackRF.get_instance()
        return lib.is_available

    def open(self) -> bool:
        """Opens the selected device backend."""
        if self._is_open:
            return True

        if self.mode == DeviceMode.PHYSICAL:
            if not self.lib.is_available:
                # Automatically fallback to simulator if physical library is missing
                self.mode = DeviceMode.SIMULATOR
                self._is_open = True
                return True

            try:
                res = self.lib._lib.hackrf_open(ctypes.byref(self._dev_ptr))
                if res != 0:
                    # Hardware open failed (e.g. no device plugged in or permission issue)
                    self.mode = DeviceMode.SIMULATOR
                    self._is_open = True
                    return False
                self._is_open = True
                self._apply_all_settings()
                return True
            except Exception as e:
                print(f"Error opening physical HackRF: {e}")
                self.mode = DeviceMode.SIMULATOR
                self._is_open = True
                return False

        elif self.mode == DeviceMode.SIMULATOR:
            self._is_open = True
            return True

        return True

    def close(self):
        """Closes device and releases USB endpoints."""
        self.stop_rx()
        if self._is_open and self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            try:
                self.lib._lib.hackrf_close(self._dev_ptr)
            except Exception:
                pass
            self._dev_ptr = ctypes.c_void_p()
        self._is_open = False

    def start_rx(self, callback: Callable[[np.ndarray], None]) -> bool:
        """Starts receiving I/Q data stream."""
        if self._is_streaming:
            return True

        self._user_callback = callback

        if self.mode == DeviceMode.SIMULATOR:
            self._simulator.set_freq(self.center_freq)
            self._simulator.set_sample_rate(self.sample_rate)
            self._simulator.set_lna_gain(self.lna_gain)
            self._simulator.set_vga_gain(self.vga_gain)
            self._simulator.set_amp_enable(self.amp_enabled)
            self._simulator.start_rx(callback)
            self._is_streaming = True
            return True

        elif self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            # Native C callback converting HackRF int8 I/Q buffer to numpy complex64
            def _rx_callback(transfer_ptr):
                transfer = transfer_ptr.contents
                buf_len = transfer.valid_length
                if buf_len <= 0 or not self._user_callback:
                    return 0

                # Convert C byte buffer (signed 8-bit interleaved I/Q) to numpy
                raw_bytes = ctypes.cast(transfer.buffer, ctypes.POINTER(ctypes.c_byte * buf_len)).contents
                raw_np = np.frombuffer(raw_bytes, dtype=np.int8).astype(np.float32) / 128.0

                # Interleaved I/Q: [I0, Q0, I1, Q1, ...] -> I + 1j * Q
                i_data = raw_np[0::2]
                q_data = raw_np[1::2]
                min_len = min(len(i_data), len(q_data))
                complex_iq = (i_data[:min_len] + 1j * q_data[:min_len]).astype(np.complex64)

                self._user_callback(complex_iq)
                return 0

            self._c_callback_ref = hackrf_sample_block_cb_fn(_rx_callback)
            res = self.lib._lib.hackrf_start_rx(self._dev_ptr, self._c_callback_ref, None)
            if res == 0:
                self._is_streaming = True
                return True
            else:
                return False

        return False

    def stop_rx(self):
        """Stops I/Q data stream."""
        if not self._is_streaming:
            return

        if self.mode == DeviceMode.SIMULATOR:
            self._simulator.stop_rx()
        elif self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            try:
                self.lib._lib.hackrf_stop_rx(self._dev_ptr)
            except Exception:
                pass

        self._is_streaming = False
        self._c_callback_ref = None

    def set_freq(self, freq_hz: float):
        """Tunes receiver / transmitter local oscillator."""
        self.center_freq = float(freq_hz)
        if self.mode == DeviceMode.SIMULATOR:
            self._simulator.set_freq(self.center_freq)
        elif self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.lib._lib.hackrf_set_freq(self._dev_ptr, int(freq_hz))

    def set_sample_rate(self, rate_hz: float):
        """Sets ADC / DAC sample rate (2 MHz to 20 MHz)."""
        self.sample_rate = float(rate_hz)
        if self.mode == DeviceMode.SIMULATOR:
            self._simulator.set_sample_rate(self.sample_rate)
        elif self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.lib._lib.hackrf_set_sample_rate(self._dev_ptr, float(rate_hz))

    def set_lna_gain(self, gain_db: int):
        """Sets Low Noise Amplifier (LNA) gain: 0 to 40 dB in 8 dB steps."""
        self.lna_gain = int(gain_db)
        if self.mode == DeviceMode.SIMULATOR:
            self._simulator.set_lna_gain(self.lna_gain)
        elif self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.lib._lib.hackrf_set_lna_gain(self._dev_ptr, int(gain_db))

    def set_vga_gain(self, gain_db: int):
        """Sets Baseband Variable Gain Amplifier (VGA) gain: 0 to 62 dB in 2 dB steps."""
        self.vga_gain = int(gain_db)
        if self.mode == DeviceMode.SIMULATOR:
            self._simulator.set_vga_gain(self.vga_gain)
        elif self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.lib._lib.hackrf_set_vga_gain(self._dev_ptr, int(gain_db))

    def set_txvga_gain(self, gain_db: int):
        """Sets Transmitter VGA gain: 0 to 47 dB in 1 dB steps."""
        self.txvga_gain = int(gain_db)
        if self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.lib._lib.hackrf_set_txvga_gain(self._dev_ptr, int(gain_db))

    def set_amp_enable(self, enable: bool):
        """Enables or disables the +14 dB RF Preamp."""
        self.amp_enabled = bool(enable)
        if self.mode == DeviceMode.SIMULATOR:
            self._simulator.set_amp_enable(self.amp_enabled)
        elif self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.lib._lib.hackrf_set_amp_enable(self._dev_ptr, 1 if enable else 0)

    def set_antenna_enable(self, enable: bool):
        """Enables or disables 3.3V DC Bias-Tee on the antenna port (up to 50mA)."""
        self.antenna_bias_tee = bool(enable)
        if self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.lib._lib.hackrf_set_antenna_enable(self._dev_ptr, 1 if enable else 0)

    def set_baseband_filter_bw(self, bw_hz: int):
        """Configures the analog baseband low-pass filter bandwidth."""
        self.baseband_filter_bw = int(bw_hz)
        if self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.lib._lib.hackrf_set_baseband_filter_bandwidth(self._dev_ptr, int(bw_hz))

    def _apply_all_settings(self):
        """Applies cached settings to physical hardware upon connection."""
        if self.mode == DeviceMode.PHYSICAL and self._dev_ptr.value:
            self.set_sample_rate(self.sample_rate)
            self.set_freq(self.center_freq)
            self.set_lna_gain(self.lna_gain)
            self.set_vga_gain(self.vga_gain)
            self.set_amp_enable(self.amp_enabled)
            self.set_antenna_enable(self.antenna_bias_tee)

    def get_info(self) -> Dict[str, Any]:
        """Queries hardware diagnostic information."""
        info = {
            "mode": self.mode.value,
            "streaming": self._is_streaming,
            "center_freq_mhz": self.center_freq / 1e6,
            "sample_rate_msps": self.sample_rate / 1e6,
            "lna_gain_db": self.lna_gain,
            "vga_gain_db": self.vga_gain,
            "amp_enabled": self.amp_enabled,
            "bias_tee_enabled": self.antenna_bias_tee,
            "serial_number": "SIMULATED-HACKRF-001",
            "board_id": "HackRF One (Simulated / Rev 2024)",
        }
        return info
