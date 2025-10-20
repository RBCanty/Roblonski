import datetime
import time
from dataclasses import dataclass
from typing import Literal, Callable, NamedTuple

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from aux_devices.spectra import Spectrum
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE, Placeable, ShiftingPlaceable
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import AspiratePipettingSpec, DispensePipettingSpec, MixingSpec
from liquid_handling.liquid_handling_specification import Comment  # , ExternalWash
from liquid_handling.liquid_handling_specification import ComponentSpec, AirGap, TipExitMethod
from data_management.common_dp_steps import get_files, take_sigal_at, SpectralProcessingSpec
from workflows.common_macros import boot_with_user, clean_up, inter_clean, volume_to_center_droplet, \
    test_well, record_spectrum
from workflows.rplqy_v1.naming import RPLQYApellomancer
from workflows.common_abstractions import Dilution, Volumetric
from workflows.rplqy_v1.rplqy_dp import extract_background, extract_data, save_data_summary

COMPONENT_TYPE = tuple[ShiftingPlaceable[Placeable], float | int]
MIN_PIPETTE_VOLUME = 7
# For PL
# MAX_WORKABLE_SIGNAL = 0.110
# TARGET_WORKABLE_SIGNAL = 0.100
# For ABS
# MAX_WORKABLE_SIGNAL = 0.710
# TARGET_WORKABLE_SIGNAL = 0.700
max_workable_signal = 0.110
target_workable_signal = 0.100

NEW_VIAL_VOLUME = 250
MAX_VIAL_VOLUME = 1_000
MAX_MOVE_VOLUME = 900
BACK_AIR_GAP = 120
FRONT_AIR_GAP = 10


def _calculate_new_vial_mixing_parameters(vial_volume: float) -> tuple[float, int]:
    """
    :param vial_volume: The volume of the vial being mixing
    :return: The displacement [0] and number of iterations [1] to acheive good mixing
    """
    new_stock_mixing_displacement = 100 + (vial_volume - 250) * 100 / 750
    # This will range from 100 to 200 as vial_volume varies from 250 to 1000.
    new_stock_mixing_iterations = int(0.67 + 3 * vial_volume / new_stock_mixing_displacement)
    # This will range from 8 to 15 as vial_volume varies from 250 to 1000.
    return new_stock_mixing_displacement, new_stock_mixing_iterations


@dataclass
class RPLQYSpec:
    """ Description of SV-style experiment.

     - mix_iterations: int
     - mix_displacement: float
     - dye: COMPONENT_TYPE | None
     - dye_concentration: float | None
     - diluent: Placeable | None
     - dilution: Dilution | None
     - dilution_iterations: int
     - spec_abs: OpticalSpecs | None
     - spec_pl: OpticalSpecs | None
     - name_wizard: SVApellomancer
    """
    mix_iterations: int = 0
    """ Number of mixing iterations """
    mix_displacement: float = -3
    """ (+ for absolute)/(- for relative to droplet)"""
    dye: COMPONENT_TYPE = None
    """ (Location of Dye, Total volume of droplet) """
    dye_concentration: float = 0
    """ Source dye concentration """
    diluent: Placeable = None
    dilution: Dilution = None
    """ How are dilutions performed """
    dilution_iterations: int = 0
    """ How many in this sequence """
    spec_abs: OpticalSpecs | None = None
    """ If (None-ness) and how to measure absorbance spectra """
    spec_pl: OpticalSpecs | None = None
    """ If (None-ness) and how to measure photoluminescence spectra """
    name_wizard: RPLQYApellomancer = RPLQYApellomancer("../stern_volmer/", "Test", "test", "r")
    """ Object for determining how to save the file """

    @property
    def dilution_repr(self):
        if self.dilution is None:
            return None
        scheme_name = type(self.dilution).__name__.split(".")[-1]
        return f"{scheme_name}(value={self.dilution.value})"

    @property
    def droplet_volume(self):
        if self.dye is None:
            return None
        return self.dye[1]

    def prepare_name(self, spectral_mode: Literal['ABS', 'PL'], instance_idx: int, dil_seq_idx: int | None):
        _name_wizard = self.name_wizard
        return _name_wizard.make_file_name(
            spec=spectral_mode,
            dye_concentration=self.dye_concentration,
            total_volume=self.droplet_volume,
            mix=self.mix_iterations,
            instance_idx=instance_idx,
            dil_seq_idx=dil_seq_idx
        )

    def generate_tag(self):
        """ Produces a comma-separated tag of the form 'var=value, ...' """
        return (f"mix_iter={self.mix_iterations}, mix_disp={self.mix_displacement}\n"
                f"droplet_volume={self.droplet_volume}\n"
                f"dilution_scheme={self.dilution_repr}, n_dil={self.dilution_iterations}")


