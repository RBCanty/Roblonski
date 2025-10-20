import datetime
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from typing import Iterable, Callable, Literal

from aux_devices.ocean_optics_spectrometer import SpectrometerSystem, OpticalSpecs
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE, Placeable, HandlerBed
from liquid_handling.gilson_handler import Gilson241LiquidHandler
# from liquid_handling.liquid_handling_specification import TipExitMethod, ExternalWash, AspiratePipettingSpec, AirGap
from workflows.common_macros import volume_to_center_droplet, record_spectrum
from data_management.apellomancer import SequentialApellomancer
from workflows.stern_volmer.naming import SVSpecDescription, SVApellomancer

COMPONENT_TYPE = tuple[Placeable, float | int]


@dataclass
class SVSpec:
    """ Description of SV-style experiment.

     - mix_iterations: int
     - mix_displacement: float
     - catalyst: COMPONENT_TYPE | None
     - quencher: COMPONENT_TYPE | None
     - diluent: COMPONENT_TYPE | None
     - spec_abs: OpticalSpecs | None
     - spec_pl: OpticalSpecs | None
     - name_wizard: SVApellomancer
    """
    mix_iterations: int = 0
    """ Number of mixing iterations """
    mix_displacement: float = -1.4
    """ (+ for absolute)/(- for relative to droplet)"""
    catalyst: COMPONENT_TYPE = None
    quencher: COMPONENT_TYPE = None
    diluent: COMPONENT_TYPE = None
    spec_abs: OpticalSpecs | None = None
    """ If (None-ness) and how to measure absorbance spectra """
    spec_pl: OpticalSpecs | None = None
    """ If (None-ness) and how to measure photoluminescence spectra """
    name_wizard: SVApellomancer | SequentialApellomancer = SequentialApellomancer("./", "Test", "test", "r")
    """ Object for determining how to save the file """

    @property
    def components(self) -> tuple[COMPONENT_TYPE, ...]:
        """ Should match Gilson241LiquidHandler.prepare_droplet_in_liquid_line() """
        return tuple(c for c in (self.catalyst, self.quencher, self.diluent) if c)

    @property
    def cat_vol(self) -> None | int | float:
        return None if self.catalyst is None else self.catalyst[1]

    @property
    def quench_vol(self) -> None | int | float:
        return None if self.quencher is None else self.quencher[1]

    @property
    def dil_vol(self) -> None | int | float:
        return None if self.diluent is None else self.diluent[1]

    def prepare_name(self, spectral_mode: Literal['ABS', 'PL'], seq: int, override_name_wizard: SVApellomancer = None):
        _name_wizard = self.name_wizard if override_name_wizard is None else override_name_wizard
        if isinstance(_name_wizard, SequentialApellomancer):
            return _name_wizard.make_file_name(spectral_mode, seq)
        return _name_wizard.make_file_name(
            cat=self.cat_vol,
            quench=self.quench_vol,
            dil=self.dil_vol,
            mix=self.mix_iterations,
            spec=spectral_mode,
            seq=seq,
        )

    def generate_tag(self):
        return (f"mix_iter={self.mix_iterations}, mix_disp={self.mix_displacement}, "
                f"vC={self.cat_vol}, vQ={self.quench_vol}, vD={self.dil_vol}")


class SVSpecFactory:
    def __init__(self,
                 name_wizard: SVApellomancer | SequentialApellomancer = None,
                 mix_iterations: int = 0,
                 spec_abs: OpticalSpecs = None,
                 spec_pl: OpticalSpecs = None,
                 mix_disp: float = -1.4):
        if name_wizard is None:
            name_wizard = SequentialApellomancer("./", "Test", "test", "r")
        self.name_wizard = name_wizard
        self.mix_iterations = mix_iterations
        self.mix_disp = mix_disp
        self.spec_abs = spec_abs
        self.spec_pl = spec_pl

    def make(self,
             catalyst: COMPONENT_TYPE = None,
             quencher: COMPONENT_TYPE = None,
             diluent: COMPONENT_TYPE = None,
             supress_measurement: bool = False):
        return SVSpec(
            mix_iterations=self.mix_iterations,
            mix_displacement=self.mix_disp,
            catalyst=catalyst,
            quencher=quencher,
            diluent=diluent,
            spec_abs=None if supress_measurement else self.spec_abs,
            spec_pl=None if supress_measurement else self.spec_pl,
            name_wizard=self.name_wizard
        )

    def make_from_description(self,
                              description: SVSpecDescription,
                              cat: Placeable, qch: Placeable, dil: Placeable
                              ):
        return SVSpec(
            mix_iterations=description.mixing_iteration,
            mix_displacement=self.mix_disp,
            catalyst=None if description.catalyst is None else (cat, description.catalyst),
            quencher=None if description.quencher is None else (qch, description.quencher),
            diluent=None if description.diluent is None else (dil, description.diluent),
            spec_abs=self.spec_abs,
            spec_pl=self.spec_pl,
            name_wizard=self.name_wizard
        )

