"""
Hardware & Frequency Controls Widget for HackRF One.
Provides intuitive tuning, gain adjustment, presets, and radio state management.
"""

from PyQt5 import QtWidgets, QtCore, QtGui


class ControlsWidget(QtWidgets.QWidget):
    """Control panel for HackRF SDR radio parameters."""

    # Signals emitted on user adjustments
    frequency_changed = QtCore.pyqtSignal(float)      # Hz
    sample_rate_changed = QtCore.pyqtSignal(float)    # Hz
    lna_gain_changed = QtCore.pyqtSignal(int)         # dB
    vga_gain_changed = QtCore.pyqtSignal(int)         # dB
    amp_toggled = QtCore.pyqtSignal(bool)             # RF Preamp (+14 dB)
    bias_tee_toggled = QtCore.pyqtSignal(bool)        # 3.3V Bias Tee
    baseband_filter_changed = QtCore.pyqtSignal(int)  # Hz
    device_mode_changed = QtCore.pyqtSignal(str)      # "Hardware", "Simulator", "File"
    start_stop_clicked = QtCore.pyqtSignal(bool)      # True = Start, False = Stop

    PRESETS = [
        ("--- Select Frequency Preset ---", None),
        ("FM 88.50 MHz (Radio One)", 88.5e6),
        ("FM 91.30 MHz (Jazz Waves)", 91.3e6),
        ("FM 95.10 MHz (Classical Air)", 95.1e6),
        ("FM 98.50 MHz (NPR News)", 98.5e6),
        ("FM 101.10 MHz (Rock FM)", 101.1e6),
        ("FM 104.70 MHz (Hit Radio)", 104.7e6),
        ("FM 107.50 MHz (Pop Radio)", 107.5e6),
        ("Airband 121.500 MHz (Emergency Guard)", 121.5e6),
        ("Airband 124.850 MHz (Tower / Approach)", 124.85e6),
        ("Ham 2m 145.500 MHz (VHF FM Calling)", 145.5e6),
        ("Ham 2m 146.520 MHz (National Simplex)", 146.52e6),
        ("ISM 433.920 MHz (Car Remotes / Weather)", 433.92e6),
        ("Ham 70cm 433.000 MHz (UHF Calling)", 433.0e6),
        ("ISM 868.300 MHz (EU LoRa / Smart Meters)", 868.3e6),
        ("ISM 915.000 MHz (US ISM Band)", 915.0e6),
        ("WiFi 2.412 GHz (Channel 1)", 2412.0e6),
        ("WiFi 2.437 GHz (Channel 6)", 2437.0e6),
        ("WiFi 2.462 GHz (Channel 11)", 2462.0e6),
        ("BLE 2.402 GHz (Advertising 37)", 2402.0e6),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = False
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 1. Main Action Button: Start / Stop SDR Streaming
        self.btn_run = QtWidgets.QPushButton("START SDR")
        self.btn_run.setFixedHeight(44)
        self.btn_run.setCheckable(True)
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #0d8050;
                color: #ffffff;
                font-weight: bold;
                font-size: 15px;
                border-radius: 4px;
                border: 1px solid #14a065;
            }
            QPushButton:hover {
                background-color: #12965f;
            }
            QPushButton:checked {
                background-color: #c9302c;
                border: 1px solid #d9534f;
            }
        """)
        self.btn_run.toggled.connect(self._on_run_toggled)
        layout.addWidget(self.btn_run)

        # 2. Device Source Selection
        group_dev = QtWidgets.QGroupBox("RF Source / Backend")
        layout_dev = QtWidgets.QVBoxLayout(group_dev)

        self.combo_source = QtWidgets.QComboBox()
        self.combo_source.addItems([
            "Built-in RF Simulator (Recommended for testing)",
            "Hardware USB (HackRF One)",
            "Playback Recorded I/Q File"
        ])
        self.combo_source.currentIndexChanged.connect(self._on_source_changed)
        layout_dev.addWidget(self.combo_source)
        layout.addWidget(group_dev)

        # 3. Frequency Tuning Group
        group_freq = QtWidgets.QGroupBox("Tuning & Frequency")
        layout_freq = QtWidgets.QVBoxLayout(group_freq)

        # Digital MHz Spin Box
        self.spin_freq = QtWidgets.QDoubleSpinBox()
        self.spin_freq.setRange(1.0, 6000.0)  # HackRF frequency range: 1 MHz to 6 GHz
        self.spin_freq.setValue(100.000)
        self.spin_freq.setDecimals(4)
        self.spin_freq.setSuffix(" MHz")
        self.spin_freq.setStyleSheet("font-size: 18px; font-weight: bold; color: #00e6c3; padding: 4px;")
        self.spin_freq.valueChanged.connect(self._on_spin_freq_changed)
        layout_freq.addWidget(self.spin_freq)

        # Frequency Quick Step Buttons
        layout_steps = QtWidgets.QGridLayout()
        steps = [
            ("-10M", -10.0), ("-1M", -1.0), ("-100k", -0.1), ("-10k", -0.01),
            ("+10k", 0.01), ("+100k", 0.1), ("+1M", 1.0), ("+10M", 10.0)
        ]
        col = 0
        row = 0
        for label, delta in steps:
            btn = QtWidgets.QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked, d=delta: self.step_frequency(d))
            layout_steps.addWidget(btn, row, col)
            col += 1
            if col == 4:
                col = 0
                row += 1
        layout_freq.addLayout(layout_steps)

        # Quick Presets Menu
        self.combo_presets = QtWidgets.QComboBox()
        for name, _ in self.PRESETS:
            self.combo_presets.addItem(name)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        layout_freq.addWidget(self.combo_presets)

        layout.addWidget(group_freq)

        # 4. Gain Controls Group
        group_gain = QtWidgets.QGroupBox("HackRF Gain Architecture")
        layout_gain = QtWidgets.QVBoxLayout(group_gain)

        # LNA Gain (0 to 40 dB, 8 dB steps)
        layout_lna = QtWidgets.QHBoxLayout()
        layout_lna.addWidget(QtWidgets.QLabel("LNA Gain (RF):"))
        self.lbl_lna_val = QtWidgets.QLabel("32 dB")
        self.lbl_lna_val.setStyleSheet("font-weight: bold;")
        layout_lna.addWidget(self.lbl_lna_val)
        layout_gain.addLayout(layout_lna)

        self.slider_lna = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_lna.setRange(0, 40)
        self.slider_lna.setSingleStep(8)
        self.slider_lna.setPageStep(8)
        self.slider_lna.setValue(32)
        self.slider_lna.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider_lna.setTickInterval(8)
        self.slider_lna.valueChanged.connect(self._on_lna_slider_changed)
        layout_gain.addWidget(self.slider_lna)

        # VGA Gain (0 to 62 dB, 2 dB steps)
        layout_vga = QtWidgets.QHBoxLayout()
        layout_vga.addWidget(QtWidgets.QLabel("VGA Gain (Baseband):"))
        self.lbl_vga_val = QtWidgets.QLabel("30 dB")
        self.lbl_vga_val.setStyleSheet("font-weight: bold;")
        layout_vga.addWidget(self.lbl_vga_val)
        layout_gain.addLayout(layout_vga)

        self.slider_vga = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_vga.setRange(0, 62)
        self.slider_vga.setSingleStep(2)
        self.slider_vga.setPageStep(4)
        self.slider_vga.setValue(30)
        self.slider_vga.valueChanged.connect(self._on_vga_slider_changed)
        layout_gain.addWidget(self.slider_vga)

        # Hardware toggles: Preamp (+14 dB) & Antenna Bias-Tee (3.3V)
        self.chk_amp = QtWidgets.QCheckBox("Enable RF Preamp (+14 dB)")
        self.chk_amp.setToolTip("Enables HackRF front-end MMIC amplifier (+14 dB gain)")
        self.chk_amp.toggled.connect(self.amp_toggled.emit)
        layout_gain.addWidget(self.chk_amp)

        self.chk_bias_tee = QtWidgets.QCheckBox("Enable Antenna Bias-Tee (3.3V DC)")
        self.chk_bias_tee.setToolTip("Supplies 3.3V DC (up to 50mA) to active antennas / LNAs. Use with care!")
        self.chk_bias_tee.toggled.connect(self._on_bias_tee_toggled)
        layout_gain.addWidget(self.chk_bias_tee)

        layout.addWidget(group_gain)

        # 5. SDR Parameters: Sample Rate & Baseband Filter
        group_sdr = QtWidgets.QGroupBox("Sample Rate & Filter")
        layout_sdr = QtWidgets.QVBoxLayout(group_sdr)

        layout_sdr.addWidget(QtWidgets.QLabel("Sample Rate:"))
        self.combo_rate = QtWidgets.QComboBox()
        self.combo_rate.addItems(["2 MSPS", "4 MSPS", "8 MSPS", "10 MSPS", "16 MSPS", "20 MSPS"])
        self.combo_rate.currentIndexChanged.connect(self._on_rate_changed)
        layout_sdr.addWidget(self.combo_rate)

        layout_sdr.addWidget(QtWidgets.QLabel("Baseband Filter Bandwidth:"))
        self.combo_filter = QtWidgets.QComboBox()
        self.combo_filter.addItems([
            "1.75 MHz", "2.5 MHz", "3.5 MHz", "5.0 MHz",
            "7.0 MHz", "10.0 MHz", "14.0 MHz", "20.0 MHz", "28.0 MHz"
        ])
        self.combo_filter.currentIndexChanged.connect(self._on_filter_changed)
        layout_sdr.addWidget(self.combo_filter)

        layout.addWidget(group_sdr)
        layout.addStretch()

    def _on_run_toggled(self, checked: bool):
        self.is_running = checked
        if checked:
            self.btn_run.setText("STOP SDR")
        else:
            self.btn_run.setText("START SDR")
        self.start_stop_clicked.emit(checked)

    def _on_source_changed(self, index: int):
        sources = ["Simulator", "Hardware", "File"]
        self.device_mode_changed.emit(sources[index])

    def _on_spin_freq_changed(self, value: float):
        freq_hz = value * 1e6
        self.frequency_changed.emit(freq_hz)

    def step_frequency(self, delta_mhz: float):
        new_val = self.spin_freq.value() + delta_mhz
        new_val = max(1.0, min(6000.0, new_val))
        self.spin_freq.setValue(new_val)

    def set_frequency_mhz(self, freq_mhz: float):
        self.spin_freq.blockSignals(True)
        self.spin_freq.setValue(freq_mhz)
        self.spin_freq.blockSignals(False)
        self.frequency_changed.emit(freq_mhz * 1e6)

    def _on_preset_selected(self, index: int):
        if index > 0 and index < len(self.PRESETS):
            _, freq_hz = self.PRESETS[index]
            if freq_hz is not None:
                self.set_frequency_mhz(freq_hz / 1e6)

    def _on_lna_slider_changed(self, value: int):
        # Round to nearest 8 dB
        rounded = int(round(value / 8.0) * 8)
        self.slider_lna.blockSignals(True)
        self.slider_lna.setValue(rounded)
        self.slider_lna.blockSignals(False)
        self.lbl_lna_val.setText(f"{rounded} dB")
        self.lna_gain_changed.emit(rounded)

    def _on_vga_slider_changed(self, value: int):
        # Round to nearest 2 dB
        rounded = int(round(value / 2.0) * 2)
        self.slider_vga.blockSignals(True)
        self.slider_vga.setValue(rounded)
        self.slider_vga.blockSignals(False)
        self.lbl_vga_val.setText(f"{rounded} dB")
        self.vga_gain_changed.emit(rounded)

    def _on_bias_tee_toggled(self, checked: bool):
        if checked:
            reply = QtWidgets.QMessageBox.warning(
                self, "Antenna Bias-Tee Warning",
                "Enabling Bias-Tee supplies +3.3V DC power out of the antenna port.\n"
                "Do NOT enable this with antennas or instruments that do not support DC power!\n\n"
                "Enable 3.3V Bias-Tee anyway?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            if reply != QtWidgets.QMessageBox.Yes:
                self.chk_bias_tee.blockSignals(True)
                self.chk_bias_tee.setChecked(False)
                self.chk_bias_tee.blockSignals(False)
                return
        self.bias_tee_toggled.emit(checked)

    def _on_rate_changed(self, index: int):
        rates = [2.0e6, 4.0e6, 8.0e6, 10.0e6, 16.0e6, 20.0e6]
        self.sample_rate_changed.emit(rates[index])

    def _on_filter_changed(self, index: int):
        filters = [1750000, 2500000, 3500000, 5000000, 7000000, 10000000, 14000000, 20000000, 28000000]
        self.baseband_filter_changed.emit(filters[index])
