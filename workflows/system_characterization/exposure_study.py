import time
from contextlib import redirect_stdout
from io import StringIO

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from aux_devices.spectra import SpectraStack
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from workflows.common_macros import prime, clean_up, inter_clean, volume_to_center_droplet
from misc_func import safe_project_dir
from workflows.stern_volmer.stern_volmer_core import run_campaign


def create_study(sample_volume: int = 30,
                 n_mix: int = 6):
    yield {
        'mix_iterations': n_mix,
        'components': ((CATALYST, sample_volume), ),
        'name_tag': f"c{sample_volume}"
    }


def measure_spectrum(save_iter: int | str):
    my_spec.backend.correct_dark_counts = opt_specs.correct_dark_counts
    time.sleep(1)

    spectra = list(my_spec.yield_abs_spectra(**opt_specs))
    stack = SpectraStack(*spectra)

    tag = opt_specs.generate_tag()
    cor_tag = opt_specs.generate_corrections_tag()

    with open(f"{template}_ABS_{save_iter}.csv", "w+") as _file:
        _file.write(f"name, {template}_ABS_{save_iter}.csv\n{tag}\n{cor_tag}\n")
        stack.print(file_stream=_file, header=["wavelength (nm)", *[f"ABS_{i}" for i in range(len(spectra))]])


def grab_droplet_fixed(_test_args: dict):
    name_tag = _test_args.pop('name_tag')

    back_air_gap = 20
    front_airgap = 10

    with redirect_stdout(StringIO()):
        droplet_volume = glh.prepare_droplet_in_liquid_line(
            back_air_gap=back_air_gap,
            front_air_gap=front_airgap,
            air_rate=DEFAULT_SYRINGE_FLOWRATE,
            aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
            mix_displacement=0,
            mix_rate=2 * DEFAULT_SYRINGE_FLOWRATE,
            **_test_args
        )
    my_spec.measure_average_reference(**opt_specs, mode="abs", light="light")
    my_spec.measure_average_reference(**opt_specs, mode="abs", light="dark")

    _move = volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2)
    glh.aspirate_from_curr_pos(_move, 0.5*DEFAULT_SYRINGE_FLOWRATE)

    measure_spectrum(name_tag)


if __name__ == '__main__':
    inty_timey = 25_002
    template = safe_project_dir(parent_dir="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
                                project_header="Exposure Tests",
                                exp_header=f"exposure_MeBlue_y{inty_timey}")

    my_spec = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))

    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    # opt_specs = OpticalSpecs(count=20, interval=0.010, integration_time=inty_timey, correct_dark_counts=True)  # PL
    opt_specs = OpticalSpecs(count=100, interval=0.010, integration_time=inty_timey, correct_dark_counts=True)  # ABS

    CATALYST = glh.locate_position_name("pos_1_rack", "A1")
    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    prime(glh, WASTE)
    try:
        run_campaign(
            create_study(
                sample_volume=50,
                n_mix=6),
            do_droplet_thing=grab_droplet_fixed,
            post=lambda: inter_clean(glh, WASTE, EX_WASH)
        )
    except KeyboardInterrupt:
        print("User exited the loop early")
    clean_up(glh, WASTE)