# # Not used
# def experimental_space():
#     """ Provides a nested dictionary of experiments:
#
#     - Toplevel key: Catalyst concentration
#     - Inner key: Quencher concentration
#     - Inner value: a tuple of (catalyst, quencher, diluent) volumes
#     """
#     min_aliquot = 7
#     min_droplet = 20
#     max_droplet = 30
#     c_cat = 0.1
#     c_qch = 0.1
#     c_cat_precision = 4
#     c_qch_precision = 3
#
#     def _space():
#         for v_c in range(min_aliquot, max_droplet - min_aliquot + 1):
#             for v_q in range(min_aliquot, max_droplet - min_aliquot + 1):
#                 for v_d in range(min_aliquot, max_droplet - min_aliquot + 1):
#                     v_ta = v_c + v_q + v_d
#                     if not (min_droplet <= v_ta <= max_droplet):
#                         continue
#                     yield v_c, v_q, v_d, round(c_qch*v_q/v_ta, c_cat_precision), round(c_cat*v_c/v_ta, c_qch_precision)
#
#     const_c_cat: dict[float, list[tuple[float, float, float, float]]] = {}
#     for *_spec, _c_cat in _space():
#         const_c_cat.setdefault(_c_cat, [])
#         const_c_cat[_c_cat].append(_spec)
#     unique_space: dict[float, dict[float, tuple[float, float, float]]] = {}
#     for _c_cat, _specs in const_c_cat.items():
#         unique_space.setdefault(_c_cat, {})
#         for *_spec, _c_qch in _specs:
#             unique_space[_c_cat].setdefault(_c_qch, _spec)
#             candidate_volume = sum(_spec)
#             incumbent_volume = sum(unique_space[_c_cat][_c_qch])
#             if candidate_volume > incumbent_volume:
#                 continue
#             if candidate_volume < incumbent_volume:
#                 unique_space[_c_cat][_c_qch] = _spec
#                 continue
#             # so ==
#             candidate_min_volume = min(_spec)
#             incumbent_min_volume = min(unique_space[_c_cat][_c_qch])
#             if candidate_min_volume < incumbent_min_volume:
#                 continue
#             if candidate_min_volume > incumbent_min_volume:
#                 unique_space[_c_cat][_c_qch] = _spec
#                 continue
#             # so ==
#             pass
#
#     return unique_space


def measure_pl_spectrum(my_spec: SpectrometerSystem,
                        spec: SVSpec,
                        counter: int):
    file_name = spec.prepare_name("PL", counter)
    file_path = spec.name_wizard.make_full_path(file_name, ".csv")

    spec_tag = spec.generate_tag()
    tag = spec.spec_pl.generate_tag()
    cor_tag = spec.spec_pl.generate_corrections_tag()
    file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n"
                   f"wavelength (nm), dark reference (int), light reference (int), pl (int)\n")

    return record_spectrum(my_spec, spec.spec_pl, 'PL', file_path, file_header)


def measure_abs_spectrum(my_spec: SpectrometerSystem,
                         spec: SVSpec,
                         counter: int):
    file_name = spec.prepare_name("ABS", counter)
    file_path = spec.name_wizard.make_full_path(file_name, ".csv")

    spec_tag = spec.generate_tag()
    tag = spec.spec_abs.generate_tag()
    cor_tag = spec.spec_abs.generate_corrections_tag()
    file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n"
                   f"wavelength (nm), dark reference (int), light reference (int), abs (mAU)\n")

    return record_spectrum(my_spec, spec.spec_abs, 'ABS', file_path, file_header)


def grab_droplet_fixed(glh: Gilson241LiquidHandler,
                       spec: SVSpec,
                       wash: Placeable,
                       waste: Placeable,
                       my_spec: SpectrometerSystem,
                       counter: int,
                       ):
    back_air_gap = 20
    front_airgap = 10

    print(f"Preparing droplet {counter}")
    with redirect_stdout(StringIO()):
        droplet_volume = glh.prepare_droplet_in_liquid_line(
            components=spec.components,
            back_air_gap=back_air_gap,
            front_air_gap=front_airgap,
            air_rate=DEFAULT_SYRINGE_FLOWRATE,
            aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
            mix_iterations=spec.mix_iterations,
            mix_displacement=spec.mix_displacement,
            mix_rate=4*DEFAULT_SYRINGE_FLOWRATE,
            # dip_tips=ExternalWash(
            #     positions=wash,
            #     tip_exit_method=TipExitMethod.DRAG,
            #     air_gap=AspiratePipettingSpec(
            #         component=AirGap(position=waste, volume=10)
            #     ),
            #     n_iter=2
            # )
        )

    glh.utilize_spectrometer(
        my_spec,
        volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2),
        (spec.spec_abs, lambda _s: measure_abs_spectrum(_s, spec, counter)),
        (spec.spec_pl, lambda _s: measure_pl_spectrum(_s, spec, counter))
    )


def run_campaign[T](study: Iterable[T],
                    do_droplet_thing: Callable[[T, int], ...],
                    post: Callable[[], ...],
                    start_at: int = 0,
                    handler_bed: HandlerBed = None) -> int:
    """
    :param study: Iterable of experimental specification. Must match signature of do_droplet_thing
      and contain a 'name_tag'.
    :param do_droplet_thing: Given study and its index as the only two arguments.
    :param post: Runs after do_droplet_thing(), intended for washing
    :param start_at: Used to offset the sequence counter
    :param handler_bed: Used for resource tracking
    :return: start_index + (consumed indices) + 1, i.e., what to pass into the next run_campaign(start_at=...) call
    """
    current_volume: float | None = None
    last_idx = start_at - 1
    for idx, test in enumerate(study, start=start_at):
        if handler_bed:
            current_volume = handler_bed.read_resource_cfg().get('system_fluid_volume_mL', current_volume)
        if (current_volume is not None) and (current_volume <= 0):
            print("Safe volume exhausted, exiting.")
            raise StopIteration

        try:
            name_tag = test['name_tag']
        except TypeError:
            name_tag = ""

        print(f"Running {name_tag}  ({current_volume} mL remaining) : {datetime.datetime.now()}")
        do_droplet_thing(test, idx)
        post()
        last_idx = idx
    return last_idx + 1
