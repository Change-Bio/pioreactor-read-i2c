# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from typing import Tuple

import click
import numpy as np
from pioreactor.background_jobs.base import LongRunningBackgroundJob
from pioreactor.config import config
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import UNIVERSAL_EXPERIMENT
from smbus2 import SMBus

__plugin_summary__ = "Reads voltages from ADS1015 I2C ADC and exports to MQTT"
__plugin_version__ = "0.1.0"
__plugin_name__ = "I2C to Voltage"
__plugin_author__ = "Noah Sprent"
__plugin_homepage__ = "https://github.com/noahsprent/pioreactor-i2c-to-voltage"


def __dir__():
    return ["click_i2c_to_voltage"]


# ADS1015 registers
CONV = 0x00
CONF = 0x01

# Full-scale ranges and corresponding LSB sizes (ADS1015, 12-bit effective)
# gain bits : (FSR volts, LSB volts)
PGA = {
    0b000: (6.144, 0.003),  # ±6.144 V  (2/3x gain)
    0b001: (4.096, 0.002),  # ±4.096 V
    0b010: (2.048, 0.001),  # ±2.048 V
    0b011: (1.024, 0.0005),  # ±1.024 V
    0b100: (0.512, 0.00025),  # ±0.512 V
    0b101: (0.256, 0.000125),  # ±0.256 V
}


