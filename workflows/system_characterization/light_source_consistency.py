import os.path
import random
from contextlib import redirect_stdout
from io import StringIO

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from deck_layout.handler_bed import Coordinate, Point2D, DEFAULT_SYRINGE_FLOWRATE
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import TipExitMethod, ExternalWash
from workflows.common_macros import prime, volume_to_center_droplet, clean_up
from misc_func import silence
from workflows.stern_volmer.naming import SVApellomancer


def generate_coordinates(n_points: int):
    for _ in range(n_points):
        yield Coordinate(xy=Point2D(x=random.randint(5, 160), y=random.randint(5, 240)), z=118)


def measure_spectrum(name_wizard: SVApellomancer, at_coordinate: Coordinate | str):
    if isinstance(at_coordinate, str):
        file_name = at_coordinate
    else:
        file_name = f"{at_coordinate.xy.x}_{at_coordinate.xy.y}"
        with redirect_stdout(StringIO()):
            glh.move_arm_to(at_coordinate)
    print(f"Measuring spectra for: {file_name}")
    my_spectrometer.measure_pl_spectra(**pl_opt_specs).save_to_file(name_wizard.make_full_path(file_name, ".spec"))


@silence
def safe_move_z():
    glh.chain_pipette(
        ExternalWash(
            positions=EX_WASH,
            tip_exit_method=TipExitMethod.DRAG,
            n_iter=3
        )
    )


@silence
def make_and_place_droplet():
    back_air_gap = 20
    front_airgap = 20
    droplet_volume = glh.prepare_droplet_in_liquid_line(
        components=[
            (CATALYST, 50),
        ],
        back_air_gap=back_air_gap,
        front_air_gap=front_airgap,
        air_rate=DEFAULT_SYRINGE_FLOWRATE,
        aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        mix_iterations=0,
        mix_displacement=-1,  # negative means droplet volumes (instead of constant displacement)
        mix_rate=2 * DEFAULT_SYRINGE_FLOWRATE,
    )
    _move = volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2)
    glh.aspirate_from_curr_pos(_move, DEFAULT_SYRINGE_FLOWRATE)


def get_files(directory: str):
    for *_, file_names in os.walk(directory):
        for file_name in file_names:
            yield os.path.join(directory, file_name)


def get_data(from_files: list[str]):
    x_axis: list[float] = []
    y_axes: list[list[float]] = []
    is_first = True

    for file in from_files:
        with open(file, "r") as csv:
            y_axis: list[float | str] = []
            for line in csv:
                try:
                    w, _light = line.split(", ")
                except ValueError:
                    continue

                try:
                    wavelength = float(w)
                except ValueError:
                    continue
                if is_first:
                    x_axis.append(wavelength)

                try:
                    light = float(_light)
                except ValueError:
                    light = "nan"
                y_axis.append(light)
        y_axes.append(y_axis)
        is_first = False
        print("DEBUG", f"added {len(y_axis)} abs values, currently at {len(y_axes)} spectra")

    return x_axis, y_axes


def save_data(x_axis: list[float], y_axes: list[list[float]], to_file: str):
    with open(to_file, 'w+') as output_file:
        output_file.write(f"Index, " + f", ".join([f"{i}" for i in range(len(y_axes))]) + "\n")
        output_file.write(f"Wavelength, " + f", ".join([f"PL{i}" for i in range(len(y_axes))]) + "\n")
        for w, *a in zip(x_axis, *y_axes):
            lights = ", ".join([f"{_a}" for _a in a])
            output_file.write(f"{w}, {lights}\n")


if __name__ == '__main__':
    my_name_wizard = SVApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name="IPL Study",
        file_header="rubpy_mecn_randxy",
        mode='w'
    )

    # pl_opt_specs = OpticalSpecs(count=20, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)  # Normal
    pl_opt_specs = OpticalSpecs(count=20, interval=0.1, integration_time=100_000, correct_dark_counts=True)

    my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    my_spectrometer.pl.backend.correct_dark_counts = True
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    CATALYST = glh.locate_position_name("pos_1_rack", "A1")

    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    prime(glh, WASTE, volume=400)
    prime(glh, WASTE, volume=500)
    prime(glh, WASTE, volume=500)
    prime(glh, WASTE)
    # my_spectrometer.measure_average_reference(**pl_opt_specs, mode="pl", light="light")
    # make_and_place_droplet()
    measure_spectrum(my_name_wizard, "init")
    for coordinate in generate_coordinates(26):
        safe_move_z()
        measure_spectrum(my_name_wizard, coordinate)
    clean_up(glh, WASTE)

    my_files = list(get_files(my_name_wizard.project_directory))
    my_x_data, my_y_data = get_data(my_files)
    save_data(my_x_data, my_y_data, to_file=my_name_wizard.make_full_path("summary_light", ".csv"))
