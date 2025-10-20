# GX-241 Liquid Handler (Version 2.0.2.5)

from typing import Literal
from gilson_codexes.command_abc import Immediate, Buffered


MOTOR_STATUS = Literal['x', '0', '1', 0, 1]
""" No change (x), Off (0), or On (1) """


class GetModuleID(Immediate):
    """ Pulls for the liquid handler firmware version (%) """
    cmd_str = "%"
    rsp_fmt = "'GX-241 II va.b.c.d' where a, b, c, and d represent the firmware version"


class Reset(Immediate):
    """ Resets liquid handler ($) """
    cmd_str = "$"
    rsp_fmt = "echo"


class GetStatusSummary(Immediate):
    """ Pulls for motor, injector, and error information (*) """
    cmd_str = "*"
    rsp_fmt = "'Motor Status, X/Y/Z positions, Valve (Load/Inject), Error Number' (eg PPPP 100/20/125 VI E0)"


class SetMotorStatus(Buffered):
    """ Selectively turns x, y, and z motors on/off (Exyz) """
    cmd_str = "Exyz"

    def __init__(self, x: MOTOR_STATUS, y: MOTOR_STATUS, z: MOTOR_STATUS):
        self.x = x
        self.y = y
        self.z = z

    @property
    def cmd_str(self):  # noqa
        return f"E{self.x}{self.y}{self.z}"


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


class HomeMotors(Buffered):
    """ Homes the liquid handler arm (H) """
    cmd_str = "H"


class GetMotorStatus(Immediate):
    """ Pulls the x, y, and z motor status (M) """
    cmd_str = "M"
    rsp_fmt = "'xyz' where each is E (error), R (running), U (unpowered), or P (parked)"


class GetLiquidLevelFrequency(Immediate):
    """ Pulls for the current LLD oscillator frequency (n) """
    cmd_str = "n"
    rsp_fmt = "Current frequency of the LLD oscillator in Hz"


class GetXYZPosition(Immediate):
    """ Pulls for the current x, y, z position in mm (P) """
    cmd_str = "P"
    rsp_fmt = "'X/Y/Z' in mm (resolved to 0.1 mm)"


class GetTravelRanges(Immediate):
    """ Pulls for the min and max coordinates for each axis (Q) """
    cmd_str = "Q"
    rsp_fmt = "'Axis=min/max' for each axis (X, Y, and Z; in order)"


class GetXYCoordinates(Immediate):
    """ Pulls for the current x, y coordinate (X) """
    cmd_str = "X"
    rsp_fmt = "'xxx.xx/yyy.yy' for the X and Y positions in mm"


class MoveXY(Buffered):
    """ Moves the arm to a given X/Y coordinate (X...) """
    cmd_str = "X[px[:sx[dx]]][/py[:sy[:dy]]]"

    def __init__(self,
                 target_x: int, target_y: int, *,
                 speed_x: int | str = None, speed_y: int | str = None,
                 drive_x: int | str = None, drive_y: int | str = None):
        """
        :param target_x: The X coordinate
        :param target_y: The Y coordinate
        :param speed_x: (Optional) X Speed in mm/sec (default is 125; maximum is 150 mm/sec)
        :param speed_y: (Optional) Y Speed in mm/sec (default is 125; maximum is 150 mm/sec)
        :param drive_x: (Optional, requires speed_x) Drive power in %(?) (default & max is 100%)
        :param drive_y: (Optional, requires speed_y) Drive power in %(?) (default & max is 100%)
        """
        self.px = target_x
        self.py = target_y
        self.sx = speed_x
        self.sy = speed_y
        self.dx = drive_x
        self.dy = drive_y
        if self.dy is not None:
            assert self.sy is not None, "Cannot specify y drive without y speed"
        if self.dx is not None:
            assert self.sx is not None, "Cannot specify x drive without x speed"

    @property
    def cmd_str(self):  # noqa
        cmd = f"X{self.px}"
        if self.sx:
            cmd += f":{self.sx}"
        if self.dx:
            cmd += f":{self.dx}"
        if self.py:
            cmd += f"/{self.py}"
        if self.sy:
            cmd += f":{self.sy}"
        if self.dy:
            cmd += f":{self.dy}"
        return cmd


class GetZCoordinate(Immediate):
    """ Pulls for the current Z coordinate (Z)"""
    cmd_str = "Z"
    rsp_fmt = "'zzz.zz' for the Z height (high-up, low-down) in mm"


class MoveZ(Buffered):
    """ Moves the arm to a given Z coordinate (Z...) """
    cmd_str = "Z[pz[:sz[:dz]]]"

    def __init__(self, target_z: int, *, speed_z: int | str = None, drive_z: int | str = None):
        """
        :param target_z: The Z coordinate
        :param speed_z: (Optional) Z Speed in mm/sec (default is 125; maximum is 150 mm/sec)
        :param drive_z: (Optional, requires speed_z) Drive power in %(?) (default & max is 100%)
        """
        self.pz = target_z
        self.sz = speed_z
        self.dz = drive_z
        if self.dz is not None:
            assert self.sz is not None, "Cannot specify z drive without z speed"

    @property
    def cmd_str(self):  # noqa
        cmd = f"Z{self.pz}"
        if self.sz:
            cmd += f":{self.sz}"
        if self.dz:
            cmd += f":{self.dz}"
        return cmd


class MoveZUntilPhaseChange(Buffered):
    """ Moves the arm to a given Z coordinate but stops if oscillator changes (z...) """
    cmd_str = "z[pz[:sz[:dz]]]"

    def __init__(self, target_z: int, *, speed_z: int | str = None, drive_z: int | str):
        """
        If liquid is encountered (on a downward movement) or air is encountered (on an upward
        movement) the movement stops immediately. After movement stops, the position at which
        liquid (or air) was found can be read using the immediate Z command. If the position is the
        same as the target specified, it may be assumed that liquid (or air) was not encountered

        :param target_z: Target Z coordinate (may halt early at phase change)
        :param speed_z: (Optional) Z Speed in mm/sec (default is 40; maximum is 150 mm/sec)
        :param drive_z: (Optional, requires speed_z) Drive power in %(?) (default & max is 100%)
        """
        self.pz = target_z
        self.sz = speed_z
        self.dz = drive_z
        if self.dz is not None:
            assert self.sz is not None, "Cannot specify z drive without z speed"

    @property
    def cmd_str(self):  # noqa
        cmd = f"z{self.pz}"
        if self.sz:
            cmd += f":{self.sz}"
        if self.dz:
            cmd += f":{self.dz}"
        return cmd


GX241_ERROR_CODES = {
    0: "No Error",
    10: "Unknown command", 11: "Invalid NV-RAM address", 12: "Safety stop activated", 13: "Bad parameter entered",
    14: "FIFO Full", 15: "FIFO Add", 16: "Character limit",
    17: "X Axis park location", 18: "Y Axis park location",
    20: "X Axis not homed", 21: "Y Axis not homed", 22: "Z Axis not homed",
    24: "X Axis moving", 25: "Y Axis moving", 26: "Z Axis moving",
    28: "X Axis stall", 29: "Y Axis stall", 30: "Z Axis stall",
    32: "X Axis encoder", 33: "Y Axis encoder", 34: "Z Axis encoder",
    36: "X Axis speed range", 37: "Y Axis speed range", 38: "Z Axis speed range",
    40: "X Axis target range", 41: "Y Axis target range", 42: "Z Axis target range",
    99: "Accessory Error"
}

if __name__ == '__main__':
    t = SetMotorStatus(1, 1, 1)
    print(t.cmd_str)

    b = GetStatusSummary()
    print(b.cmd_str)
