import random
from typing import Generator, Any

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from workflows.common_macros import prime, clean_up, inter_clean
from workflows.stern_volmer.stern_volmer_core import grab_droplet_fixed, run_campaign, SVSpec, SVSpecFactory
from workflows.stern_volmer.naming import SVApellomancer


def manual_study(factory: SVSpecFactory,
                 min_aliquot: int = 5,
                 max_q_aliquot: int = 21,
                 step_size: int = 4,
                 max_total: int = 50
                 ) -> Generator[SVSpec, Any, None]:
    yield factory.make(catalyst=(CATALYST, max_total), quencher=(QUENCH, 0))
    yield factory.make(catalyst=(CATALYST, 0), quencher=(QUENCH, max_total))
    q_values = [q for q in range(min_aliquot, max_q_aliquot+1, step_size) if (max_total - q) >= min_aliquot]
    random.shuffle(q_values)
    print(f"Preparing to run 2+{len(q_values)} experiments...")
    for q in q_values:
        yield factory.make(catalyst=(CATALYST, max_total - q), quencher=(QUENCH, q))


def linear_study(factory: SVSpecFactory,
                 n_samples: int,
                 min_aliquot: int = 5,
                 max_total: int = 50,
                 ):
    yield factory.make(catalyst=(CATALYST, max_total), quencher=(QUENCH, 0))
    yield factory.make(catalyst=(CATALYST, 0), quencher=(QUENCH, max_total))
    interval = (max_total - 2*min_aliquot) / (n_samples - 1)
    q_values = [round(min_aliquot + idx*interval, 3) for idx in range(0, n_samples)]
    random.shuffle(q_values)
    print(f"Preparing to run 2+{len(q_values)} experiments...")
    for q in q_values:
        yield factory.make(catalyst=(CATALYST, max_total - q), quencher=(QUENCH, q))


if __name__ == '__main__':
    name_wizard = SVApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name="SV Tests",
        file_header="sva2_rubppy_ferrocene",
        mode='w'
    )

    pl_opt_specs = OpticalSpecs(count=20, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)
    abs_opt_specs = OpticalSpecs(count=20, interval=0.1, integration_time=25_000, correct_dark_counts=False)

    default_factory = SVSpecFactory(
        name_wizard,
        3,
        None,  # abs_opt_specs
        pl_opt_specs,
        mix_disp=-2.0
    )

    my_spec = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    CATALYST = glh.locate_position_name("pos_1_rack", "A1")
    QUENCH = glh.locate_position_name("pos_1_rack", "A2")

    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    # # # # START # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    prime(glh, WASTE)
    try:
        run_campaign(
            linear_study(
                default_factory,
                n_samples=5,
                min_aliquot=5,
                max_total=50,
            ),
            do_droplet_thing=lambda x, y: grab_droplet_fixed(
                glh,
                x,
                EX_WASH,
                WASTE,
                my_spec,
                y
            ),
            post=lambda: inter_clean(glh, WASTE, EX_WASH)
        )
    except KeyboardInterrupt:
        print("User exited the loop early")
    clean_up(glh, WASTE)
