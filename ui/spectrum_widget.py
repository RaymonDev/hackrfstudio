"""
Interactive Real-Time Spectrum and Waterfall (Spectrogram) Display.
Powered by pyqtgraph for high-FPS 60Hz hardware-accelerated rendering.
"""

import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg


class SpectrumWidget(QtWidgets.QWidget):
    """Real-time FFT Spectrum Analyzer and scrolling Waterfall view."""

    # Signal emitted when user clicks on spectrum to tune channel offset (Hz)
    channel_tuned = QtCore.pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.center_freq_mhz = 100.0
        self.sample_rate_mhz = 2.0
        self.channel_offset_hz = 0.0
        self.demod_bandwidth_khz = 200.0  # Width of receiver passband

        # Waterfall buffer
        self.waterfall_history = 160
        self.fft_size = 2048
        self.waterfall_buffer = np.full((self.waterfall_history, self.fft_size), -100.0, dtype=np.float32)

        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Splitter between Spectrum Plot (top) and Waterfall (bottom)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        layout.addWidget(self.splitter)

        # 1. Spectrum Plot Widget
        self.spectrum_plot = pg.PlotWidget(title="<b>RF SPECTRUM</b> (Power vs Frequency)")
        self.spectrum_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spectrum_plot.setYRange(-115, -10, padding=0)
        self.spectrum_plot.setLabel("left", "Power", units="dBFS")
        self.spectrum_plot.setLabel("bottom", "Frequency", units="MHz")
        self.spectrum_plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.spectrum_plot.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)

        # Real-time FFT spectrum curve (Neon Cyan)
        pen_live = pg.mkPen(color=(0, 255, 230), width=1.5)
        self.curve_live = self.spectrum_plot.plot(pen=pen_live)

        # Peak Hold curve (Amber)
        pen_peak = pg.mkPen(color=(255, 180, 0, 160), width=1.0, style=QtCore.Qt.DashLine)
        self.curve_peak = self.spectrum_plot.plot(pen=pen_peak)

        # Shaded Demodulation Channel Overlay (Shows active receiver passband)
        self.channel_region = pg.LinearRegionItem(
            values=[self.center_freq_mhz - 0.1, self.center_freq_mhz + 0.1],
            brush=pg.mkBrush(0, 180, 255, 45),
            pen=pg.mkPen(0, 200, 255, 120),
            movable=True
        )
        self.channel_region.sigRegionChanged.connect(self._on_channel_region_moved)
        self.spectrum_plot.addItem(self.channel_region)

        # Center frequency LO marker (vertical red line)
        self.lo_line = pg.InfiniteLine(pos=self.center_freq_mhz, angle=90, pen=pg.mkPen((255, 60, 60, 180), width=1, style=QtCore.Qt.DotLine))
        self.spectrum_plot.addItem(self.lo_line)

        # Click to tune on spectrum
        self.spectrum_plot.scene().sigMouseClicked.connect(self._on_spectrum_clicked)

        self.splitter.addWidget(self.spectrum_plot)

        # 2. Waterfall Plot Widget
        self.waterfall_plot = pg.PlotWidget(title="<b>SPECTROGRAM / WATERFALL</b>")
        self.waterfall_plot.setLabel("left", "Time History")
        self.waterfall_plot.setLabel("bottom", "Frequency", units="MHz")
        self.waterfall_plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.waterfall_plot.getAxis("left").setStyle(showValues=False)

        # Waterfall Image Item
        self.waterfall_img = pg.ImageItem()
        self.waterfall_plot.addItem(self.waterfall_img)

        # Setup colormap (Turbo / Heatmap)
        pos = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        color = np.array([
            [15, 15, 35, 255],     # Dark blue floor
            [0, 110, 210, 255],    # Blue
            [0, 200, 120, 255],    # Cyan/Green
            [255, 215, 0, 255],    # Yellow
            [255, 50, 50, 255],    # Red peaks
        ], dtype=np.ubyte)
        cmap = pg.ColorMap(pos, color)
        self.waterfall_lut = cmap.getLookupTable(0.0, 1.0, 256)
        self.waterfall_img.setLookupTable(self.waterfall_lut)
        self.waterfall_img.setLevels([-105, -25])

        self.splitter.addWidget(self.waterfall_plot)
        self.splitter.setSizes([350, 250])

    def set_rf_parameters(self, center_freq_hz: float, sample_rate_hz: float):
        """Updates frequency limits and axes."""
        self.center_freq_mhz = center_freq_hz / 1e6
        self.sample_rate_mhz = sample_rate_hz / 1e6

        min_f = self.center_freq_mhz - (self.sample_rate_mhz / 2.0)
        max_f = self.center_freq_mhz + (self.sample_rate_mhz / 2.0)

        self.spectrum_plot.setXRange(min_f, max_f, padding=0)
        self.waterfall_plot.setXRange(min_f, max_f, padding=0)

        # Update LO marker
        self.lo_line.setPos(self.center_freq_mhz)
        self._update_channel_region()

        # Update waterfall transform
        self._update_waterfall_rect(min_f, max_f)

    def set_demod_bandwidth(self, bw_khz: float):
        self.demod_bandwidth_khz = float(bw_khz)
        self._update_channel_region()

    def set_channel_offset(self, offset_hz: float):
        self.channel_offset_hz = float(offset_hz)
        self._update_channel_region()

    def _update_channel_region(self):
        half_span_mhz = (self.demod_bandwidth_khz / 1000.0) / 2.0
        center_mhz = self.center_freq_mhz + (self.channel_offset_hz / 1e6)
        self.channel_region.blockSignals(True)
        self.channel_region.setRegion([center_mhz - half_span_mhz, center_mhz + half_span_mhz])
        self.channel_region.blockSignals(False)

    def _on_channel_region_moved(self):
        min_v, max_v = self.channel_region.getRegion()
        center_mhz = (min_v + max_v) / 2.0
        offset_hz = (center_mhz - self.center_freq_mhz) * 1e6
        self.channel_offset_hz = offset_hz
        self.channel_tuned.emit(offset_hz)

    def _on_spectrum_clicked(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            pos = event.scenePos()
            if self.spectrum_plot.sceneBoundingRect().contains(pos):
                mouse_point = self.spectrum_plot.plotItem.vb.mapSceneToView(pos)
                clicked_freq_mhz = mouse_point.x()
                offset_hz = (clicked_freq_mhz - self.center_freq_mhz) * 1e6
                # Limit to Nyquist span
                max_offset = (self.sample_rate_mhz * 1e6) / 2.0
                if -max_offset <= offset_hz <= max_offset:
                    self.set_channel_offset(offset_hz)
                    self.channel_tuned.emit(offset_hz)

    def _update_waterfall_rect(self, min_f: float, max_f: float):
        # Maps pixel buffer coordinate space to frequency in MHz and time rows
        rect = QtCore.QRectF(min_f, 0, (max_f - min_f), self.waterfall_history)
        self.waterfall_img.setRect(rect)

    def update_spectrum(self, freqs_mhz: np.ndarray, power_db: np.ndarray, peak_db=None):
        """Called on UI thread to render new FFT slice and waterfall row."""
        # 1. Update live FFT line
        self.curve_live.setData(freqs_mhz, power_db)

        # 2. Update peak hold line
        if peak_db is not None:
            self.curve_peak.setData(freqs_mhz, peak_db)
        else:
            self.curve_peak.clear()

        # 3. Update Waterfall Spectrogram
        if len(power_db) != self.fft_size:
            self.fft_size = len(power_db)
            self.waterfall_buffer = np.full((self.waterfall_history, self.fft_size), -100.0, dtype=np.float32)

        # Roll down waterfall history and push new row at top
        self.waterfall_buffer = np.roll(self.waterfall_buffer, 1, axis=0)
        self.waterfall_buffer[0, :] = power_db
        self.waterfall_img.setImage(self.waterfall_buffer.T, autoLevels=False)

    def set_waterfall_levels(self, min_db: float, max_db: float):
        """Adjusts visual contrast/brightness of waterfall."""
        self.waterfall_img.setLevels([min_db, max_db])
