"""
Native HackRF C Library Wrapper using ctypes.
Supports Windows (hackrf.dll), Linux (libhackrf.so), and macOS (libhackrf.dylib).
Gracefully handles environments where the hardware library is not yet installed.
"""

import sys
import os
import ctypes
from ctypes import (
    c_int, c_uint8, c_uint16, c_uint32, c_uint64, c_double,
    c_void_p, c_char_p, POINTER, Structure, CFUNCTYPE, CDLL
)
from enum import IntEnum
from typing import Optional, Tuple, List, Callable


class TransceiverMode(IntEnum):
    OFF = 0
    RECEIVE = 1
    TRANSMIT = 2
    SS = 3
    CPLD_UPDATE = 4
    RX_SWEEP = 5


class HackRFError(Exception):
    """Exception raised for HackRF C API errors."""
    pass


ERROR_STRINGS = {
    0: "HACKRF_SUCCESS",
    1: "HACKRF_TRUE",
    -2: "Invalid parameter (HACKRF_ERROR_INVALID_PARAM)",
    -5: "USB device not found (HACKRF_ERROR_NOT_FOUND)",
    -6: "Device busy (HACKRF_ERROR_BUSY)",
    -11: "Memory allocation failed in libhackrf (HACKRF_ERROR_NO_MEM)",
    -1000: "libusb error (HACKRF_ERROR_LIBUSB)",
    -1001: "Error setting up transfer thread (HACKRF_ERROR_THREAD)",
    -1002: "Streaming thread could not start (HACKRF_ERROR_STREAMING_THREAD_ERR)",
    -1003: "Streaming thread stopped due to an error (HACKRF_ERROR_STREAMING_STOPPED)",
    -1004: "Streaming thread exited normally (HACKRF_ERROR_STREAMING_EXIT_CALLED)",
    -1005: "Installed firmware does not support this function (HACKRF_ERROR_USB_API_VERSION)",
    -2000: "Cannot exit library as devices are still in use (HACKRF_ERROR_NOT_LAST_DEVICE)",
    -9999: "Unspecified error (HACKRF_ERROR_OTHER)",
}


class HackRFTransfer(Structure):
    _fields_ = [
        ("device", c_void_p),
        ("buffer", POINTER(ctypes.c_byte)),
        ("buffer_length", c_int),
        ("valid_length", c_int),
        ("rx_ctx", c_void_p),
        ("tx_ctx", c_void_p),
    ]


class ReadPartIdSerialNo(Structure):
    _fields_ = [
        ("part_id", c_uint32 * 2),
        ("serial_no", c_uint32 * 4),
    ]


class HackRFDeviceList(Structure):
    _fields_ = [
        ("serial_numbers", POINTER(c_char_p)),
        ("usb_board_ids", c_void_p),
        ("usb_device_index", POINTER(c_int)),
        ("devicecount", c_int),
        ("usb_devices", POINTER(c_void_p)),
        ("usb_devicecount", c_int),
    ]


# Callback function prototype for RX/TX/Sweep: int(hackrf_transfer* transfer)
hackrf_sample_block_cb_fn = CFUNCTYPE(c_int, POINTER(HackRFTransfer))


