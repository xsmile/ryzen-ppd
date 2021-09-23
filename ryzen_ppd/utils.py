"""Utility functions."""

import glob
import logging
import os
import sys

logger = logging.getLogger(__name__)


def critical(msg: str, force_exit: bool = False) -> None:
    """
    Prints a critical error message and exits the application.
    :param msg: Error message
    :param force_exit: Exit the application without calling cleanup handlers
    """
    logger.critical(msg)
    if force_exit:
        os._exit(1)
    sys.exit(1)


def check_root() -> None:
    """Verifies root privileges."""
    if os.geteuid() != 0:
        critical('root privileges required')


def check_acpi_call_module() -> None:
    """Verifies the presence of the `acpi_call` kernel module."""
    if not os.path.exists('/proc/acpi/call'):
        critical('kernel module acpi_call is not loaded')


def is_on_ac() -> bool:
    """
    Checks if the system is using AC as the power source.
    :return: True if on AC
    """
    paths = glob.glob('/sys/class/power_supply/AC*/online')
    for path in paths:
        with open(path, encoding='utf_8') as f:
            return int(f.read()) == 1
    # Otherwise assume AC
    return True
