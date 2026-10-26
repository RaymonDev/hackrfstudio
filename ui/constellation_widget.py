"""
IQ Constellation Diagram & Time-Domain Oscilloscope Widget.
Visualizes I vs Q scatter and raw time waveforms for modulation analysis.
"""

import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg


class ConstellationWidget(QtWidgets.QWidget):
    """Constellation (I vs Q) and Time-Domain Oscilloscope."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        # 1. IQ Constellation Scatter Plot (Left)
        self.plot_constellation = pg.PlotWidget(title="<b>IQ CONSTELLATION</b> (I vs Q)")
        self.plot_constellation.showGrid(x=True, y=True, alpha=0.3)
        self.plot_constellation.setXRange(-1.0, 1.0, padding=0.05)
        self.plot_constellation.setYRange(-1.0, 1.0, padding=0.05)
        self.plot_constellation.setLabel("bottom", "In-Phase (I)")
        self.plot_constellation.setLabel("left", "Quadrature (Q)")

        # Scatter plot item
        self.scatter_item = pg.ScatterPlotItem(
            size=4,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(0, 240, 255, 120),
            pxMode=True
        )
        self.plot_constellation.addItem(self.scatter_item)
        layout.addWidget(self.plot_constellation, stretch=1)

        # 2. Time-Domain Oscilloscope (Right)
        self.plot_scope = pg.PlotWidget(title="<b>TIME-DOMAIN WAVEFORM</b> (I/Q Scope)")
        self.plot_scope.showGrid(x=True, y=True, alpha=0.3)
        self.plot_scope.setYRange(-1.0, 1.0, padding=0.05)
        self.plot_scope.setLabel("bottom", "Samples")
        self.plot_scope.setLabel("left", "Amplitude")
        self.plot_scope.addLegend(offset=(10, 10))

        pen_i = pg.mkPen(color=(0, 255, 230), width=1.5)
        pen_q = pg.mkPen(color=(255, 0, 150), width=1.5)
        self.curve_i = self.plot_scope.plot(pen=pen_i, name="In-Phase (I)")
        self.curve_q = self.plot_scope.plot(pen=pen_q, name="Quadrature (Q)")

        layout.addWidget(self.plot_scope, stretch=2)

    def update_samples(self, iq_samples: np.ndarray):
        """Updates constellation points and time-domain curves."""
        if len(iq_samples) == 0:
            return

        # Decimate / slice for responsive plotting (e.g. 1024 points max)
        pts_to_plot = min(1024, len(iq_samples))
        samples = iq_samples[:pts_to_plot]

        i_data = np.real(samples)
        q_data = np.imag(samples)

        # 1. Update Constellation Scatter
        self.scatter_item.setData(x=i_data, y=q_data)

        # 2. Update Time-Domain Scope
        x_axis = np.arange(pts_to_plot)
        self.curve_i.setData(x_axis, i_data)
        self.curve_q.setData(x_axis, q_data)
