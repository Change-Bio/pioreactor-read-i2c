# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name="pioreactor_i2c_to_voltage",
    version="0.1.0",
    license_files = ('LICENSE.txt',),
    description="This plugin reads voltages from ADS1015 I2C ADC and exports them to MQTT for access by other jobs.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author_email="noahsprent@gmail.com",
    author="Noah Sprent",
    url="https://github.com/noahsprent/pioreactor-i2c-to-voltage",
    packages=find_packages(),
    include_package_data=True,
    install_requires=["smbus2"],
    entry_points={
        "pioreactor.plugins": "pioreactor_i2c_to_voltage = pioreactor_i2c_to_voltage"
    },
)
