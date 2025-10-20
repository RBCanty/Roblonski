from enum import StrEnum, auto
from typing import NamedTuple

from deck_layout.handler_bed import Placeable, DEFAULT_XY_SPEED, DEFAULT_Z_SPEED, DEFAULT_SYRINGE_FLOWRATE
from misc_func import Number


class ComponentSpec(NamedTuple):
    """
    - position = A Placeable object
    - volume = A number or None
    """
    position: Placeable
    volume: Number | None

    def updated_copy(self, **kwargs):
        return ComponentSpec(**{**self._asdict(), **kwargs})


class AirGap(NamedTuple):
    """
    - volume = A number
    - position = A Placeable object or None (Default: None)
    """
    volume: Number
    position: Placeable | None = None

    def updated_copy(self, **kwargs):
        return AirGap(**{**self._asdict(), **kwargs})


class ArmSpec(NamedTuple):
    """
    - xy_speed = How fast the robotic arm should move in the xy plane
    - z_speed = How fast the cannula should move up/down
    """
    xy_speed: int = DEFAULT_XY_SPEED
    z_speed: int = DEFAULT_Z_SPEED

    def updated_copy(self, **kwargs):
        return ArmSpec(**{**self._asdict(), **kwargs})


class TipExitMethod(StrEnum):
    """
    - CENTER = Draw straight up (z)
    - TIP_TOUCH = Draw straight up to the access point (z), then tap against the edge/rim of the vial (xy, xy)
    - DRAG = Move to the edge of the vial (xy), then draw up (z), then move back (xy)
    """
    CENTER = auto()
    TIP_TOUCH = auto()
    DRAG = auto()
    NONE = auto()


class DispensePipettingSpec(NamedTuple):
    """
    - component = A ComponentSpec or AirGap
    - rate = A Number describing the dispense flow rate
    - arm = An ArmSpec describing how the XYZ robot should move
    - sensor_depth = Leave as None until implemented (future: Go to the liquid level then sensor_depth mm deeper)
    - tip_exit_method = A TipExitMethod specifying how the tip should be removed
    - free_dispense = A boolean: if False (default), dispense with the tip at the bottom of the vial, otherwise,
      dispense from the access Z height (so not in contact with the existing liquid in the vial).
    - disp_on_edge = If true it will move to the tip-touch position before dispensing
    """
    component: ComponentSpec | AirGap
    rate: Number = DEFAULT_SYRINGE_FLOWRATE
    arm: ArmSpec = ArmSpec()
    sensor_depth: Number | None = None
    tip_exit_method: TipExitMethod = TipExitMethod.CENTER
    free_dispense: bool = False
    disp_on_edge: bool = False

    def updated_copy(self, **kwargs):
        return DispensePipettingSpec(**{**self._asdict(), **kwargs})


class DispenseAllSpec(NamedTuple):
    """
    - position = Where to dispense
    - arm = An ArmSpec describing how the XYZ robot should move
    - tip_exit_method = A TipExitMethod specifying how the tip should be removed
    - free_dispense = A boolean: if False (default), dispense with the tip at the bottom of the vial, otherwise,
      dispense from the access Z height (so not in contact with the existing liquid in the vial).
    - disp_on_edge = If true it will move to the tip-touch position before dispensing
    """
    position: Placeable
    arm: ArmSpec = ArmSpec()
    tip_exit_method: TipExitMethod = TipExitMethod.CENTER
    free_dispense: bool = False
    disp_on_edge: bool = False

    def updated_copy(self, **kwargs):
        return DispenseAllSpec(**{**self._asdict(), **kwargs})


class AspiratePipettingSpec(NamedTuple):
    """
    - component = A ComponentSpec or AirGap
    - rate = A Number describing the aspiration flow rate
    - arm = An ArmSpec describing how the XYZ robot should move
    - sensor_depth = Leave as None until implemented (future: Go to the liquid level then sensor_depth mm deeper)
    - tip_exit_method = A TipExitMethod specifying how the tip should be removed
    """
    component: ComponentSpec | AirGap
    rate: Number = DEFAULT_SYRINGE_FLOWRATE
    arm: ArmSpec = ArmSpec()
    sensor_depth: Number | None = None
    tip_exit_method: TipExitMethod = TipExitMethod.CENTER

    def updated_copy(self, **kwargs):
        return AspiratePipettingSpec(**{**self._asdict(), **kwargs})

    def cast_to_dispense(self, free_dispense: bool = False) -> DispensePipettingSpec:
        return DispensePipettingSpec(*self, free_dispense=free_dispense)


class AspirateSystemSpec(NamedTuple):
    """
    - volume = Volume to pull from the reservoir
    - rate = A Number describing the aspiration flow rate
    """
    volume: Number
    rate: Number = DEFAULT_SYRINGE_FLOWRATE

    def updated_copy(self, **kwargs):
        return AspiratePipettingSpec(**{**self._asdict(), **kwargs})


