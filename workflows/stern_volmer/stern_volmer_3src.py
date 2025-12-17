# NOTICE: tutorial_8.py as a walkthrough of this code with all the methods in the workflows/stern_volmer directory
#   merged into a single, annotated file.


from typing import Generator, Any, Callable

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from data_management.simple_linear_regression import slr
from workflows.common_macros import prime, clean_up, inter_clean
from misc_func import shuffle_study
from data_management.common_dp_steps import get_files, take_sigal_at, SpectralProcessingSpec
from workflows.stern_volmer.stern_volmer_core import SVSpec, SVSpecFactory, grab_droplet_fixed, run_campaign
from workflows.stern_volmer.naming import SVApellomancer
from workflows.stern_volmer.stern_volmer_dp import extract_data, determine_base_intensity, save_data_summary


# This is called "manual" because the values are manually specified. It is the primary SV study.
def manual_study(factory: SVSpecFactory,
                 cat_aliquot: int = 10,
                 min_aliquot: int = 7,
                 n_samples: int = 4,
                 max_total: int = 50
                 ) -> Generator[SVSpec, Any, None]:
    available = max_total - cat_aliquot
    yield factory.make(catalyst=(CATALYST, cat_aliquot), quencher=(QUENCH, 0), diluent=(DILUENT, available))
    yield factory.make(catalyst=(CATALYST, cat_aliquot), quencher=(QUENCH, available), diluent=(DILUENT, 0))

    interval = (available - 2 * min_aliquot) / (n_samples - 1)
    q_values = [round(min_aliquot + idx * interval, 3) for idx in range(0, n_samples)]
    for q in q_values:
        yield factory.make(catalyst=(CATALYST, cat_aliquot), quencher=(QUENCH, q), diluent=(DILUENT, available - q))


# This is called "automatic" because the platform automatically calculates the values. It is the validation SV study.
def automatic_study(factory: SVSpecFactory,
                    _calibration: Callable[[float], float],
                    req_threshold: float = 1.0,
                    intercept_check: float = None) -> Generator[SVSpec, Any, None]:
    apellomancer = factory.name_wizard
    data_files = get_files(directory=apellomancer.project_directory, key="_PL_")
    data_entries = extract_data(data_files, apellomancer, cat_conc, quench_conc, signal_method, _calibration)
    if not data_entries:
        print("No data found for automatic_study()...")
        return

    data_entries.sort(key=lambda d: d.quencher_concentration)

    save_data_summary(data_entries, os.path.join(name_wizard.project_directory, f"{q_name}_summary.csv"), signal_method)

    # Perform (prelim) regression to determine if this is even necessary
    i_0, i_0_idx = determine_base_intensity(*data_entries)
    x_data = [entry.quencher_concentration for entry in data_entries]
    y_data = [i_0 / entry.signal_value for entry in data_entries]
    slr_results = slr(x_data, y_data)

    r2_is_good = (req_threshold is None) or (slr_results.pearsons_r2 >= req_threshold)
    intercept_is_good = (intercept_check is None) or ((1 - intercept_check) <= slr_results.intercept <= (1 + intercept_check))
    if r2_is_good and intercept_is_good:
        print("Both R2 and y(0) are good!")
        return
    print(f"Performing check experiments [{r2_is_good=}, {intercept_is_good=}]")

    # To redo the I_0 test
    if i_0_idx:
        check_i_0 = data_entries[i_0_idx[0]]
        yield factory.make_from_description(check_i_0.nominal, CATALYST, QUENCH, DILUENT)

    # To redo the most suspicious point (that isn't I_0)
    surprises = slr_results.surprise(x_data, y_data)
    try:
        retest, _ = surprises.pop(0)
        while retest in i_0_idx:
            retest, _ = surprises.pop(0)
        yield factory.make_from_description(data_entries[retest].nominal, CATALYST, QUENCH, DILUENT)
    except IndexError:
        pass