def _make_concentration_tag(spec: RPLQYSpec,
                            global_counter: int,
                            dilution_counter: int | None,
                            net_dilution: float | tuple):
    if isinstance(net_dilution, tuple):
        return (f"Conc_0={spec.dye_concentration}, nFRAC={net_dilution[0]}, "
                f"nConc_({global_counter};{dilution_counter})={net_dilution[0] * spec.dye_concentration}, "
                f"aFRAC={net_dilution[1]}, "
                f"aConc_({global_counter};{dilution_counter})={net_dilution[1] * spec.dye_concentration}")
    else:
        return (f"Conc_0={spec.dye_concentration}, FRAC={net_dilution}, "
                f"Conc_({global_counter};{dilution_counter})={net_dilution * spec.dye_concentration}")


def measure_pl_spectrum(my_spec: SpectrometerSystem,
                        spec: RPLQYSpec,
                        global_counter: int,
                        dilution_counter: int | None,
                        net_dilution: float | tuple  = 1.0):
    file_name = spec.prepare_name("PL", global_counter, dilution_counter)
    file_path = spec.name_wizard.make_full_path(file_name, ".csv")

    spec_tag = spec.generate_tag()
    tag = spec.spec_pl.generate_tag()
    cor_tag = spec.spec_pl.generate_corrections_tag()
    conc_tag = _make_concentration_tag(spec, global_counter, dilution_counter, net_dilution)
    file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n{conc_tag}\n"
                   f"wavelength (nm), dark reference (int), light reference (int), pl (int)\n")

    return record_spectrum(my_spec, spec.spec_pl, 'PL', file_path, file_header)


def measure_abs_spectrum(my_spec: SpectrometerSystem,
                         spec: RPLQYSpec,
                         global_counter: int,
                         dilution_counter: int | None,
                         net_dilution: float | tuple = 1.0):
    file_name = spec.prepare_name("ABS", global_counter, dilution_counter)
    file_path = spec.name_wizard.make_full_path(file_name, ".csv")

    spec_tag = spec.generate_tag()
    tag = spec.spec_abs.generate_tag()
    cor_tag = spec.spec_abs.generate_corrections_tag()
    conc_tag = _make_concentration_tag(spec, global_counter, dilution_counter, net_dilution)
    file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n{conc_tag}\n"
                   f"wavelength (nm), dark reference (int), light reference (int), abs (mAU)\n")

    return record_spectrum(my_spec, spec.spec_abs, 'ABS', file_path, file_header)


