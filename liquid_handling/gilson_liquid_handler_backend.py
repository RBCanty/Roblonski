"""
Written by R. Ben Canty, C. Hicham Moran, Nikolai Mukhin, Fernando Delgado-Licona
TODO: Check sig-figs in the Gilson command signatures
  Add the Direct Inject unit
"""
from datetime import datetime
from tkinter.messagebox import askyesnocancel
from typing import Literal

from deck_layout.coordinates import Point2D
from deck_layout.handler_bed import DEFAULT_XY_SPEED, DEFAULT_Z_SPEED, DEFAULT_SYRINGE_FLOWRATE
from deck_layout.handler_bed import MAX_Z_HEIGHT, SYSTEM_AIR_GAP
from gilson_codexes import direct_inject_codex as i_lib
from gilson_codexes import gx241_codex as a_lib
from gilson_codexes import pump_codex as p_lib
from gilson_codexes.command_abc import DeviceStatus, Buffered, Immediate
from gilson_codexes.pump_codex import ValveStates, VALVE_STATE
from liquid_handling.gilson_connection import GilsonSerialInputOutputChannel, USB_AUTODETECT
from misc_func import Number


class _Gilson241LiquidHandler:
    """ A class representing a Gilson GX-241 liquid handler core functionality (under the Hood class) """

    def __init__(self, port: str = USB_AUTODETECT, timeout: float = 1,
                 home_arm_on_startup: bool = True, home_pump_on_startup: bool = False,
                 pump_id: int = 2, handler_id: int = 30, injector_id: int = 6):
        self.com = GilsonSerialInputOutputChannel(port, timeout)
        self.handler_id = handler_id
        self.pump_id = pump_id
        self.injector_id = injector_id
        self.current_gantry_position: Point2D = None  # noqa
        self.current_z_position: int = None  # noqa
        if home_arm_on_startup:
            self.home_arm()
        if home_pump_on_startup:
            self.home_pump()
        self.aspirate_from_curr_pos(SYSTEM_AIR_GAP, DEFAULT_SYRINGE_FLOWRATE)

    def __repr__(self):
        return f"<Gilson241LiquidHandler object on {self.com.ser.port}>"

    def buffered_command(self, instrument_id: int, command: Buffered):
        """ Executes a buffered command in a blocking manner.  Handles connecting before sending part.

        :param instrument_id: The numerical ID of the device (see: 'self.{name}_id')
        :param command: The command to execute (should include all applicable parameters, formatted just as if it
          was being sent manually via serial).
        """
        self.com.connect_to(instrument_id)
        self.com.buffered_command(command)
        self.motor_wait()

    def immediate_command(self, instrument_id: int, command: Immediate, verbose=1):
        """ Executes an immediate command.  Handles connecting before sending part.

        :param instrument_id: The numerical ID of the device (see: 'self.{name}_id')
        :param command: The command to execute (should include all applicable parameters, formatted just as if it
          was being sent manually via serial).
        :param verbose: 0 - no IO, 1 - marks command, 2 - Debug

        :return: The response string from the command
        """
        self.com.connect_to(instrument_id)
        return self.com.immediate_command(command, verbose)

    def home_arm(self):
        """
        Moves the Gilson GX-241 Liquid handler's arm/gantry to the home position. Will move the Z axis to the maximum
          possible height.
        """
        self.buffered_command(self.handler_id, a_lib.HomeMotors())
        self.current_gantry_position = Point2D(0, 0)
        self.current_z_position = 0  # TODO: update with actual values :)

    def home_pump(self):
        """ Moves the syringe to the home position (flushing out any liquid therein) """
        self.buffered_command(self.pump_id, p_lib.HomePump())

    def motor_wait(self, timeout: float = 60):
        """
        Repeatedly queries the current connected device's motor status, stopping only when there is no
          indication that the motor is moving.

        :param timeout: timeout duration in seconds (default = 60)
        """
        start = datetime.now()
        while (datetime.now() - start).total_seconds() < timeout:
            motor_code = self.com.immediate_command(a_lib.GetMotorStatus(), verbose=0)
            if DeviceStatus.busy not in motor_code:
                break
        else:
            # The 'else' of a 'while' loop only runs if the loop exits normally (so not via 'break')
            print(f"\033[93m WARNING: timeout exceeded awaiting a ready status \033[0m")

    def move_arm_xy(self, target_point: Point2D, speed: int = DEFAULT_XY_SPEED):
        """
        Moves the GX-241's gantry in the XY direction to a target point. (Motor buffered)

        :param target_point: A Point2D object encoding the target position in the XY plane.
        :param speed: The XY speed (in mm/s) at which the gantry should move. The firmware default is 300 mm/s,
          and speed maxes out at 350 mm/s. The software default is set here using the constant: DEFAULT_XY_SPEED
        """
        command = a_lib.MoveXY(
            target_x=target_point.x, target_y=target_point.y,
            speed_x=speed, speed_y=speed,
        )  # f"{XY_MOVE_CMD_B}{target_point.x}:{speed}/{target_point.y}:{speed}"
        self.buffered_command(self.handler_id, command)
        self.current_gantry_position = target_point

    def move_arm_z(self, target_z: int, speed: int = DEFAULT_Z_SPEED):
        """
        Moves the GX-241's probe in the Z direction to a target height (or Z coordinate). (Motor buffered)

        NOTE: Z=125 is Higher than Z=25.

        :param target_z: An integer (in mm) encoding the target height
        :param speed: The Z speed (in mm/s) at which the gantry should move. The firmware default is 125 mm/s,
          and speed maxes out at 150 mm/s. The software default is set here using the constant: DEFAULT_Z_SPEED
        """
        command = a_lib.MoveZ(target_z=target_z, speed_z=speed)  # f"{Z_MOVE_CMD_B}{target_z}:{speed}"
        self.buffered_command(self.handler_id, command)
        self.current_z_position = target_z

    def pump_pumping_cmd(self, instrument_id: int, volume_ul: Number, valve_pos: VALVE_STATE,
                         flow_rate: Number = None, block: bool = True):
        """
        Worker method

        Commands the pump to pump a specified volume at a specified flow rate at a specified valve position.
        Don't use this directly if you can help it, as the volume_ul parameter has different semantics than
        in other methods in this class.

        :param instrument_id: The numerical ID of the Gilson Pump, (set via a dial on the back).
        :param volume_ul: the volume (uL) to pump NOTE: May be positive or negative for the "Needle" position, positive
          only for the "Reservoir" position
        :param flow_rate: the flow rate (mL/min) at which to pump liquid (if None will use most recent flow rate)
        :param valve_pos: (str) the valve position of the pump: "N" corresponds to the needle, "R" to the reservoir.
        :param block: Specifies whether to wait for the command to finish executing before allowing other actions.
          Default is True--use False at your own risk!

        :raises ValueError: When the valve position is invalid, if attempting to dispense to reservoir, or if volume
          is miniscule/zero.
        """
        valve_pos = valve_pos.upper()
        if valve_pos not in [ValveStates.needle, ValveStates.reservoir]:
            raise ValueError(f"Invalid valve position {valve_pos} specified! must be either "
                             f"{ValveStates.needle} or {ValveStates.reservoir}.")
        if (valve_pos == ValveStates.reservoir) and (volume_ul < 0):
            raise ValueError(f"Invalid flow rate {flow_rate} for current valve position:"
                             f" \"{valve_pos}\" (Reservoir)! Cannot dispense to reservoir.")
        if (not volume_ul) or (abs(volume_ul) < 0.001):
            raise ValueError("Please specify a nonzero volume!")

        pump_cmd = p_lib.RunPump(valve_position=valve_pos, volume=volume_ul, flow_rate=flow_rate)
        # f"{PUMP_PUMP_CMD_B}{valve_pos}:{volume_ul}:{flow_rate}"

        if block:
            self.buffered_command(instrument_id, pump_cmd)
            # print("DEBUG", self.immediate_command(instrument_id, p_lib.GetMotorStatus()))
        else:
            self.com.connect_to(instrument_id)
            self.com.buffered_command(pump_cmd)

    def dispense_to_curr_pos(self, volume_ul: Number, flow_rate: Number):
        """
        Issues a command for the pump to dispense to the probe from the syringe at the probe's current position.

        :param volume_ul: the volume (uL) to pump (ignores sign, will dispense)
        :param flow_rate: the flow rate (mL/min) at which to pump liquid

        :raises ValueError: If volume is miniscule/zero
        """
        self.pump_pumping_cmd(instrument_id=self.pump_id,
                              volume_ul=-abs(volume_ul), flow_rate=flow_rate, valve_pos=ValveStates.needle)

    def aspirate_from_curr_pos(self, volume_ul: Number, flow_rate: Number):
        """
        Issues a command to the pump for it to aspirate a specified volume at the probe's current position.

        :param volume_ul: the volume (uL) to pump (ignores sign, will aspirate)
        :param flow_rate: the flow rate (mL/min) at which to pump liquid

        :raises ValueError: If volume is miniscule/zero
        """
        self.pump_pumping_cmd(instrument_id=self.pump_id,
                              volume_ul=abs(volume_ul), flow_rate=flow_rate, valve_pos=ValveStates.needle)

    def aspirate_from_reservoir(self, volume_ul: Number, flow_rate: Number):
        """
        Issues a command for the pump to aspirate from the reservoir connected to said pump at the probe's
          current position.

        :param volume_ul: the volume (uL) to pump (ignores sign, will aspirate)
        :param flow_rate: the flow rate (mL/min) at which to pump liquid. Be mindful of the recommended flow rate for
          the current syringe--this method isn't!

        :raises ValueError: If volume is miniscule/zero.
        """
        self.pump_pumping_cmd(instrument_id=self.pump_id,
                              volume_ul=abs(volume_ul), flow_rate=flow_rate, valve_pos=ValveStates.reservoir)

    def get_current_coordinates(self):
        """ Queries the liquid handler for the current XYZ position. """
        xy_coord_str = self.immediate_command(self.handler_id, a_lib.GetXYCoordinates()).strip()
        x_str, y_str = xy_coord_str.split("/")
        x_coord = float(x_str)
        y_coord = float(y_str)
        print(f"{x_coord=}, {y_coord=}", )
        z_coord_str = self.immediate_command(self.handler_id, a_lib.GetZCoordinate()).strip()
        z_coord = float(z_coord_str)
        print(f"{z_coord=}")
        return x_coord, y_coord, z_coord

    def set_pump_to_volume(self, volume: Literal[100, 250, 500, 1000, 5000, 10000]):
        """ Modifies pump internals so that it knows the syringe size (in uL) """
        self.buffered_command(self.pump_id, p_lib.SetSyringeSize(volume))
        print(self.immediate_command(self.pump_id, p_lib.GetSyringeSize()))

    def _stop_pump(self):
        self.com.buffered_command(p_lib.PumpStop())

    def _connect_to_injector(self):
        self.com.connect_to(self.injector_id)

    def _connect_to_pump(self):
        self.com.connect_to(self.pump_id)

    def _switch_load(self):
        self.com.buffered_command(i_lib.SwitchLoad())


