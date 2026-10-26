"""
Dialog Windows for HackRF Studio:
- Device Diagnostics & Info
- I/Q Signal Recording Configuration
- About & Hardware Guide
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from recording.iq_file import FileFormat


class DeviceInfoDialog(QtWidgets.QDialog):
    """Displays connected HackRF One hardware attributes and diagnostics."""

    def __init__(self, device_info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HackRF One Device Diagnostics")
        self.resize(480, 360)
        self._init_ui(device_info)

    def _init_ui(self, info: dict):
        layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel("<b>Great Scott Gadgets - HackRF One</b>")
        title.setStyleSheet("font-size: 16px; color: #00ffaa;")
        layout.addWidget(title)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        for key, val in info.items():
            k_name = key.replace("_", " ").title()
            v_label = QtWidgets.QLabel(str(val))
            v_label.setStyleSheet("font-family: Consolas; font-weight: bold;")
            form.addRow(f"{k_name}:", v_label)

        layout.addLayout(form)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)


class RecordDialog(QtWidgets.QDialog):
    """Configures I/Q recording path and format."""

    def __init__(self, current_freq_mhz: float, current_rate_msps: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record Raw I/Q Signal")
        self.resize(450, 240)
        self.file_path = ""
        self.selected_format = FileFormat.HACKRF_INT8
        self._init_ui(current_freq_mhz, current_rate_msps)

    def _init_ui(self, freq_mhz: float, rate_msps: float):
        layout = QtWidgets.QVBoxLayout(self)

        # File path selector
        layout_path = QtWidgets.QHBoxLayout()
        default_name = f"hackrf_capture_{freq_mhz:.3f}MHz_{rate_msps:.1f}MSPS.c8"
        self.edit_path = QtWidgets.QLineEdit(default_name)
        btn_browse = QtWidgets.QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse)
        layout_path.addWidget(self.edit_path)
        layout_path.addWidget(btn_browse)

        layout.addWidget(QtWidgets.QLabel("Output Destination File:"))
        layout.addLayout(layout_path)

        # File format selector
        layout.addWidget(QtWidgets.QLabel("File Format:"))
        self.combo_format = QtWidgets.QComboBox()
        for fmt in FileFormat:
            self.combo_format.addItem(fmt.value, fmt)
        layout.addWidget(self.combo_format)

        # Info label
        self.lbl_rate = QtWidgets.QLabel(
            f"Capturing at {freq_mhz:.3f} MHz, {rate_msps:.1f} MSPS.\n"
            f"Approximate data throughput: {rate_msps * 2:.1f} MB/s"
        )
        self.lbl_rate.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(self.lbl_rate)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _browse(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save I/Q File", self.edit_path.text(),
            "HackRF Native (*.c8 *.bin);;GNU Radio Float (*.cf32);;WAV Audio (*.wav);;All Files (*)"
        )
        if path:
            self.edit_path.setText(path)

    def _accept(self):
        self.file_path = self.edit_path.text()
        self.selected_format = self.combo_format.currentData()
        self.accept()


class AboutDialog(QtWidgets.QDialog):
    """About HackRF Studio dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About HackRF Studio")
        self.resize(460, 320)
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        txt = QtWidgets.QLabel(
            "<h2 style='color:#00ffaa;'>HackRF Studio</h2>"
            "<b>Modern Software-Defined Radio Workstation for HackRF One</b><br><br>"
            "Features:<br>"
            "• Real-time 60 FPS FFT Spectrum Analyzer & Spectrogram Waterfall<br>"
            "• Demodulator Engine: WFM (Broadcast FM), NFM, AM, SSB, CW<br>"
            "• 1 MHz to 6 GHz Wideband Panoramic Spectrum Sweep Scanner<br>"
            "• Sub-GHz Digital Protocol Inspector (ASK/OOK 433 MHz & 315 MHz)<br>"
            "• TX Signal Generator & RF Transmitter Workbench<br>"
            "• High-Fidelity Physics RF Simulator for offline use<br>"
            "• Raw I/Q File Recording & Continuous Playback<br><br>"
            "<small>Compatible with Great Scott Gadgets HackRF One & HackRF Jawbreaker.</small>"
        )
        txt.setWordWrap(True)
        layout.addWidget(txt)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)
