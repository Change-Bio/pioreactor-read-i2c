# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from typing import Tuple

import click
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
    }

    def __init__(self, unit: str, experiment: str, **kwargs):
        super().__init__(unit=unit, experiment=experiment)
        time_between_readings = 4
        assert time_between_readings >= 2.0

        self.i2c_bus = config.getint("i2c_to_voltage.config", "i2c_bus")
        self.i2c_addr = int(config.get("i2c_to_voltage.config", "i2c_addr"), 16)
        self.gain_bits = config.getint("i2c_to_voltage.config", "gain_bits")

        self.timer_thread = RepeatedTimer(
            time_between_readings,
            self.read_voltages,
            job_name=self.job_name,
            run_immediately=True,
        ).start()

    def on_ready(self):
        self.logger.debug(
            f"Reading from I2C bus {self.i2c_bus}, address 0x{self.i2c_addr:02X}, gain bits {self.gain_bits}"
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
            time.sleep(0.01)  # allow conversion (~0.6 ms needed)
            hi, lo = bus.read_i2c_block_data(self.i2c_addr, CONV, 2)

        raw16 = (hi << 8) | lo
        raw12 = raw16 >> 4  # ADS1015 packs 12-bit result left-justified
        if raw12 & 0x800:  # sign-extend
            raw12 -= 1 << 12

        fsr, lsb = PGA[self.gain_bits]
        volts = raw12 * lsb
        return raw12, volts

    def read_voltages(self):
        """Read all 4 channels and publish to MQTT."""
        try:
            for channel in range(4):
                raw, volts = self.read_single_ended(channel)
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/A{channel}",
                    volts,
                )
                self.logger.debug(f"A{channel}: raw={raw:5d} → {volts:7.4f} V")
        except Exception as e:
            self.logger.error(f"Error reading I2C: {e}")


@click.command(name="i2c_to_voltage", help=__plugin_summary__)
def click_i2c_to_voltage():

    unit = get_unit_name()
    experiment = UNIVERSAL_EXPERIMENT
    job = I2CToVoltage(
        unit=unit,
        experiment=experiment,
    )
    job.block_until_disconnected()
