# -*- coding: utf-8 -*-
from time import sleep
import click
from pioreactor.whoami import get_unit_name, get_assigned_experiment_name
from pioreactor.background_jobs.base import BackgroundJob
import serial
import json
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.background_jobs.leader.mqtt_to_db_streaming import produce_metadata
from pioreactor.background_jobs.leader.mqtt_to_db_streaming import register_source_to_sink
from pioreactor.background_jobs.leader.mqtt_to_db_streaming import TopicToParserToTable
from pioreactor.utils import timing

__plugin_summary__ = "Reads pH from Vernier FPH-BTA probe"
__plugin_version__ = "0.0.2"
__plugin_name__ = "Vernier FPH-BTA"
__plugin_author__ = "Noah Sprent"
__plugin_homepage__ = "https://github.com/noahsprent/vernier-FPH-BTA"

# Serial port settings
serial_port = '/dev/ttyACM0'
baud_rate = 9600


def __dir__():
    return ['click_read_ph']


def parser(topic, payload) -> dict:
    metadata = produce_metadata(topic)
    return {
        "experiment": metadata.experiment,
        "pioreactor_unit": metadata.pioreactor_unit,
        "timestamp": timing.current_utc_timestamp(),
        "ph_reading": float(payload),
    }


register_source_to_sink(
    TopicToParserToTable(
        ["pioreactor/+/+/vernier_fph_bta/ph_reading"],
        parser,
        "ph_readings",
    )
)

class ReadPh(BackgroundJob):

    job_name="vernier_fph_bta"
    published_settings = {
        "ph_reading": {"datatype": "float", "settable": False},
        "pin": {"datatype": "string", "settable": True},
        "slope": {"datatype": "float", "settable": True},
        "intercept": {"datatype": "float", "settable": True},
    }

    def __init__(self, unit, experiment, **kwargs):
        super().__init__(unit=unit, experiment=experiment)
        time_between_readings = 4 
        assert time_between_readings >= 2.0

        self.pin = "A2"
        self.slope = -7.78
        self.intercept = 16.34
        
        self.timer_thread = RepeatedTimer(time_between_readings, self.read_pH, job_name=self.job_name, run_immediately=True).start()

    def on_ready(self):
        self.logger.debug(f"Listening on {serial_port}...")

    def on_disconnected(self):
        self.logger.debug(f"Disconnecting from {serial_port}")

    def read_pH(self):
        with serial.Serial(serial_port, baud_rate, timeout=1) as ser:
            buffer = ''
            while True:
                line = ser.readline().decode('utf-8').strip()
                try:
                    data = json.loads(line)
                    samples = 2
                    running_sum = 0.0
                    for _ in range(samples):
                        running_sum += data[self.pin]
                        sleep(0.05)
                        current_timeout = 1.5
                        sleep(current_timeout)
                    self.ph_reading = (running_sum/samples)*self.slope + self.intercept
                    return self.ph_reading
                except json.JSONDecodeError:
                    sleep(1)

@click.command(name="vernier_fph_bta", help=__plugin_summary__)
def click_read_ph():

    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)
    job = ReadPh(
        unit=unit,
        experiment=experiment,
        )
    job.block_until_disconnected()
