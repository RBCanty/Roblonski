"""
Written by R. Ben Canty, C. Hicham Moran, Nikolai Mukhin, Fernando Delgado-Licona
TODO: Check sig-figs in the Gilson command signatures
  Add the Direct Inject unit
"""
import time
from functools import partial
from threading import Event, Thread
from tkinter.messagebox import askyesnocancel
from typing import Iterable, Callable
from contextlib import redirect_stdout
from io import StringIO

from aux_devices.ocean_optics_spectrometer import SpectrometerSystem, OpticalSpecs, Spectrum
from aux_devices.spectra import SpectraStack
from deck_layout.coordinates import Point2D
from deck_layout.handler_bed import DEFAULT_WASTE_LOC, DEFAULT_INJECTOR_LOC  # , DEFAULT_BULK_SOLVENT_RACK_NAME
from deck_layout.handler_bed import DEFAULT_XY_SPEED, DEFAULT_Z_SPEED, DEFAULT_SYRINGE_FLOWRATE
from deck_layout.handler_bed import HandlerBed
from deck_layout.handler_bed import MAX_Z_HEIGHT, MAX_SYRINGE_VOL, PRIMING_FLOWRATE, SYSTEM_AIR_GAP
from deck_layout.handler_bed import Placeable, NamePlace, Coordinate
from gilson_codexes import direct_inject_codex as i_lib
from gilson_codexes import gx241_codex as a_lib
from gilson_codexes import pump_codex as p_lib
from gilson_codexes.command_abc import DeviceStatus
from gilson_codexes.pump_codex import ValveStates
from liquid_handling.gilson_connection import USB_AUTODETECT
from liquid_handling.gilson_liquid_handler_backend import _Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import ComponentSpec, AirGap, ArmSpec, TipExitMethod
from liquid_handling.liquid_handling_specification import (MixingSpec,
                                                           AspiratePipettingSpec,
                                                           AspirateSystemSpec,
                                                           DispensePipettingSpec, DispenseAllSpec,
                                                           ExternalWash, InternalWash, InternalClean, PokeNeedleSpec,
                                                           Comment, UserIntervention, Wait)
from user_interface.quick_gui import QuickButtonUI, tk
from misc_func import silence, Number

VALID_SPEC = (AspiratePipettingSpec | DispensePipettingSpec | AspirateSystemSpec | DispenseAllSpec |
              MixingSpec | ExternalWash | InternalWash | InternalClean | PokeNeedleSpec |
              UserIntervention | Comment | Wait |
              None)


