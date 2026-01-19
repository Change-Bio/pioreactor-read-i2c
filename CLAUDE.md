# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Pioreactor plugin that reads voltage data from one or more ADS1015 I2C analog-to-digital converters and publishes voltage values to MQTT topics. It enables the Pioreactor to read analog sensor data through multiple 4-channel 12-bit ADCs.

**Key Architecture:**
- Main job class: `I2CToVoltage` (extends `LongRunningBackgroundJob` from pioreactor)
- Runs as a systemd service on boot via `pioreactor_startup_run@i2c_to_voltage.service`
- Uses `RepeatedTimer` to sample all 4 ADC channels from all configured addresses at high frequency (default 200Hz)
- Publishes filtered voltage data to MQTT at lower frequency (default 1Hz)
- Publishes voltage data to MQTT: `pioreactor/{unit}/{experiment}/pioreactor_read_serial/0x{addr}_A{0-3}`
- Hardware: One or more ADS1015 12-bit ADCs on I2C bus (default addresses 0x48, 0x4A)

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
i2c_addr=0x48,0x4A
gain_bits=0
sampling_rate=200
publish_rate=1.0
moving_avg_window=20
enable_filtering=true
diagnostic_duration=10
```

These are settable at runtime via MQTT or the UI.

**Configuration Details:**
- `i2c_bus`: I2C bus number (typically 1 on Raspberry Pi)
- `i2c_addr`: Comma-separated list of hex addresses of ADS1015 ADCs (e.g., 0x48,0x4A; can be 0x48-0x4B depending on ADDR pin wiring)
- `gain_bits`: PGA gain setting (0-5) controlling voltage range:
  - 0: ±6.144V (safe for 0-5V sensors)
  - 1: ±4.096V
  - 2: ±2.048V
  - 3: ±1.024V
  - 4: ±0.512V
  - 5: ±0.256V
- `sampling_rate`: High-frequency ADC sampling rate in Hz (default 200)
- `publish_rate`: Low-frequency MQTT publish rate in Hz (default 1.0)
- `moving_avg_window`: Number of samples to average for noise filtering (default 20)
- `enable_filtering`: Enable/disable moving average filter (default true)
- `diagnostic_duration`: Duration in seconds for FFT-based noise diagnostics (default 10)

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

The plugin reads from one or more ADS1015 12-bit ADCs via I2C:
- 4 single-ended channels per ADC (A0-A3)
- Configurable gain/voltage range via PGA settings
- Single-shot conversion mode at 1600 SPS
- High-frequency sampling (default 200Hz) with moving average filtering
- Low-frequency publishing (default 1Hz) to reduce MQTT traffic
- Voltage values are published to individual MQTT topics per ADC address and channel
- Topic format: `pioreactor/{unit}/{experiment}/pioreactor_read_serial/0x{addr}_A{channel}`
- FFT-based noise diagnostics available for identifying interference sources

## Pioreactor Plugin Conventions

- Plugin metadata: `__plugin_summary__`, `__plugin_version__`, `__plugin_name__`, `__plugin_author__`, `__plugin_homepage__`
- Entry point: `pioreactor.plugins` in setup.py
- Jobs extend `LongRunningBackgroundJob` with `job_name` and `published_settings`
- UI YAML files define how settings appear in the web interface
- Installation scripts use `systemctl` to manage services
