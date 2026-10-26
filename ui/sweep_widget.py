"""
Wideband Spectrum Sweep Panorama Widget (1 MHz to 6 GHz).
Visualizes wide spans, runs peak detection, and allows 1-click tuning.
"""

import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
from hackrf.sweep_scanner import WidebandSweepScanner, SweepResult


class SweepWidget(QtWidgets.QWidget):
    """Panoramic Wideband Spectrum Analyzer."""

    # Emitted when user clicks 'Tune SDR Here' on a detected peak
    tune_requested = QtCore.pyqtSignal(float)  # Frequency in Hz

    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.device = device
        self.scanner = WidebandSweepScanner(self.device)
        self.scanner_running = False

        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Left Column: Sweep Controls and Peak Table (350px)
        left_panel = QtWidgets.QWidget()
        layout_left = QtWidgets.QVBoxLayout(left_panel)
        layout_left.setContentsMargins(0, 0, 0, 0)
        left_panel.setFixedWidth(340)

        # Start / Stop Sweep Button
        self.btn_sweep = QtWidgets.QPushButton("START WIDEBAND SWEEP")
        self.btn_sweep.setFixedHeight(40)
        self.btn_sweep.setCheckable(True)
        self.btn_sweep.setStyleSheet("""
            QPushButton {
                background-color: #0d8050;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border-radius: 4px;
            }
            QPushButton:checked {
                background-color: #c9302c;
            }
        """)
        self.btn_sweep.toggled.connect(self._on_sweep_toggled)
        layout_left.addWidget(self.btn_sweep)

        # Band Presets
        group_bands = QtWidgets.QGroupBox("Quick Scan Band Presets")
        layout_bands = QtWidgets.QGridLayout(group_bands)

        bands = [
            ("FM (87-108M)", 87e6, 108e6),
            ("Airband (118-137M)", 118e6, 137e6),
            ("Ham 2m (144-148M)", 144e6, 148e6),
            ("ISM (430-440M)", 430e6, 440e6),
            ("ISM (860-930M)", 860e6, 930e6),
            ("WiFi (2.4-2.5G)", 2400e6, 2500e6),
            ("Full (10-1000M)", 10e6, 1000e6),
            ("Full (1-6 GHz)", 1000e6, 6000e6),
        ]

        row = 0
        col = 0
        for name, f_start, f_stop in bands:
            btn = QtWidgets.QPushButton(name)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda ch, s=f_start, e=f_stop: self._set_scan_range(s, e))
            layout_bands.addWidget(btn, row, col)
            col += 1
            if col == 2:
                col = 0
                row += 1
        layout_left.addWidget(group_bands)

        # Manual Range Inputs
        group_custom = QtWidgets.QGroupBox("Custom Range (MHz)")
        layout_custom = QtWidgets.QHBoxLayout(group_custom)
        self.spin_start = QtWidgets.QDoubleSpinBox()
        self.spin_start.setRange(1.0, 6000.0)
        self.spin_start.setValue(87.0)
        self.spin_stop = QtWidgets.QDoubleSpinBox()
        self.spin_stop.setRange(1.0, 6000.0)
        self.spin_stop.setValue(108.0)
        layout_custom.addWidget(QtWidgets.QLabel("Start:"))
        layout_custom.addWidget(self.spin_start)
        layout_custom.addWidget(QtWidgets.QLabel("Stop:"))
        layout_custom.addWidget(self.spin_stop)
        layout_left.addWidget(group_custom)

        # Peak Detection Threshold
        layout_thresh = QtWidgets.QHBoxLayout()
        layout_thresh.addWidget(QtWidgets.QLabel("Peak Threshold:"))
        self.spin_thresh = QtWidgets.QSpinBox()
        self.spin_thresh.setRange(-110, -20)
        self.spin_thresh.setValue(-65)
        self.spin_thresh.setSuffix(" dBFS")
        layout_thresh.addWidget(self.spin_thresh)
        layout_left.addLayout(layout_thresh)

        # Detected Peaks Table
        layout_left.addWidget(QtWidgets.QLabel("<b>Detected RF Emitters:</b>"))
        self.table_peaks = QtWidgets.QTableWidget(0, 3)
        self.table_peaks.setHorizontalHeaderLabels(["Freq (MHz)", "Power", "Action"])
        self.table_peaks.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table_peaks.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table_peaks.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        layout_left.addWidget(self.table_peaks)

        layout.addWidget(left_panel)

        # Right Column: Wideband Panorama Plot
        self.plot_sweep = pg.PlotWidget(title="<b>WIDEBAND SPECTRUM PANORAMA</b> (1 MHz - 6 GHz)")
        self.plot_sweep.showGrid(x=True, y=True, alpha=0.3)
        self.plot_sweep.setYRange(-110, -10, padding=0)
        self.plot_sweep.setLabel("left", "Power", units="dBFS")
        self.plot_sweep.setLabel("bottom", "Frequency", units="MHz")
        self.plot_sweep.getAxis("bottom").enableAutoSIPrefix(False)

        pen_sweep = pg.mkPen(color=(0, 255, 180), width=1.5)
        self.curve_sweep = self.plot_sweep.plot(pen=pen_sweep)

        # Peak scatter markers
        self.peak_markers = pg.ScatterPlotItem(
            size=8,
            symbol="t1",  # Triangle marker pointing down
            pen=pg.mkPen((255, 230, 0), width=1),
            brush=pg.mkBrush(255, 230, 0, 220),
            pxMode=True
        )
        self.plot_sweep.addItem(self.peak_markers)

        layout.addWidget(self.plot_sweep, stretch=1)

    def _set_scan_range(self, start_hz: float, stop_hz: float):
        self.spin_start.setValue(start_hz / 1e6)
        self.spin_stop.setValue(stop_hz / 1e6)
        if self.scanner_running:
            self.scanner.configure(start_hz, stop_hz)

    def _on_sweep_toggled(self, checked: bool):
        self.scanner_running = checked
        if checked:
            self.btn_sweep.setText("STOP WIDEBAND SWEEP")
            start_hz = self.spin_start.value() * 1e6
            stop_hz = self.spin_stop.value() * 1e6
            self.scanner.configure(start_hz, stop_hz)
            self.plot_sweep.setXRange(start_hz / 1e6, stop_hz / 1e6, padding=0)
            self.scanner.start_sweep(self._on_sweep_data)
        else:
            self.btn_sweep.setText("START WIDEBAND SWEEP")
            self.scanner.stop_sweep()

    def _on_sweep_data(self, result: SweepResult):
        # Update UI safely
        QtCore.QMetaObject.invokeMethod(
            self, "_update_sweep_ui", QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(object, result)
        )

    @QtCore.pyqtSlot(object)
    def _update_sweep_ui(self, result: SweepResult):
        freq_mhz = result.freq_mhz
        powers = result.power_db

        self.curve_sweep.setData(freq_mhz, powers)

        # Detect peaks
        thresh = float(self.spin_thresh.value())
        peaks = self.scanner.detect_peaks(result, threshold_db=thresh)

        if peaks:
            peak_x = [p["freq_mhz"] for p in peaks]
            peak_y = [p["power_db"] + 4.0 for p in peaks]
            self.peak_markers.setData(x=peak_x, y=peak_y)

            # Update peak table
            self.table_peaks.setRowCount(len(peaks))
            for row, p in enumerate(peaks):
                f_item = QtWidgets.QTableWidgetItem(f"{p['freq_mhz']:.3f}")
                p_item = QtWidgets.QTableWidgetItem(f"{p['power_db']:.1f} dB")

                btn_tune = QtWidgets.QPushButton("Tune")
                btn_tune.setFixedHeight(20)
                freq_hz = p["freq_hz"]
                btn_tune.clicked.connect(lambda ch, f=freq_hz: self.tune_requested.emit(f))

                self.table_peaks.setItem(row, 0, f_item)
                self.table_peaks.setItem(row, 1, p_item)
                self.table_peaks.setCellWidget(row, 2, btn_tune)
        else:
            self.peak_markers.clear()
            self.table_peaks.setRowCount(0)