class Gilson241LiquidHandler(_Gilson241LiquidHandler):
    """ A class representing a Gilson GX-241 liquid handler. """
    def __init__(self, port: str = USB_AUTODETECT, timeout: float = 1,
                 home_arm_on_startup: bool = True, home_pump_on_startup: bool = False):
        super().__init__(port, timeout, home_arm_on_startup, home_pump_on_startup)
        self.bed: HandlerBed | None = None
        self._waste_location: tuple[str, str] = DEFAULT_WASTE_LOC
        self._injector_location: tuple[str, str] = DEFAULT_INJECTOR_LOC

    @property
    def waste_location(self):
        return self.locate_position_name(*self._waste_location)

    @property
    def injector_location(self):
        return self.locate_position_name(*self._injector_location)

    def load_bed(self, directory: str, bed_file: str):
        self.bed = HandlerBed.load_from_file(directory, bed_file)

    @silence
    def move_arm_xy(self, target_point: Point2D, speed: int | float = DEFAULT_XY_SPEED):
        """
        Moves the GX-241's gantry in the XY direction to a target point. (Motor buffered)

        :param target_point: A Point2D object encoding the target position in the XY plane.
        :param speed: The XY speed (in mm/s) at which the gantry should move. The firmware default is 300 mm/s,
          and speed maxes out at 350 mm/s. The software default is set here using the constant: DEFAULT_XY_SPEED
        """
        if self.bed:
            target_point = target_point.interpolate_max(self.bed.get_min_xy())  # Clamp XY coordinates
            target_point = target_point.interpolate_min(self.bed.get_max_xy())  # .
        super().move_arm_xy(target_point, speed)

    @silence
    def move_arm_z(self, target_z: int | float, speed: int | float = DEFAULT_Z_SPEED):
        """
        Moves the GX-241's probe in the Z direction to a target height (or Z coordinate). (Motor buffered)

        NOTE: Z=125 is Higher than Z=25.

        :param target_z: A number (in mm) encoding the target height
        :param speed: The Z speed (in mm/s) at which the gantry should move. The firmware default is 125 mm/s,
          and speed maxes out at 150 mm/s. The software default is set here using the constant: DEFAULT_Z_SPEED
        """
        if self.bed:
            _lb = self.bed.get_min_z()
            _ub = self.bed.get_max_z()
        else:
            _lb = 5
            _ub = MAX_Z_HEIGHT
        target_z = max(_lb, min(target_z, _ub))  # Clamp Z value
        super().move_arm_z(target_z, speed)

    def aspirate_from_reservoir(self, volume_ul: Number, flow_rate: Number):
        if self.bed is not None:
            self.bed.update_resource_cfg_value("system_fluid_volume_mL", lambda x: x - volume_ul/1000)
        return super().aspirate_from_reservoir(volume_ul, flow_rate)

    # ## BUILDER ## # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    def _tip_exit_center(self, position: Placeable, z_speed: int):
        """ Pull the tip straight up from the center """
        self.move_arm_z(position.get_access_z(), z_speed)

    def _tip_exit_touch(self, position: Placeable, z_speed: int, xy_speed: int):
        """ Pull the tip up from the center, then touch it against the lip """
        self.move_arm_z(position.get_access_z() - 1, z_speed)
        if (self.current_z_position is None) or (self.bed is None):  # Abort
            return
        self.move_arm_xy(position.get_edge(), xy_speed)
        self.move_arm_xy(position.get_xy_position(), xy_speed)
        self.move_arm_z(position.get_access_z(), z_speed)

    def _tip_exit_drag(self, position: Placeable, z_speed: int, xy_speed: int):
        """ Move to the lip, then pull the tip up, then return to center """
        if (self.current_z_position is None) or (self.bed is None):  # Abort
            self.move_arm_z(position.get_access_z(), z_speed)
            return
        self.move_arm_xy(position.get_edge(), xy_speed)
        self.move_arm_z(position.get_access_z(), z_speed)
        self.move_arm_xy(position.get_xy_position(), xy_speed)

    @silence
    def _dispatch_tip_exit(self, method: TipExitMethod, position: Placeable, z_speed: int, xy_speed: int):
        if method == TipExitMethod.CENTER:
            self._tip_exit_center(position, z_speed)
        elif method == TipExitMethod.TIP_TOUCH:
            self._tip_exit_touch(position, z_speed, xy_speed)
        elif method == TipExitMethod.DRAG:
            self._tip_exit_drag(position, z_speed, xy_speed)
        elif method == TipExitMethod.NONE:
            pass

    def _aspirate(self, specification: AspiratePipettingSpec):
        """ If AirGap, then takes an Airgap at max Z height or the access Z position of a specified vial.  Otherwise,
        moves the tip to the transfer location specified.  If volume is Truthy, it will aspirate; otherwise, nothing
        will happen.  Then it removes the tip as specified. """
        component = specification.component
        flow_rate = specification.rate
        arm_spec = specification.arm
        sensor = specification.sensor_depth
        tip_method = specification.tip_exit_method
        xy_speed, z_speed = arm_spec

        if isinstance(component, AirGap):
            volume = component.volume
            position = component.position
            if position is None:
                self.move_arm_z(MAX_Z_HEIGHT, z_speed)
            else:
                self.move_arm_to(position, xy_speed, z_speed)
            self.aspirate_from_curr_pos(abs(volume), flow_rate)
            return
        if sensor is not None:
            raise NotImplementedError("Liquid level detection not yet implemented, sorry.")

        position = component.position
        volume = component.volume
        self.move_arm_to(position, xy_speed, z_speed)
        if volume:
            self.move_arm_z(position.get_transfer_z(), z_speed)
            self.aspirate_from_curr_pos(abs(volume), flow_rate)
        self._dispatch_tip_exit(tip_method, position, z_speed, xy_speed)

    def _dispense(self, specification: DispensePipettingSpec):
        """ If AirGap, then dispenses an Airgap at max Z height or the access Z position of a specified vial. Otherwise,
        moves the tip to the transfer location specified.  If volume is Truthy, it will dispense; otherwise, nothing
        will happen.  Then it removes the tip as specified. """
        component = specification.component
        flow_rate = specification.rate
        arm_spec = specification.arm
        sensor = specification.sensor_depth
        tip_method = specification.tip_exit_method
        free_dispense = specification.free_dispense
        disp_on_edge = specification.disp_on_edge
        xy_speed, z_speed = arm_spec

        if isinstance(component, AirGap):
            volume = component.volume
            position = component.position
            if position is None:
                self.move_arm_z(MAX_Z_HEIGHT, z_speed)
            else:
                self.move_arm_to(position, xy_speed, z_speed, disp_on_edge)
            self.dispense_to_curr_pos(abs(volume), flow_rate)
            return
        if sensor is not None:
            raise NotImplementedError("Liquid level detection not yet implemented, sorry.")

        position = component.position
        volume = component.volume
        self.move_arm_to(position, xy_speed, z_speed, disp_on_edge)

        if free_dispense:
            dispense_z = position.get_access_z()
        else:
            dispense_z = position.get_transfer_z()
        self.move_arm_z(dispense_z, z_speed)

        if volume:
            self.dispense_to_curr_pos(abs(volume), flow_rate)
        self._dispatch_tip_exit(tip_method, position, z_speed, xy_speed)

    @silence
    def _dispense_all(self, specification: DispenseAllSpec):
        """ If AirGap, then dispenses an Airgap at max Z height or the access Z position of a specified vial. Otherwise,
        moves the tip to the transfer location specified.  If volume is Truthy, it will dispense; otherwise, nothing
        will happen.  Then it removes the tip as specified. """
        position = specification.position
        arm_spec = specification.arm
        tip_method = specification.tip_exit_method
        free_dispense = specification.free_dispense
        disp_on_edge = specification.disp_on_edge
        xy_speed, z_speed = arm_spec

        self.move_arm_to(position, xy_speed, z_speed, disp_on_edge)

        if free_dispense:
            dispense_z = position.get_access_z()
        else:
            dispense_z = position.get_transfer_z()
        self.move_arm_z(dispense_z, z_speed)

        self.home_pump()
        self._dispatch_tip_exit(tip_method, position, z_speed, xy_speed)

    @silence
    def _mix(self, specification: MixingSpec):
        """ Moves to Max Z height or the Access Z height of the vial, takes an air gap if specified truthy.
        If a location is specified, it will aspirate from/dispense to that vial, otherwise it will aspirate/dispense
        air.  It repeats this action a specified number of times, then removes the tip (is applicable) as specified.
        Finally, it blows out the specified volume of air (if truthy).
        """
        mix_displacement = specification.mixing_displacement
        mix_rate = specification.rate
        mix_iterations = specification.n_iterations
        location = specification.location
        air = specification.blowout_volume

        if (not mix_displacement) or (not mix_iterations):
            return

        if location is None:
            self.move_arm_z(MAX_Z_HEIGHT)
        else:
            position, arm, _ = location  # type: Placeable, ArmSpec, TipExitMethod
            self.move_arm_to(position, arm.xy_speed, arm.z_speed)
            self.move_arm_z(position.get_access_z(), arm.z_speed)

        if (air is not None) and (air > 0):
            self.aspirate_from_curr_pos(air, DEFAULT_SYRINGE_FLOWRATE)

        if location is not None:
            position, arm, _ = location  # type: Placeable, ArmSpec, TipExitMethod
            self.move_arm_z(position.get_transfer_z(), arm.z_speed)

        for _ in range(mix_iterations):
            self.aspirate_from_curr_pos(mix_displacement, mix_rate)
            self.dispense_to_curr_pos(mix_displacement, mix_rate)

        if location is not None:
            position, arm, tip_method = location  # type: Placeable, ArmSpec, TipExitMethod
            self._dispatch_tip_exit(tip_method, position, arm.z_speed, arm.xy_speed)

        if air:  # Z = Z max if no location or the Access Z of the vial if location.
            self.dispense_to_curr_pos(air, DEFAULT_SYRINGE_FLOWRATE)

    @silence
    def _external_wash(self, specification: ExternalWash):
        """ Takes an air-gap if specified, then dips the needle into a reservoir (exiting using the specified exit
        method) a number of times to clean the outside of the needle. The airgap (if present) is then ejected.
        """
        air_gap = specification.air_gap
        arm_spec = specification.arm
        xy_speed, z_speed = arm_spec
        tip_method = specification.tip_exit_method

        _temp = specification.positions
        dip_positions: tuple[Placeable] = _temp if isinstance(_temp, tuple) else (_temp, )
        for position in dip_positions:
            if air_gap:
                self._aspirate(air_gap)
            self.move_arm_to(position, xy_speed, z_speed)
            for _ in range(specification.n_iter):
                self.move_arm_z(position.get_transfer_z(), z_speed)
                self._dispatch_tip_exit(tip_method, position, z_speed, xy_speed)
            if air_gap:
                air_gap_disp = air_gap.cast_to_dispense(free_dispense=True)
                self._dispense(air_gap_disp.updated_copy(tip_exit_method=TipExitMethod.TIP_TOUCH))

    @silence
    def _clean(self, specification: InternalClean):
        """ Moves to Max Z height or the Access Z height of the vial, homes the pump.
        Iteratively aspirates from the reservoir, then dispenses to the needle.
        Restores the system air gap.
        """
        cleaning_volume = specification.cleaning_volume
        flow_rate = specification.rate
        location = specification.location
        arm = specification.arm

        self.move_arm_to(location, arm.xy_speed, arm.z_speed, specification.disp_on_edge)
        if specification.free_dispense:
            self.move_arm_z(location.get_access_z(), arm.z_speed)
        else:
            self.move_arm_z(location.get_transfer_z(), arm.z_speed)

        if specification.pre_flush:
            self.home_pump()
        for _ in range(specification.n_iterations):
            self.aspirate_from_reservoir(cleaning_volume, flow_rate)
            self.dispense_to_curr_pos(cleaning_volume, flow_rate)

        self._dispatch_tip_exit(specification.tip_exit_method, location, arm.z_speed, arm.xy_speed)
        self.aspirate_from_curr_pos(SYSTEM_AIR_GAP, DEFAULT_SYRINGE_FLOWRATE)

    def chain_pipette(self, *specifications: VALID_SPEC):
        """ Based on a sequence of specifications, this method executes each operation in order. """
        for spec in specifications:
            if isinstance(spec, AspiratePipettingSpec):
                self._aspirate(spec)
            elif isinstance(spec, DispensePipettingSpec):
                self._dispense(spec)
            elif isinstance(spec, MixingSpec):
                self._mix(spec)
            elif isinstance(spec, (ExternalWash, PokeNeedleSpec)):
                self._external_wash(spec)
            elif isinstance(spec, InternalWash):
                self._mix(spec.cast_to_mix())
            elif isinstance(spec, InternalClean):
                self._clean(spec)
            elif isinstance(spec, DispenseAllSpec):
                self._dispense_all(spec)
            elif isinstance(spec, AspirateSystemSpec):
                self.aspirate_from_reservoir(spec.volume, spec.rate)
            elif isinstance(spec, UserIntervention):
                if spec.home_arm:
                    self.home_arm()
                QuickButtonUI(tk.Tk(), title=spec.title, dialog=spec.prompt).run()
            elif isinstance(spec, Comment):
                print(spec.message)
            elif isinstance(spec, Wait):
                time.sleep(spec.duration * 60.0)
            elif spec is None:
                continue
            else:
                print(f"Warning, unknown specification:\n{spec}")

    # ## CORE USER-END ## # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def move_arm_to(self,
                    position: Placeable,
                    xy_speed=DEFAULT_XY_SPEED,
                    z_speed=DEFAULT_Z_SPEED,
                    use_edge=False):
        """ Moves the arm to max Z (for travel), moves to the target XY coordinate, then down to the specified Z
         coordinate. """
        try:
            self.move_arm_z(MAX_Z_HEIGHT, z_speed)
            if use_edge:
                self.move_arm_xy(position.get_edge(), xy_speed)
            else:
                self.move_arm_xy(position.get_xy_position(), xy_speed)
            self.move_arm_z(position.get_access_z(), z_speed)
        except Exception:
            print(f"DEBUG::move_arm_to():  {position!r}")
            raise

    def aspirate(self,
                 component: ComponentSpec | AirGap,
                 flow_rate: Number,
                 arm_spec: ArmSpec = ArmSpec(),
                 tip_method: TipExitMethod = TipExitMethod.CENTER):
        """ Simple aspirate method """
        return self._aspirate(
            AspiratePipettingSpec(
                component=component,
                rate=flow_rate,
                arm=arm_spec,
                sensor_depth=None,
                tip_exit_method=tip_method
            )
        )

    def dispense(self,
                 component: ComponentSpec | AirGap,
                 flow_rate: Number,
                 arm_spec: ArmSpec = ArmSpec(),
                 tip_method: TipExitMethod = TipExitMethod.CENTER,
                 free_dispense: bool = False):
        """ Simple aspirate method """
        return self._dispense(
            DispensePipettingSpec(
                component=component,
                rate=flow_rate,
                arm=arm_spec,
                sensor_depth=None,
                tip_exit_method=tip_method,
                free_dispense=free_dispense,
            )
        )

    def dispense_all(self, position: Placeable, arm_parameters: ArmSpec = ArmSpec()):
        """ Empties the syringe pump

        Args:
            position: Any placeable object
            arm_parameters: specifications for xy and z movement speeds
        """
        xy_speed = arm_parameters.xy_speed
        z_speed = arm_parameters.z_speed
        self.move_arm_to(position, xy_speed, z_speed)
        self.home_pump()

    def inject(self, *_, **__):
        """ Move to the injector, deposit sample, change injector state? """
        raise NotImplementedError

    @staticmethod
    def locate_position_xyz(x: int, y: int, z: int, _eo: int = 0) -> Coordinate:
        return Coordinate(xy=Point2D(x, y), z=z, edge_offset=_eo)

    def locate_position_name(self, rack_name: str, vial_id: str) -> NamePlace:
        return NamePlace(self.bed, rack_name, vial_id)

    # ## HELPER USER-END ## # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def prime_needle(self, prime_volume=MAX_SYRINGE_VOL, flow_rate=PRIMING_FLOWRATE):
        """
        Primes the needle by repeatedly drawing from the reservoir and dispensing to the probe's
        liquid line until the user confirms that liquid is leaving the needle via a dialog box
        that will appear every 5 cycles.

        :param prime_volume: the volume (uL) to move on each aspirate-dispense cycle. NOTE: MUST BE POSITIVE!
        :param flow_rate: the flow rate (mL/min) of the pumping in each direction.
        """
        self.move_arm_to(self.waste_location)
        self.home_pump()

        while True:
            for _ in range(5):
                self.aspirate_from_reservoir(prime_volume, flow_rate)
                self.dispense_to_curr_pos(prime_volume, flow_rate)
            if askyesnocancel("Priming needle...", "Is liquid coming out of the needle?"):
                break

    def wash_needle(self, *_, **__):
        raise NotImplementedError

    def prepare_droplet_in_liquid_line(self,
                                       components: Iterable[tuple[Placeable, float]],
                                       back_air_gap: Number,
                                       front_air_gap: Number,
                                       air_rate: Number,
                                       aspirate_rate: Number,
                                       mix_displacement: Number,
                                       mix_rate: Number,
                                       mix_iterations: int,
                                       dip_tips: ExternalWash = None,
                                       dab_tips: PokeNeedleSpec = None,
                                       arm_spec: ArmSpec = ArmSpec(),
                                       tip_method: TipExitMethod = TipExitMethod.CENTER,
                                       backlash: float = None
                                       ):
        """ Samples from a series of vials then mixes to form a single homogeneous droplet in the liquid line.

        :param components: An iterable of tuples of the form (Position, Volume in uL), eg (A1, 10).
                           Note that 0-valued and negative volumes are ignored.
        :param back_air_gap: Volume (uL) of the airgap preceding the droplet (tubing end)
        :param front_air_gap: Volume (uL) of the airgap following the droplet (needle-tip end)
        :param air_rate: Flow rate (mL/min) for air gaps
        :param aspirate_rate: Flow rate (mL/min) for sample aspiration
        :param mix_displacement: Volume (uL) of the mix command
          (if value < 0, then Volume_displacement = |value| * Volume_droplet)
        :param mix_rate: Flow rate (mL/min) for mixing
        :param mix_iterations: Number of times to mix
        :param dip_tips: Where and how to dip the needle tip
        :param dab_tips: Where and how to poke the needle tip
        :param arm_spec: How the XYZ arm should move
        :param tip_method: How the tip should exit the vials specified in components
        :param backlash: DISPENSE into each well before aspirating

        :returns: The volume of liquid comprising the droplet (does not include air-gaps)
        """
        n_components = sum([1 for _, v in components if v > 0])
        droplet_volume = sum([c[1] for c in components], start=0.0)
        if mix_displacement < 0:
            mix_displacement = abs(mix_displacement) * droplet_volume
        total_volume = back_air_gap + front_air_gap + mix_displacement + droplet_volume
        if total_volume > MAX_SYRINGE_VOL:
            raise ValueError(f"Total necessary volume ({total_volume}) exceed syringe ({MAX_SYRINGE_VOL})")

        # Take first airgap
        self._aspirate(
            AspiratePipettingSpec(
                component=AirGap(volume=back_air_gap),
                rate=air_rate,
                arm=arm_spec,
            )
        )

        # Take each sample
        first = True
        for position, volume in components:
            if not volume:
                continue
            if (not first) and dip_tips:
                self._external_wash(dip_tips)
            if (not first) and dab_tips:
                self._external_wash(dab_tips)
            first = False
            if backlash and backlash > 0:
                self.dispense(
                    component=ComponentSpec(position, backlash),
                    flow_rate=aspirate_rate,
                    arm_spec=arm_spec,
                    tip_method=TipExitMethod.NONE
                )
            self.aspirate(
                component=ComponentSpec(position, volume),
                flow_rate=aspirate_rate,
                arm_spec=arm_spec,
                tip_method=tip_method,
            )

        # Take second airgap
        self._aspirate(
            AspiratePipettingSpec(
                component=AirGap(volume=front_air_gap),
                rate=air_rate,
                arm=arm_spec,
            )
        )

        if n_components > 1:
            self._mix(
                MixingSpec(
                    mixing_displacement=mix_displacement,
                    rate=mix_rate,
                    n_iterations=mix_iterations,
                    location=None,
                    blowout_volume=None
                )
            )

        return droplet_volume

    def distribute_droplet(self,
                           destinations: Iterable[tuple[Placeable, float, bool]],
                           front_air_gap: Number,
                           air_rate: Number,
                           dispense_rate: Number,
                           dip_tips: ExternalWash = None,
                           dab_tips: PokeNeedleSpec = None,
                           arm_spec: ArmSpec = ArmSpec(),
                           tip_method: TipExitMethod = TipExitMethod.CENTER):
        """ Dispenses the contents of the needle to multiple destinations. This method is ignorant to the actual
        volume loaded in the needle.

        :param destinations: An iterable of tuples of the form (Position, Volume in uL, use free dispense).
                             Note that 0-valued and negative volumes are ignored.
        :param front_air_gap: Volume (uL) of the airgap on the tip-ward end of the droplet (restored at end)
        :param air_rate: Flow rate (mL/min) for air gaps
        :param dispense_rate: Flow rate (mL/min) for sample dispense
        :param dip_tips: Where and how to dip the needle tip
        :param dab_tips: Where and how to poke the needle tip
        :param arm_spec: How the XYZ arm should move
        :param tip_method: How the tip should exit the vials specified in components

        :returns: The total volume of liquid dispensed (does not include air-gaps)"""

        dispensed_volume = sum([c[1] for c in destinations], start=0.0)

        # Take each sample
        first = True
        ejected_airgap = False
        for position, volume, free in destinations:
            if volume <= 0:
                continue
            if (not first) and dip_tips:
                self._external_wash(dip_tips)
            if (not first) and dab_tips:
                self._external_wash(dab_tips)
            if first:
                self.dispense(
                    component=ComponentSpec(position, front_air_gap),
                    flow_rate=dispense_rate,
                    arm_spec=arm_spec,
                    tip_method=tip_method,
                    free_dispense=True
                )
                ejected_airgap = True
                first = False

            self.dispense(
                component=ComponentSpec(position, volume),
                flow_rate=dispense_rate,
                arm_spec=arm_spec,
                tip_method=tip_method,
                free_dispense=free
            )

        # restore airgap
        if ejected_airgap:
            self._aspirate(
                AspiratePipettingSpec(
                    component=AirGap(volume=front_air_gap),
                    rate=air_rate,
                    arm=arm_spec,
                )
            )

        return dispensed_volume

    @silence
    def prepare_system_diluted_stock(self,
                                     source: Placeable,
                                     destination: Placeable,
                                     total_volume: float,
                                     dilution_factor: float,
                                     aspirate_rate: Number,
                                     mix_displacement: Number,
                                     mix_rate: Number,
                                     mix_iterations: int,
                                     back_air_gap: Number,
                                     front_air_gap: Number,
                                     air_rate: Number,
                                     waste_pos: Placeable,
                                     arm_spec: ArmSpec = ArmSpec(),
                                     tip_method: TipExitMethod = TipExitMethod.CENTER):
        """ Creates a droplet inside the needle using a source well and the system fluid. Leaves with tip dirty.

        :param source: Location, where to take sample
        :param destination: Location, where to create the new vial
        :param total_volume: Final volume of the diluted solution
        :param dilution_factor: (Volume Source)/(Total Volume) = (Dilution Factor)
        :param aspirate_rate: Flow rate (mL/min) for sample aspiration
        :param mix_displacement: Volume (uL) of the mix command
          (if value < 0, then Volume_displacement = |value| * Volume_droplet)
        :param mix_rate: Flow rate (mL/min) for mixing
        :param mix_iterations: Number of times to mix
        :param back_air_gap: Volume (uL) of the airgap preceding the droplet (tubing end)
        :param front_air_gap: Volume (uL) of the airgap following the droplet (needle-tip end)
        :param air_rate: Flow rate (mL/min) for air gaps
        :param waste_pos: Where to clear the system air gap (waste)
        :param arm_spec: How the XYZ arm should move
        :param tip_method: How the tip should exit the vials specified in components
        :return: None
        """
        vol_source = total_volume*dilution_factor
        vol_diluent = total_volume - vol_source
        check_volume = back_air_gap + front_air_gap + mix_displacement + total_volume
        if check_volume > MAX_SYRINGE_VOL:
            raise ValueError(f"Total necessary volume ({check_volume}) exceed syringe ({MAX_SYRINGE_VOL})")

        source_spec = AspiratePipettingSpec(
            component=ComponentSpec(
                position=source,
                volume=vol_source
            ),
            rate=aspirate_rate,
            arm=arm_spec,
            tip_exit_method=tip_method,
        )

        source_sequence = [
            DispenseAllSpec(waste_pos, arm_spec, TipExitMethod.TIP_TOUCH, True, True),
            AspiratePipettingSpec(component=AirGap(volume=back_air_gap), rate=air_rate, arm=arm_spec),
            source_spec,
            AspiratePipettingSpec(component=AirGap(volume=front_air_gap), rate=air_rate, arm=arm_spec),
            DispensePipettingSpec(component=ComponentSpec(position=destination, volume=vol_source + front_air_gap)),
        ]
        diluent_sequence = [
            DispenseAllSpec(waste_pos, arm_spec, TipExitMethod.TIP_TOUCH, True, True),
            AspirateSystemSpec(vol_diluent, aspirate_rate),
            DispensePipettingSpec(component=ComponentSpec(position=destination, volume=vol_diluent)),
            AspiratePipettingSpec(component=AirGap(SYSTEM_AIR_GAP, waste_pos), rate=air_rate, arm=arm_spec),
        ]
        closing_sequence = [
            MixingSpec(mixing_displacement=mix_displacement, rate=mix_rate, n_iterations=mix_iterations,
                       location=(destination, arm_spec, tip_method), blowout_volume=front_air_gap + mix_displacement),
        ]
        # Do the largest volume first
        if dilution_factor >= 0.5:  # Source is largest volume
            total_sequence = source_sequence + diluent_sequence + closing_sequence
        else:  # Diluent is largest volume
            total_sequence = diluent_sequence + source_sequence + closing_sequence

        self.chain_pipette(*total_sequence)

    @silence
    def prepare_vial_diluted_stock(self,
                                   source: Placeable,
                                   diluent: Placeable,
                                   destination: Placeable,
                                   volume_source: Number,
                                   volume_diluent: Number,
                                   aspirate_rate: Number,
                                   mix_displacement: Number,
                                   mix_rate: Number,
                                   mix_iterations: int,
                                   back_air_gap: Number,
                                   front_air_gap: Number,
                                   air_rate: Number,
                                   wash_protocol: Callable = None,
                                   blowout_volume: float = 20,
                                   ):
        """ Prepares a mixture of two vials in a new vial. Leaves the tip dirty.

        :param source: Location, where to take sample
        :param diluent: Location, where to take diluent
        :param destination: Location, where to create the new vial
        :param volume_source: How much sample to use
        :param volume_diluent: How much diluent to use
        :param aspirate_rate: Flow rate (mL/min) for sample aspiration
        :param mix_displacement: Volume (uL) of the mix command
          (if value < 0, then Volume_displacement = |value| * Volume_droplet)
        :param mix_rate: Flow rate (mL/min) for mixing
        :param mix_iterations: Number of times to mix
        :param back_air_gap: Volume (uL) of the airgap preceding the droplet (tubing end)
        :param front_air_gap: Volume (uL) of the airgap following the droplet (needle-tip end)
        :param air_rate: Flow rate (mL/min) for air gaps
        :param wash_protocol: Method called at start and between wells
        :param blowout_volume: Vial mixing blowout volume
        :return: None
        """
        if wash_protocol is None:
            wash_protocol = lambda: 0
        wash_protocol()
        def _add_dye():
            self.chain_pipette(
                AspiratePipettingSpec(AirGap(back_air_gap), rate=air_rate),
                AspiratePipettingSpec(ComponentSpec(source, volume_source), rate=aspirate_rate),
                AspiratePipettingSpec(AirGap(front_air_gap), rate=air_rate),
                DispensePipettingSpec(ComponentSpec(destination, front_air_gap+volume_source+back_air_gap/2), rate=aspirate_rate)
            )
        def _add_diluent():
            self.chain_pipette(
                AspiratePipettingSpec(AirGap(back_air_gap), rate=air_rate),
                AspiratePipettingSpec(ComponentSpec(diluent, volume_diluent), rate=aspirate_rate),
                AspiratePipettingSpec(AirGap(front_air_gap), rate=air_rate),
                DispensePipettingSpec(ComponentSpec(destination, front_air_gap+volume_diluent+back_air_gap/2), rate=aspirate_rate)
            )
        if volume_source > volume_diluent:
            _add_dye()
            wash_protocol()
            _add_diluent()
        else:
            _add_diluent()
            wash_protocol()
            _add_dye()
        print(f"Mixing {mix_iterations} with {mix_displacement} uL at {mix_rate} mL/min.")
        self.chain_pipette(
            AspiratePipettingSpec(AirGap(back_air_gap), rate=air_rate),
            MixingSpec(
                mixing_displacement=mix_displacement,
                rate=mix_rate,
                n_iterations=mix_iterations,
                location=(destination, ArmSpec(), TipExitMethod.CENTER),
                blowout_volume=blowout_volume + mix_displacement
            )
        )

    def prepare_vial(self,
                     components: Iterable[tuple[Placeable, float]],
                     destination: Placeable,
                     back_air_gap: Number,
                     blow_out: Number | None,
                     air_rate: Number,
                     aspirate_rate: Number,
                     mix_displacement: Number,
                     mix_rate: Number,
                     mix_iterations: int,
                     mix_each: bool,
                     dip_tips: ExternalWash = None,
                     dab_tips: PokeNeedleSpec = None,
                     arm_spec: ArmSpec = ArmSpec(),
                     tip_method: TipExitMethod = TipExitMethod.CENTER,
                     free_dispense: bool = False
                     ):
        """ Collects samples from multiple vials into a single vial.

        :param components: An iterable of tuples of the form (Position, Volume in uL), eg (A1, 10).
                           Note that 0-valued and negative volumes are ignored.
        :param destination: Location, where to create the new vial
        :param back_air_gap: Volume (uL) of the (additional) airgap protecting the system fluid (tubing end)
        :param blow_out: Volume (uL) aspirated before mixing and ejected after mixing (None --> do not do this)
        :param air_rate: Flow rate (mL/min) for air gaps and blow out
        :param aspirate_rate: Flow rate (mL/min) for sample aspiration
        :param mix_displacement: Volume (uL) of the mix command
          (if value < 0, then Volume_displacement = |value| * Volume_droplet)
        :param mix_rate: Flow rate (mL/min) for mixing
        :param mix_iterations: Number of times to mix
        :param mix_each: True - mix after each addition, False - mix at end
        :param dip_tips: Where and how to dip the needle tip
        :param dab_tips: Where and how to poke the needle tip
        :param arm_spec: How the XYZ arm should move
        :param tip_method: How the tip should exit the vials specified in components and destination
        :param free_dispense: use free dispense when dispensing to the destination

        :returns: The volume of liquid comprising the droplet (does not include air-gaps)
        """
        components = [c for c in components if c[1] > 0]
        n_components = len(components)
        vial_volume = sum([c[1] for c in components])

        # Take first airgap
        self._aspirate(
            AspiratePipettingSpec(
                component=AirGap(volume=back_air_gap),
                rate=air_rate,
                arm=arm_spec,
            )
        )

        # Take each sample
        idx = 0
        cumulative_volume = 0.0
        for position, volume in components:
            if idx and dip_tips:
                self._external_wash(dip_tips)
            if idx and dab_tips:
                self._external_wash(dab_tips)
            self.aspirate(
                component=ComponentSpec(position, volume),
                flow_rate=aspirate_rate,
                arm_spec=arm_spec,
                tip_method=tip_method,
            )
            self.dispense(
                component=ComponentSpec(destination, volume),
                flow_rate=aspirate_rate,
                arm_spec=arm_spec,
                tip_method=tip_method,
                free_dispense=free_dispense
            )
            cumulative_volume += volume
            if mix_each or idx == (n_components - 1):
                self._mix(
                    MixingSpec(
                        mixing_displacement=mix_displacement if mix_displacement >=0 else abs(mix_displacement) * cumulative_volume,
                        rate=mix_rate,
                        n_iterations=mix_iterations,
                        location=None,
                        blowout_volume=blow_out
                    )
                )
            idx += 1

        return vial_volume


    def utilize_spectrometer(self,
                             my_spec: SpectrometerSystem,
                             volume_to_center_droplet: Number,
                             absorbance: tuple[OpticalSpecs, Callable[['SpectrometerSystem'], Spectrum]] = None,
                             photoluminescence: tuple[OpticalSpecs, Callable[['SpectrometerSystem'], Spectrum]] = None,
                             measurement_spacing: float = 1.0
                             ) -> SpectraStack:
        """ Moves a droplet into the spectrometer and performs the designated measurements.

        :param my_spec: The spectrometer to use
        :param volume_to_center_droplet: How far to move the droplet to center it in the spectrometer
        :param absorbance: How absorbance measurements should be conducted (None if not to be conducted) and what
          method to use to perform the measurement.
        :param photoluminescence: How photoluminescence measurements should be conducted (None if not to be conducted)
          and what method to use to perform the measurement.
        :param measurement_spacing: A wait time between absorbance and photoluminescence measurements.

        :return: A SpectraStack.  If both ABS and PL were requested, ABS will be first.
        """
        if absorbance:
            spec_abs, measure_abs_spectrum = absorbance
        else:
            spec_abs, measure_abs_spectrum = (None, None)
        if photoluminescence:
            spec_pl, measure_pl_spectrum = photoluminescence
        else:
            spec_pl, measure_pl_spectrum = (None, None)

        if spec_abs:
            my_spec.backend.correct_dark_counts = spec_abs.correct_dark_counts
            time.sleep(1)
            my_spec.measure_average_reference(**spec_abs, light="dark", mode="abs")
            my_spec.measure_average_reference(**spec_abs, light="light", mode="abs")

        print(f"Centering droplet ({volume_to_center_droplet} uL)")
        with redirect_stdout(StringIO()):
            self.aspirate_from_curr_pos(volume_to_center_droplet, 0.5 * DEFAULT_SYRINGE_FLOWRATE)

        print(f"Measuring spectra\n\tABS = {spec_abs}\n\tPL = {spec_pl}")
        ret = SpectraStack()
        if spec_abs is not None:
            ret.append(measure_abs_spectrum(my_spec))
        time.sleep(measurement_spacing)
        if spec_pl is not None:
            ret.append(measure_pl_spectrum(my_spec))

        print(f"Returning droplet ({volume_to_center_droplet} uL)")
        with redirect_stdout(StringIO()):
            self.dispense_to_curr_pos(volume_to_center_droplet, 0.5 * DEFAULT_SYRINGE_FLOWRATE)

        return ret

    def query_pump(self, error=True, module_id=False, syringe_size=False, motor_status=False, syringe_status=False):
        """ Quick way to query the pump """
        quick_call = partial(self.immediate_command, instrument_id=self.pump_id, verbose=0)
        if error:
            print("Error", quick_call(p_lib.ReadError()))
        if module_id:
            print("Module ID", quick_call(p_lib.GetModuleID()))
        if syringe_size:
            print("Syringe Size", quick_call(p_lib.GetSyringeSize()))
        if motor_status:
            print("Motor Status", quick_call(p_lib.GetMotorStatus()))
        if syringe_status:
            print("Syringe Status", quick_call(p_lib.GetSyringeStatus()))

    def query_arm(self, general=True, ranges=False, liquid_level=False):
        """ Quick way to query the liquid handler """
        quick_call = partial(self.immediate_command, instrument_id=self.handler_id, verbose=0)
        if general:
            print("General", quick_call(a_lib.GetStatusSummary()))
            "'Motor Status, X/Y/Z positions, Valve (Load/Inject), Error Number' (eg PPPP 100/20/125 VI E0)"
        if ranges:
            print("Ranges", quick_call(a_lib.GetTravelRanges()))
        if liquid_level:
            print("Liquid Level Oscillator", quick_call(a_lib.GetLiquidLevelFrequency()))

    def query_injector(self, error=True, module_id=False, selector_status=False):
        """ Quick way to query the injector """
        quick_call = partial(self.immediate_command, instrument_id=self.injector_id, verbose=0)
        if error:
            print("Error", quick_call(i_lib.ReadError()))
        if module_id:
            print("Module ID", quick_call(i_lib.GetModuleID()))
        if selector_status:
            print("Selector Status", quick_call(i_lib.GetInjectorStatus()))

    def injector_load(self):
        self._connect_to_injector()
        self._switch_load()
        while True:
            motor_code = self.immediate_command(self.injector_id, i_lib.GetInjectorStatus(), verbose=0)
            if DeviceStatus.busy not in motor_code:
                break

    def injector_sample(self):
        self._connect_to_injector()
        while True:
            motor_code = self.immediate_command(self.injector_id, i_lib.GetInjectorStatus(), verbose=0)
            if DeviceStatus.busy not in motor_code:
                break

    def pump_until(self, flow_rate: Number, trigger: Event):
        """ Runs the pump at a flow rate until `trigger` is set, at which point a stop signal is sent. """
        self.move_arm_z(MAX_Z_HEIGHT)

        self._connect_to_pump()
        state = self.immediate_command(self.pump_id, p_lib.GetSyringeStatus())
        current_volume = float(state[2:].strip())

        self.pump_pumping_cmd(self.pump_id, MAX_SYRINGE_VOL - current_volume, ValveStates.needle,
                              flow_rate, block=False)
        while not trigger.is_set():
            motor_code = self.immediate_command(self.pump_id, p_lib.GetMotorStatus(), verbose=0)
            if DeviceStatus.busy not in motor_code:
                return trigger
        self._stop_pump()
        return trigger

    # # While never fully implemented (having the spectrometer act as a droplet detector for auto-centering the droplet
    # #   in the flow cell), this code provides an example use case of the pump_until() method.
    # def hold_droplet_in_spectrometer(self, flow_rate: Number, spectrometer: SpectrometerSystem, **kwargs):
    #     """ Attempts to place the droplet in the path of the spectrometer.  Requires that the light and dark reference
    #      spectra have been already been defined with compatible integration times. """
    #     self.move_arm_z(MAX_Z_HEIGHT)
    #
    #     droplet_detected = Event()
    #     detect_droplet_kwargs = {
    #             'semaphore': droplet_detected,
    #             'lambda_min': 200,
    #             'lambda_max': 1000,
    #         }
    #     detect_droplet_kwargs.update(**kwargs)
    #
    #     await_droplet = Thread(
    #         target=spectrometer.detect_droplet_double_latch,
    #         kwargs=detect_droplet_kwargs
    #     )
    #     await_droplet.start()
    #
    #     droplet_detected = self.pump_until(flow_rate, droplet_detected)
    #
    #     if not droplet_detected.is_set():
    #         raise RuntimeError("Pump stopped before droplet was detected")
    #     if hasattr(droplet_detected, 'is_bad'):
    #         raise droplet_detected.is_bad


