#!/usr/bin/env python3
"""
HackRF Studio - Launch Entry Point
Advanced Software-Defined Radio Workstation for HackRF One.
"""

import sys
import os
import signal
import argparse

from PyQt5 import QtCore, QtWidgets, QtGui

# Enable high DPI scaling
QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

from ui.main_window import MainWindow


def parse_args():
    parser = argparse.ArgumentParser(description="HackRF Studio - SDR Workstation")
    parser.add_argument("--freq", type=float, default=100.0, help="Initial center frequency in MHz (default: 100.0)")
    parser.add_argument("--rate", type=float, default=2.0, help="Initial sample rate in MSPS (default: 2.0)")
    parser.add_argument("--hardware", action="store_true", help="Force physical USB hardware mode on startup")
    parser.add_argument("--headless-test", action="store_true", help="Run self-test without opening GUI window")
    return parser.parse_args()


def load_stylesheet(app: QtWidgets.QApplication):
    qss_path = os.path.join(os.path.dirname(__file__), "assets", "style.qss")
    if os.path.isfile(qss_path):
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
        except Exception as e:
            print(f"Note: Could not load custom style.qss: {e}")


def main():
    args = parse_args()

    # Handle Ctrl+C cleanly
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("HackRF Studio")
    app.setOrganizationName("HackRF-Studio")

    load_stylesheet(app)

    window = MainWindow()

    if args.freq:
        window.controls_widget.set_frequency_mhz(args.freq)

    if args.hardware:
        window.controls_widget.combo_source.setCurrentIndex(1)  # Hardware

    if args.headless_test:
        print("Self-test mode: verifying initialization...")
        info = window.device.get_info()
        print(f"Device initialized successfully: {info}")
        sys.exit(0)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
