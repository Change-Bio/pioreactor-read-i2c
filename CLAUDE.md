# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Pioreactor plugin that reads voltage data from an ADS1015 I2C analog-to-digital converter and publishes voltage values to MQTT topics. It enables the Pioreactor to read analog sensor data through the 4-channel 12-bit ADC.

**Key Architecture:**
- Main job class: `I2CToVoltage` (extends `LongRunningBackgroundJob` from pioreactor)
- Runs as a systemd service on boot via `pioreactor_startup_run@i2c_to_voltage.service`
- Uses `RepeatedTimer` to read all 4 ADC channels every 4+ seconds
- Publishes voltage data to MQTT: `pioreactor/{unit}/{experiment}/i2c_to_voltage/A{0-3}`
- Hardware: ADS1015 12-bit ADC on I2C bus (default address 0x48)

## Development Commands

### Installation
```bash
# Install in development mode
pip install -e .

# Install Pioreactor framework (for development)
pip install git+https://github.com/pioreactor/pioreactor.git#egg=pioreactor[worker]

# Install required dependencies
pip install smbus2

# Install test dependencies
pip install pytest fake-rpi crudini
```

### Building and Distribution
```bash
# Build distribution packages
python setup.py sdist bdist_wheel

# The build/ and dist/ directories contain build artifacts
```

### Code Quality
```bash
# Run pre-commit hooks manually
pre-commit run --all-files

# Install pre-commit hooks
pre-commit install
```

Pre-commit runs:
- Black formatter (line length: 100)
- Flake8 linter (max line length: 90, ignores E203,E266,E501,W503,E402,E401)
- mypy type checking
- Various file checks (trailing whitespace, EOF, YAML syntax, etc.)

### Testing
The CI workflow shows the test setup pattern:
```bash
# Create test environment
mkdir -p .pioreactor/storage
wget https://raw.githubusercontent.com/Pioreactor/pioreactor/master/config.dev.ini
crudini --merge config.dev.ini < pioreactor_i2c_to_voltage/additional_config.ini

# Run tests (requires Mosquitto MQTT broker running)
TESTING=1 TMPDIR=/tmp/ pytest
```

Note: The CI workflow references outdated test paths (`pioreactor_relay_plugin/test_relay.py`) - actual tests would be in `pioreactor_i2c_to_voltage/`.

### Running the Plugin
```bash
# Command line
pio run i2c_to_voltage

# Check systemd service status
systemctl status pioreactor_startup_run@i2c_to_voltage.service
```

## Configuration

The plugin adds configuration to Pioreactor's `config.ini`:

```ini
[i2c_to_voltage.config]
i2c_bus=1
i2c_addr=0x48
gain_bits=0
```

These are settable at runtime via MQTT or the UI.

**Configuration Details:**
- `i2c_bus`: I2C bus number (typically 1 on Raspberry Pi)
- `i2c_addr`: Hex address of ADS1015 (0x48 default, can be 0x49-0x4B depending on ADDR pin)
- `gain_bits`: PGA gain setting (0-5) controlling voltage range:
  - 0: ±6.144V (safe for 0-5V sensors)
  - 1: ±4.096V
  - 2: ±2.048V
  - 3: ±1.024V
  - 4: ±0.512V
  - 5: ±0.256V

## Plugin Structure

```
pioreactor_i2c_to_voltage/
├── __init__.py                    # Exports click_i2c_to_voltage
├── i2c_to_voltage.py              # Main job implementation
├── ui/contrib/jobs/
│   └── i2c_to_voltage.yaml        # UI configuration
├── additional_config.ini          # Default config values
├── post_install.sh                # Enables systemd service
└── pre_uninstall.sh               # Disables systemd service
```

## ADS1015 ADC Details

The plugin reads from an ADS1015 12-bit ADC via I2C:
- 4 single-ended channels (A0-A3)
- Configurable gain/voltage range via PGA settings
- Single-shot conversion mode at 1600 SPS
- Each channel is read sequentially every 4+ seconds
- Voltage values are published to individual MQTT topics per channel

## Pioreactor Plugin Conventions

- Plugin metadata: `__plugin_summary__`, `__plugin_version__`, `__plugin_name__`, `__plugin_author__`, `__plugin_homepage__`
- Entry point: `pioreactor.plugins` in setup.py
- Jobs extend `LongRunningBackgroundJob` with `job_name` and `published_settings`
- UI YAML files define how settings appear in the web interface
- Installation scripts use `systemctl` to manage services