class Gilson241LiquidHandlerConfigurator:
    """ A helper class for getting constants and configs up and running """
    def __init__(self, controller: _Gilson241LiquidHandler):
        self.ctrl = controller

    def prime_pump_at_xy(self, x: int, y: int, volume: Number, flow_rate: Number):
        """ Primes the pump at an x/y position rather than at waste
        :param x: X coordinate
        :param y: Y coordinate
        :param volume: in uL
        :param flow_rate: in mL/min """
        self.ctrl.home_arm()
        self.ctrl.move_arm_xy(Point2D(x, y))
        self.ctrl.move_arm_z(MAX_Z_HEIGHT-10)
        self.ctrl.home_pump()
        while True:
            self.ctrl.aspirate_from_reservoir(volume, flow_rate)
            self.ctrl.dispense_to_curr_pos(volume, flow_rate)
            if askyesnocancel("Priming needle...", "Is liquid coming out of the needle?"):
                break

    def seek_positions(self, xy_motor_speed=DEFAULT_XY_SPEED, z_motor_speed=DEFAULT_Z_SPEED):
        """ Helper macro to find the XYZ coordinates of locations
        :param xy_motor_speed: The XY motor speed in mm/s
        :param z_motor_speed: The Z motor speed in mm/s
        """
        self.ctrl.home_arm()
        while True:
            print("Please enter your desired X, Y, and Z coordinates as: '##, ##, ##' (or 'exit')")
            user_input = input("x, y, z =\n")
            if 'exit' in user_input.lower():
                break
            try:
                x, y, z = user_input.strip().replace(" ", "").split(",")
                x = int(x)
                y = int(y)
                z = int(z)
            except:  # noqa
                print("poorly formatted input, try again")
                continue

            self.ctrl.move_arm_z(MAX_Z_HEIGHT, z_motor_speed)
            self.ctrl.move_arm_xy(Point2D(x, y), xy_motor_speed)
            self.ctrl.move_arm_z(z, z_motor_speed)

            print("XY", self.ctrl.immediate_command(self.ctrl.handler_id, a_lib.GetXYCoordinates()))
            print("Z", self.ctrl.immediate_command(self.ctrl.handler_id, a_lib.GetZCoordinate()))
            print()
