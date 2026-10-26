"""
Signal Generator & Transmitter Workbench for HackRF One.
Provides controlled, safe signal generation with safety guards and waveform preview.
"""

import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
from dsp.signal_gen import SignalGenerator, SignalType


class TXWidget(QtWidgets.QWidget):
    """Signal Generator and Transmission Workbench."""

    tx_start_requested = QtCore.pyqtSignal(dict)  # TX parameters dict
    tx_stop_requested = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sig_gen = SignalGenerator()
        self.is_transmitting = False
        self._tx_timer = QtCore.QTimer(self)
        self._tx_timer.timeout.connect(self._on_tx_timeout)
        self._countdown_sec = 0

        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Left Column: Configuration Controls
        left_container = QtWidgets.QWidget()
        left_container.setFixedWidth(360)
        layout_left = QtWidgets.QVBoxLayout(left_container)
        layout_left.setContentsMargins(0, 0, 0, 0)

        # 1. Transmitter Armed Safeguard Group
        group_safety = QtWidgets.QGroupBox("SAFETY INTERLOCK")
        group_safety.setStyleSheet("QGroupBox { font-weight: bold; color: #ff5555; }")
        layout_safety = QtWidgets.QVBoxLayout(group_safety)

        self.chk_arm = QtWidgets.QCheckBox("ARM TRANSMITTER (Enable RF Output)")
        self.chk_arm.setStyleSheet("font-weight: bold; font-size: 13px; color: #ff8888;")
        self.chk_arm.toggled.connect(self._on_arm_toggled)
        layout_safety.addWidget(self.chk_arm)

        layout_dur = QtWidgets.QHBoxLayout()
        layout_dur.addWidget(QtWidgets.QLabel("Auto-Stop Timer:"))
        self.combo_dur = QtWidgets.QComboBox()
        self.combo_dur.addItems(["3 Seconds", "5 Seconds", "10 Seconds", "30 Seconds", "Manual Stop"])
        layout_dur.addWidget(self.combo_dur)
        layout_safety.addLayout(layout_dur)

        # TX Button
        self.btn_tx = QtWidgets.QPushButton("START TRANSMISSION")
        self.btn_tx.setFixedHeight(45)
        self.btn_tx.setEnabled(False)
        self.btn_tx.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border-radius: 4px;
            }
            QPushButton:enabled {
                background-color: #c9302c;
            }
            QPushButton:hover:enabled {
                background-color: #e03630;
            }
        """)
        self.btn_tx.clicked.connect(self._toggle_transmission)
        layout_safety.addWidget(self.btn_tx)

        self.lbl_tx_status = QtWidgets.QLabel("Status: IDLE / SAFE")
        self.lbl_tx_status.setStyleSheet("color: #888888; font-weight: bold; font-size: 12px;")
        layout_safety.addWidget(self.lbl_tx_status)

        layout_left.addWidget(group_safety)

        # 2. Waveform & Modulation Group
        group_wave = QtWidgets.QGroupBox("Waveform Synthesizer")
        layout_wave = QtWidgets.QVBoxLayout(group_wave)

        layout_wave.addWidget(QtWidgets.QLabel("Signal Type:"))
        self.combo_type = QtWidgets.QComboBox()
        for st in SignalType:
            self.combo_type.addItem(st.value, st)
        self.combo_type.currentIndexChanged.connect(self._on_type_changed)
        layout_wave.addWidget(self.combo_type)

        # Transmit Frequency
        layout_freq = QtWidgets.QHBoxLayout()
        layout_freq.addWidget(QtWidgets.QLabel("TX Frequency:"))
        self.spin_freq = QtWidgets.QDoubleSpinBox()
        self.spin_freq.setRange(1.0, 6000.0)
        self.spin_freq.setValue(433.920)
        self.spin_freq.setDecimals(4)
        self.spin_freq.setSuffix(" MHz")
        layout_freq.addWidget(self.spin_freq)
        layout_wave.addLayout(layout_freq)

        # TX VGA Gain (0 to 47 dB)
        layout_gain = QtWidgets.QHBoxLayout()
        layout_gain.addWidget(QtWidgets.QLabel("TX VGA Power:"))
        self.lbl_gain = QtWidgets.QLabel("20 dB")
        self.lbl_gain.setStyleSheet("font-weight: bold;")
        layout_gain.addWidget(self.lbl_gain)
        layout_wave.addLayout(layout_gain)

        self.slider_gain = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_gain.setRange(0, 47)
        self.slider_gain.setValue(20)
        self.slider_gain.valueChanged.connect(lambda v: self.lbl_gain.setText(f"{v} dB"))
        layout_wave.addWidget(self.slider_gain)

        # Modulation Tone
        layout_tone = QtWidgets.QHBoxLayout()
        layout_tone.addWidget(QtWidgets.QLabel("Modulation Tone:"))
        self.spin_tone = QtWidgets.QSpinBox()
        self.spin_tone.setRange(10, 50000)
        self.spin_tone.setValue(1000)
        self.spin_tone.setSuffix(" Hz")
        self.spin_tone.valueChanged.connect(self._update_preview)
        layout_tone.addWidget(self.spin_tone)
        layout_wave.addLayout(layout_tone)

        # ASK Hex Payload
        layout_wave.addWidget(QtWidgets.QLabel("ASK/OOK Hex Pattern:"))
        self.edit_hex = QtWidgets.QLineEdit("0x1A2B3C4D")
        self.edit_hex.textChanged.connect(self._update_preview)
        layout_wave.addWidget(self.edit_hex)

        layout_left.addWidget(group_wave)
        layout_left.addStretch()
        layout.addWidget(left_container)

        # Right Column: Live Synthesizer Waveform Preview
        self.plot_preview = pg.PlotWidget(title="<b>SYNTHESIZED TX WAVEFORM PREVIEW</b>")
        self.plot_preview.showGrid(x=True, y=True, alpha=0.3)
        self.plot_preview.setYRange(-1.2, 1.2, padding=0.05)
        self.plot_preview.setLabel("bottom", "Time (Sample Points)")
        self.plot_preview.setLabel("left", "Amplitude")
        self.plot_preview.addLegend(offset=(10, 10))

        pen_i = pg.mkPen(color=(0, 255, 200), width=1.5)
        pen_q = pg.mkPen(color=(255, 80, 80), width=1.5)
        self.curve_i = self.plot_preview.plot(pen=pen_i, name="TX I (Real)")
        self.curve_q = self.plot_preview.plot(pen=pen_q, name="TX Q (Imag)")

        layout.addWidget(self.plot_preview, stretch=1)

        self._update_preview()

    def set_payload_hex(self, hex_str: str):
        self.combo_type.setCurrentIndex(4)  # ASK
        self.edit_hex.setText(hex_str)
        self._update_preview()

    def _on_arm_toggled(self, armed: bool):
        self.btn_tx.setEnabled(armed)
        if not armed and self.is_transmitting:
            self._stop_transmission()

    def _on_type_changed(self, index: int):
        st = self.combo_type.itemData(index)
        if st:
            self.sig_gen.signal_type = st
            self._update_preview()

    def _update_preview(self):
        self.sig_gen.tone_freq_hz = float(self.spin_tone.value())
        preview_samples = self.sig_gen.generate_chunk(512)
        x = np.arange(len(preview_samples))
        self.curve_i.setData(x, np.real(preview_samples))
        self.curve_q.setData(x, np.imag(preview_samples))

    def _toggle_transmission(self):
        if not self.is_transmitting:
            self._start_transmission()
        else:
            self._stop_transmission()

    def _start_transmission(self):
        self.is_transmitting = True
        self.btn_tx.setText("ABORT TRANSMISSION")
        self.btn_tx.setStyleSheet("background-color: #ff0000; color: #ffffff; font-weight: bold; font-size: 15px;")

        # Durations: 3s, 5s, 10s, 30s, Manual
        dur_map = [3, 5, 10, 30, 0]
        dur = dur_map[self.combo_dur.currentIndex()]
        if dur > 0:
            self._countdown_sec = dur
            self.lbl_tx_status.setText(f"Status: TRANSMITTING (Auto-stop in {dur}s)...")
            self.lbl_tx_status.setStyleSheet("color: #ff3333; font-weight: bold; font-size: 13px;")
            self._tx_timer.start(1000)
        else:
            self.lbl_tx_status.setText("Status: TRANSMITTING (Continuous)...")
            self.lbl_tx_status.setStyleSheet("color: #ff3333; font-weight: bold; font-size: 13px;")

        params = {
            "freq_hz": self.spin_freq.value() * 1e6,
            "vga_gain": self.slider_gain.value(),
            "signal_type": self.sig_gen.signal_type,
            "tone_hz": float(self.spin_tone.value()),
            "hex_str": self.edit_hex.text(),
        }
        self.tx_start_requested.emit(params)

    def _stop_transmission(self):
        self.is_transmitting = False
        self._tx_timer.stop()
        self.btn_tx.setText("START TRANSMISSION")
        self.btn_tx.setStyleSheet("background-color: #c9302c; color: #ffffff; font-weight: bold; font-size: 14px;")
        self.lbl_tx_status.setText("Status: IDLE / SAFE")
        self.lbl_tx_status.setStyleSheet("color: #888888; font-weight: bold; font-size: 12px;")
        self.tx_stop_requested.emit()

    def _on_tx_timeout(self):
        self._countdown_sec -= 1
        if self._countdown_sec <= 0:
            self._stop_transmission()
        else:
            self.lbl_tx_status.setText(f"Status: TRANSMITTING (Auto-stop in {self._countdown_sec}s)...")
