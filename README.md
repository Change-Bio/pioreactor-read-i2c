## Pioreactor I2C to Voltage Plugin

This plugin reads voltages from an ADS1015 I2C analog-to-digital converter and exports the voltage values to MQTT so they can be accessed by different jobs. The ADS1015 provides 4 single-ended channels (A0-A3) that can measure voltages from sensors connected to the Pioreactor.

You can set this job to run automatically on starting the Raspberry Pi and then whenever you start any jobs that need voltage data it will be available.

## Hardware Setup

This plugin is designed for the ADS1015 12-bit ADC:
- Connect the ADS1015 to the Raspberry Pi I2C bus (typically bus 1)
- Default I2C address is 0x48 (can be changed via ADDR pin wiring)
- Supports full-scale voltage ranges from ±0.256V to ±6.144V via gain settings

## Installation

Install from the Pioreactor plugins web interface or the command line:

```
pio install-plugin pioreactor-i2c-to-voltage # to install directly on the Pioreactor

# OR, on the leader's command line:

pios install-plugin pioreactor-i2c-to-voltage # to install on all Pioreactors in a cluster
```

Or install through the web interface (_Plugins_ tab). This will install the plugin on all Pioreactors within the cluster.

## Usage

#### Run on startup

The script should start on boot, as it is added to systemctl by the install script.
If you don't want this to happen, and would prefer to start it manually, first disable autorunning through systemctl and then you can control using the below.

#### Through the command line:
```
pio run i2c_to_voltage
```

#### Through the UI:

Under _Manage_, there will be a new _Activities_ option called _i2c_to_voltage_.
Editable settings are:
- **I2C Bus**: The I2C bus number (typically 1 on Raspberry Pi)
- **I2C Address**: The I2C address of the ADS1015 (e.g., 0x48)
- **Gain Bits**: PGA gain setting to set voltage range:
  - 0: ±6.144V (default, safely reads 0-5V sensors)
  - 1: ±4.096V
  - 2: ±2.048V
  - 3: ±1.024V
  - 4: ±0.512V
  - 5: ±0.256V

## MQTT Topics

Voltages are published to:
```
pioreactor/{unit}/{experiment}/i2c_to_voltage/A0
pioreactor/{unit}/{experiment}/i2c_to_voltage/A1
pioreactor/{unit}/{experiment}/i2c_to_voltage/A2
pioreactor/{unit}/{experiment}/i2c_to_voltage/A3
```

## Plugin documentation

Documentation for plugins can be found on the [Pioreactor docs](https://docs.pioreactor.com/developer-guide/intro-plugins).
