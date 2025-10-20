from contextlib import redirect_stdout
from io import StringIO
from random import sample
from typing import Generator, Any

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from aux_devices.spectra import ZipSpectra
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE, NamePlace
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import TipExitMethod, ExternalWash, AspiratePipettingSpec, AirGap
from workflows.common_macros import prime, clean_up, inter_clean, volume_to_center_droplet
from misc_func import safe_project_dir


def create_study(sample_a_range: range,
                 sample_b_range: range,
                 sample_c_range: range,
                 min_volume: int,
                 max_volume: int,
                 n_mix: int = 6,
                 max_studies: int = None):
    """ Combinatorial search space for the study
    :param sample_a_range: range(min, max) for component A
    :param sample_b_range: ditto for component B
    :param sample_c_range: ditto for component C
    :param min_volume: A+B+C >= min
    :param max_volume: A+B+C <= max
    :param n_mix: How many times to mix
    :param max_studies: Down-select to this many experiments
    """
    def compositions() -> Generator[tuple[tuple[NamePlace, int], ...], Any, None]:
        for a_vol in sample_a_range:
            for b_vol in sample_b_range:
                for c_vol in sample_c_range:
                    if not (min_volume < (a_vol + b_vol + c_vol) < max_volume):
                        continue
                    # a tuple of tuples so as to match the signature of glh.prepare_droplet_in_liquid_line
                    yield (
                        (SAMPLE_A, a_vol),
                        (SAMPLE_B, b_vol),
                        (SAMPLE_C, c_vol)
                    )

    working_compositions = list(compositions())
    n_studies = len(working_compositions)
    if max_studies is None:
        max_studies = n_studies

    working_compositions = sample(working_compositions, k=min(max_studies, n_studies))
    print(f"Preparing to run {n_studies} experiments")
    for composition in working_compositions:
        # keywords match signature of glh.prepare_droplet_in_liquid_line, note that 'name_tag' gets popped off though.
        yield {
            'mix_iterations': n_mix,
            'components': composition,
            'name_tag': f"a{composition[0][1]}_b{composition[1][1]}_c{composition[2][1]}_m{n_mix}"
        }


def measure_spectrum(save_iter: int | str):
    """ Measures a spectrum and saves it to a file along with the reference spectra present when measured """
    my_spec.backend.correct_dark_counts = pl_opt_specs.correct_dark_counts
    pl_spectrum = my_spec.measure_pl_spectra(**pl_opt_specs)

    tag = pl_opt_specs.generate_tag()
    cor_tag = pl_opt_specs.generate_corrections_tag()

    with open(f"{template}_{save_iter}.csv", "w+") as _file:
        _file.write(f"name, {template}_{save_iter}_PL.csv\n{tag}\n{cor_tag}\n")
        _file.write(f"wavelength (nm), dark reference (int), light reference (int), pl (int)\n")
        ZipSpectra(pl_spectrum, my_spec.pl).print(file_stream=_file)


def run_experiment(test_args: dict):
    """ Prepare a droplet, move it into the spectrometer, measure spectrum """
    name_tag = test_args.pop('name_tag')

    back_air_gap = 20
    front_airgap = 10

    with redirect_stdout(StringIO()):
        droplet_volume = glh.prepare_droplet_in_liquid_line(
            back_air_gap=back_air_gap,
            front_air_gap=front_airgap,
            air_rate=DEFAULT_SYRINGE_FLOWRATE,
            aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
            mix_displacement=-1.3,  # negative means droplet volumes (instead of constant displacement)
            mix_rate=2 * DEFAULT_SYRINGE_FLOWRATE,
            dip_tips=ExternalWash(
                positions=EX_WASH,
                tip_exit_method=TipExitMethod.DRAG,
                air_gap=AspiratePipettingSpec(
                    component=AirGap(position=WASTE, volume=10)
                ),
                n_iter=2
            ),
            **test_args
        )

    _move = volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2)
    glh.aspirate_from_curr_pos(_move, 0.5*DEFAULT_SYRINGE_FLOWRATE)

    measure_spectrum(name_tag)


if __name__ == '__main__':
    # TODO: Update to your directory and preferred file names
    template = safe_project_dir(parent_dir="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
                                project_header="NanoRods Tests",
                                exp_header="gold_nanorods")

    my_spec = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        # TODO: I (Ben) can help you make your own Deck layout
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    pl_opt_specs = OpticalSpecs(count=20, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)

    SAMPLE_A = glh.locate_position_name("pos_1_rack", "A1")
    SAMPLE_B = glh.locate_position_name("pos_1_rack", "A2")
    SAMPLE_C = glh.locate_position_name("pos_1_rack", "A3")

    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    volume_limit = 90  # mL
    current_volume = 0
    study = create_study(
            sample_a_range=range(7,15),
            sample_b_range=range(7,20),
            sample_c_range=range(7,25),
            min_volume=25,
            max_volume=50,
            n_mix=6)

    prime(glh, WASTE)
    try:
        for test in study:
            if current_volume > volume_limit:
                print("Safe volume exhausted, exiting.")
                break
            print(f"Running {test['name_tag']}  ({volume_limit - current_volume} mL remaining)")
            run_experiment(test)
            inter_clean(glh, WASTE, EX_WASH)
            current_volume += 3 * 200 / 1000
    except KeyboardInterrupt:
        print("User exited the loop early")
    clean_up(glh, WASTE)
