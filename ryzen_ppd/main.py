"""Periodically applies power profiles and handles several D-Bus signals."""

import argparse
import configparser
import json
import logging
import threading
from typing import Any, Callable, Dict, List

from dbus_next import BusType
from dbus_next.glib import MessageBus
from gi.repository import GLib

import ryzen_ppd
from ryzen_ppd.cpu import RyzenAdj
from ryzen_ppd.utils import check_acpi_call_module, check_root, critical, is_on_ac

LOGGING_FORMAT = '[%(levelname)s] %(message)s'
logger = logging.getLogger(__name__)
cfg = {}


def parse_args() -> argparse.Namespace:
    """
    Parses command line arguments.
    :return: Namespace of the argument parser
    """
    parser = argparse.ArgumentParser(description=ryzen_ppd.__description__)
    parser.add_argument('-c', '--config', help='configuration file path', default='/etc/ryzen-ppd.ini')
    parser.add_argument('-v', '--verbose', help='increase output verbosity',
                        action='store_const', dest='loglevel', const=logging.DEBUG, default=logging.INFO)
    parser.add_argument('--version', action='version', version=f'{parser.prog:s} {ryzen_ppd.__version__:s}')
    result = parser.parse_args()

    return result


def get_power_profile(name: str) -> List[int]:
    """
    Gets the power and thermal limits depending on the given profile name.
    :param name: Name of the power profile
    :return: List of power and thermal limits on success
    """
    return cfg['profiles'][name]


def parse_config(cfgfile: str) -> Dict[str, Any]:
    """
    Parses the configuration file and does basic sanity checks.
    :param cfgfile: Path of the configuration file
    :return: Configuration
    """
    parser = configparser.ConfigParser()
    try:
        parser.read(cfgfile)
    except configparser.MissingSectionHeaderError:
        critical(f'invalid configuration file: {cfgfile:s}')
    result = {}

    # RyzenAdj settings
    section = 'ryzenadj'
    result.update({section: {
        'limits': json.loads(parser.get(section, 'limits', fallback='[]')),
        'monitor': parser.get(section, 'monitor', fallback='stapm_limit')
    }})
    if result[section]['monitor'] not in result[section]['limits']:
        critical(f'invalid monitor value: {result[section]["monitor"]}')

    # Power profiles
    section = 'profiles'
    result.update({section: {}})
    if not parser.has_section(section):
        critical(f'missing configuration section: {section:s}')
    for profile, limits in parser[section].items():
        limits = json.loads(limits)
        if len(limits) != len(result['ryzenadj']['limits']):
            critical('invalid limit configuration')
        for limit in limits:
            if not isinstance(limit, int):
                critical(f'invalid limit {limit:s}')
        result[section].update({
            profile: limits
        })

    # DYTC settings
    section = 'dytc'
    result.update({section: {
        'method': parser.get(section, 'method', fallback=None),
        'low-power': int(parser.get(section, 'low-power', fallback='0x13b001'), 16),
        'balanced': int(parser.get(section, 'balanced', fallback='0x1fb001'), 16),
        'performance': int(parser.get(section, 'performance', fallback='0x12b001'), 16)
    }})
    if result['dytc']['method'] is not None:
        check_acpi_call_module()

    # AC settings
    section = 'ac'
    result.update({section: {
        'profile': parser.get(section, 'profile', fallback='balanced'),
        'update_rate_s': parser.getfloat(section, 'update_rate_s', fallback=4),
        'platform_profile': parser.get(section, 'platform_profile', fallback='balanced')
    }})

    # Battery settings
    section = 'battery'
    result.update({section: {
        'profile': parser.get(section, 'profile', fallback='low-power'),
        'update_rate_s': parser.getfloat(section, 'update_rate_s', fallback=32),
        'platform_profile': parser.get(section, 'platform_profile', fallback='low-power')
    }})

    # Check for non-existing profiles
    for power_source in ['ac', 'battery']:
        power_profile_name = result[power_source]['profile']
        platform_profile_name = result[power_source]['platform_profile']
        if power_profile_name not in result['profiles']:
            critical(f'undefined power profile: {power_profile_name:s}')
        if platform_profile_name not in result['dytc']:
            critical(f'undefined platform profile: {power_profile_name:s}')

    return result


def get_dytc_cmd(name: str) -> int:
    """
    Gets the DYTC command depending on the given platform profile name.
    :param name: Name of the platform profile
    :return: DYTC command on success, else None
    """
    return cfg['dytc'][name]


def write_power_profile(cpu: RyzenAdj, profile: List[int]) -> None:
    """
    Writes the given power profile by using the RyzenAdj library.
    :param cpu: RyzenAdj instance
    :param profile: List of power and thermal limits
    """
    # Minimize interaction with RyzenAdj by checking the monitored value first
    cpu.refresh()
    limit_name = cfg['ryzenadj']['monitor']
    limit_idx = cfg['ryzenadj']['limits'].index(limit_name)
    cur_limit = cpu.get(limit_name)
    # RyzenAdj uses inconsistent formats for various functions. This will only work with power limits.
    target_limit = profile[limit_idx] / 1000
    if cur_limit == target_limit:
        logger.debug(f'monitored {limit_name} has not changed')
        return

    logger.debug(f'monitored {limit_name} has changed: {target_limit} != {cur_limit}')
    for i, limit in enumerate(cfg['ryzenadj']['limits']):
        logger.debug(f'{limit:s}: {profile[i]:d}')
        cpu.set(limit, profile[i])


