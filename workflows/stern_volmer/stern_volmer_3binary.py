import datetime
import time

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from aux_devices.spectra import ZipSpectra
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import AspiratePipettingSpec, DispensePipettingSpec, MixingSpec
from liquid_handling.liquid_handling_specification import ComponentSpec, AirGap, TipExitMethod
from liquid_handling.liquid_handling_specification import ExternalWash, Comment
from workflows.common_macros import prime, clean_up, volume_to_center_droplet, inter_clean
from workflows.stern_volmer.stern_volmer_core import SequentialApellomancer


def core_loop_scd(total_volume: int | float,
                  replaced_volume: int | float,
                  n_samples: int,
                  apellomancer: SequentialApellomancer):
    back_air_gap = 20
    front_air_gap = 10

    print(f"Preparing point 0")
    glh.prepare_droplet_in_liquid_line(
        components=(
            (CATALYST, total_volume / 2),
            (DILUENT, total_volume / 2),
        ),
        back_air_gap=back_air_gap,
        front_air_gap=front_air_gap,
        air_rate=DEFAULT_SYRINGE_FLOWRATE,
        aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        mix_displacement=-2.0,
        mix_rate=2*DEFAULT_SYRINGE_FLOWRATE,
        mix_iterations=3,
        dip_tips=ExternalWash(
            positions=EX_WASH,
            tip_exit_method=TipExitMethod.DRAG,
            air_gap=AspiratePipettingSpec(
                component=AirGap(position=WASTE, volume=10)
            ),
            n_iter=2
        ),
    )
    measure_pl(total_volume, front_air_gap, apellomancer, 0, 0.0)

    inter_clean(glh, WASTE, EX_WASH)

    print(f"Preparing point 1")
    glh.prepare_droplet_in_liquid_line(
        components=(
            (CATALYST, total_volume / 2),
            (QUENCH, total_volume / 2),
        ),
        back_air_gap=back_air_gap,
        front_air_gap=front_air_gap,
        air_rate=DEFAULT_SYRINGE_FLOWRATE,
        aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        mix_displacement=-2.0,
        mix_rate=2 * DEFAULT_SYRINGE_FLOWRATE,
        mix_iterations=3,
        dip_tips=ExternalWash(
            positions=EX_WASH,
            tip_exit_method=TipExitMethod.DRAG,
            air_gap=AspiratePipettingSpec(
                component=AirGap(position=WASTE, volume=10)
            ),
            n_iter=2
        ),
    )
    measure_pl(total_volume, front_air_gap, apellomancer, 1, 0.5)

    for idx in range(n_samples):
        glh.chain_pipette(
            Comment(message=f"Preparing point {idx+2}"),
            DispensePipettingSpec(
                component=ComponentSpec(position=WASTE, volume=front_air_gap + replaced_volume),
                free_dispense=True,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            ),
            ExternalWash(
                positions=EX_WASH,
                air_gap=AspiratePipettingSpec(
                    component=AirGap(position=EX_WASH, volume=front_air_gap)
                ),
                tip_exit_method=TipExitMethod.DRAG,
                n_iter=2
            ),
            AspiratePipettingSpec(
                component=ComponentSpec(position=CATALYST, volume=replaced_volume / 2)
            ),
            ExternalWash(
                positions=EX_WASH,
                air_gap=AspiratePipettingSpec(
                    component=AirGap(position=EX_WASH, volume=front_air_gap)
                ),
                tip_exit_method=TipExitMethod.DRAG,
                n_iter=2
            ),
            AspiratePipettingSpec(
                component=ComponentSpec(position=DILUENT, volume=replaced_volume / 2)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=front_air_gap)
            ),
            MixingSpec(
                mixing_displacement=2.0 * total_volume,
                rate=2 * DEFAULT_SYRINGE_FLOWRATE,
                n_iterations=3
            )
        )

        net_fraction = 0.5*(1 - replaced_volume / total_volume)**(idx + 1)
        measure_pl(total_volume, front_air_gap, apellomancer, idx+2, net_fraction)


