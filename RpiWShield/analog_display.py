#!/usr/bin/env python3
"""
Analog Signal Sampler + FFT Display
====================================
Hardware: Raspberry Pi 3 Model B + DFRobot Arduino Expansion Shield v2.0 (DFR0327)
ADC:      ADS1115 via I2C (default address 0x48), channel A0

Usage:
    python3 analog_display.py [--channel 0-3] [--rate HZ] [--buffer 512|1024|2048]

If ADS1115 hardware is not found, runs in simulation mode with a synthetic signal.
"""

import argparse
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque

# ── Hardware setup ────────────────────────────────────────────────────────────

def init_adc(channel: int):
    """Try to initialise ADS1115 on I2C. Returns (adc_read_fn, vref) or None."""
    try:
        import board
        import busio
        import adafruit_ads1x15.ads1115 as ADS
        from adafruit_ads1x15.analog_in import AnalogIn
        from adafruit_ads1x15.ads1x15 import Mode

        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c)
        ads.mode = Mode.CONTINUOUS          # fastest continuous conversion
        ads.gain = 1                        # ±4.096 V range
        ads.data_rate = 860                 # max SPS for ADS1115

        ch_map = {0: ADS.P0, 1: ADS.P1, 2: ADS.P2, 3: ADS.P3}
        chan = AnalogIn(ads, ch_map[channel])

        print(f"[HW] ADS1115 found on I2C. Channel A{channel}, gain=1 (±4.096 V).")

        def read():
            return chan.voltage   # returns float in volts

        return read, 4.096

    except Exception as e:
        print(f"[SIM] ADS1115 not available ({e}). Running in simulation mode.")
        return None, None


def make_sim_signal(sample_rate: float):
    """Returns a function that simulates a noisy multi-tone signal."""
    t_state = [0.0]
    dt = 1.0 / sample_rate

    def read():
        t = t_state[0]
        t_state[0] += dt
        # 50 Hz fundamental + 3rd harmonic + noise
        v = (
            1.2 * np.sin(2 * np.pi * 50 * t)
            + 0.4 * np.sin(2 * np.pi * 150 * t + 0.3)
            + 0.15 * np.sin(2 * np.pi * 230 * t)
            + 0.08 * np.random.randn()
        )
        return float(np.clip(v, -4.096, 4.096))

    return read

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Analog sampler + FFT display")
    parser.add_argument("--channel", type=int, default=0, choices=[0, 1, 2, 3],
                        help="ADS1115 channel (0=A0 … 3=A3, default 0)")
    parser.add_argument("--rate", type=float, default=500,
                        help="Target sample rate in Hz (default 500)")
    parser.add_argument("--buffer", type=int, default=1024,
                        help="Number of samples to display/FFT (default 1024; use power of 2)")
    args = parser.parse_args()

    sample_rate = args.rate
    buf_size    = args.buffer
    dt          = 1.0 / sample_rate

    # Initialise ADC or simulation
    read_fn, vref = init_adc(args.channel)
    simulated = read_fn is None
    if simulated:
        read_fn = make_sim_signal(sample_rate)
        vref = 4.096

    # Sample buffer (deque so new samples push old ones out)
    samples = deque([0.0] * buf_size, maxlen=buf_size)
    t_axis  = np.arange(buf_size) / sample_rate          # seconds
    f_axis  = np.fft.rfftfreq(buf_size, d=1.0 / sample_rate)  # Hz

    # ── Figure layout ─────────────────────────────────────────────────────────
    fig, (ax_time, ax_fft) = plt.subplots(2, 1, figsize=(12, 7))
    fig.suptitle(
        f"{'[SIMULATION] ' if simulated else ''}Analog Channel A{args.channel}  "
        f"—  {sample_rate:.0f} Hz  /  {buf_size} samples",
        fontsize=13,
    )

    # Time domain
    ax_time.set_title("Time Domain")
    ax_time.set_xlabel("Time (s)")
    ax_time.set_ylabel("Voltage (V)")
    ax_time.set_xlim(0, buf_size / sample_rate)
    ax_time.set_ylim(-vref * 1.1, vref * 1.1)
    ax_time.axhline(0, color="grey", linewidth=0.5, linestyle="--")
    ax_time.grid(True, alpha=0.3)
    (line_time,) = ax_time.plot(t_axis, list(samples), color="deepskyblue", linewidth=0.8)

    # FFT
    ax_fft.set_title("Frequency Spectrum (FFT magnitude)")
    ax_fft.set_xlabel("Frequency (Hz)")
    ax_fft.set_ylabel("|Amplitude| (V)")
    ax_fft.set_xlim(0, sample_rate / 2)
    ax_fft.set_ylim(0, vref)
    ax_fft.grid(True, alpha=0.3)
    (line_fft,) = ax_fft.plot(f_axis, np.zeros_like(f_axis), color="orangered", linewidth=0.9)

    # Info text: peak frequency
    info_text = ax_fft.text(
        0.98, 0.95, "", transform=ax_fft.transAxes,
        ha="right", va="top", fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7),
    )

    fig.tight_layout()

    # ── Sampling state ────────────────────────────────────────────────────────
    next_sample_time = [time.perf_counter()]

    def collect_samples():
        """Grab as many samples as are due since the last animation frame."""
        now = time.perf_counter()
        while next_sample_time[0] <= now:
            samples.append(read_fn())
            next_sample_time[0] += dt

    # ── Animation callback ────────────────────────────────────────────────────
    def update(_frame):
        collect_samples()

        data = np.array(samples)

        # Time domain
        line_time.set_ydata(data)

        # FFT — apply Hann window to reduce spectral leakage
        window   = np.hanning(buf_size)
        spectrum = np.abs(np.fft.rfft(data * window)) * 2 / buf_size
        line_fft.set_ydata(spectrum)

        # Peak frequency annotation
        peak_idx  = np.argmax(spectrum[1:]) + 1   # skip DC
        peak_freq = f_axis[peak_idx]
        peak_amp  = spectrum[peak_idx]
        info_text.set_text(f"Peak: {peak_freq:.1f} Hz  ({peak_amp:.4f} V)")

        return line_time, line_fft, info_text

    ani = animation.FuncAnimation(
        fig, update,
        interval=50,          # ms between frames → ~20 fps
        blit=True,
        cache_frame_data=False,
    )

    plt.show()


if __name__ == "__main__":
    main()
