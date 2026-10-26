"""
Demodulator & Audio Controls Widget for HackRF SDR.
Manages mode selection, volume, squelch, AGC, and RSSI (S-Meter).
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from dsp.demodulator import DemodMode


class DemodWidget(QtWidgets.QWidget):
    """Audio and Demodulation Control Panel."""

    mode_changed = QtCore.pyqtSignal(DemodMode)
    bandwidth_changed = QtCore.pyqtSignal(float)     # kHz
    volume_changed = QtCore.pyqtSignal(float)        # 0.0 to 1.0
    mute_toggled = QtCore.pyqtSignal(bool)
    squelch_changed = QtCore.pyqtSignal(float)       # dBFS
    agc_toggled = QtCore.pyqtSignal(bool)

    DEFAULT_BW = {
        DemodMode.WFM: 200.0,
        DemodMode.NFM: 15.0,
        DemodMode.AM: 8.0,
        DemodMode.USB: 3.0,
        DemodMode.LSB: 3.0,
        DemodMode.CW: 1.0,
        DemodMode.RAW: 200.0,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mode = DemodMode.WFM
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 1. Mode Selection Group
        group_mode = QtWidgets.QGroupBox("Demodulation Mode")
        layout_mode = QtWidgets.QVBoxLayout(group_mode)

        self.combo_mode = QtWidgets.QComboBox()
        for mode in DemodMode:
            self.combo_mode.addItem(mode.value, mode)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        layout_mode.addWidget(self.combo_mode)

        # Receiver Bandwidth
        layout_bw = QtWidgets.QHBoxLayout()
        layout_bw.addWidget(QtWidgets.QLabel("Filter Bandwidth:"))
        self.lbl_bw = QtWidgets.QLabel("200 kHz")
        self.lbl_bw.setStyleSheet("font-weight: bold; color: #00e6c3;")
        layout_bw.addWidget(self.lbl_bw)
        layout_mode.addLayout(layout_bw)

        self.slider_bw = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_bw.setRange(1, 300)
        self.slider_bw.setValue(200)
        self.slider_bw.valueChanged.connect(self._on_bw_changed)
        layout_mode.addWidget(self.slider_bw)

        layout.addWidget(group_mode)

        # 2. RSSI & Squelch Group
        group_squelch = QtWidgets.QGroupBox("Signal Strength & Squelch")
        layout_squelch = QtWidgets.QVBoxLayout(group_squelch)

        # RSSI S-Meter Bar
        layout_meter = QtWidgets.QHBoxLayout()
        layout_meter.addWidget(QtWidgets.QLabel("Signal (RSSI):"))
        self.lbl_rssi = QtWidgets.QLabel("-95.0 dBFS")
        self.lbl_rssi.setStyleSheet("font-weight: bold;")
        layout_meter.addWidget(self.lbl_rssi)
        layout_squelch.addLayout(layout_meter)

        self.bar_rssi = QtWidgets.QProgressBar()
        self.bar_rssi.setRange(-110, -10)
        self.bar_rssi.setValue(-95)
        self.bar_rssi.setTextVisible(False)
        self.bar_rssi.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 3px;
                background-color: #222;
                height: 14px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0088ff, stop:0.7 #00ffaa, stop:1.0 #ff3333);
            }
        """)
        layout_squelch.addWidget(self.bar_rssi)

        # Squelch Threshold Slider
        layout_sql = QtWidgets.QHBoxLayout()
        layout_sql.addWidget(QtWidgets.QLabel("Squelch Gate:"))
        self.lbl_sql = QtWidgets.QLabel("-70 dBFS")
        self.lbl_sql.setStyleSheet("font-weight: bold;")
        layout_sql.addWidget(self.lbl_sql)
        layout_squelch.addLayout(layout_sql)

        self.slider_sql = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_sql.setRange(-110, -20)
        self.slider_sql.setValue(-70)
        self.slider_sql.valueChanged.connect(self._on_sql_changed)
        layout_squelch.addWidget(self.slider_sql)

        # Squelch LED Indicator
        self.lbl_gate_status = QtWidgets.QLabel("● Squelch CLOSED (Muted)")
        self.lbl_gate_status.setStyleSheet("color: #888888; font-weight: bold;")
        layout_squelch.addWidget(self.lbl_gate_status)

        layout.addWidget(group_squelch)

        # 3. Audio & Volume Group
        group_audio = QtWidgets.QGroupBox("Audio Controls")
        layout_audio = QtWidgets.QVBoxLayout(group_audio)

        layout_vol = QtWidgets.QHBoxLayout()
        layout_vol.addWidget(QtWidgets.QLabel("Volume:"))
        self.lbl_vol = QtWidgets.QLabel("80%")
        self.lbl_vol.setStyleSheet("font-weight: bold;")
        layout_vol.addWidget(self.lbl_vol)
        layout_audio.addLayout(layout_vol)

        self.slider_vol = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(80)
        self.slider_vol.valueChanged.connect(self._on_vol_changed)
        layout_audio.addWidget(self.slider_vol)

        layout_audio_opts = QtWidgets.QHBoxLayout()
        self.btn_mute = QtWidgets.QPushButton("Mute")
        self.btn_mute.setCheckable(True)
        self.btn_mute.toggled.connect(self.mute_toggled.emit)
        layout_audio_opts.addWidget(self.btn_mute)

        self.chk_agc = QtWidgets.QCheckBox("Enable AGC")
        self.chk_agc.setChecked(True)
        self.chk_agc.toggled.connect(self.agc_toggled.emit)
        layout_audio_opts.addWidget(self.chk_agc)

        layout_audio.addLayout(layout_audio_opts)
        layout.addWidget(group_audio)

        layout.addStretch()

    def _on_mode_changed(self, index: int):
        mode = self.combo_mode.itemData(index)
        if mode:
            self.current_mode = mode
            default_bw = self.DEFAULT_BW.get(mode, 20.0)
            self.slider_bw.setValue(int(default_bw))
            self.mode_changed.emit(mode)

    def _on_bw_changed(self, val: int):
        self.lbl_bw.setText(f"{val} kHz")
        self.bandwidth_changed.emit(float(val))

    def _on_sql_changed(self, val: int):
        self.lbl_sql.setText(f"{val} dBFS")
        self.squelch_changed.emit(float(val))

    def _on_vol_changed(self, val: int):
        self.lbl_vol.setText(f"{val}%")
        self.volume_changed.emit(val / 100.0)

    def update_rssi(self, rssi_db: float, squelch_open: bool):
        """Called periodically by DSP engine to update signal strength display."""
        clamped = max(-110, min(-10, int(rssi_db)))
        self.bar_rssi.setValue(clamped)
        self.lbl_rssi.setText(f"{rssi_db:.1f} dBFS")

        if squelch_open:
            self.lbl_gate_status.setText("● Squelch OPEN (Signal Active)")
            self.lbl_gate_status.setStyleSheet("color: #00ffaa; font-weight: bold;")
        else:
            self.lbl_gate_status.setText("● Squelch CLOSED (Muted)")
            self.lbl_gate_status.setStyleSheet("color: #888888; font-weight: bold;")