def core_loop(glh:Gilson241LiquidHandler, my_spec: SpectrometerSystem, global_counter: int, specification: RPLQYSpec, calibration: Callable[[float], float]):
    total_volume: float = specification.droplet_volume
    if not total_volume:
        print("No droplet volume specified, skipping...")
        return
    cal_total_volume = calibration(total_volume)

    dilution = specification.dilution
    if specification.mix_displacement > 0:
        mixing_displacement = specification.mix_displacement
    else:
        mixing_displacement = -specification.mix_displacement * total_volume

    current_dye: ShiftingPlaceable[Placeable] = specification.dye[0]
    working_pre_dilution_factor: tuple[float, float] = (1.0, 1.0)
    """ (Nominal, Actual) """
    spec_args = (specification, global_counter, None, 1.0)
    test_spectra = test_well(
        glh,
        my_spec,
        current_dye,
        total_volume,
        lambda ag, dv: volume_to_center_droplet(46, 146, 21, ag, dv, lag=2),
        absorbance=(specification.spec_abs, lambda _ms: measure_abs_spectrum(_ms, *spec_args)),
        photoluminescence=(specification.spec_pl, lambda _ms: measure_pl_spectrum(_ms, *spec_args)),
        air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
    )
    # ^ Okay, so if you have dilution counters 1...N, then you need to grab the file without a dilution counter a 0
    # But if you have 0...N, then you are good and should not grab any other files

    lb, ub, peak_func = abs_peak_method
    test_abs: Spectrum = test_spectra[0].segment(lower_bound=lb, upper_bound=ub)
    highest_peak = peak_func(test_abs) / 1000
    print(f"ABS_{global_counter} = {highest_peak} (vs {max_workable_signal})")

    too_dilute_to_do_anything = highest_peak <= max_workable_signal
    too_dilute_to_do_anything = True

    _hold_dye_vol = target_workable_signal * total_volume / highest_peak
    _replace_vol = total_volume - _hold_dye_vol
    is_feasible_to_dilute_in_needle = (_hold_dye_vol > 2*MIN_PIPETTE_VOLUME) and (_replace_vol > 2*MIN_PIPETTE_VOLUME)

    if too_dilute_to_do_anything:
        # We can't do anything about that
        #   In some reality we could try "concentrating" the sample, but for now
        print(f"Too dilute (OD = {highest_peak}) to do any corrective actions.")
        pass
    elif is_feasible_to_dilute_in_needle and False:  # "and False" --> This method is, in practice, unreliable, avoid.
        # IF: We can achieve the dilution directly in the needle
        glh.chain_pipette(
            Comment(message=f"Quick Pre-dilution"),
            DispensePipettingSpec(
                component=ComponentSpec(position=WASTE, volume=FRONT_AIR_GAP + _replace_vol),
                free_dispense=True,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            ),
            # ExternalWash(
            #     positions=EX_WASH,
            #     air_gap=AspiratePipettingSpec(
            #         component=AirGap(position=EX_WASH, volume=front_air_gap)
            #     ),
            #     tip_exit_method=TipExitMethod.DRAG,
            #     n_iter=2
            # ),
            AspiratePipettingSpec(
                component=ComponentSpec(position=DILUENT, volume=_replace_vol)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=FRONT_AIR_GAP)
            ),
            MixingSpec(
                mixing_displacement=mixing_displacement,
                rate=4 * DEFAULT_SYRINGE_FLOWRATE,
                n_iterations=specification.mix_iterations
            )
        )
        working_pre_dilution_factor = (
            (total_volume - _replace_vol)/total_volume,
            (cal_total_volume - calibration(_replace_vol))/cal_total_volume
        )
        spec_args = (specification, global_counter, 0, working_pre_dilution_factor)
        glh.utilize_spectrometer(
            my_spec,
            volume_to_center_droplet(46, 146, 21, FRONT_AIR_GAP, total_volume, lag=2),
            absorbance=(specification.spec_abs, lambda _ms: measure_abs_spectrum(_ms, *spec_args)),
            photoluminescence=(specification.spec_pl, lambda _ms: measure_pl_spectrum(_ms, *spec_args))
        )
    else:
        # We need to prepare a new Dye well.
        if highest_peak < 0.1:
            ratio = target_workable_signal / highest_peak  # < 1.0 (this case shouldn't ever be called)
            print(f"Why are we preparing a new well when the highest peak is less than 0.1 AU?")
        else:
            scaling_basis = 1.01
            highest_peak = highest_peak * (scaling_basis ** (highest_peak/0.10 - 1))
            ratio = target_workable_signal / highest_peak
            # ^ This is an attempt to capture the non-linearity of highly concentrated solutions
            # Roughly, it says "treat (in mAU) 100 (actual value) as 100 (for the math), 500 as 520, 1000 as 1100,
            #   2000 as 2400, 3000 as 4000".

        total_parts = 1/min(ratio, 1 - ratio)
        volume_per_part = NEW_VIAL_VOLUME / total_parts
        if volume_per_part < 2*MIN_PIPETTE_VOLUME:
            volume_per_part = 2*MIN_PIPETTE_VOLUME

        print(f"DEBUG: Preparing new well: {ratio=}, {total_parts=}, {volume_per_part=}")

        total_new_stock_volume = volume_per_part * total_parts
        new_stock_dye_volume = volume_per_part * (ratio * total_parts)
        new_stock_dil_volume = volume_per_part * ((1 - ratio)*total_parts)

        enough_volume_in_vial = total_new_stock_volume <= MAX_VIAL_VOLUME
        enough_volume_in_syr = (new_stock_dye_volume <= MAX_MOVE_VOLUME) and (new_stock_dil_volume <= MAX_MOVE_VOLUME)
        if not (enough_volume_in_vial and enough_volume_in_syr):
            print(f"Not enough volume to prepare a new stock solution, \n"
                  f"{target_workable_signal / highest_peak = }\n"
                  f"Adjusted highest_peak = {(10 ** 0.5) * highest_peak ** 1.5}\n"
                  f"{total_new_stock_volume <= MAX_VIAL_VOLUME = }\n"
                  f"{new_stock_dye_volume <= MAX_MOVE_VOLUME = }\n"
                  f"{new_stock_dil_volume <= MAX_MOVE_VOLUME = }\n"
                  f"skipping...")
            return

        dye_source: Placeable = current_dye.place                     # ## ############### ### ### #### ########### ## #
        current_dye.next()                                            # ## SPECIFICATION'S DYE HAS BEEN INCREMENTED !! #
                                                                      # ## ############### ### ### #### ########### ## #

        _nv_mix_disp, _nv_mix_iter = _calculate_new_vial_mixing_parameters(total_new_stock_volume)
        glh.prepare_vial_diluted_stock(
            source=dye_source,
            diluent=specification.diluent,
            destination=current_dye,
            volume_source=new_stock_dye_volume,
            volume_diluent=new_stock_dil_volume,
            aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
            mix_displacement=_nv_mix_disp,
            mix_rate=4*DEFAULT_SYRINGE_FLOWRATE,
            mix_iterations=_nv_mix_iter,
            back_air_gap=BACK_AIR_GAP,
            front_air_gap=FRONT_AIR_GAP,
            air_rate=DEFAULT_SYRINGE_FLOWRATE,
            wash_protocol=lambda: inter_clean(glh, WASTE, EX_WASH, 200),
            blowout_volume=20
        )
        inter_clean(glh, WASTE, EX_WASH, 200)

        working_pre_dilution_factor = (
            new_stock_dye_volume / total_new_stock_volume,
            calibration(new_stock_dye_volume) / calibration(total_new_stock_volume)
        )
        spec_args = (specification, global_counter, 0, working_pre_dilution_factor)
        test_well(
            glh,
            my_spec,
            current_dye,
            total_volume,
            lambda ag, dv: volume_to_center_droplet(46, 146, 21, ag, dv, lag=2),
            absorbance=(specification.spec_abs, lambda _ms: measure_abs_spectrum(_ms, *spec_args)),
            photoluminescence=(specification.spec_pl, lambda _ms: measure_pl_spectrum(_ms, *spec_args)),
            air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
        )

    # To recap that massive IF-ELIF-ELSE Clause:
    #   If the solution was too dilute to do anything, we just perform serial dilution on the droplet already in the
    #     needle. Dilution counter starts at 1. In data processing, the lack of an index 0 will tell us to look for
    #     the file without an index and treat that at index 0. (index 0 --> no dilution)
    #   If the solution was too concentrated, but could be diluted in the needle, we do so. Then we measure the
    #     droplet again, this time with an index of 0.
    #   If the solution was way too concentrated, we prepare a new, diluted stock solution on the platform. Then we
    #     make a new droplet and measure it (with an index of 0).
    #   Ultimately, regardless of path, we have a droplet in the needle with a back air gap and offset from the tip
    #     by the front air gap's volume.  We want to start with dilution counter 1, and proceed from there.

    replaced_volume = dilution.get_volume(total_volume)
    for dil_dx in range(specification.dilution_iterations):
        glh.chain_pipette(
            Comment(message=f"Dilution step {dil_dx + 1}"),
            DispensePipettingSpec(
                component=ComponentSpec(position=WASTE, volume=FRONT_AIR_GAP),
                free_dispense=True,
                tip_exit_method=TipExitMethod.CENTER
            ),
            DispensePipettingSpec(
                component=ComponentSpec(position=WASTE, volume=replaced_volume),
                free_dispense=True,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            ),
            AspiratePipettingSpec(
                component=ComponentSpec(position=DILUENT, volume=replaced_volume)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=FRONT_AIR_GAP)
            ),
            MixingSpec(
                mixing_displacement=3.0 * total_volume,
                rate=2 * DEFAULT_SYRINGE_FLOWRATE,
                n_iterations=3
            ),
        )

        nominal_dilution_factor = 1 - (replaced_volume / total_volume)
        nom_net_fraction = working_pre_dilution_factor[0] * (nominal_dilution_factor ** (dil_dx + 1))
        actual_dilution_factor = 1 - calibration(replaced_volume) / cal_total_volume
        cal_net_fraction = working_pre_dilution_factor[1] * (actual_dilution_factor ** (dil_dx + 1))

        spec_args = (specification, global_counter, dil_dx + 1, (nom_net_fraction, cal_net_fraction))
        glh.utilize_spectrometer(
            my_spec,
            volume_to_center_droplet(46, 146, 21, FRONT_AIR_GAP, total_volume, lag=2),
            absorbance=(specification.spec_abs, lambda _ms: measure_abs_spectrum(_ms, *spec_args)),
            photoluminescence=(specification.spec_pl, lambda _ms: measure_pl_spectrum(_ms, *spec_args))
        )
    inter_clean(glh, WASTE, EX_WASH, 200)