if __name__ == '__main__':
    import threading
    from gilson_liquid_handler_backend import Gilson241LiquidHandlerConfigurator

    def spin_off_dialog_box() -> Event:
        flag = Event()

        def monitor(trigger: Event):
            ui = QuickButtonUI(
                tk.Tk(),
                title="Watcher",
                dialog="Press any button when the droplet is in the detector"
            )
            ui.run()
            trigger.set()

        t = threading.Thread(target=monitor, args=(flag, ), daemon=True)
        t.start()  # the aspirate_until()/ui.run() will act as the thread.join()

        return flag


    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/Pilot_Experiments_Deck",
        bed_file="Gilson_Bed.bed"
    )  # TODO: Switch to config file to make code development on multiple computers easier
    glh.set_pump_to_volume(1000)

    helper = Gilson241LiquidHandlerConfigurator(glh)

    # helper.seek_positions()

    print(glh.immediate_command(glh.pump_id, p_lib.GetSyringeSize()))
    helper.prime_pump_at_xy(x=100, y=100, volume=MAX_SYRINGE_VOL, flow_rate=PRIMING_FLOWRATE)

    glh.prepare_droplet_in_liquid_line(
        # components=[("pos_1_rack", "A1", 5), ("pos_1_rack", "A2", 5), ("pos_1_rack", "A3", 5)],
        # You can add/remove as necessary, it will go through those positions drawing 5 uL from each
        components=[
            (glh.locate_position_name("pos_1_rack", "A1"), 15),
            (glh.locate_position_xyz(100, 100, 90))
        ],
        back_air_gap=50,
        # This is the air gap protecting your droplet from the backing fluid
        front_air_gap=30,
        # This is the air gap protecting your droplet from falling out of the needle
        air_rate=0.25,
        # This is the rate for moving air
        aspirate_rate=0.25,
        # Rate when taking up sample (mL/min)
        mix_displacement=15,
        # how many microliters to move around for mixing
        mix_rate=0.5,
        # Rate when mixing (mL/min)
        mix_iterations=2,
        # how many times to move the droplet to achieve good mixing
        dip_tips=None,
        # replace with the dip-wash solvent bottle
    )
    semaphore = spin_off_dialog_box()  # ignore this
    glh.pump_until(flow_rate=0.1, trigger=semaphore)  # set a reasonable flow rate
    # ^^^ This guy should open a dialog box then you click anything when the droplet is in position,
    #       the pump should stop and then the program will continue
    glh.move_arm_to(glh.locate_position_name("pos_1_rack", "B4"))
    glh.home_pump()  # Dumps anything remaining in the lines to well B4
    glh.home_arm()
