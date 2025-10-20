"""
A heavily edited version of (GitHub: drvirgilio)'s gsioc controller code
Gilson GSIOC communication protocol

Edited by Richard B Canty

For further help, consult:
  - http://pubdata.theorchromo.ru/manuals/Gilson/GSIOC%20Tech%20Man.pdf
"""

# immediate commands are an ascii string
# buffered commands are an ascii string

import atexit
import datetime
import time

import serial
import serial.tools.list_ports

from gilson_codexes.command_abc import Buffered, Immediate

# Change this based on the Windows Device Manager entry for
# whichever RS232-to-USB cable you are using to connect to
# the Gilson platform.
USB_DEVICE_NAME = "Prolific PL2303GS USB Serial COM Port"


def stamp(msg: str):
    _msg = datetime.datetime.now().strftime("%a %b %d - %H:%M:%S -- ") + msg
    if msg:
        print(_msg)
    return _msg


ENCODING = 'ascii'
DISCONNECT_EVERY_SLAVE = bytes.fromhex('FF')
ACKNOWLEDGE = bytes.fromhex("06")
INVALID_COMMAND = "#".encode(ENCODING)
START_BUFFERED = "\n".encode(ENCODING)
END_BUFFERED = "\r".encode(ENCODING)
CHAR = str
DISCONNECT_TIMEOUT = 0.2  # seconds
USB_AUTODETECT = "AUTO"


class GilsonSerialInputOutputChannel:
    """ Serial communication channel for a GSIOC connection. """
    def __init__(self, port: str = USB_AUTODETECT, timeout: float = 2):

        if port.upper() == USB_AUTODETECT:
            port = self.detect_usb_port()

        self.ser = serial.Serial(port=port, baudrate=19200, timeout=timeout,
                                 parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS)

        def close_out():
            self.ser.close()
            stamp("Connection closed")

        atexit.register(close_out)
        stamp(repr(self.ser))

    def connect_to(self, instrument_id: int = 0) -> None:
        """ Connects to an instrument by ID # in the range [0,64) """
        if not (0 <= instrument_id < 64):
            raise ValueError("ID out of range [0,63]")
        encoded_instrument_id = (instrument_id + 128).to_bytes(1, 'big')
        # Clean the slate
        self.ser.flush()
        self.ser.write(DISCONNECT_EVERY_SLAVE)
        time.sleep(5 * DISCONNECT_TIMEOUT)  # MUST be at LEAST 20 milliseconds
        # Connect
        self.ser.flush()
        self.ser.write(encoded_instrument_id)
        resp = self.ser.read(1)
        if not resp:
            raise ConnectionError(stamp("No response from device"))
        time.sleep(0.2)
        self.ser.flush()
        stamp(f"Connected to device {instrument_id} <{resp[0]!r}>")
        self.ser.read(16)

    def immediate_command(self, command: Immediate, verbose=1) -> str:
        """
        Typically request status reports from a slave instrument.
        Always in the form of a single character.

        :param command: A single character command
        :param verbose: 0 - no IO, 1 - marks command, 2 - Debug
        :return: A string representation of the response
        """
        cmd: CHAR = command.cmd_str
        time.sleep(0.02)
        if verbose > 0:
            stamp(cmd)
        cmd: bytes = cmd.encode(ENCODING)[:1]
        if not (0 <= cmd[0] < 128):
            raise ValueError(stamp(f"Command {cmd} (val={cmd[0]}) must have an ASCII value "
                                   f"between 0 and 127, inclusive."))
        self.ser.flush()
        self.ser.write(cmd)

        """ From documentation:
        After a slave instrument receives an immediate command, it answers the request with the first character of its 
        response. The master checks the ASCII value of the character. If the character's value is less than 128, it 
        responds to the slave with an ACK character (06 hexadecimal). This exchange continues until the slave sends 
        the last character of the response. To indicate that the last character is  being sent, the slave adds 128 
        (80 hexadecimal) to the character's value. 
        In response to an unrecognized immediate command, a slave responds with a pound sign (#), a value of 23 
        hexadecimal, and adds 128 (80 hexadecimal). """
        resp = bytearray(0)
        while True:
            resp_raw = self.ser.read(1)
            if not resp_raw:
                raise ConnectionError(stamp("No response from device"))
            if resp_raw == "#".encode(ENCODING):
                return f"Command {cmd!r} not recognized"
            # if resp_raw == "\r".encode(ENCODING):
            #     self.ser.write(ACKNOWLEDGE)
            #     continue
            if resp_raw[0] < 128:
                resp.append(resp_raw[0])
                self.ser.flush()
                self.ser.write(ACKNOWLEDGE)
                continue
            resp.append(resp_raw[0] - 128)
            if verbose > 1:
                stamp(f"{cmd} returned\n{' ' * 25}-> {resp.decode(ENCODING)}\n{command.rsp_fmt}")
            self.ser.flush()
            return resp.decode(ENCODING)

    @staticmethod
    def detect_usb_port() -> str:
        """
        Used to automatically detect which COM port the Gilson liquid handler is connected to.

        Assumptions:
         
        1. Only one USB-to-RS232 cable is actually connected to the computer. 
        2. The Gilson liquid handler is in fact connected via an RS232-to-USB cable,
           and not a native RS232 (LPT) port.
        3. The name of the RS232-to-USB cable matches the constant USB_DEVICE_NAME
        4. The correct drivers for this RS232-to-USB cable have been separately installed.               

        :return: A string representation of the COM port to which a USB-to-RS232 cable is connected
        """
        return list(map(lambda p: p.device, list(serial.tools.list_ports.grep(USB_DEVICE_NAME))))[0]

    def buffered_command(self, command: Buffered, verbose=1) -> None:
        """
        Typically for instructions and hardware operations

        :param command: A single character command
        :param verbose: Will stamp if verbose is greater than 0
        :return: A string representation of the response
        """
        # time.sleep(1) #1
        cmd = command.cmd_str
        if verbose > 0:
            stamp(cmd)
        _command: bytes = f"{cmd}\r".encode(ENCODING)

        self.ser.flush()

        _iter = iter([slice(i, i + 1) for i in range(len(_command))])
        sel = next(_iter)
        timeout = DISCONNECT_TIMEOUT * (len(_command) + 1)
        _timer = datetime.datetime.now()
        self.ser.flush()
        self.ser.write(b'\n')
        self.ser.read_until(b"\n")  # There can be only 1 of these read, so be careful uncommenting the next line
        # stamp("Flushing: " + repr(self.ser.read_until(b"\n")))
        while (datetime.datetime.now() - _timer).total_seconds() < timeout:
            char = _command[sel]
            self.ser.flush()
            self.ser.write(char)
            check = self.ser.read(1)
            if char == b'\r' and check == b'\r':
                break
            if char != b'#' and check == b'#':
                # time.sleep(1) #2
                continue
            if check != char:
                check += self.ser.read(4)
                raise ConnectionError(stamp(f"Unrecognized response {check!r} while processing {cmd!r}"))
            try:
                sel = next(_iter)
            except StopIteration:
                raise ConnectionError(stamp(f"Exhausted command {_command!r} without terminating on '\r' character."))
        else:
            raise ConnectionError(stamp(f"Timed out while awaiting {cmd!r}"))
        # time.sleep(1) #3
        self.ser.flush()


class GilsonArgumentError(ValueError):
    pass
