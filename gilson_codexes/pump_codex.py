# GX Syringe Pump (Version 1.0.6.9)

from typing import Literal
from enum import StrEnum
from gilson_codexes.command_abc import Immediate, Buffered
from misc_func import Number


class ValveStates(StrEnum):
    """ Needle (N) or Reservoir (R) """
    needle = "N"
    reservoir = "R"


VALVE_STATE = Literal[ValveStates.needle, ValveStates.reservoir]
""" Needle or Reservoir (For type hinting) """


class GetModuleID(Immediate):
    """ Pulls for the pump firmware version (%) """
    cmd_str = "%"
    rsp_fmt = "'GX Syringe Pump va.b.c.d' where a, b, c, and d represent the firmware version"


class Reset(Immediate):
    """ Resets pump ($) """
    cmd_str = "$"
    rsp_fmt = "echo"


class ReadError(Immediate):
    """ Pulls for the current error (e) """
    cmd_str = "e"
    rsp_fmt = "'n' where n is an error number"


class ClearError(Buffered):
    """ Removes error state (e) """
    cmd_str = "e"


class RaiseError(Buffered):
    """ Manually sets the error state (en) """
    cmd_str = "en"

    def __init__(self, err_no: int):
        self.n = err_no

    @property
    def cmd_str(self):  # noqa
        return f"e{self.n}"


class GetSyringeSize(Immediate):
    """ Pulls for the syringe size and flow rate (F) """
    cmd_str = "F"
    rsp_fmt = "'syringe size[ul] min-max (default)[mL/min]'"


class SetSyringeSize(Buffered):
    cmd_str = "@4=v"

    def __init__(self, volume: Literal[100, 250, 500, 1000, 5000, 10000]):
        """ :param volume: Syringe volume in uL """
        self.v = volume
        assert self.v in [100, 250, 500, 1000, 5000, 10000], "Syringe volume must be a valid volume"

    @property
    def cmd_str(self):  # noqa
        return f"@4={self.v}"


class GetMotorStatus(Immediate):
    """ Pulls the valve and syringe motor status (M) """
    cmd_str = "M"
    rsp_fmt = ("'ab' where a is the valve motor status and b is the syringe motor status.  "
               "Each is E (error), R (running), U (unpowered), or P (parked)")


class RunPump(Buffered):
    """ Executes the pump (Pn:v.vvv:s) """
    cmd_str = "Pn:v.vvv:s"

    def __init__(self, valve_position: VALVE_STATE, volume: Number, flow_rate: Number = None):
        """
        :param valve_position: If the pump should draw from the reservoir (R) or needle (N)
        :param volume: The volume to be aspirated (+) or dispensed (-) in uL
        :param flow_rate: (Optional) Using the given flow rate in uL
          per minute (0.1 is a good value for a 100 uL syringe)
        """
        self.valve: str = valve_position
        self.vol = f":{volume:.3f}".rstrip("0").rstrip(".")
        # TODO:
        #   "Pn:v.vvv:s" Does it really have nano-liter precision !?
        #   Or is that the British notation, and it's "n,nnn" in US notation?
        self.rate = "" if flow_rate is None else f":{flow_rate:.2f}".rstrip("0").rstrip(".")
        if self.valve == ValveStates.reservoir:
            assert volume > 0, "Cannot dispense to reservoir"

    @property
    def cmd_str(self):  # noqa
        return f"P{self.valve}{self.vol}{self.rate}"


class GetSyringeStatus(Immediate):
    """ Pulls for the valve position and current volume pulled (P) """
    cmd_str = "P"
    rsp_fmt = ("'n:v.vvv' where n is the valve position (R for reservoir/N for needle) "
               "and v.vvv current volume in uL in syringe (can be '?' if unknown, e.g. not homed")


class PumpStop(Buffered):
    """ Stops the pump (PX) """
    cmd_str = "PX"


class HomePump(Buffered):
    """ Homes the pump syringe """
    cmd_str = "p"


GX_PUMP_ERROR_CODES = {
    0: "No Error",
    10: "Unknown buffered command", 11: "Invalid NV-RAM address", 12: "Safety stop activated",
    16: "character limit",
    20: "Pump command while not homed", 22: "Pump command while busy",
    24: "invalid Syringe position", 26: "Invalid syringe volume",
    28: "Invalid flow rate", 30: "Invalid syringe size",
    32: "Invalid valve position", 34: "Missing valve encoder",
    88: "Error unknown"
}
