import time
from typing import Callable

from aux_devices.ocean_optics_spectrometer import SpectrometerSystem, OpticalSpecs, LightSource
from data_management.common_dp_steps import SpectralProcessingSpec, take_sigal_near, take_integral, \
    find_wavelength_of_max_signal, take_sigal_at
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from workflows.common_abstractions import Fractional, Calibration
from workflows.common_macros import boot_with_user, clean_up, inter_clean, volume_to_center_droplet
from workflows.serial_measurement.naming import SMApellomancer
from workflows.serial_measurement.serial_spec import Experiment
from workflows.serial_measurement.sm_assay_core import core_loop
from workflows.serial_measurement.sm_dp import process_abs_data, process_pl_data, process_rplqy_data, ComparativeDatum


def boot(upn: str, ):
    rt_nm = SMApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name=upn,
        file_header="name__var__",  # this is meaningless (it immediately gets updated)
        mode="w"
    )
    rt_spec = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    rt_glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    rt_glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    print("\n".join(rt_glh.bed.init_message()))
    rt_glh.set_pump_to_volume(1_000)

    return rt_nm, rt_spec, rt_glh


class AbsorbanceFilter:
    def __init__(self, sel_idx: int, min_threshold: float):
        self.sel_idx = sel_idx
        self.min_threshold = min_threshold

    def serialize(self):
        sel_idx = self.sel_idx
        min_threshold = self.min_threshold
        return f"AbsorbanceFilter({sel_idx=}, {min_threshold=})"

    def __call__(self, cd: ComparativeDatum):
        return cd.signals[self.sel_idx] >= self.min_threshold