if __name__ == '__main__':
    from deck_layout.handler_bed import ShiftingPlaceable, Placeable
    from operator import itemgetter
    import random
    import os

    umbrella_project_name = "Big SVA 3"
    name_wizard = SVApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name=umbrella_project_name,
        file_header="sva3_rubppy__var__",
        mode='w'
    )

    abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False)
    pl_opt_specs = OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)

    default_factory = SVSpecFactory(
        name_wizard,
        3,
        None,  # abs_opt_specs
        pl_opt_specs,
        mix_disp=-3.0
    )

    my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    catalyst_wells = [
        glh.locate_position_name("pos_1_rack", "B1"),
        glh.locate_position_name("pos_1_rack", "D1"),
        glh.locate_position_name("pos_1_rack", "G1"),
        # glh.locate_position_name("pos_1_rack", "J1")
    ]
    change_cat_vial_every_n_quenchers: int = 4

    ledger: list[tuple[str, str, str, str, float]] = [
        # Rack,        Q-Well, Dil-Well, Q-Name,    Q-Conc
        ("pos_1_rack", "L2",   "L3",     "control", 1.0),
        ("pos_1_rack", "A2",   "A3",     "ferrocene", 1.4997),
        ("pos_1_rack", "B2",   "B3",     "decamethylferrocene", 0.9971),
        ("pos_1_rack", "C2",   "C3",     "1_1-dimethylferrocene", 1.5269),

        ("pos_1_rack", "D2",   "D3",     "acetylferrocene", 1.4926),
        ("pos_1_rack", "E2",   "E3",     "benzoylferrocene", 0.9803),
        ("pos_1_rack", "F2",   "F3",     "3-nitrobenzaldehyde", 499.5439),
        ("pos_1_rack", "G2",   "G3",     "methyl_4-nitrobenzoate", 21.5349),

        ("pos_1_rack", "H2",   "H3",     "4-nitrobenzaldehyde", 4.9500),
        ("pos_1_rack", "I2",   "I3",     "anthracene", 2.4207),
        ("pos_1_rack", "J2",   "J3",     "acridine", 2.9389),
        ("pos_1_rack", "K2",   "K3",     "pyrene", 9.6625),
    ]
    random.shuffle(ledger) # Rep 1 was in-oder, Reps 2 and 3 are shuffled.

    get_q_well = itemgetter(0, 1)
    get_d_well = itemgetter(0, 2)
    get_details = itemgetter(3, 4)
    quencher_wells: list[Placeable] = [glh.locate_position_name(*get_q_well(row)) for row in ledger]
    quencher_meta: list[tuple[str, float]] = [get_details(row) for row in ledger]
    diluent_wells: list[Placeable] = [glh.locate_position_name(*get_d_well(row)) for row in ledger]

    CATALYST = ShiftingPlaceable[Placeable](catalyst_wells)
    QUENCH = ShiftingPlaceable[Placeable](quencher_wells)
    DILUENT = ShiftingPlaceable[Placeable](diluent_wells)

    cat_conc = 5.0191
    quench_conc = 1
    calibration: Callable[[float], float] = lambda x: max(0.0, 0.9765 * float(x) - 0.2440)  # Set Feb 4, 2025 from "Manuscript Figures Data.xlsx"   # In the published code this data was moved to the Calibration.xlsx file.
    signal_method: SpectralProcessingSpec = SpectralProcessingSpec(None, None, take_sigal_at(610))  # Take the point closest to 610 nm

    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    # # # # START # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    prime(glh, WASTE, 1400)
    global_index = 0                                                          # Remember to set if Resuming a campaign #
    try:
        for q_idx, (q_name, q_conc) in enumerate(quencher_meta):
            print(f"Current quencher = {q_name}")
            name_wizard.file_header = f"sva3_rubppy_{q_name}"
            name_wizard.update_sub_directory(q_name)
            my_spectrometer.measure_average_reference('pl', 'dark', **pl_opt_specs)
            my_spectrometer.measure_average_reference('pl', 'light', **pl_opt_specs)

            quench_conc = q_conc
            # Primary study
            global_index = run_campaign(
                shuffle_study(
                    manual_study(
                        default_factory,
                        cat_aliquot=10,
                        min_aliquot=10,
                        n_samples=4,
                        max_total=50
                    ),  # V(Q) = 0 | 10  16.67  23.33  30 | 40
                    n_init=2,
                ),
                do_droplet_thing=lambda x, y: grab_droplet_fixed(
                    glh,
                    x,
                    EX_WASH,
                    WASTE,
                    my_spectrometer,
                    y
                ),
                post=lambda: inter_clean(glh, WASTE, EX_WASH),
                start_at=global_index,
                handler_bed=glh.bed
            )
            # Check most suspicious point and re-test I_0
            global_index = run_campaign(
                automatic_study(
                    default_factory,
                    calibration,
                    req_threshold=0.97,
                    intercept_check=0.1
                ),
                do_droplet_thing=lambda x, y: grab_droplet_fixed(
                    glh,
                    x,
                    EX_WASH,
                    WASTE,
                    my_spectrometer,
                    y
                ),
                post=lambda: inter_clean(glh, WASTE, EX_WASH),
                start_at=global_index,
                handler_bed=glh.bed
            )

            try:
                my_data_files = get_files(directory=name_wizard.project_directory, key="_PL_")
                my_data_entries = extract_data(my_data_files, name_wizard, cat_conc, quench_conc, signal_method, calibration)
                if my_data_entries:
                    my_data_entries.sort(key=lambda d: d.quencher_concentration)
                    save_data_summary(my_data_entries, os.path.join(name_wizard.project_directory, f"{q_name}_summary.csv"), signal_method)
                else:
                    print(f"No data found for {q_name}?")
            except Exception as e:
                print(f"The following error prevented saving summary data for {q_name}")
                print(repr(e))

            # We have finished a quencher, update
            qc = QUENCH.next()
            dc = DILUENT.next()
            cc = None
            if q_idx % change_cat_vial_every_n_quenchers == (change_cat_vial_every_n_quenchers - 1):
                cc = CATALYST.next()
            print(f"Changing analyte [debug: {qc=}, {dc=}, {cc=}]")
    except KeyboardInterrupt:
        print("User exited the loop early")
    except StopIteration:
        print("Exiting early due to system volume concerns.")
    clean_up(glh, WASTE)

    # ID of vial cap is 6 mm
    # Access ID is 6.2 mm
    # Vial cap taurus width: 2.6 mm
