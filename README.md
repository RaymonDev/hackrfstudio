# HackRF Studio 🛰️⚡

**HackRF Studio** is an advanced, high-performance Software-Defined Radio (SDR) workstation designed specifically for the **Great Scott Gadgets HackRF One** (and HackRF Jawbreaker).

Built from the ground up with **Python 3**, **PyQt5**, **pyqtgraph**, and **NumPy/SciPy**, HackRF Studio combines a 60 FPS spectrum analyzer, real-time audio demodulation, panoramic wideband frequency sweeping (1 MHz to 6 GHz), a Sub-GHz digital protocol inspector (ASK/OOK 433/315 MHz), an RF signal recorder/player, and a transmission (TX) signal generator workbench.

---

## 🌟 Key Features

### 1. 📡 60 FPS Real-Time Spectrum & Waterfall
- **FFT Spectrum Analyzer**: Hardware-accelerated curve rendering with customizable FFT sizes (512 to 8192), window functions (Hann, Hamming, Blackman-Harris), exponential averaging, and peak hold.
- **Dynamic Waterfall (Spectrogram)**: Scrolling 2D color heatmap with selectable palettes (*Turbo, Viridis, Inferno, Night Sky*), dynamic dB range scaling, and contrast control.
- **Click-to-Tune Receiver Overlay**: Visual passband highlight showing exactly where the receiver is tuned; drag or click anywhere to tune off-center channels in real-time.

### 2. 📻 Multi-Mode Audio Demodulator
- **Wideband FM (WFM)**: Broadcast radio (88–108 MHz) with quadrature discriminator, 50µs/75µs de-emphasis filtering, and crystal-clear audio.
- **Narrowband FM (NFM)**: Walkie-talkies, marine radio, and ham repeaters (12.5 kHz / 25 kHz) with audio low-pass filtering.
- **Amplitude Modulation (AM)**: Aviation airband (118–137 MHz), emergency guard (121.5 MHz), and shortwave with DC blocking and envelope detection.
- **Single Sideband (USB / LSB)**: Amateur radio HF/VHF SSB voice.
- **Continuous Wave (CW)**: Morse code reception with 700 Hz Beat Frequency Oscillator (BFO).
- **Intelligent Squelch & S-Meter**: Real-time RSSI signal strength display (dBFS) with configurable squelch gate to eliminate static background noise.
- **Automatic Gain Control (AGC)**: Prevents clipping and balances quiet signals automatically.

### 3. 🌐 Wideband Spectrum Sweep (1 MHz – 6 GHz)
- **High-Speed Band Panorama**: Scans broad frequency ranges up to 6 GHz.
- **Quick-Scan Presets**:
  - FM Broadcast (87 – 108 MHz)
  - Aviation Airband (118 – 137 MHz)
  - Ham 2m VHF (144 – 148 MHz)
  - ISM 433 MHz & Ham 70cm (430 – 440 MHz)
  - ISM 868 MHz & 915 MHz
  - 2.4 GHz WiFi & Bluetooth (2400 – 2500 MHz)
  - Full Spectrum Panorama (10 MHz – 6000 MHz)
- **Automated Emitter / Peak Detector**: Scans and displays discovered transmitters in a table with signal strength and a **"Tune SDR Here"** button.

### 4. 🔑 Sub-GHz Digital Protocol Inspector
- **ASK / OOK Burst Capture**: Detects remote control signals (car key fobs, garage door openers, 433.92 MHz weather stations, smart meters).
- **Logic Waveform Scope**: Displays decoded high/low pulses with microsecond timing.
- **Payload Decoding**: Converts pulse trains to binary strings and hexadecimal payloads (e.g. `0x1A2B3C4D`).
- **1-Click Transfer**: Send captured hex packets directly to the TX Workbench for replay.

### 5. 📡 TX Signal Generator Workbench
- **Waveform Synthesizer**: Generates clean I/Q signals for transmission testing:
  - **Continuous Wave (CW)** carrier tone
  - **Two-Tone IMD Test** for amplifier linearity testing
  - **FM Modulated Tone / Siren**
  - **Frequency Chirp (FMCW Sweep)**
  - **ASK / OOK Custom Pulse Burst**
- **Safety Safeguards**:
  - Hardware interlock: "Arm Transmitter" confirmation checkbox
  - Configurable auto-stop countdown timers (3s, 5s, 10s, 30s)
  - Abort transmission button

### 6. 💾 Raw I/Q Recorder & Player
- **Record**: Captures live RF I/Q directly to disk:
  - Native HackRF format (`.c8` 8-bit signed interleaved)
  - GNU Radio float format (`.cf32` complex float 32)
  - Standard 16-bit PCM WAV (Left = I, Right = Q)
  - JSON metadata sidecar (`.json`) preserving frequency, sample rate, and timestamps.
- **Replay**: Play back captured RF files in a seamless loop with full spectrum and demodulator operation.