class MixingSpec(NamedTuple):
    """
    - mixing_displacement = The volume to move while mixing
    - rate = The volumetric flow rate used while mixing
    - n_iterations = How many aspirate/dispense cycles to perform (default = 1)
    - location = Where to perform the mixing operation (default = None).  If None, then mix at max Z height.
      If specified, then mix in the vial.
    - blowout_volume = A volume of air to take before mixing and expel after mixing.
    """
    mixing_displacement: Number
    rate: Number = DEFAULT_SYRINGE_FLOWRATE
    n_iterations: int = 1
    location: tuple[Placeable, ArmSpec, TipExitMethod] | None = None
    """ (Where, how it should move to the vial, how it should exit the vial) """
    blowout_volume: Number | None = 10.0

    def updated_copy(self, **kwargs):
        return MixingSpec(**{**self._asdict(), **kwargs})


class ExternalWash(NamedTuple):
    """
    - positions = Placeable(s) of where to dip
    - arm = An ArmSpec describing how the XYZ robot should move when dipping
    - tip_exit_method = A TipExitMethod specifying how the tip should be removed when dipping
    - air_gap = An AspiratePipettingSpec which controls the front air gap for the wash -- arm, tip_exit_method, etc.
      specified within this specification will apply only to actions involving the air gap
    - n_iter = Number of times to dip the needle (per position)
    """
    positions: Placeable | tuple[Placeable]
    arm: ArmSpec = ArmSpec()
    tip_exit_method: TipExitMethod = TipExitMethod.CENTER
    air_gap: AspiratePipettingSpec | None = None
    n_iter: int = 1

    def updated_copy(self, **kwargs):
        return ExternalWash(**{**self._asdict(), **kwargs})


class InternalWash(NamedTuple):
    """
    - washing_displacement = The volume to move while mixing
    - location = Where to wash
    - n_iterations = How many aspirate/dispense cycles to perform (default = 1)
    - rate = The volumetric flow rate used while mixing
    - blowout_volume = A volume of air to take before mixing and expel after mixing.
    - arm = An ArmSpec describing how the XYZ robot should move when dipping
    - tip_exit_method = A TipExitMethod specifying how the tip should be removed when dipping
    """
    washing_displacement: Number
    location: Placeable
    n_iterations: int = 1
    rate: Number = DEFAULT_SYRINGE_FLOWRATE
    blowout_volume: Number | None = None
    arm: ArmSpec = ArmSpec()
    tip_exit_method: TipExitMethod = TipExitMethod.CENTER

    def updated_copy(self, **kwargs):
        return InternalWash(**{**self._asdict(), **kwargs})

    def cast_to_mix(self):
        return MixingSpec(
            mixing_displacement=self.washing_displacement,
            rate=self.rate,
            n_iterations=self.n_iterations,
            location=(self.location, self.arm, self.tip_exit_method),
            blowout_volume=self.blowout_volume
        )


class InternalClean(NamedTuple):
    """
    - cleaning_volume = How much volume to throw
    - location = Where to wash
    - n_iterations = How many times to cycle
    - rate = The volumetric flow rate used while washing
    - free_dispense = A boolean: if False (default), dispense with the tip at the bottom of the vial, otherwise,
      dispense from the access Z height (so not in contact with the existing liquid in the vial).
    - pre_flush = Empty the syringe (home the pump) before washing cycle
    - arm = An ArmSpec describing how the XYZ robot should move
    - tip_exit_method: TipExitMethod = A TipExitMethod specifying how the tip should be removed when dipping
    - disp_on_edge = If true it will move to the tip-touch position before dispensing
    """
    cleaning_volume: Number
    location: Placeable
    n_iterations: int = 1
    rate: Number = DEFAULT_SYRINGE_FLOWRATE
    free_dispense: bool = False
    disp_on_edge: bool = False
    pre_flush: bool = True
    arm: ArmSpec = ArmSpec()
    tip_exit_method: TipExitMethod = TipExitMethod.CENTER

    def updated_copy(self, **kwargs):
        return InternalClean(**{**self._asdict(), **kwargs})


class Comment(NamedTuple):
    message: str


class UserIntervention(NamedTuple):
    prompt: str
    title: str = "User action required"
    home_arm: bool = True


class Wait(NamedTuple):
    duration: float
    """ Minutes """


class PokeNeedleSpec(ExternalWash):
    """
    - positions = Placeable(s) of where to poke the needle
    - arm = An ArmSpec describing how the XYZ robot should move when poking
    - tip_exit_method = A TipExitMethod specifying how the tip should be removed when poking
    - air_gap = An AspiratePipettingSpec which controls the front air gap for the poke -- arm, tip_exit_method, etc.
      specified within this specification will apply only to actions involving the air gap
    - n_iter = Number of times to poke the needle (per position)
    """
    pass