class LedgerLine(NamedTuple):
    name: str
    concentration: float
    source: tuple[str, str]
    alt_source: tuple[str, str]
    diluent: tuple[str, str]
    absorption: SpectralProcessingSpec
    photoluminescence: SpectralProcessingSpec
    abs_target_val: float
    solvent: str

    @property
    def meta(self):
        return self.name, self.concentration, self.solvent


if __name__ == '__main__':
    import os

    umbrella_project_name = "Beer-Lambert Study"
    my_name_wizard = RPLQYApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name=umbrella_project_name,
        file_header="rplqy__var__",
        mode="w"
    )
    my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    my_glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    my_glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    my_glh.set_pump_to_volume(1_000)

    # Specifications # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    system_fluid = "MeCN"
    abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False)
    pl_opt_specs = None  # OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)
    ledger = [
        LedgerLine(
            name="rubpy5",
            concentration=0.2,
            source=("pos_1_rack", "A1"),
            alt_source=("pos_1_rack", "A2"),
            diluent=("pos_1_rack", "A3"),
            absorption=SpectralProcessingSpec(350, 800, take_sigal_at(452)),
            photoluminescence=SpectralProcessingSpec(None, None, take_sigal_at(610)),
            abs_target_val=0.1,
            solvent=system_fluid
        ),
        # LedgerLine(
        #     name="rubpy2",
        #     concentration=0.4,
        #     source=("pos_1_rack", "B1"),
        #     alt_source=("pos_1_rack", "B2"),
        #     diluent=("pos_1_rack", "B3"),
        #     absorption=(350, 800, take_sigal_at(452)),
        #     photoluminescence=(None, None, take_sigal_at(610)),
        #     abs_target_val=0.1,
        #     solvent=system_fluid
        # ),
        # LedgerLine(
        #     name="rubpy3",
        #     concentration=0.8,
        #     source=("pos_1_rack", "C1"),
        #     alt_source=("pos_1_rack", "C2"),
        #     diluent=("pos_1_rack", "C3"),
        #     absorption=(350, 800, take_sigal_at(452)),
        #     photoluminescence=(None, None, take_sigal_at(610)),
        #     abs_target_val=0.1,
        #     solvent=system_fluid
        # ),
        # LedgerLine(
        #     name="rubpy4",
        #     concentration=0.6,
        #     source=("pos_1_rack", "D1"),
        #     alt_source=("pos_1_rack", "D2"),
        #     diluent=("pos_1_rack", "D3"),
        #     absorption=(350, 800, take_sigal_at(452)),
        #     photoluminescence=(None, None, take_sigal_at(610)),
        #     abs_target_val=0.1,
        #     solvent=system_fluid
        # ),
    ]
    dye_wells: list[ShiftingPlaceable[Placeable]] = [
        ShiftingPlaceable[Placeable](
            [
                my_glh.locate_position_name(*x.source),  # use this for dye
                my_glh.locate_position_name(*x.alt_source)  # use this to prepare a diluted stock
            ]
        )
        for x in ledger
    ]
    dil_wells: list[Placeable] = [my_glh.locate_position_name(*x.diluent) for x in ledger]

    DYE = ShiftingPlaceable[ShiftingPlaceable[Placeable]](dye_wells)
    DILUENT = ShiftingPlaceable[Placeable](dil_wells)

    WASTE = my_glh.locate_position_name('waste', "A1")
    EX_WASH = my_glh.locate_position_name('wash', "A1")

    sample_volume = 50
    dilution_spec = Volumetric(sample_volume / 3)
    # dilution_spec = Volumetric(sample_volume / 4)

    boot_with_user(my_glh, WASTE)
    try:
        for d_idx, line in enumerate(ledger):
            print(f"Current dye = {line.name}")
            my_name_wizard.file_header = f"blec_{line.name}"
            my_name_wizard.update_sub_directory(line.name)
            abs_peak_method = line.absorption  # <-- wah

            max_workable_signal = line.abs_target_val + 0.010
            target_workable_signal = line.abs_target_val

            this_experiment = RPLQYSpec(
                mix_iterations=4,
                mix_displacement=-3,
                dye=(DYE.place, sample_volume),  # (Where is the dye, what is the total droplet size)
                dye_concentration=line.concentration,
                diluent=DILUENT,
                dilution=dilution_spec,
                dilution_iterations=6,
                spec_abs=abs_opt_specs,
                spec_pl=pl_opt_specs,
                name_wizard=my_name_wizard
            )

            if pl_opt_specs is not None:
                my_spectrometer.measure_average_reference('pl', 'dark', **pl_opt_specs)
                time.sleep(1)
                my_spectrometer.measure_average_reference('pl', 'light', **pl_opt_specs)
                time.sleep(1)
            if (abs_opt_specs is not None) and (line.solvent != system_fluid):
                ref_spec_args = (this_experiment, None, None, (0, 0))
                test_well(
                    my_glh,
                    my_spectrometer,
                    DILUENT,
                    this_experiment.droplet_volume,
                    lambda ag, dv: volume_to_center_droplet(46, 146, 21, ag, dv, lag=2),
                    absorbance=(abs_opt_specs, lambda _ms: measure_abs_spectrum(_ms, *ref_spec_args)),
                    photoluminescence=(pl_opt_specs, lambda _ms: measure_pl_spectrum(_ms, *ref_spec_args)),
                    air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
                )

            try:
                core_loop(
                    my_glh,
                    my_spectrometer,
                    d_idx,
                    this_experiment,
                    lambda x: max(0.0, 0.9765 * float(x) - 0.2440)  # Set Feb 4, 2025 from "Manuscript Figures Data.xlsx"
                )
            except KeyboardInterrupt:
                print(f"User stopped serial dilution early, moving to data processing in 5 seconds")
                time.sleep(5)

            if abs_opt_specs:
                try:
                    my_data_files = get_files(directory=my_name_wizard.project_directory, key="_ABS_")
                    bkg = extract_background(my_data_files, my_name_wizard)
                    my_data_entries = extract_data(my_data_files, my_name_wizard, line.concentration, line.absorption, bkg)
                    if my_data_entries:
                        save_data_summary(my_data_entries, os.path.join(my_name_wizard.project_directory, f"{line.name}_abs_summary.csv"), line.absorption)
                    else:
                        print(f"No abs data found for {line.name}?")
                except Exception as e:
                    print(f"The following error prevented saving ABS summary data for {line.name}")
                    print(repr(e))

            if pl_opt_specs:
                try:
                    my_data_files = get_files(directory=my_name_wizard.project_directory, key="_PL_")
                    bkg = extract_background(my_data_files, my_name_wizard)
                    my_data_entries = extract_data(my_data_files, my_name_wizard, line.concentration, line.photoluminescence, bkg)
                    if my_data_entries:
                        save_data_summary(my_data_entries, os.path.join(my_name_wizard.project_directory, f"{line.name}_pl_summary.csv"), line.photoluminescence)
                    else:
                        print(f"No pl data found for {line.name}?")
                except Exception as e:
                    print(f"The following error prevented saving PL summary data for {line.name}")
                    print(repr(e))

            inter_clean(my_glh, WASTE, EX_WASH)
            if my_glh.bed is not None:
                sys_vol_remaining: float | None = my_glh.bed.read_resource_cfg().get('system_fluid_volume_mL', None)
                print(f"estimated {sys_vol_remaining} mL of system fluid remaining")
                if (sys_vol_remaining is not None) and (sys_vol_remaining < 0):
                    raise StopIteration

            dye_check = DYE.next()
            dil_check = DILUENT.next()
            print(f"Changing analyte [debug: {dye_check=}, {dil_check=}")
    except KeyboardInterrupt:
        print("User exited the loop early")
    except StopIteration:
        print("Exiting early due to system volume concerns.")



    clean_up(my_glh, WASTE)