### 7. 🧪 Built-in RF Physics Simulator
- Allows developers and users to explore, test, and demonstrate all features **without needing physical hardware plugged in**.
- Generates realistic thermal noise floor, simulated FM broadcast stations with audio, aviation AM carriers, and intermittent 433.92 MHz keyfob bursts!

---

## 🛠️ Hardware Requirements & Windows Driver Setup

### Physical HackRF One Setup (Windows):
1. Plug your **HackRF One** into a USB 2.0 or 3.0 port.
2. If Windows has not installed the WinUSB driver:
   - Download and run [Zadig](https://zadig.akeo.ie/).
   - Click **Options -> List All Devices**.
   - Select **HackRF One** from the dropdown.
   - Choose **WinUSB** as the driver on the right side and click **Install Driver** (or **Replace Driver**).
3. Place `hackrf.dll` and `libusb-1.0.dll` in the project `bin/` directory or ensure they are accessible on your system `PATH`.
4. Launch HackRF Studio and select **Hardware USB (HackRF One)** in the RF Source dropdown!

---

## 🚀 Quickstart & Usage

### 1. Installation
Ensure Python 3.10+ is installed, then install requirements:
```powershell
pip install -r requirements.txt
```

### 2. Launching HackRF Studio
Start the graphical workstation:
```powershell
python run_studio.py
```

### 3. Command-Line Options
```powershell
# Launch directly tuned to 433.92 MHz with 4 MSPS sample rate:
python run_studio.py --freq 433.92 --rate 4.0

# Launch in physical hardware mode:
python run_studio.py --hardware

# Run headless self-test:
python run_studio.py --headless-test
```

### 4. Running the Test Suite
HackRF Studio includes automated unit and integration tests:
```powershell
python -m unittest discover tests
```

---

## 📂 Project Architecture

```
HackRFStudio/
├── hackrf/
│   ├── driver.py            # ctypes wrapper for libhackrf / hackrf.dll
│   ├── device.py            # Hardware Abstraction Layer (HAL)
│   ├── simulator.py         # Realistic RF spectrum physics generator
│   └── sweep_scanner.py     # Fast wideband sweep controller (1 MHz - 6 GHz)
├── dsp/
│   ├── fft_processor.py     # High-speed FFT, windowing, averaging & peak hold
│   ├── filter.py            # Decimation, Butterworth LPF, FM deemphasis, DC blocker
│   ├── demodulator.py       # AM, WFM, NFM, USB, LSB, CW demodulators + Squelch & AGC
│   ├── protocol_decoder.py  # 433 MHz / 315 MHz ASK/OOK pulse analyzer & bit slicer
│   └── signal_gen.py        # Signal synthesizer for TX (CW, two-tone, chirp, FM, OOK)
├── audio/
│   └── output.py            # Sounddevice audio streaming engine with jitter buffering
├── recording/
│   └── iq_file.py           # Capture & replay raw I/Q (.c8, .cf32, .wav + JSON metadata)
├── ui/
│   ├── main_window.py       # Main Qt layout & background worker orchestrator
│   ├── spectrum_widget.py   # Real-time FFT spectrum & 2D Waterfall spectrogram
│   ├── controls_widget.py   # Tuning dial, quick steps, presets, LNA/VGA gains, bias-tee
│   ├── demod_widget.py      # Mode selector, volume, squelch gate, S-meter
│   ├── constellation_widget.py # IQ constellation scatter & time-domain oscilloscope
│   ├── sweep_widget.py      # Panoramic wideband spectrum analyzer & peak detector
│   ├── pulse_widget.py      # Sub-GHz pulse analyzer & hex payload inspector
│   ├── tx_widget.py         # Signal generator & TX workbench (with safety guards)
│   └── dialogs.py           # Device info diagnostics, recording dialogs
├── assets/
│   └── style.qss            # Custom dark aerospace SDR theme
├── tests/
│   ├── test_dsp.py          # DSP, demodulator, filter unit tests
│   ├── test_simulator.py    # RF simulation tests
│   ├── test_file_io.py      # I/Q file recording & replay tests
│   ├── test_protocol.py     # Protocol decoder & signal generator tests
│   └── test_integration.py # Live end-to-end streaming integration tests
├── run_studio.py            # Primary launcher CLI and GUI entry point
├── requirements.txt         # Dependencies
└── README.md                # Documentation
```

---

## 🛡️ HackRF One Hardware Specifications Supported
- **Operating Frequency**: 1 MHz to 6 GHz (continuous)
- **Sample Rate**: 2 MSPS to 20 MSPS
- **Resolution**: 8-bit quadrature (I/Q)
- **LNA Gain**: 0 to 40 dB (in 8 dB steps)
- **VGA Gain (RX)**: 0 to 62 dB (in 2 dB steps)
- **TX VGA Gain**: 0 to 47 dB (in 1 dB steps)
- **RF Preamp**: +14 dB front-end MMIC amplifier
- **Antenna Bias-Tee**: 3.3V DC power (up to 50 mA) for active antennas / LNAs
- **Transceiver Modes**: Half-duplex Transmit (TX) and Receive (RX)
