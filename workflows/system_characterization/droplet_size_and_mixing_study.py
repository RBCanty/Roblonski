from dataclasses import dataclass

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from workflows.common_macros import prime, clean_up, inter_clean
from misc_func import shuffle_study
from workflows.stern_volmer.naming import SVApellomancer
from workflows.stern_volmer.stern_volmer_core import SVSpecFactory, grab_droplet_fixed, run_campaign


@dataclass()
class MixingSpec:
    droplet_volume: float
    mixing_displacement: float
    """ (+) for absolute displacement in uL / (-) for relative displacement [multiple of droplet_volume] """
    number_of_cycles: int


def _create_mixings():
    spans = {
        9: [1.4, 1.1],
        7: [1.7, 1.4, 1.1],
        5: [2.0, 1.7, 1.4, 1.1],
        3: [2.0, 1.7, 1.4, 1.1]
    }
    for droplet_volume in [40, ]:  # [40, 45, 50]:
        for n_cycles, rel_disps in spans.items():
            for rel_disp in rel_disps:
                yield MixingSpec(droplet_volume, -rel_disp, n_cycles)


def _create_concentrations(factory: SVSpecFactory,
                           n_samples: int,
                           min_aliquot: float | int,
                           max_total: float | int):
    catalyst_vol = 10
    available = max_total - catalyst_vol
    interval = (max_total - catalyst_vol - 2 * min_aliquot) / (n_samples - 1)
    q_values = [round(min_aliquot + idx * interval, 3) for idx in range(0, n_samples)]
    for q in q_values:
        yield factory.make(catalyst=(CATALYST, catalyst_vol), quencher=(QUENCH, q), diluent=(DILUENT, available - q))


def create_study():
    default_factory = SVSpecFactory(
        name_wizard,
        0,
        abs_opt_specs,
        None,
        0
    )
    yield default_factory.make(catalyst=(CATALYST, 0), quencher=(QUENCH, 50), diluent=(DILUENT, 0))
    for mix_spec in _create_mixings():
        default_factory.mix_iterations = mix_spec.number_of_cycles
        default_factory.mix_disp = mix_spec.mixing_displacement
        yield from _create_concentrations(default_factory, 3, 7, mix_spec.droplet_volume)


if __name__ == '__main__':
    name_wizard = SVApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name="Mixing Study",
        file_header="sv_style_3src_mixing",
        mode='w'
    )

    abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False)

    my_spec = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    CATALYST = glh.locate_position_name("pos_1_rack", "A1")
    QUENCH = glh.locate_position_name("pos_1_rack", "A2")  # 40 uL of (34.9 mg/10 mL) into 2000 uL MeCN
    DILUENT = glh.locate_position_name("pos_1_rack", "A3")

    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    my_study = shuffle_study(list(create_study()), 1)

    prime(glh, WASTE, volume=1200)
    try:
        run_campaign(
            my_study,
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