def core_loop_scq(total_volume: int | float,
                  replaced_volume: int | float,
                  n_samples: int,
                  apellomancer: SequentialApellomancer):
    back_air_gap = 20
    front_air_gap = 10

    print(f"Preparing point 0")
    glh.prepare_droplet_in_liquid_line(
        components=(
            (CATALYST, total_volume / 2),
            (DILUENT, total_volume / 2),
        ),
        back_air_gap=back_air_gap,
        front_air_gap=front_air_gap,
        air_rate=DEFAULT_SYRINGE_FLOWRATE,
        aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        mix_displacement=-2.0,
        mix_rate=2*DEFAULT_SYRINGE_FLOWRATE,
        mix_iterations=3,
        dip_tips=ExternalWash(
            positions=EX_WASH,
            tip_exit_method=TipExitMethod.DRAG,
            air_gap=AspiratePipettingSpec(
                component=AirGap(position=WASTE, volume=10)
            ),
            n_iter=2
        ),
    )
    measure_pl(total_volume, front_air_gap, apellomancer, 0, 0.0)

    for idx in range(n_samples):
        glh.chain_pipette(
            Comment(message=f"Preparing point {idx+1}"),
            DispensePipettingSpec(
                component=ComponentSpec(position=WASTE, volume=front_air_gap + replaced_volume),
                free_dispense=True,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            ),
            # ExternalWash
            AspiratePipettingSpec(
                component=ComponentSpec(position=CATALYST, volume=replaced_volume / 2)
            ),
            # ExternalWash
            AspiratePipettingSpec(
                component=ComponentSpec(position=QUENCH, volume=replaced_volume / 2)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=front_air_gap)
            ),
            MixingSpec(
                mixing_displacement=2.0 * total_volume,
                rate=2 * DEFAULT_SYRINGE_FLOWRATE,
                n_iterations=3
            )
        )
        net_fraction = 0.5*(1 - (1 - replaced_volume / total_volume)**(idx + 1))
        measure_pl(total_volume, front_air_gap, apellomancer, idx+1, net_fraction)


    inter_clean(glh, WASTE,EX_WASH)

    print(f"Preparing point {n_samples+1}")
    glh.prepare_droplet_in_liquid_line(
        components=(
            (CATALYST, total_volume / 2),
            (QUENCH, total_volume / 2),
        ),
        back_air_gap=back_air_gap,
        front_air_gap=front_air_gap,
        air_rate=DEFAULT_SYRINGE_FLOWRATE,
        aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        mix_displacement=-2.0,
        mix_rate=2*DEFAULT_SYRINGE_FLOWRATE,
        mix_iterations=3,
        dip_tips=ExternalWash(
            positions=EX_WASH,
            tip_exit_method=TipExitMethod.DRAG,
            air_gap=AspiratePipettingSpec(
                component=AirGap(position=WASTE, volume=10)
            ),
            n_iter=2
        ),
    )
    measure_pl(total_volume, front_air_gap, apellomancer, n_samples+1, 0.5)


def core_loop_conv(total_volume: int | float,
                      replaced_volume: int | float,
                      n_steps_per: int,
                      apellomancer: SequentialApellomancer):
    back_air_gap = 20
    front_air_gap = 10
    global_idx = 0

    print(f"Preparing point {global_idx}")
    glh.prepare_droplet_in_liquid_line(
        components=(
            (CATALYST, total_volume / 2),
            (DILUENT, total_volume / 2),
        ),
        back_air_gap=back_air_gap,
        front_air_gap=front_air_gap,
        air_rate=DEFAULT_SYRINGE_FLOWRATE,
        aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        mix_displacement=-2.0,
        mix_rate=2*DEFAULT_SYRINGE_FLOWRATE,
        mix_iterations=3,
        dip_tips=ExternalWash(
            positions=EX_WASH,
            tip_exit_method=TipExitMethod.DRAG,
            air_gap=AspiratePipettingSpec(
                component=AirGap(position=WASTE, volume=10)
            ),
            n_iter=2
        ),
    )
    measure_pl(total_volume, front_air_gap, apellomancer, global_idx, 0.0)
    global_idx += 1

    for idx in range(n_steps_per):
        glh.chain_pipette(
            Comment(message=f"Preparing point {global_idx}"),
            DispensePipettingSpec(
                component=ComponentSpec(position=WASTE, volume=front_air_gap + replaced_volume),
                free_dispense=True,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            ),
            # ExternalWash
            AspiratePipettingSpec(
                component=ComponentSpec(position=CATALYST, volume=replaced_volume / 2)
            ),
            # ExternalWash
            AspiratePipettingSpec(
                component=ComponentSpec(position=QUENCH, volume=replaced_volume / 2)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=front_air_gap)
            ),
            MixingSpec(
                mixing_displacement=2.0 * total_volume,
                rate=2 * DEFAULT_SYRINGE_FLOWRATE,
                n_iterations=3
            )
        )
        net_fraction = 0.5*(1 - (1 - replaced_volume / total_volume)**(idx + 1))
        measure_pl(total_volume, front_air_gap, apellomancer, global_idx, net_fraction)
        global_idx += 1

    inter_clean(glh, WASTE,EX_WASH)

    print(f"Preparing point {global_idx}")
    glh.prepare_droplet_in_liquid_line(
        components=(
            (CATALYST, total_volume / 2),
            (QUENCH, total_volume / 2),
        ),
        back_air_gap=back_air_gap,
        front_air_gap=front_air_gap,
        air_rate=DEFAULT_SYRINGE_FLOWRATE,
        aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        mix_displacement=-2.0,
        mix_rate=2*DEFAULT_SYRINGE_FLOWRATE,
        mix_iterations=3,
        dip_tips=ExternalWash(
            positions=EX_WASH,
            tip_exit_method=TipExitMethod.DRAG,
            air_gap=AspiratePipettingSpec(
                component=AirGap(position=WASTE, volume=10)
            ),
            n_iter=2
        ),
    )
    measure_pl(total_volume, front_air_gap, apellomancer, global_idx, 0.5)
    global_idx += 1

    for idx in range(n_steps_per):
        glh.chain_pipette(
            Comment(message=f"Preparing point {global_idx}"),
            DispensePipettingSpec(
                component=ComponentSpec(position=WASTE, volume=front_air_gap + replaced_volume),
                free_dispense=True,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            ),
            # ExternalWash
            AspiratePipettingSpec(
                component=ComponentSpec(position=CATALYST, volume=replaced_volume / 2)
            ),
            # ExternalWash
            AspiratePipettingSpec(
                component=ComponentSpec(position=DILUENT, volume=replaced_volume / 2)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=front_air_gap)
            ),
            MixingSpec(
                mixing_displacement=2.0 * total_volume,
                rate=2 * DEFAULT_SYRINGE_FLOWRATE,
                n_iterations=3
            )
        )
        net_fraction = 0.5*(1 - replaced_volume / total_volume)**(idx + 1)
        measure_pl(total_volume, front_air_gap, apellomancer, global_idx, net_fraction)
        global_idx += 1

    inter_clean(glh, WASTE,EX_WASH)


