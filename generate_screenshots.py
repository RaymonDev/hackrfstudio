"""Script to capture real high-resolution screenshots of HackRF Studio."""

import os
import sys
import time
import numpy as np

from PyQt5 import QtCore, QtWidgets, QtGui

# Enable high DPI scaling
QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

from ui.main_window import MainWindow
from dsp.protocol_decoder import PacketRecord


def capture_all():
    app = QtWidgets.QApplication(sys.argv)

    # Load stylesheet
    qss_path = os.path.join(os.path.dirname(__file__), "assets", "style.qss")
    if os.path.isfile(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    out_dir = os.path.join(os.path.dirname(__file__), "assets", "screenshots")
    os.makedirs(out_dir, exist_ok=True)

    window = MainWindow()
    window.resize(1280, 800)
    window.show()

    # 1. Start SDR in Simulator mode at 100 MHz (FM Broadcast band)
    window.controls_widget.set_frequency_mhz(100.0)
    window._on_start_stop(True)

    # Process events and simulate for 2 seconds to fill waterfall and spectrum
    print("Capturing Tab 1: Spectrum & Waterfall...")
    start_t = time.time()
    while time.time() - start_t < 2.0:
        app.processEvents()
        time.sleep(0.03)

    window.tabs.setCurrentIndex(0)
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()

    pix = window.grab()
    pix.save(os.path.join(out_dir, "01_spectrum_waterfall.png"), "PNG")

    # 2. Wideband Sweep Panorama Tab
    print("Capturing Tab 2: Wideband Sweep...")
    window.tabs.setCurrentIndex(1)
    app.processEvents()
    window.sweep_widget._set_scan_range(88e6, 108e6)
    window.sweep_widget.btn_sweep.setChecked(True)

    start_t = time.time()
    while time.time() - start_t < 1.5:
        app.processEvents()
        time.sleep(0.03)

    pix = window.grab()
    pix.save(os.path.join(out_dir, "02_wideband_sweep.png"), "PNG")
    window.sweep_widget.btn_sweep.setChecked(False)

    # 3. Sub-GHz Pulse Inspector Tab
    print("Capturing Tab 3: Sub-GHz Protocol Inspector...")
    window.tabs.setCurrentIndex(2)
    # Inject a realistic weather sensor / remote packet
    timings = [450, 450, 900, 450, 450, 450, 900, 450, 900, 450, 450, 450, 900, 450, 450, 450,
               900, 450, 900, 450, 450, 450, 450, 450, 900, 450, 450, 450, 900, 450, 900, 450]
    pkt = PacketRecord(
        timestamp=time.time(),
        duration_ms=48.2,
        pulse_count=32,
        binary_str="10101100110100101011000101101001",
        hex_str="0xACD2B169",
        timings=timings
    )
    window.pulse_widget.decoder.history.insert(0, pkt)
    window.pulse_widget._add_packets_to_table([pkt])
    window.pulse_widget._display_packet(pkt)
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()

    pix = window.grab()
    pix.save(os.path.join(out_dir, "03_subghz_pulse_inspector.png"), "PNG")

    # 4. TX Workbench Tab
    print("Capturing Tab 4: TX Workbench...")
    window.tabs.setCurrentIndex(3)
    window.tx_widget.combo_type.setCurrentIndex(1)  # Two-Tone IMD Test
    window.tx_widget.chk_arm.setChecked(True)
    window.tx_widget._update_preview()
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()

    pix = window.grab()
    pix.save(os.path.join(out_dir, "04_tx_workbench.png"), "PNG")

    # 5. Constellation & Scope Tab
    print("Capturing Tab 5: Constellation & Scope...")
    window.tabs.setCurrentIndex(4)
    start_t = time.time()
    while time.time() - start_t < 0.5:
        app.processEvents()
        time.sleep(0.03)

    pix = window.grab()
    pix.save(os.path.join(out_dir, "05_constellation_scope.png"), "PNG")

    # Stop SDR
    window._on_start_stop(False)
    window.close()
    print("All screenshots captured successfully in assets/screenshots/")


if __name__ == "__main__":
    capture_all()
