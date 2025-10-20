import datetime
import time
from contextlib import redirect_stdout
from io import StringIO

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from workflows.common_macros import prime, clean_up, inter_clean, volume_to_center_droplet
from workflows.stern_volmer.naming import SVApellomancer
from workflows.stern_volmer.stern_volmer_core import run_campaign, measure_abs_spectrum, SVSpecFactory, SVSpec


def define_study(factory: SVSpecFactory, n_sets: int, runs_per_set: int):
    yield factory.make(diluent=(NATED, 30))
    # yield factory.make(quencher=(NATING, 30))
    for i in range(n_sets * runs_per_set + 1):
        yield factory.make(catalyst=(RESET, 10), quencher=(NATING, 15), diluent=(NATED, 15), supress_measurement=True)
        if i % runs_per_set == 0:
            yield factory.make(diluent=(NATED, 30))


def droplet_thing(spec: SVSpec, counter: int):

    back_air_gap = 20
    front_airgap = 10

    print(f"Taking sample: {counter}")
    with redirect_stdout(StringIO()):
        droplet_volume = glh.prepare_droplet_in_liquid_line(
            components=spec.components,
            back_air_gap=back_air_gap,
            front_air_gap=front_airgap,
            air_rate=DEFAULT_SYRINGE_FLOWRATE,
            aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
            mix_iterations=spec.mix_iterations,
            mix_displacement=-3,  # negative means droplet volumes (instead of constant displacement)
            mix_rate=2 * DEFAULT_SYRINGE_FLOWRATE,
            # dip_tips=ExternalWash(
            #     positions=EX_WASH,
            #     tip_exit_method=TipExitMethod.DRAG,
            #     air_gap=AspiratePipettingSpec(
            #         component=AirGap(position=WASTE, volume=10)
            #     ),
            #     n_iter=2
            # ),
            dab_tips=needle_dab,
        )

    if spec.spec_abs:
        print("Collecting reference spectra")
        my_spec.backend.correct_dark_counts = spec.spec_abs.correct_dark_counts
        time.sleep(1)
        my_spec.measure_average_reference(**spec.spec_abs, light="dark", mode="abs")
        my_spec.measure_average_reference(**spec.spec_abs, light="light", mode="abs")

        _move = volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2)
        print(f"Centering droplet ({_move} uL)")
        with redirect_stdout(StringIO()):
            glh.aspirate_from_curr_pos(_move, 0.5*DEFAULT_SYRINGE_FLOWRATE)

        print(f"Measuring spectra for {counter}")
        measure_abs_spectrum(my_spec, spec, counter)
    else:
        try:
            with open(spec.name_wizard.make_full_path(f"timer", ".csv"), 'a+') as _file:
                print(f"{counter}, {datetime.datetime.now()}", end='\n', file=_file)
        except:
            pass


if __name__ == '__main__':
    name_wizard = SVApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name="Contamination Study",
        file_header="sva_style_3src_cap",
        mode='w'
    )

    abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False)

    default_factory = SVSpecFactory(
        name_wizard,
        3,
        abs_opt_specs,
        None
    )

    my_spec = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    RESET = glh.locate_position_name("pos_1_rack", "A1")
    NATING = glh.locate_position_name("pos_1_rack", "A2")
    NATED = glh.locate_position_name("pos_1_rack", "A3")

    DAB = glh.locate_position_name("pos_1_rack", "A4")

    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    needle_dab = None  # PokeNeedleSpec(positions=DAB)  # None

    # print("Waiting 30 minutes for lamp to warm up")
    # for w in range(6):
    #     time.sleep(5*60)
    #     print(f"\t{(w+1)*5} min down")

    prime(glh, WASTE)
    try:
        run_campaign(
            define_study(default_factory, 5, 3),
            do_droplet_thing=droplet_thing,
            post=lambda: inter_clean(glh, WASTE, EX_WASH)
        )
    except KeyboardInterrupt:
        print("User exited the loop early")
    clean_up(glh, WASTE)