def measure_pl(droplet_volume: int | float,
               front_airgap: int | float,
               apellomancer: SequentialApellomancer,
               seq: int, frac: float):
    my_spectrometer.backend.correct_dark_counts = pl_opt_specs.correct_dark_counts
    time.sleep(1)

    _move = volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2)
    glh.aspirate_from_curr_pos(_move, 0.5 * DEFAULT_SYRINGE_FLOWRATE)
    pl_spectrum = my_spectrometer.measure_pl_spectra(**pl_opt_specs)
    glh.dispense_to_curr_pos(_move, 0.5 * DEFAULT_SYRINGE_FLOWRATE)

    tag = pl_opt_specs.generate_tag()
    cor_tag = pl_opt_specs.generate_corrections_tag()

    file_name = apellomancer.make_file_name('PL', seq)
    file_path = apellomancer.make_full_path(file_name, ".csv")

    with open(file_path, "w+") as _file:
        _file.write(f"name, {file_name}\n{datetime.datetime.now()}\n{tag}\n{cor_tag}\nFraction, {frac}\n")
        _file.write(f"wavelength (nm), dark reference (int), light reference (int), pl (int)\n")
        ZipSpectra(pl_spectrum, my_spectrometer.pl).print(file_stream=_file)


if __name__ == '__main__':
    name_wizard = SequentialApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project/Alternate Approaches",
        project_name="SVb Tests",
        file_header="svab_rubppy_ferrocene",
        mode='w'
    )

    pl_opt_specs = OpticalSpecs(count=3, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)

    my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    CATALYST = glh.locate_position_name("pos_1_rack", "A1")
    QUENCH = glh.locate_position_name("pos_1_rack", "A2")
    DILUENT = glh.locate_position_name("pos_1_rack", "A3")

    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    # # # # START # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    prime(glh, WASTE, 600)
    my_spectrometer.measure_average_reference('pl', 'dark', **pl_opt_specs)
    my_spectrometer.measure_average_reference('pl', 'light', **pl_opt_specs)
    try:
        core_loop_scq(60, 24, 5, name_wizard)
    except KeyboardInterrupt:
        print("User exited the loop early")
    inter_clean(glh, WASTE, EX_WASH)
    clean_up(glh, WASTE)

    # # # #

    name_wizard = SequentialApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project/Alternate Approaches",
        project_name="SVb Tests",
        file_header="svab_rubppy_ferrocene",
        mode='a'
    )

    prime(glh, WASTE, 600)
    my_spectrometer.measure_average_reference('pl', 'dark', **pl_opt_specs)
    my_spectrometer.measure_average_reference('pl', 'light', **pl_opt_specs)
    try:
        core_loop_conv(50, 20, 2, name_wizard)
    except KeyboardInterrupt:
        print("User exited the loop early")
    inter_clean(glh, WASTE, EX_WASH)
    clean_up(glh, WASTE)
