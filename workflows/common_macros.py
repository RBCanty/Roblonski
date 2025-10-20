import time
from typing import Callable, Literal

from aux_devices.ocean_optics_spectrometer import SpectrometerSystem, OpticalSpecs, ZipSpectra
from aux_devices.spectra import SpectraStack, Spectrum, intensity_to_absorbance
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE, SYSTEM_AIR_GAP, NamePlace, Placeable
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import InternalClean, TipExitMethod, ExternalWash, AirGap, \
    AspiratePipettingSpec
from misc_func import silence, Number
from user_interface.style import warning_text


def boot_with_user(glh: Gilson241LiquidHandler, waste: NamePlace):
    """ Prompt user to define prime volume AND prompt user to specify system liquid level. """
    system_cfg_dict = glh.bed.read_resource_cfg()
    system_fluid_level = system_cfg_dict.get('system_fluid_volume_mL', 'unk')

    user_response_prime = input(warning_text("Please specify what volume to prime the system with\n"))
    try:
        prime_volume = float(user_response_prime.strip())
    except ValueError:
        print(f"Unable to parse '{user_response_prime.strip()}', using 600 uL to prime.")
        prime_volume = 600
    user_response_tank = input(warning_text(f"System thinks there are {system_fluid_level} mL of usable backing fluid\n"
                                       f"Enter anything other than a number to confirm or type a number to set it.\n"))
    try:
        new_system_volume = float(user_response_tank.strip())
        system_cfg_dict['system_fluid_volume_mL'] = new_system_volume
        glh.bed.write_resource_cfg(system_cfg_dict)
    except ValueError:
        print(f"(Echo '{user_response_tank.strip()}') Using {system_fluid_level}.")

    prime(glh, waste, prime_volume)


@silence
def prime(glh: Gilson241LiquidHandler, waste: NamePlace, volume: float = 200, chunk_size: float = 400):
    """ Empty the syringe, then flush with backing fluid, restore system air gap """
    glh.dispense_all(waste)

    n_chunks = int(volume / chunk_size)
    for _ in range(n_chunks):
        glh.aspirate_from_reservoir(chunk_size, 2*DEFAULT_SYRINGE_FLOWRATE)
        glh.dispense_all(waste)
    remaining = volume - chunk_size * n_chunks
    if remaining > 1:
        glh.aspirate_from_reservoir(remaining, 2 * DEFAULT_SYRINGE_FLOWRATE)
        glh.dispense_to_curr_pos(remaining, 2*DEFAULT_SYRINGE_FLOWRATE)

    glh.aspirate_from_curr_pos(SYSTEM_AIR_GAP, DEFAULT_SYRINGE_FLOWRATE)


@silence
def clean_up(glh: Gilson241LiquidHandler, waste: NamePlace, volume: float = 200):
    """ Internal vent of 200 uL three times, then home arm """
    glh.chain_pipette(
        InternalClean(
            cleaning_volume=volume,
            rate=2*DEFAULT_SYRINGE_FLOWRATE,
            location=waste,
            n_iterations=3,
            free_dispense=True,
            disp_on_edge=True,
            pre_flush=True,
            tip_exit_method=TipExitMethod.TIP_TOUCH
        )
    )
    glh.home_arm()


@silence
def inter_clean(glh: Gilson241LiquidHandler, waste: Placeable, wash: Placeable, volume: float = 200):
    """ Empties the syringe, internal washes, external washes, then internal washes again (Restores System airgap) """
    glh.chain_pipette(
        InternalClean(
            cleaning_volume=volume,
            rate=2 * DEFAULT_SYRINGE_FLOWRATE,
            location=waste,
            n_iterations=1,
            free_dispense=True,
            disp_on_edge=True,
            pre_flush=True,
            tip_exit_method=TipExitMethod.TIP_TOUCH
        ),
        ExternalWash(
            positions=wash,
            tip_exit_method=TipExitMethod.DRAG,
            air_gap=AspiratePipettingSpec(
                component=AirGap(position=waste, volume=10)
            ),
            n_iter=2
        ),
        InternalClean(
            cleaning_volume=volume,
            rate=2 * DEFAULT_SYRINGE_FLOWRATE,
            location=waste,
            n_iterations=2,
            free_dispense=True,
            disp_on_edge=True,
            pre_flush=True,
            tip_exit_method=TipExitMethod.TIP_TOUCH
        )
    )


