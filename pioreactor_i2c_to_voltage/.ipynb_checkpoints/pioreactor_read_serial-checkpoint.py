# -*- coding: utf-8 -*-
from time import sleep
import click
from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT 
from pioreactor.background_jobs.base import LongRunningBackgroundJob
import serial
import json
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.background_jobs.leader.mqtt_to_db_streaming import produce_metadata
from pioreactor.background_jobs.leader.mqtt_to_db_streaming import register_source_to_sink
from pioreactor.background_jobs.leader.mqtt_to_db_streaming import TopicToParserToTable
from pioreactor.utils import timing

__plugin_summary__ = "Reads json from serial and exports key:value pairs to MQTT"
__plugin_version__ = "0.0.1"
__plugin_name__ = "Pioreactor Read Serial"
__plugin_author__ = "Noah Sprent"
__plugin_homepage__ = "https://github.com/noahsprent/pioreactor-read-serial"

def __dir__():
    return['click_pioreactor_read_serial']

class ReadSerial(LongRunningBackgroundJob):

    job_name="pioreactor_read_serial"
    published_settings = {
        "baud_rate": {"datatype": "int", "settable": True},
        "serial_port": {"datatype": "string", "settable": True},
    }

    def __init__(self, unit: str, experiment: str, **kwargs):
        super().__init__(unit=unit, experiment=experiment)
        time_between_readings = 4
        assert time_between_readings >= 2.0

        self.serial_port = config.get("read_serial.config", "serial_port")
        self.baud_rate = config.getfloat("read_serial.config", "baud_rate")
        
        self.timer_thread = RepeatedTimer(time_between_readings, self.read_serial, job_name=self.job_name, run_immediately=True).start()

    def on_ready(self):
        self.logger.debug(f"Listening on {self.serial_port} at {self.baud_rate} SPS...")

    def on_disconnected(self):
        self.logger.debug(f"Disconnecting from {self.serial_port}")

    def read_serial(self):
        with serial.Serial(self.serial_port, self.baud_rate, timeout=1) as ser:
            buffer = ''
            while True:
                line = ser.readline().decode('utf-8').strip()
                try:
                    data = json.loads(line)
                    for key, value in data.items():
                        self.publish(f"pioreactor/{self.unit}/experiment/{self.job_name}/{key}", value)

                except json.JSONDecodeError:
                    sleep(1)

@click.command(name="pioreactor_read_serial", help=__plugin_summary__)
def click_pioreactor_read_serial():

    unit = get_unit_name()
    experiment = UNIVERSAL_EXPERIMENT
    job = ReadSerial(
        unit=unit,
        experiment=experiment,
        )
    job.block_until_disconnected()