class LibHackRF:
    """Wrapper that manages loading and invoking libhackrf functions."""

    _instance: Optional["LibHackRF"] = None

    def __init__(self, custom_path: Optional[str] = None):
        self._lib = None
        self._initialized = False
        self._load_error: Optional[str] = None
        self._dll_path: Optional[str] = None
        self._load_library(custom_path)

    @classmethod
    def get_instance(cls, custom_path: Optional[str] = None) -> "LibHackRF":
        if cls._instance is None:
            cls._instance = LibHackRF(custom_path)
        return cls._instance

    @property
    def is_available(self) -> bool:
        return self._lib is not None and self._initialized

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    @property
    def dll_path(self) -> Optional[str]:
        return self._dll_path

    def _find_library_paths(self, custom_path: Optional[str] = None) -> List[str]:
        candidates = []
        if custom_path:
            candidates.append(custom_path)

        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bin_dir = os.path.join(app_dir, "bin")

        if sys.platform.startswith("win"):
            candidates.extend([
                os.path.join(bin_dir, "hackrf.dll"),
                os.path.join(bin_dir, "libhackrf.dll"),
                "hackrf.dll",
                "libhackrf.dll",
                r"C:\Program Files\HackRF\bin\hackrf.dll",
                r"C:\Program Files (x86)\HackRF\bin\hackrf.dll",
                os.path.join(sys.prefix, "Library", "bin", "hackrf.dll"),
                os.path.join(sys.prefix, "Library", "bin", "libhackrf.dll"),
                os.path.join(os.environ.get("USERPROFILE", ""), "miniforge3", "Library", "bin", "hackrf.dll"),
            ])
        elif sys.platform.startswith("darwin"):
            candidates.extend([
                os.path.join(bin_dir, "libhackrf.dylib"),
                "libhackrf.dylib",
                "/opt/homebrew/lib/libhackrf.dylib",
                "/usr/local/lib/libhackrf.dylib",
                os.path.join(sys.prefix, "lib", "libhackrf.dylib"),
            ])
        else:  # Linux / Unix
            candidates.extend([
                os.path.join(bin_dir, "libhackrf.so.0"),
                os.path.join(bin_dir, "libhackrf.so"),
                "libhackrf.so.0",
                "libhackrf.so",
                "/usr/lib/libhackrf.so.0",
                "/usr/lib/x86_64-linux-gnu/libhackrf.so.0",
                "/usr/local/lib/libhackrf.so.0",
                os.path.join(sys.prefix, "lib", "libhackrf.so.0"),
            ])
        return candidates

    def _load_library(self, custom_path: Optional[str] = None):
        candidates = self._find_library_paths(custom_path)
        last_error = None

        for path in candidates:
            try:
                if os.path.isfile(path) or path in ("hackrf.dll", "libhackrf.dll", "libhackrf.so.0", "libhackrf.so", "libhackrf.dylib"):
                    # On Windows, ensure directory is in DLL search path
                    if sys.platform.startswith("win") and os.path.isfile(path):
                        dir_path = os.path.dirname(os.path.abspath(path))
                        if hasattr(os, "add_dll_directory"):
                            try:
                                os.add_dll_directory(dir_path)
                            except Exception:
                                pass
                    lib = CDLL(path)
                    self._bind_functions(lib)
                    res = lib.hackrf_init()
                    if res == 0:
                        self._lib = lib
                        self._initialized = True
                        self._dll_path = path
                        return
                    else:
                        last_error = f"hackrf_init failed with code {res}"
            except Exception as e:
                last_error = str(e)

        self._load_error = last_error or "HackRF C library not found on system paths."

    def _bind_functions(self, lib: CDLL):
        lib.hackrf_init.restype = c_int
        lib.hackrf_init.argtypes = []

        lib.hackrf_exit.restype = c_int
        lib.hackrf_exit.argtypes = []

        lib.hackrf_open.restype = c_int
        lib.hackrf_open.argtypes = [POINTER(c_void_p)]

        lib.hackrf_open_by_serial.restype = c_int
        lib.hackrf_open_by_serial.argtypes = [c_char_p, POINTER(c_void_p)]

        lib.hackrf_close.restype = c_int
        lib.hackrf_close.argtypes = [c_void_p]

        lib.hackrf_set_sample_rate.restype = c_int
        lib.hackrf_set_sample_rate.argtypes = [c_void_p, c_double]

        lib.hackrf_set_freq.restype = c_int
        lib.hackrf_set_freq.argtypes = [c_void_p, c_uint64]

        lib.hackrf_set_amp_enable.restype = c_int
        lib.hackrf_set_amp_enable.argtypes = [c_void_p, c_uint8]

        lib.hackrf_set_lna_gain.restype = c_int
        lib.hackrf_set_lna_gain.argtypes = [c_void_p, c_uint32]

        lib.hackrf_set_vga_gain.restype = c_int
        lib.hackrf_set_vga_gain.argtypes = [c_void_p, c_uint32]

        lib.hackrf_set_txvga_gain.restype = c_int
        lib.hackrf_set_txvga_gain.argtypes = [c_void_p, c_uint32]

        lib.hackrf_set_antenna_enable.restype = c_int
        lib.hackrf_set_antenna_enable.argtypes = [c_void_p, c_uint8]

        lib.hackrf_set_baseband_filter_bandwidth.restype = c_int
        lib.hackrf_set_baseband_filter_bandwidth.argtypes = [c_void_p, c_uint32]

        lib.hackrf_start_rx.restype = c_int
        lib.hackrf_start_rx.argtypes = [c_void_p, hackrf_sample_block_cb_fn, c_void_p]

        lib.hackrf_stop_rx.restype = c_int
        lib.hackrf_stop_rx.argtypes = [c_void_p]

        lib.hackrf_start_tx.restype = c_int
        lib.hackrf_start_tx.argtypes = [c_void_p, hackrf_sample_block_cb_fn, c_void_p]

        lib.hackrf_stop_tx.restype = c_int
        lib.hackrf_stop_tx.argtypes = [c_void_p]

        lib.hackrf_board_partid_serialno_read.restype = c_int
        lib.hackrf_board_partid_serialno_read.argtypes = [c_void_p, POINTER(ReadPartIdSerialNo)]

        # Sweep functions (if available in lib)
        if hasattr(lib, "hackrf_init_sweep"):
            lib.hackrf_init_sweep.restype = c_int
            lib.hackrf_init_sweep.argtypes = [
                c_void_p, POINTER(c_uint16), c_uint32, c_uint32, c_uint32, c_uint32, c_int
            ]
        if hasattr(lib, "hackrf_start_rx_sweep"):
            lib.hackrf_start_rx_sweep.restype = c_int
            lib.hackrf_start_rx_sweep.argtypes = [c_void_p, hackrf_sample_block_cb_fn, c_void_p]

    def check_result(self, res: int, func_name: str = "HackRF operation"):
        if res != 0:
            err_msg = ERROR_STRINGS.get(res, f"Unknown error code {res}")
            raise HackRFError(f"{func_name} failed: {err_msg} (code {res})")

    def exit(self):
        if self._lib and self._initialized:
            try:
                self._lib.hackrf_exit()
            except Exception:
                pass
            self._initialized = False