def volume_to_center_droplet(needle: float, tube: float, die: float, front_airgap: float, droplet_volume: float, lag: float = 2) -> float:
    """ Based on relevant volumes, it provides the volume to aspirate (from needle) to center the droplet in the
    spectrometer. All volumes in microlitres.

    Calculated volume: (needle + tube + die/2) - front_airgap - (droplet_volume/2) - lag

    :param needle: The volume from the tip of the needle to where it connects to the tube.
    :param tube: The volume of the tube between the needle and flowcell's entrance.
    :param die: The volume of the flow cell (entrance to exit).
    :param front_airgap: The volume of the front airgap in use when the aspiration to center the droplet is to be called.
    :param droplet_volume: The volume of the droplet in use when the aspiration to center the droplet is to be called.
    :param lag: A constant volume removed from the calculated volume to center the droplet.
    :returns: The volume to aspirate to center a droplet in the flow cell. Min value: 0.
    """
    return max(0.0, (needle + tube + die/2) - front_airgap - (droplet_volume/2) - lag)


def test_well(glh: Gilson241LiquidHandler,
              spectrometer: SpectrometerSystem,
              well: Placeable,
              sample_volume: float,
              volume_to_center_droplet_partial: Callable[[float, float], float],
              absorbance: tuple[OpticalSpecs, Callable[['SpectrometerSystem'], Spectrum]] = None,
              photoluminescence: tuple[OpticalSpecs, Callable[['SpectrometerSystem'], Spectrum]] = None,
              measurement_spacing: float = 1.0,
              air_gaps: tuple[Number, Number] = None
              ) -> SpectraStack:
    """ Grabs a droplet form the specified well then measures it on the spectrometer.

    This method is effectively a call to Gilson241LiquidHandler.prepare_droplet_in_liquid_line() with one component
    followed by a call to Gilson241LiquidHandler.utilize_spectrometer()

    volume_to_center_droplet_partial: volume_to_center_droplet() with needle, tube, die, and lag preloaded
    air_gaps: default to (20, 10) and is (back/system-side, front/vial-side); which is to say it is called on
    front_airgap and droplet_volume (in that order).
    :return: A SpectraStack. If both ABS and PL were requested, ABS will be first (index 0).
    """
    if air_gaps is None:
        air_gaps = (20, 10)
    back_ag, front_ag = air_gaps

    droplet_volume = glh.prepare_droplet_in_liquid_line(
        components=[(well, sample_volume), ],
        back_air_gap=back_ag,
        front_air_gap=front_ag,
        air_rate=DEFAULT_SYRINGE_FLOWRATE,
        aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        mix_displacement=0,
        mix_rate=0,
        mix_iterations=0,
    )
    if not (absorbance or photoluminescence):
        return SpectraStack()

    return glh.utilize_spectrometer(
        spectrometer,
        volume_to_center_droplet_partial(front_ag, droplet_volume),
        absorbance,
        photoluminescence,
        measurement_spacing
    )


def record_spectrum(my_spec: SpectrometerSystem,
                    opt_spec: OpticalSpecs,
                    mode: Literal['ABS', 'PL'],
                    file_path: str,
                    file_header: str = ""):
    """ Measures a spectrum (Abs in mOD, PL in counts) and, if file_path is not an empty string, will attempt to save
    the data to the specified file.  If the file is open (raises a PermissionError), the program will pause until the
    user confirms that they have closed the file. """
    my_spec.backend.correct_dark_counts = opt_spec.correct_dark_counts
    time.sleep(1)
    if mode.upper() == "PL":
        opt_spectrum = my_spec.measure_pl_spectra(**opt_spec)
        reference = my_spec.pl
    elif mode.upper() == "ABS":
        opt_spectrum = my_spec.measure_abs_spectra(**opt_spec)
        reference = my_spec.abs
    else:
        raise ValueError(f"mode must be 'ABS' or 'PL' not {mode}")

    if file_path:
        if not file_header.endswith("\n"):
            file_header = file_header + "\n"
        try:
            with open(file_path, 'w+'):
                pass
        except PermissionError:
            input(warning_text(f"The file '{file_path}' is already open! Please close it then press enter.\n"))
        with open(file_path, 'w+') as _file:
            _file.write(f"name, {file_path}\n")
            if file_header:
                _file.write(file_header)
            ZipSpectra(opt_spectrum, reference).print(file_stream=_file)

    return opt_spectrum


