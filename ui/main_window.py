"""
Main Application Window for HackRF Studio.
Coordinates the hardware abstraction layer, DSP pipeline, audio engine,
and UI visualization tabs.
"""

import os
import sys
import time
import queue
import threading
import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui

from hackrf.device import HackRFDevice, DeviceMode
from dsp.fft_processor import FFTProcessor
from dsp.demodulator import SDRDemodulator, DemodMode
from audio.output import AudioOutput
from recording.iq_file import IQRecorder, IQPlayer, FileFormat

from .spectrum_widget import SpectrumWidget
from .controls_widget import ControlsWidget
from .demod_widget import DemodWidget
from .constellation_widget import ConstellationWidget
from .sweep_widget import SweepWidget
from .pulse_widget import PulseWidget
from .tx_widget import TXWidget
from .dialogs import DeviceInfoDialog, RecordDialog, AboutDialog


class MainWindow(QtWidgets.QMainWindow):
    """Primary application window and orchestrator for HackRF Studio."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("HackRF Studio - Software Defined Radio Suite")
        self.resize(1280, 800)

        # 1. Initialize Subsystems
        self.device = HackRFDevice(mode=DeviceMode.SIMULATOR)
        self.fft_proc = FFTProcessor(fft_size=2048)
        self.demodulator = SDRDemodulator(sample_rate=self.device.sample_rate)
        self.audio_out = AudioOutput()
        self.recorder = IQRecorder()
        self.player = IQPlayer()

        # DSP Queue between RX thread and UI/Audio threads
        self._rx_queue = queue.Queue(maxsize=15)
        self._iq_worker_running = False
        self._iq_worker_thread = None

        # FPS metrics
        self._frame_count = 0
        self._last_fps_time = time.time()
        self._current_fps = 0.0

        # UI Timer for refreshing graphics at up to 60 FPS
        self._ui_timer = QtCore.QTimer(self)
        self._ui_timer.timeout.connect(self._on_ui_refresh)

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        # Menu Bar
        self._setup_menu_bar()

        # Central Layout: Sidebar Controls + Tabbed Workspaces
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QHBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Left Column: Hardware & Tuning Controls (Dock-like)
        self.controls_widget = ControlsWidget()
        self.controls_widget.setFixedWidth(280)
        main_layout.addWidget(self.controls_widget)

        # Right Area: Tabbed Workspaces
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab {
                font-weight: bold;
                padding: 8px 16px;
                font-size: 12px;
            }
        """)

        # Tab 1: Spectrum & Audio Demodulation
        tab_spectrum = QtWidgets.QWidget()
        layout_tab_spec = QtWidgets.QHBoxLayout(tab_spectrum)
        layout_tab_spec.setContentsMargins(0, 0, 0, 0)

        self.spectrum_widget = SpectrumWidget()
        layout_tab_spec.addWidget(self.spectrum_widget, stretch=1)

        self.demod_widget = DemodWidget()
        self.demod_widget.setFixedWidth(240)
        layout_tab_spec.addWidget(self.demod_widget)

        self.tabs.addTab(tab_spectrum, "Spectrum & Waterfall")

        # Tab 2: Wideband Panoramic Sweep (1 MHz - 6 GHz)
        self.sweep_widget = SweepWidget(self.device)
        self.tabs.addTab(self.sweep_widget, "Wideband Sweep (1-6 GHz)")

        # Tab 3: Sub-GHz Pulse Analyzer (433 / 315 / 868 MHz)
        self.pulse_widget = PulseWidget()
        self.tabs.addTab(self.pulse_widget, "Sub-GHz Protocol Inspector")

        # Tab 4: TX Signal Generator Workbench
        self.tx_widget = TXWidget()
        self.tabs.addTab(self.tx_widget, "TX Workbench")

        # Tab 5: Constellation & Oscilloscope
        self.constellation_widget = ConstellationWidget()
        self.tabs.addTab(self.constellation_widget, "Constellation & Scope")

        main_layout.addWidget(self.tabs, stretch=1)

        # Status Bar
        self.status_bar = self.statusBar()
        self.lbl_status_dev = QtWidgets.QLabel("Source: SIMULATOR")
        self.lbl_status_freq = QtWidgets.QLabel("Freq: 100.000 MHz")
        self.lbl_status_rate = QtWidgets.QLabel("Rate: 2.0 MSPS")
        self.lbl_status_rec = QtWidgets.QLabel("")
        self.lbl_status_fps = QtWidgets.QLabel("FPS: 0")

        self.status_bar.addPermanentWidget(self.lbl_status_rec)
        self.status_bar.addPermanentWidget(self.lbl_status_dev)
        self.status_bar.addPermanentWidget(self.lbl_status_freq)
        self.status_bar.addPermanentWidget(self.lbl_status_rate)
        self.status_bar.addPermanentWidget(self.lbl_status_fps)

    def _setup_menu_bar(self):
        menubar = self.menuBar()

        # File Menu
        menu_file = menubar.addMenu("&File")

        action_open_iq = QtWidgets.QAction("Open I/Q File for Playback...", self)
        action_open_iq.triggered.connect(self._open_iq_file)
        menu_file.addAction(action_open_iq)

        action_record = QtWidgets.QAction("Start I/Q Recording...", self)
        action_record.triggered.connect(self._prompt_record)
        menu_file.addAction(action_record)

        action_stop_rec = QtWidgets.QAction("Stop Recording", self)
        action_stop_rec.triggered.connect(self._stop_record)
        menu_file.addAction(action_stop_rec)

        menu_file.addSeparator()
        action_exit = QtWidgets.QAction("Exit", self)
        action_exit.triggered.connect(self.close)
        menu_file.addAction(action_exit)

        # Hardware Menu
        menu_hw = menubar.addMenu("&Hardware")

        action_info = QtWidgets.QAction("HackRF Device Diagnostics...", self)
        action_info.triggered.connect(self._show_device_info)
        menu_hw.addAction(action_info)

        # Help Menu
        menu_help = menubar.addMenu("&Help")

        action_about = QtWidgets.QAction("About HackRF Studio", self)
        action_about.triggered.connect(self._show_about)
        menu_help.addAction(action_about)

    def _connect_signals(self):
        # Controls Widget -> Hardware/DSP
        self.controls_widget.start_stop_clicked.connect(self._on_start_stop)
        self.controls_widget.frequency_changed.connect(self._on_frequency_changed)
        self.controls_widget.sample_rate_changed.connect(self._on_sample_rate_changed)
        self.controls_widget.lna_gain_changed.connect(self.device.set_lna_gain)
        self.controls_widget.vga_gain_changed.connect(self.device.set_vga_gain)
        self.controls_widget.amp_toggled.connect(self.device.set_amp_enable)
        self.controls_widget.bias_tee_toggled.connect(self.device.set_antenna_enable)
        self.controls_widget.baseband_filter_changed.connect(self.device.set_baseband_filter_bw)
        self.controls_widget.device_mode_changed.connect(self._on_device_mode_changed)

        # Spectrum Widget Tuning Cursor
        self.spectrum_widget.channel_tuned.connect(self._on_channel_tuned)

        # Demod Widget Controls
        self.demod_widget.mode_changed.connect(self.demodulator.set_mode)
        self.demod_widget.bandwidth_changed.connect(self.spectrum_widget.set_demod_bandwidth)
        self.demod_widget.volume_changed.connect(self.audio_out.set_volume)
        self.demod_widget.mute_toggled.connect(self.audio_out.set_mute)
        self.demod_widget.squelch_changed.connect(self.demodulator.set_squelch)

        # Sweep Widget 1-click tune
        self.sweep_widget.tune_requested.connect(self._tune_from_sweep)

        # Pulse Inspector -> TX workbench
        self.pulse_widget.load_to_tx_requested.connect(self._load_hex_to_tx)

    def _on_start_stop(self, start: bool):
        if start:
            self.device.open()
            self._start_dsp_worker()
            self.audio_out.start()
            self.device.start_rx(self._on_raw_iq_chunk)
            self._ui_timer.start(25)  # 40 FPS refresh rate
        else:
            self._ui_timer.stop()
            self.device.stop_rx()
            self.audio_out.stop()
            self._stop_dsp_worker()
            if self.recorder.is_recording:
                self._stop_record()

    def _on_frequency_changed(self, freq_hz: float):
        self.device.set_freq(freq_hz)
        self.spectrum_widget.set_rf_parameters(freq_hz, self.device.sample_rate)
        self.lbl_status_freq.setText(f"Freq: {freq_hz / 1e6:.4f} MHz")

    def _on_sample_rate_changed(self, rate_hz: float):
        self.device.set_sample_rate(rate_hz)
        self.demodulator.set_sample_rate(rate_hz)
        self.pulse_widget.decoder.set_sample_rate(rate_hz)
        self.spectrum_widget.set_rf_parameters(self.device.center_freq, rate_hz)
        self.lbl_status_rate.setText(f"Rate: {rate_hz / 1e6:.1f} MSPS")

    def _on_device_mode_changed(self, mode_name: str):
        was_running = self.controls_widget.is_running
        if was_running:
            self._on_start_stop(False)

        if mode_name == "Hardware":
            self.device.mode = DeviceMode.PHYSICAL
            self.lbl_status_dev.setText("Source: HARDWARE USB")
        elif mode_name == "Simulator":
            self.device.mode = DeviceMode.SIMULATOR
            self.lbl_status_dev.setText("Source: SIMULATOR")
        elif mode_name == "File":
            self.device.mode = DeviceMode.FILE_PLAYBACK
            self.lbl_status_dev.setText("Source: FILE PLAYBACK")

        if was_running:
            self._on_start_stop(True)

    def _on_channel_tuned(self, offset_hz: float):
        self.demodulator.set_channel_offset(offset_hz)

    def _tune_from_sweep(self, freq_hz: float):
        self.controls_widget.set_frequency_mhz(freq_hz / 1e6)
        self.tabs.setCurrentIndex(0)  # Jump to Spectrum tab

    def _load_hex_to_tx(self, hex_str: str):
        self.tx_widget.set_payload_hex(hex_str)
        self.tabs.setCurrentIndex(3)  # Jump to TX tab

    def _on_raw_iq_chunk(self, iq_chunk: np.ndarray):
        """Called by background hardware / simulator thread."""
        try:
            self._rx_queue.put_nowait(iq_chunk)
        except queue.Full:
            pass  # Drop frame under high load to keep pipeline smooth

    def _start_dsp_worker(self):
        self._iq_worker_running = True
        self._iq_worker_thread = threading.Thread(target=self._dsp_worker_loop, daemon=True)
        self._iq_worker_thread.start()

    def _stop_dsp_worker(self):
        self._iq_worker_running = False
        if self._iq_worker_thread and self._iq_worker_thread.is_alive():
            self._iq_worker_thread.join(timeout=1.0)
        self._iq_worker_thread = None

    def _dsp_worker_loop(self):
        """Dedicated high-priority DSP and Audio Thread."""
        while self._iq_worker_running:
            try:
                iq_chunk = self._rx_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # 1. Recording to disk if active
            if self.recorder.is_recording:
                self.recorder.write_chunk(iq_chunk)

            # 2. Audio Demodulation
            audio_pcm, rssi_db = self.demodulator.demodulate(iq_chunk)
            if len(audio_pcm) > 0:
                self.audio_out.write(audio_pcm)

            # 3. Cache latest chunk for UI thread rendering
            self._latest_iq = iq_chunk
            self._latest_rssi = (rssi_db, self.demodulator.squelch_open)

    def _on_ui_refresh(self):
        """Timer callback (40 FPS) updating GUI components."""
        if not hasattr(self, "_latest_iq") or self._latest_iq is None:
            return

        iq = self._latest_iq

        # 1. Update FFT Spectrum & Waterfall
        freqs_mhz, power_db, peak_db = self.fft_proc.process(
            iq, self.device.center_freq, self.device.sample_rate
        )
        self.spectrum_widget.update_spectrum(freqs_mhz, power_db, peak_db)

        # 2. Update RSSI and Squelch state
        if hasattr(self, "_latest_rssi"):
            rssi_db, sql_open = self._latest_rssi
            self.demod_widget.update_rssi(rssi_db, sql_open)

        # 3. Update Constellation & Time-Domain Oscilloscope (if active tab)
        if self.tabs.currentIndex() == 4:
            self.constellation_widget.update_samples(iq)

        # 4. Update Sub-GHz Pulse Analyzer (if active tab)
        if self.tabs.currentIndex() == 2:
            self.pulse_widget.process_iq(iq)

        # 5. Update Recording Status
        if self.recorder.is_recording:
            stats = self.recorder.get_stats()
            self.lbl_status_rec.setText(f"🔴 REC [{stats['duration_sec']:.1f}s | {stats['mb_written']:.1f} MB]")
            self.lbl_status_rec.setStyleSheet("color: #ff3333; font-weight: bold;")
        else:
            self.lbl_status_rec.setText("")

        # 6. FPS Counter
        self._frame_count += 1
        now = time.time()
        if (now - self._last_fps_time) >= 1.0:
            self._current_fps = self._frame_count / (now - self._last_fps_time)
            self._frame_count = 0
            self._last_fps_time = now
            self.lbl_status_fps.setText(f"FPS: {self._current_fps:.0f}")

    def _prompt_record(self):
        dlg = RecordDialog(self.device.center_freq / 1e6, self.device.sample_rate / 1e6, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted and dlg.file_path:
            self.recorder.start_recording(
                dlg.file_path, dlg.selected_format,
                self.device.center_freq, self.device.sample_rate
            )
            QtWidgets.QMessageBox.information(
                self, "Recording Started",
                f"Recording raw I/Q samples to:\n{dlg.file_path}"
            )

    def _stop_record(self):
        if self.recorder.is_recording:
            info = self.recorder.stop_recording()
            QtWidgets.QMessageBox.information(
                self, "Recording Saved",
                f"Capture complete!\n"
                f"File: {info.get('file_path')}\n"
                f"Size: {info.get('mb_written', 0):.2f} MB\n"
                f"Duration: {info.get('duration_sec', 0):.1f} seconds"
            )

    def _open_iq_file(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Recorded I/Q File", "",
            "I/Q Files (*.c8 *.bin *.cf32 *.wav);;All Files (*)"
        )
        if path:
            if self.player.load_file(path):
                self.controls_widget.set_frequency_mhz(self.player.center_freq / 1e6)
                self.controls_widget.combo_source.setCurrentIndex(2)  # File mode
                self.player.start_playback(self._on_raw_iq_chunk)
                QtWidgets.QMessageBox.information(self, "I/Q File Loaded", f"Playing back: {path}")

    def _show_device_info(self):
        info = self.device.get_info()
        dlg = DeviceInfoDialog(info, self)
        dlg.exec_()

    def _show_about(self):
        dlg = AboutDialog(self)
        dlg.exec_()

    def closeEvent(self, event):
        self._on_start_stop(False)
        self.device.close()
        event.accept()
