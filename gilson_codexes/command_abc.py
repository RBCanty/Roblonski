from enum import StrEnum


class DeviceStatus(StrEnum):
    """ Error, Busy, Off, or Parked """
    error = "E"
    busy = "R"
    off = "U"
    parked = "P"


class Buffered:
    """ Gilson buffered commands take a command string then execute an operation which takes time and so cannot
    provide a meaningful return value when called. """
    cmd_str = ""

    def __str__(self) -> str:
        return self.cmd_str


class Immediate:
    """ Gilson immediate commands take a command character then execute immediately--permitting a meaningful return
    value. """
    cmd_str = ""
    rsp_fmt = "Response format not defined"

    def __str__(self) -> str:
        return self.cmd_str

    def response(self) -> str:
        return self.rsp_fmt


class CustomBuffered(Buffered):
    """ To allow easy debug and access to commands not included in this Python module """
    def __init__(self, cmd: str):
        self.cmd_str = cmd


class CustomImmediate(Immediate):
    """ To allow easy debug and access to commands not included in this Python module """
    def __init__(self, cmd: str, rsp: str = "not set"):
        self.cmd_str = cmd
        self.rsp_fmt = rsp
        assert len(cmd) == 1, "Immediate commands can only be 1 character long"
