# GX Direct Injection Module (Version 1.1.0)

from gilson_codexes.command_abc import Immediate, Buffered


class GetModuleID(Immediate):
    """ Pulls for the injector firmware version (%) """
    cmd_str = "%"
    rsp_fmt = "'GX D Inject vx.y.z' where a, b, c, and d represent the firmware version"


class Reset(Immediate):
    """ Resets injector ($) """
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


class SwitchInject(Buffered):
    """ Throws the injector into the inject state (VI) """
    cmd_str = "VI"


class SwitchLoad(Buffered):
    """ Throws the injector into the loading state (VL) """
    cmd_str = "VL"


class GetInjectorStatus(Immediate):
    """ Pulls for the injector motor status (X) """
    cmd_str = "X"
    rsp_fmt = "'i' where i is R for moving, L for load position, and I for inject position"


GX_INJECT_CODES = {
    0: "No Error",
    1: "Unknown command", 2: "Invalid NV-RAM address",
    3: "Previous move not complete", 4: "Invalid position requested"
}