def record_reference(my_spec: SpectrometerSystem,
                     opt_spec: OpticalSpecs,
                     mode: Literal['ABS', 'PL'],
                     file_path: str,
                     file_header: str = ""):
    """ Measures a dark then light reference spectrum (Abs in mOD, PL in counts) and, if file_path is not an empty
    string, will attempt to save the data to the specified file.  If the file is open (raises a PermissionError), the
    program will pause until the user confirms that they have closed the file. """
    my_spec.backend.correct_dark_counts = opt_spec.correct_dark_counts
    time.sleep(1)
    if mode.upper() == "PL":
        my_spec.measure_average_reference('pl', 'dark', **opt_spec)
        time.sleep(1)
        my_spec.measure_average_reference('pl', 'light', **opt_spec)
        time.sleep(1)
        opt_spectrum = Spectrum(my_spec.pl.backend.wavelengths, my_spec.pl.light_reference)
        reference = my_spec.pl
    elif mode.upper() == "ABS":
        my_spec.measure_average_reference('abs', 'dark', **opt_spec)
        time.sleep(1)
        my_spec.measure_average_reference('abs', 'light', **opt_spec)
        time.sleep(1)
        opt_spectrum = intensity_to_absorbance(my_spec.abs.backend.wavelengths, my_spec.abs.light_reference, my_spec.abs.dark_reference, my_spec.abs.light_reference)
        reference = my_spec.abs
    else:
        raise ValueError(f"mode must be 'ABS' or 'PL' not {mode}")

    if file_path:
        if not file_header.endswith("\n"):
            file_header = file_header + "\n"
        try:
            with open(file_path, 'w+'):
                pass
        except PermissionError:
            input(warning_text(f"The file '{file_path}' is already open! Please close it then press enter.\n"))
        with open(file_path, 'w+') as _file:
            _file.write(f"name, {file_path}\n")
            if file_header:
                _file.write(file_header)
            ZipSpectra(opt_spectrum, reference).print(file_stream=_file)

    return opt_spectrum


if __name__ == '__main__':
    from workflows.rplqy_v1.naming import RPLQYApellomancer
    from aux_devices.ocean_optics_spectrometer import LightSource

    umbrella_project_name = "Relative PLQY Study"
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

    WASTE = my_glh.locate_position_name('waste', "A1")
    EX_WASH = my_glh.locate_position_name('wash', "A1")

    boot_with_user(my_glh, WASTE)

    # Specifications # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    system_fluid = "MeCN"
    abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=50_000, correct_dark_counts=False)
    pl_opt_specs = OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)

    samples = [
        my_glh.locate_position_name("pos_1_rack", "H4"),  # (5b)
        my_glh.locate_position_name("pos_1_rack", "I1"),  # (5c)
        my_glh.locate_position_name("pos_1_rack", "I2"),  # (1a)
        my_glh.locate_position_name("pos_1_rack", "I3"),  # (1b)
        my_glh.locate_position_name("pos_1_rack", "I4"),  # (1c)
        ]

    BACK_AIR_GAP = 20
    FRONT_AIR_GAP = 10

    def measure_abs_spectrum(_spec: SpectrometerSystem):
        spectrum = _spec.measure_abs_spectra(**abs_opt_specs)
        print("\nW, D, L, Abs")
        ZipSpectra(spectrum, _spec.abs).print()
        return spectrum

    def measure_pl_spectrum(_spec: SpectrometerSystem):
        spectrum = _spec.measure_pl_spectra(**pl_opt_specs)
        print("\nW, D, L, PL")
        ZipSpectra(spectrum, _spec.pl).print()
        return spectrum

    my_spectrometer.measure_average_reference(**pl_opt_specs, light="dark", mode="pl")
    time.sleep(1)
    my_spectrometer.measure_average_reference(**pl_opt_specs, light="light", mode="pl")
    time.sleep(1)

    for sample in samples:
        input("READY?\n")
        test_spectra = test_well(
            my_glh,
            my_spectrometer,
            sample,
            50,
            lambda ag, dv: volume_to_center_droplet(46, 146, 21, ag, dv, lag=2),
            absorbance=(abs_opt_specs, lambda _ms: measure_abs_spectrum(_ms)),
            photoluminescence=(pl_opt_specs, lambda _ms: measure_pl_spectrum(_ms)),
            air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
        )

        inter_clean(my_glh, WASTE, EX_WASH, 200)

    clean_up(my_glh, WASTE, 200)
    my_glh.home_arm()

    # for node in linear_compliment_space(0, 40, 10):
    #     print(node)
    # print()
    # for node in chebyshev_compliment_space(0.5, 20.5, 16):
    #     print(f"({round(node[0], 1)}, {round(node[1], 1)})")
    # # 20.0, 19.6, 18.8, 17.8, 16.4, 14.8, 13.1, 11.2, 9.3, 7.4, 5.7, 4.1, 2.7, 1.7, 0.9, 0.5