def write_platform_profile(cmd: int) -> None:
    """
    Writes the given platform profile by calling the DYTC method via the `acpi_call` kernel module.
    Enabled only if the DYTC method is set.
    :param cmd: DYTC command
    """
    if not cfg['dytc']['method']:
        return

    call = f'{cfg["dytc"]["method"]:s} {cmd:#x}'
    logger.debug(f'acpi_call: {call:s}')
    try:
        with open('/proc/acpi/call', 'r+', encoding='utf_8') as f:
            f.write(call)
            ret = f.read()
    except FileNotFoundError:
        logger.error('kernel module acpi_call is unloaded')
        return
    if ret.startswith('Error'):
        logger.error('could not write platform profile')


def print_settings(power_source: str) -> None:
    """
    Prints the current power profile settings.
    :param power_source: Current power source
    """
    logger.debug(
        f'power_source: {power_source:s}, '
        f'profile: {cfg[power_source]["profile"]:s}, '
        f'update_rate_s: {cfg[power_source]["update_rate_s"]:.2f}, '
        f'platform_profile: {cfg[power_source]["platform_profile"]:s}'
    )


def dbus_subscribe(ac_func: Callable, sleep_func: Callable) -> MessageBus:
    """
    Uses D-Bus to subscribe to power source and sleep signals.
    :param ac_func: Function to process power source events
    :param sleep_func: Function to process sleep events
    :return: D-Bus message bus
    """
    bus = MessageBus(bus_type=BusType.SYSTEM).connect_sync()

    # get all line power device objects on the UPower bus
    # examples: line_power_AC, line_power_ADP1
    introspection = bus.introspect_sync('org.freedesktop.UPower', '/org/freedesktop/UPower/devices')
    obj = bus.get_proxy_object('org.freedesktop.UPower', '/org/freedesktop/UPower/devices', introspection)
    devices = [d for d in obj.child_paths if 'line_power' in d]
    # subscribe to property changes on each line power device
    for device in devices:
        introspection = bus.introspect_sync('org.freedesktop.UPower', device)
        obj = bus.get_proxy_object('org.freedesktop.UPower', device, introspection)
        properties = obj.get_interface('org.freedesktop.DBus.Properties')
        properties.on_properties_changed(ac_func)

    introspection = bus.introspect_sync('org.freedesktop.login1', '/org/freedesktop/login1')
    obj = bus.get_proxy_object('org.freedesktop.login1', '/org/freedesktop/login1', introspection)
    properties = obj.get_interface('org.freedesktop.login1.Manager')
    properties.on_prepare_for_sleep(sleep_func)

    return bus


class Daemon(threading.Thread):
    """Continuously applies power and platform profiles and handles D-Bus signal callbacks."""

    def __init__(self, cpu: ryzen_ppd.cpu.RyzenAdj):
        threading.Thread.__init__(self)
        self.exit_event = threading.Event()
        self.change_event = threading.Event()
        self.power_source = 'ac' if is_on_ac() else 'battery'
        self.cpu = cpu
        print_settings(self.power_source)

    def run(self) -> None:
        write_platform_profile(get_dytc_cmd(cfg[self.power_source]['platform_profile']))

        while not self.exit_event.is_set():
            while not self.change_event.is_set():
                write_power_profile(self.cpu, get_power_profile(cfg[self.power_source]['profile']))
                self.change_event.wait(cfg[self.power_source]['update_rate_s'])

    def stop(self) -> None:
        """Sets events to stop the thread."""
        self.change_event.set()
        self.exit_event.set()

    def notify_change(self) -> None:
        """Sets an event to instantly reapply a power profile."""
        self.change_event.set()
        self.change_event.clear()

    def ac_callback(self, interface_name: str, changed_properties: Dict, invalidated_properties: List) -> None:
        """
        Handles power source events.
        :param interface_name: Name of the interface
        :param changed_properties: Properties that have changed
        :param invalidated_properties: Properties that are now invalid
        """
        try:
            if changed_properties['Online'].value:
                self.power_source = 'ac'
            else:
                self.power_source = 'battery'
        except KeyError:
            return

        logger.debug(f'switched power source to: {self.power_source:s}')
        print_settings(self.power_source)
        write_platform_profile(get_dytc_cmd(cfg[self.power_source]['platform_profile']))
        self.notify_change()

    def sleep_callback(self, args: bool) -> None:
        """
        Handles sleep events.
        :param args: True if sleeping, else False
        """
        if args:
            return

        logger.debug('woken up from sleep')
        write_platform_profile(get_dytc_cmd(cfg[self.power_source]['platform_profile']))


def excepthook(e: threading.ExceptHookArgs) -> None:
    """Handles uncaught exceptions from the Daemon thread."""
    critical(str(e.exc_value), force_exit=True)


def main() -> None:
    """Entry point."""
    global cfg

    args = parse_args()
    logging.basicConfig(format=LOGGING_FORMAT, level=args.loglevel)
    check_root()
    cfg = parse_config(args.config)

    cpu = RyzenAdj()

    threading.excepthook = excepthook
    daemon = Daemon(cpu)
    daemon.start()

    bus = dbus_subscribe(daemon.ac_callback, daemon.sleep_callback)

    loop = GLib.MainLoop()
    try:
        loop.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.quit()
        bus.disconnect()
        daemon.stop()
        daemon.join()
        cpu.stop()


if __name__ == '__main__':
    main()
