"""
Sub-GHz Digital Protocol Inspector & Pulse Analyzer Widget.
Captures, visualizes, and decodes 433 MHz / 315 MHz / 868 MHz remote packets.
"""

from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
from dsp.protocol_decoder import ProtocolDecoder, PacketRecord


class PulseWidget(QtWidgets.QWidget):
    """Sub-GHz RF Pulse Inspector and Packet Decoder."""

    # Emitted when user wants to transfer a captured packet to TX workbench
    load_to_tx_requested = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.decoder = ProtocolDecoder()
        self.selected_record: PacketRecord = None
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 1. Digital Pulse Timing Scope (Top)
        self.plot_pulse = pg.PlotWidget(title="<b>DIGITAL PULSE TRAIN</b> (Amplitude Sliced OOK)")
        self.plot_pulse.showGrid(x=True, y=True, alpha=0.3)
        self.plot_pulse.setYRange(-0.2, 1.2, padding=0.05)
        self.plot_pulse.setLabel("bottom", "Pulse Duration", units="µs")
        self.plot_pulse.setLabel("left", "Logic State")
        self.plot_pulse.setFixedHeight(180)

        pen_pulse = pg.mkPen(color=(0, 255, 120), width=2.0)
        self.curve_pulse = self.plot_pulse.plot(pen=pen_pulse)
        layout.addWidget(self.plot_pulse)

        # 2. Splitter for Packet List & Details (Bottom)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left: Table of captured packets
        table_container = QtWidgets.QWidget()
        layout_tc = QtWidgets.QVBoxLayout(table_container)
        layout_tc.setContentsMargins(0, 0, 0, 0)
        layout_tc.addWidget(QtWidgets.QLabel("<b>Captured RF Transmissions (ASK / OOK):</b>"))

        self.table_packets = QtWidgets.QTableWidget(0, 4)
        self.table_packets.setHorizontalHeaderLabels(["Time", "Hex Payload", "Bits", "Duration"])
        self.table_packets.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table_packets.itemSelectionChanged.connect(self._on_packet_selected)
        layout_tc.addWidget(self.table_packets)
        splitter.addWidget(table_container)

        # Right: Packet Inspection & Decode Details
        detail_container = QtWidgets.QWidget()
        layout_dc = QtWidgets.QVBoxLayout(detail_container)
        layout_dc.setContentsMargins(0, 0, 0, 0)
        layout_dc.addWidget(QtWidgets.QLabel("<b>Payload & Decoding Analysis:</b>"))

        self.txt_binary = QtWidgets.QTextEdit()
        self.txt_binary.setReadOnly(True)
        self.txt_binary.setFontFamily("Consolas")
        self.txt_binary.setStyleSheet("font-size: 13px; background-color: #1e1e1e; color: #00ffaa;")
        self.txt_binary.setPlaceholderText("Select a packet on the left to inspect bitstream...")
        layout_dc.addWidget(self.txt_binary)

        # Action Buttons
        layout_acts = QtWidgets.QHBoxLayout()
        self.btn_copy_hex = QtWidgets.QPushButton("Copy Hex")
        self.btn_copy_hex.clicked.connect(self._copy_hex_to_clipboard)
        layout_acts.addWidget(self.btn_copy_hex)

        self.btn_send_tx = QtWidgets.QPushButton("Load into TX Workbench")
        self.btn_send_tx.setStyleSheet("font-weight: bold; color: #ffbb00;")
        self.btn_send_tx.clicked.connect(self._send_to_tx)
        layout_acts.addWidget(self.btn_send_tx)

        self.btn_clear = QtWidgets.QPushButton("Clear History")
        self.btn_clear.clicked.connect(self._clear_history)
        layout_acts.addWidget(self.btn_clear)

        layout_dc.addLayout(layout_acts)
        splitter.addWidget(detail_container)
        splitter.setSizes([450, 400])

        layout.addWidget(splitter)

    def process_iq(self, iq_chunk):
        """Processes I/Q chunk and checks for newly decoded packets."""
        new_packets = self.decoder.process_iq(iq_chunk)
        if new_packets:
            self._add_packets_to_table(new_packets)

    def _add_packets_to_table(self, packets):
        for pkt in packets:
            row = self.table_packets.rowCount()
            self.table_packets.insertRow(row)

            time_str = QtCore.QTime.currentTime().toString("HH:mm:ss.zzz")
            self.table_packets.setItem(row, 0, QtWidgets.QTableWidgetItem(time_str))
            self.table_packets.setItem(row, 1, QtWidgets.QTableWidgetItem(pkt.hex_str))
            self.table_packets.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{len(pkt.binary_str)}"))
            self.table_packets.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{pkt.duration_ms:.1f} ms"))

            # Auto-select newest packet
            self.table_packets.selectRow(row)
            self._display_packet(pkt)

    def _on_packet_selected(self):
        selected_rows = self.table_packets.selectedItems()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if 0 <= row < len(self.decoder.history):
            pkt = self.decoder.history[row]
            self._display_packet(pkt)

    def _display_packet(self, pkt: PacketRecord):
        self.selected_record = pkt

        # Format details
        info_lines = [
            f"Hexadecimal: {pkt.hex_str}",
            f"Bit Length:  {len(pkt.binary_str)} bits",
            f"Duration:    {pkt.duration_ms:.2f} ms",
            f"Pulse Count: {pkt.pulse_count} transitions",
            "",
            "Binary Sequence:",
        ]
        # Format binary in 8-bit groups
        b_grouped = " ".join(pkt.binary_str[i:i+8] for i in range(0, len(pkt.binary_str), 8))
        info_lines.append(b_grouped)

        self.txt_binary.setPlainText("\n".join(info_lines))

        # Render digital square wave in top scope
        if pkt.timings:
            times = [0.0]
            states = [1]
            cur_t = 0.0
            cur_st = 1
            for dur in pkt.timings:
                cur_t += dur
                times.append(cur_t)
                states.append(cur_st)
                cur_st = 1 if cur_st == 0 else 0
                times.append(cur_t)
                states.append(cur_st)

            self.curve_pulse.setData(times, states)
            self.plot_pulse.setXRange(0, cur_t, padding=0.05)

    def _copy_hex_to_clipboard(self):
        if self.selected_record:
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(self.selected_record.hex_str)

    def _send_to_tx(self):
        if self.selected_record:
            self.load_to_tx_requested.emit(self.selected_record.hex_str)

    def _clear_history(self):
        self.decoder.history.clear()
        self.table_packets.setRowCount(0)
        self.txt_binary.clear()
        self.curve_pulse.clear()
