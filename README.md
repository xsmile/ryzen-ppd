# Ryzen Power Profile Daemon

Power management daemon for AMD Ryzen Mobile processors.

## Description

Power management for AMD Ryzen Mobile processors in Linux is lacking in comparison to Windows. Power and thermal limits
are preset conservatively and a possibility to change them is missing which can result in a weak overall system
performance when performance is needed and in an increased power usage when mobility is required. ACPI platform profiles
are a good solution but in practice they do not always work.

Limits can be adjusted manually with tools like RyzenAdj. However, often the notebook firmware will reset them after a
short period of time, and they need to be reapplied again.

To work around this issue, this application periodically sets power and thermal limits and automatically switches
profiles when the power source changes, e.g. when switching from AC to battery. All limit settings offered by RyzenAdj
are supported.

Additionally, ACPI platform profiles can be controlled by manually writing to the DYTC method, which is useful for kernels with an outdated thinkpad_acpi module.

## Requirements

- `python3` and the `setuptools` module
- `ryzenadj` with the libryzenadj.so library for changing CPU power settings
- `dbus` for subscribing to power source and sleep signals
- `upower` for subscribing to power source and sleep signals

### Optional

- `acpi_call` kernel module for setting ACPI platform profiles

## Installation

- `python3 setup.py install --optimize=1`
- copy the configuration file to `/etc/ryzen-ppd.ini` and edit it
- set up a file from the `scripts` directory to run the application via a service manager

## Usage

See the configuration file and the output of the command `ryzen-ppd -h`.