class I2CToVoltage(LongRunningBackgroundJob):

    job_name = "i2c_to_voltage"
    published_settings = {
        "i2c_bus": {"datatype": "int", "settable": True},
        "i2c_addr": {"datatype": "string", "settable": True},
        "gain_bits": {"datatype": "int", "settable": True},
        "sampling_rate": {"datatype": "int", "settable": True},
        "publish_rate": {"datatype": "float", "settable": True},
        "moving_avg_window": {"datatype": "int", "settable": True},
        "enable_filtering": {"datatype": "boolean", "settable": True},
        "run_diagnostics": {"datatype": "boolean", "settable": True},
    }

    def __init__(self, unit: str, experiment: str, **kwargs):
        super().__init__(unit=unit, experiment=experiment)

        # Load configuration
        self.i2c_bus = config.getint("i2c_to_voltage.config", "i2c_bus")
        self.i2c_addr = int(config.get("i2c_to_voltage.config", "i2c_addr"), 16)
        self.gain_bits = config.getint("i2c_to_voltage.config", "gain_bits")
        self.sampling_rate = config.getint("i2c_to_voltage.config", "sampling_rate")
        self.publish_rate = config.getfloat("i2c_to_voltage.config", "publish_rate")
        self.moving_avg_window = config.getint("i2c_to_voltage.config", "moving_avg_window")
        self.enable_filtering = config.getboolean("i2c_to_voltage.config", "enable_filtering")
        self.diagnostic_duration = config.getint("i2c_to_voltage.config", "diagnostic_duration")

        # Initialize buffers for each channel (simple lists)
        self.channel_buffers = [[] for _ in range(4)]

        # Calculate sampling interval
        sampling_interval = 1.0 / self.sampling_rate

        # Start high-frequency sampling thread
        self.sampling_thread = RepeatedTimer(
            sampling_interval,
            self.sample_all_channels,
            job_name=self.job_name,
            run_immediately=True,
        ).start()

        # Start low-frequency publishing thread
        publishing_interval = 1.0 / self.publish_rate
        self.publish_thread = RepeatedTimer(
            publishing_interval,
            self.publish_filtered_voltages,
            job_name=self.job_name,
            run_immediately=False,  # Wait for some samples first
        ).start()

        # Run initial diagnostics on startup
        self.run_noise_diagnostics()

    def on_ready(self):
        self.logger.info(
            f"I2C to Voltage started: bus={self.i2c_bus}, addr=0x{self.i2c_addr:02X}, "
            f"gain_bits={self.gain_bits}, sampling={self.sampling_rate}Hz, "
            f"publishing={self.publish_rate}Hz, filter_window={self.moving_avg_window}"
        )

    def on_disconnected(self):
        self.logger.debug(f"Disconnecting from I2C address 0x{self.i2c_addr:02X}")

    def read_single_ended(self, channel: int) -> Tuple[int, float]:
        """Read a single-ended channel (AINx vs GND)."""
        assert 0 <= channel <= 3
        mux = {0: 0b100, 1: 0b101, 2: 0b110, 3: 0b111}[channel]

        # Build 16-bit config word:
        # OS=1 (start conversion), MUX=AINx-GND, PGA=gain_bits,
        # MODE=1 (single-shot), DR=0b100 (1600 SPS), comparator off (COMP_QUE=11)
        conf = (
            0x8000
            | (mux << 12)
            | (self.gain_bits << 9)
            | (1 << 8)
            | (0b100 << 5)
            | 0x0003
        )

        with SMBus(self.i2c_bus) as bus:
            bus.write_i2c_block_data(
                self.i2c_addr, CONF, [(conf >> 8) & 0xFF, conf & 0xFF]
            )
            time.sleep(0.001)  # allow conversion (~0.6 ms needed, reduced for faster sampling)
            hi, lo = bus.read_i2c_block_data(self.i2c_addr, CONV, 2)

        raw16 = (hi << 8) | lo
        raw12 = raw16 >> 4  # ADS1015 packs 12-bit result left-justified
        if raw12 & 0x800:  # sign-extend
            raw12 -= 1 << 12

        fsr, lsb = PGA[self.gain_bits]
        volts = raw12 * lsb
        return raw12, volts

    def sample_all_channels(self):
        """High-frequency sampling - collect samples into buffers."""
        try:
            for channel in range(4):
                raw, volts = self.read_single_ended(channel)
                self.channel_buffers[channel].append(volts)

                # Keep only the most recent samples (moving window)
                max_buffer_size = max(self.moving_avg_window * 2, 100)  # Keep some extra for diagnostics
                if len(self.channel_buffers[channel]) > max_buffer_size:
                    self.channel_buffers[channel].pop(0)

        except Exception as e:
            self.logger.error(f"Error sampling I2C: {e}")

    def publish_filtered_voltages(self):
        """Low-frequency publishing - apply filter and publish to MQTT."""
        try:
            for channel in range(4):
                if len(self.channel_buffers[channel]) == 0:
                    continue

                if self.enable_filtering and len(self.channel_buffers[channel]) >= self.moving_avg_window:
                    # Apply moving average filter on last N samples
                    window = self.channel_buffers[channel][-self.moving_avg_window:]
                    filtered_voltage = sum(window) / len(window)
                else:
                    # No filtering or not enough samples - use latest reading
                    filtered_voltage = self.channel_buffers[channel][-1]

                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/pioreactor_read_serial/A{channel}",
                    filtered_voltage,
                )
                self.logger.debug(f"A{channel}: {filtered_voltage:7.4f} V (filtered)")

        except Exception as e:
            self.logger.error(f"Error publishing voltages: {e}")

    @property
    def run_diagnostics(self) -> bool:
        """Property to trigger diagnostics via MQTT."""
        return False

    @run_diagnostics.setter
    def run_diagnostics(self, value: bool):
        """Trigger diagnostics when set to True."""
        if value:
            self.logger.info("Running noise diagnostics (triggered via MQTT)")
            self.run_noise_diagnostics()

    def run_noise_diagnostics(self):
        """Collect high-speed samples and run FFT analysis to identify noise sources."""
        try:
            self.logger.info(f"Starting noise diagnostics for {self.diagnostic_duration} seconds...")

            # Collect samples for each channel
            for channel in range(4):
                diagnostic_samples = []
                sample_interval = 1.0 / self.sampling_rate
                num_samples = int(self.diagnostic_duration * self.sampling_rate)

                # Collect samples
                for _ in range(num_samples):
                    raw, volts = self.read_single_ended(channel)
                    diagnostic_samples.append(volts)
                    time.sleep(sample_interval)

                # Convert to numpy array
                samples = np.array(diagnostic_samples)

                # Calculate statistics
                mean_voltage = np.mean(samples)
                std_voltage = np.std(samples)
                rms_noise = np.sqrt(np.mean((samples - mean_voltage) ** 2))

                # Perform FFT
                fft_result = np.fft.fft(samples - mean_voltage)  # Remove DC component
                fft_freq = np.fft.fftfreq(len(samples), d=sample_interval)

                # Only look at positive frequencies
                positive_freq_idx = fft_freq > 0
                frequencies = fft_freq[positive_freq_idx]
                magnitudes = np.abs(fft_result[positive_freq_idx]) / len(samples)

                # Find dominant frequencies (top 5 peaks)
                peak_indices = np.argsort(magnitudes)[-5:][::-1]
                dominant_frequencies = frequencies[peak_indices].tolist()
                peak_amplitudes = magnitudes[peak_indices].tolist()

                # Calculate SNR (assuming signal is DC component, noise is AC)
                signal_power = mean_voltage ** 2
                noise_power = std_voltage ** 2
                snr_db = 10 * np.log10(signal_power / noise_power) if noise_power > 0 else float('inf')

                # Prepare diagnostic results
                diagnostic_results = {
                    "channel": channel,
                    "sample_rate_hz": self.sampling_rate,
                    "duration_s": self.diagnostic_duration,
                    "num_samples": len(samples),
                    "mean_voltage_v": float(mean_voltage),
                    "std_voltage_v": float(std_voltage),
                    "rms_noise_v": float(rms_noise),
                    "snr_db": float(snr_db),
                    "dominant_frequencies_hz": [float(f) for f in dominant_frequencies],
                    "peak_amplitudes_v": [float(a) for a in peak_amplitudes],
                }

                # Publish diagnostic results to MQTT
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/i2c_to_voltage/diagnostics/channel_{channel}",
                    json.dumps(diagnostic_results),
                )

                self.logger.info(
                    f"Channel {channel} diagnostics: mean={mean_voltage:.4f}V, "
                    f"RMS noise={rms_noise:.5f}V, SNR={snr_db:.1f}dB, "
                    f"dominant freqs={[f'{f:.1f}Hz' for f in dominant_frequencies[:3]]}"
                )

            self.logger.info("Noise diagnostics completed")

        except Exception as e:
            self.logger.error(f"Error running diagnostics: {e}")


@click.command(name="i2c_to_voltage", help=__plugin_summary__)
def click_i2c_to_voltage():

    unit = get_unit_name()
    experiment = UNIVERSAL_EXPERIMENT
    job = I2CToVoltage(
        unit=unit,
        experiment=experiment,
    )
    job.block_until_disconnected()
