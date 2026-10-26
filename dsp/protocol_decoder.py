"""
Sub-GHz Digital Protocol Inspector (ASK / OOK / FSK).
Slices pulse trains, measures timings, and decodes binary/hex payloads
for 433 MHz, 315 MHz, and 868/915 MHz devices (remotes, weather sensors, smart meters).
"""

import time
import numpy as np
from typing import List, Dict, Optional, Tuple


class PacketRecord:
    def __init__(self, timestamp: float, duration_ms: float, pulse_count: int, binary_str: str, hex_str: str, timings: List[float]):
        self.timestamp = timestamp
        self.duration_ms = duration_ms
        self.pulse_count = pulse_count
        self.binary_str = binary_str
        self.hex_str = hex_str
        self.timings = timings  # List of pulse durations in microseconds

    def summary(self) -> str:
        t_str = time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        return f"[{t_str}] {self.hex_str} ({len(self.binary_str)} bits, {self.duration_ms:.1f}ms)"


class ProtocolDecoder:
    """Detects, slices, and decodes ASK/OOK digital transmissions."""

    def __init__(self, sample_rate: float = 2.0e6):
        self.sample_rate = float(sample_rate)
        self.threshold_pct: float = 0.35  # Threshold for high/low slicing
        self.min_pulse_us: float = 80.0   # Min pulse width (reject noise spikes)
        self.max_pulse_us: float = 15000.0 # Max pulse width before packet end
        self.history: List[PacketRecord] = []
        self._max_history = 50

        # Current packet accumulation state
        self._in_packet = False
        self._current_pulses: List[Tuple[int, float]] = []  # [(state 0 or 1, duration_us)]
        self._last_state = 0
        self._state_start_time = 0.0

    def set_sample_rate(self, rate: float):
        self.sample_rate = float(rate)

    def process_iq(self, iq_chunk: np.ndarray) -> List[PacketRecord]:
        """
        Processes an I/Q chunk to detect digital pulse trains.
        Returns newly decoded packets.
        """
        if len(iq_chunk) == 0:
            return []

        # 1. Amplitude envelope
        mag = np.abs(iq_chunk)
        max_val = np.max(mag)
        if max_val < 0.05:
            # Below meaningful carrier level
            return []

        threshold = max(0.08, max_val * self.threshold_pct)
        # Sliced digital state: 1 = carrier active, 0 = silence
        digital = (mag > threshold).astype(np.int8)

        # 2. Run-length encoding of state transitions
        diffs = np.diff(digital)
        change_indices = np.where(diffs != 0)[0] + 1
        splits = np.split(digital, change_indices)

        new_packets = []
        samples_per_us = self.sample_rate / 1e6

        for segment in splits:
            if len(segment) == 0:
                continue
            state = int(segment[0])
            duration_us = len(segment) / samples_per_us

            if state == 1:
                # Carrier burst
                if duration_us >= self.min_pulse_us:
                    self._in_packet = True
                    self._current_pulses.append((1, duration_us))
            else:
                # Silence gap
                if self._in_packet:
                    if duration_us > self.max_pulse_us:
                        # Packet finished by long inter-packet gap
                        packet = self._finalize_packet()
                        if packet:
                            new_packets.append(packet)
                    elif duration_us >= self.min_pulse_us:
                        self._current_pulses.append((0, duration_us))

        return new_packets

    def _finalize_packet(self) -> Optional[PacketRecord]:
        """Analyzes accumulated pulses into bits and hex values."""
        self._in_packet = False
        pulses = self._current_pulses
        self._current_pulses = []

        # Filter out trivial noise burps
        if len(pulses) < 10:
            return None

        # Measure timings of high pulses
        high_durations = [dur for (st, dur) in pulses if st == 1]
        if not high_durations:
            return None

        median_high = float(np.median(high_durations))
        timings = [dur for (_, dur) in pulses]
        total_duration_ms = sum(timings) / 1000.0

        # PWM / Pulse width classification:
        # If high pulse > 1.4 * median -> bit '1', else bit '0'
        # Or short/long pulses
        bits = []
        for st, dur in pulses:
            if st == 1:
                if dur > (1.3 * median_high):
                    bits.append("1")
                else:
                    bits.append("0")

        if len(bits) < 8:
            return None

        binary_str = "".join(bits)

        # Convert binary string to hexadecimal representation
        hex_chars = []
        for i in range(0, len(binary_str), 4):
            nibble = binary_str[i:i + 4]
            if len(nibble) == 4:
                hex_chars.append(f"{int(nibble, 2):X}")
            else:
                hex_chars.append(f"{int(nibble.ljust(4, '0'), 2):X}")
        hex_str = "0x" + "".join(hex_chars)

        record = PacketRecord(
            timestamp=time.time(),
            duration_ms=total_duration_ms,
            pulse_count=len(pulses),
            binary_str=binary_str,
            hex_str=hex_str,
            timings=timings[:100]  # First 100 timings for visualization
        )

        self.history.insert(0, record)
        if len(self.history) > self._max_history:
            self.history.pop()

        return record
