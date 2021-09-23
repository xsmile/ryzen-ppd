"""Controls power management functions on AMD Ryzen processors."""

import logging
import math
from ctypes import c_float, c_int, c_ulong, c_void_p, cdll
from typing import Any, Optional

from ryzen_ppd.utils import critical

logger = logging.getLogger(__name__)

error_messages = {
    -1: '{:s} is not supported on this family',
    -3: '{:s} is not supported on this SMU',
    -4: '{:s} is rejected by SMU'
}


class RyzenAdj:
    """Povides methods to get and set power and thermal limits."""

    def __init__(self) -> None:
        self.lib = cdll.LoadLibrary('libryzenadj.so')

        # Define ctype mappings for types which can not be mapped automatically
        self.lib.init_ryzenadj.argtypes = []
        self.lib.init_ryzenadj.restype = c_void_p
        self.lib.cleanup_ryzenadj.argtypes = [c_void_p]
        self.lib.cleanup_ryzenadj.restypes = c_void_p
        self.lib.refresh_table.argtypes = [c_void_p]
        self.lib.refresh_table.restypes = c_int

        self.ry = self.lib.init_ryzenadj()
        if not self.ry:
            critical('could not initialize RyzenAdj')

    def stop(self) -> None:
        """Stops RyzenAdj."""
        self.lib.cleanup_ryzenadj(self.ry)

    def refresh(self) -> None:
        """Gets the currently used power management settings."""
        self.lib.refresh_table(self.ry)

    def get(self, field: str, precision: Optional[int] = 3) -> Any:
        """
        Gets a value by calling the given function.
        :param field: Field name as used by the `get_` functions in `lib/ryzenadj.h`
        :param precision: Rounding precision
        :return: Value on success, else None
        """
        fun_name = 'get_' + field
        fun = self.lib.__getattr__(fun_name)
        fun.argtypes = [c_void_p]
        fun.restype = c_float
        res = fun(self.ry)
        if math.isnan(res):
            error = error_messages.get(res, '{:s} failed with {:f}')
            logger.error(error.format(fun_name, res))
            return None
        return round(res, precision)

    def set(self, field: str, value: Optional[float] = None) -> bool:
        """
        Sets a value by calling the given function with an optional argument.
        :param field: Field name as used by the `set_` functions in `lib/ryzenadj.h`
        :param value: Value to be set
        :return: True on success, else False
        """
        fun_name = 'set_' + field
        fun = self.lib.__getattr__(fun_name)
        if value:
            fun.argtypes = [c_void_p, c_ulong]
            res = fun(self.ry, value)
        else:
            fun.argtypes = [c_void_p]
            res = fun(self.ry)
        if res:
            error = error_messages.get(res, '{:s} failed with {:f}')
            logger.error(error.format(fun_name, res))
            return False
        return True