if __name__ == '__main__':
    # Specifications # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    umbrella_project_name = "BLEC Study"
    short_title = "blec"  # "rplqy"
    my_name_wizard, my_spectrometer, my_glh = boot(umbrella_project_name)
    calculate_rplqy: bool = False
    rplqy_abs_filter = AbsorbanceFilter(0, 6)

    system_fluid = "MeCN"
    system_center_droplet_callable: Callable[[float, float], float] = \
        lambda air_gap, sample_volume: volume_to_center_droplet(46, 146, 21, air_gap, sample_volume, lag=2)
    common_kwargs = {
        'sample_volume': 50.0,
        'dilution': (Fractional(1 / 3), 6),  # (Fractional(13 / 50), 8),  #
        'name_wizard': my_name_wizard,
        'locator': my_glh.locate_position_name,
        'abs_optic_spec': OpticalSpecs(count=30, interval=0.1, integration_time=40_000, correct_dark_counts=False,  # 10_000
                                       wavelength_calibration=-5, slit="S5"),
        # 'pl_optic_spec': OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000, correct_dark_counts=True,
        #                               wavelength_calibration=-5, slit="S5"),
        'target_abs_signal_init': (100, 110),
        'calibration': Calibration(-0.2440, 0.9765, floor=0.0, meta='Set Feb 4, 2025 from "Manuscript Figures Data.xlsx"')
    }

    def take_rough_signal(wv: float, tol: float):
        return take_sigal_near(wv, tol), find_wavelength_of_max_signal(wv, tol), take_sigal_at(wv)

    ledger: list[Experiment] = [
        *Experiment(
            name="RhodamineB",
            **Experiment.auto('pos_1_rack', 'M', include_working=True, include_diluent=True),
            abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(546 - 5, 5)),
            solvent="Methanol",
            measure_reference="Vial",
            source_concentration=0.009,
            **common_kwargs
        ).span_const_source('pos_1_rack', 'N', 'O'),

        *Experiment(
            name="Ferrocene",
            **Experiment.auto('pos_1_rack', 'D', include_working=True, include_diluent=True),
            abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(442 - 5, 5)),
            solvent="Cyclohexane",
            measure_reference="Vial",
            source_concentration=6.692,
            **common_kwargs
        ).span_const_source('pos_1_rack', 'E', 'F'),

        *Experiment(
            name="ZnTPP",
            **Experiment.auto('pos_1_rack', 'G', include_working=True, include_diluent=True),
            abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(422 - 5, 5) + take_rough_signal(550 - 5, 5)),
            solvent="Toluene",
            measure_reference="Vial",
            source_concentration=0.003,
            **common_kwargs
        ).span_const_source('pos_1_rack', 'H', 'I'),

        *Experiment(
            name="Perylene",
            **Experiment.auto('pos_1_rack', 'J', include_working=True, include_diluent=True),
            abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(386 - 5, 5) + take_rough_signal(408 - 5, 5) + take_rough_signal( 430 - 5, 5) + take_rough_signal(435 - 5, 5)),
            solvent="Cyclohexane",
            measure_reference="Vial",
            source_concentration=0.038,
            **common_kwargs
        ).span_const_source('pos_1_rack', 'K', 'L'),

        *Experiment(
            name="Rubpy",
            **Experiment.auto('pos_1_rack', 'A', include_working=True, include_diluent=True),
            abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(452 - 5, 5)),
            solvent="MeCN",
            measure_reference="Vial",
            source_concentration=0.105,
            **common_kwargs
        ).span_const_source('pos_1_rack', 'B', 'C'),

        Experiment(
            name="ZnPc1",
            source_init=('pos_1_rack', 'A4'),
            working_init=('pos_1_rack', 'B4'),
            diluent_init=('pos_1_rack', 'C4'),
            abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(674 - 5, 5)),
            solvent="Pyridine",
            measure_reference="Vial",
            source_concentration=0.004,
            **common_kwargs
        ),
        Experiment(
            name="ZnPc2",
            source_init=('pos_1_rack', 'A4'),
            working_init=('pos_1_rack', 'E4'),
            diluent_init=('pos_1_rack', 'F4'),
            abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(674 - 5, 5)),
            solvent="Pyridine",
            measure_reference="Vial",
            source_concentration=0.004,
            **common_kwargs
        ),
        Experiment(
            name="ZnPc3",
            source_init=('pos_1_rack', 'A4'),
            working_init=('pos_1_rack', 'H4'),
            diluent_init=('pos_1_rack', 'I4'),
            abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(674 - 5, 5)),
            solvent="Pyridine",
            measure_reference="Vial",
            source_concentration=0.004,
            **common_kwargs
        ),
    ]

    # Execution # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    WASTE = my_glh.locate_position_name('waste', "A1")
    EX_WASH = my_glh.locate_position_name('wash', "A1")

    boot_with_user(my_glh, WASTE)
    try:
        for d_idx, line in enumerate(ledger):

            if my_glh.bed is not None:
                sys_vol_remaining: float | None = my_glh.bed.read_resource_cfg().get('system_fluid_volume_mL', None)
                print(f"estimated {sys_vol_remaining} mL of system fluid remaining")
                if (sys_vol_remaining is not None) and (sys_vol_remaining < 0):
                    raise StopIteration

            print(f"\n= = = =\nCurrent dye = {line.name}")
            my_name_wizard.file_header = f"{short_title}_{line.name}"
            my_name_wizard.update_sub_directory(line.name, mode='new')

            try:
                spec_file = my_name_wizard.make_full_path(f"spec_pre_{line.name}", "exp")
                with open(spec_file, 'w') as _file:
                    _file.write(str(line))
            except Exception as e:
                print(f"DEBUG: Failed to save a copy of the Experiment Specification: {repr(e)}")

            try:
                core_loop(
                    my_glh,
                    my_spectrometer,
                    d_idx,
                    line,
                    (WASTE, EX_WASH),
                    system_center_droplet_callable,
                    cutback_to=250.0,
                    inter_callables=(process_abs_data, process_pl_data)
                )
            except KeyboardInterrupt:
                print("User aborted core loop, moving onto next sample")
            except RuntimeError as rte:
                print(f"Encountered exception: {rte!r}, moving onto next sample")

            print("Processing data")
            try:
                spec_file = my_name_wizard.make_full_path(f"spec_post_{line.name}", "exp")
                with open(spec_file, 'w') as _file:
                    _file.write(str(line))
            except Exception as e:
                print(f"DEBUG: Failed to save a copy of the Experiment Specification: {repr(e)}")
            process_abs_data(line)
            process_pl_data(line)
            if calculate_rplqy:
                time.sleep(1)  # I noticed that even though the order is ABS, then PL, then rPLQY, the files are
                # ordered (by date modified) as ABS, then rPLQY, then PL.
                try:
                    process_rplqy_data(line, 0, 0, abs_filter=rplqy_abs_filter)
                except ValueError as ve:
                    print(f"The following error prevented saving rPLQY summary data for {line.name}\n{repr(ve)}")

            print("Cleaning between samples")
            inter_clean(my_glh, WASTE, EX_WASH)

    except KeyboardInterrupt:
        print("User exited the campaign early")
    except StopIteration:
        print("Exiting early due to system volume concerns.")

    try:
        print("Shutting down")
        clean_up(my_glh, WASTE)
    except KeyboardInterrupt:
        time.sleep(3)
        my_glh.home_arm()

    print("Done!")
