"""
In this tutorial we will examine one way of extending the presented Stern-Volmer analysis to operate on multiple
wavelengths at once as well as handle multiple different photocatalysts loaded onto the platform at once.

There are a few changes to the bookkeeping, but the big changes are to the method which creates the summary
and the method which identifies which samples to re-test (if any).
"""
import itertools
import os
from typing import Callable, Literal, NamedTuple, Sequence, Generator, Any

import numpy as np

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from aux_devices.signal_processing import smooth
from aux_devices.spectra import Spectrum, SpectrumFactory
from data_management.common_dp_steps import get_files, SpectralProcessingSpec
from data_management.common_dp_steps import take_sigal_at, take_sigal_near, find_wavelength_of_max_signal
from data_management.simple_linear_regression import slr, RegressionReport
from deck_layout.handler_bed import Placeable
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from workflows.common_macros import prime, clean_up, inter_clean
from workflows.stern_volmer.naming import SVSpecDescription, SVApellomancer
from workflows.stern_volmer.stern_volmer_core import SVSpec, SVSpecFactory, grab_droplet_fixed, run_campaign


# SKIP: This is just a cleaner version of the original Stern-Volmer approach to generating a set
# of droplet compositions that span a range.
def primary_study(factory: SVSpecFactory,
                  cat_loc: Placeable,
                  quench_loc: Placeable,
                  dil_loc: Placeable,
                  cat_aliquot: int = 10,
                  min_aliquot: int = 7,
                  n_samples: int = 4,
                  max_total: int = 50
                  ) -> Generator[SVSpec, Any, None]:
    available = max_total - cat_aliquot
    yield factory.make(catalyst=(cat_loc, cat_aliquot), quencher=(quench_loc, 0), diluent=(dil_loc, available))
    yield factory.make(catalyst=(cat_loc, cat_aliquot), quencher=(quench_loc, available), diluent=(dil_loc, 0))

    interval = (available - 2 * min_aliquot) / (n_samples - 1)
    q_values = [round(min_aliquot + idx * interval, 3) for idx in range(0, n_samples)]
    for q in q_values:
        yield factory.make(catalyst=(cat_loc, cat_aliquot), quencher=(quench_loc, q), diluent=(dil_loc, available - q))


#                                                                                                                # NEW #
# Part 1: Now that the catalyst is a free variable and the spectral analysis is being extended, we will reorganize
# the ledger of experiments from a tuple to an annotated tuple (a NamedTuple).
class LedgerLine(NamedTuple):
    rack: str
    catalyst_id: str
    catalyst_name: str
    catalyst_concentration: float
    quencher_id: str
    quencher_name: str
    quencher_concentration: float
    diluent_id: str
    spectral_analysis: SpectralProcessingSpec  # SpectralProcessingSpec already allows for single/multiple analysis
                                               #   techniques, so we can use this object as-is.
    analysis_headers: str | Sequence[str]  # We will record our names for each data-column that the analyses in
                                           #   spectral_analysis add.
    analysis_mask: bool | Sequence[bool] = True   # Not all analytical methods generate a signal value, so we want
                                                  # the ability to turn each analysis on/off.

    # Since the types in spectral_analysis, analysis_headers, and analysis_mask are either a single value or are
    #   multiple values, the following methods ensure that we always get a sequence of values (even if there is
    #   only one value in the sequence).
    def get_analyses(self) -> Sequence[Callable[[Spectrum], float]]:
        analyses = self.spectral_analysis.analysis
        if isinstance(analyses, Sequence):
            return analyses
        else:
            return [analyses, ]

    def get_headers(self) -> Sequence[str]:
        if isinstance(self.analysis_headers, str):
            return [self.analysis_headers, ]
        else:
            return self.analysis_headers

    def get_mask(self) -> Sequence[bool]:
        if isinstance(self.analysis_mask, bool):
            return [self.analysis_mask, ]
        else:
            return self.analysis_mask

    def validate(self):
        """ Raises assertion error if the lengths of the analysis, headers, and mask don't match.
        Otherwise, returns (analyses, headers, masks) """
        a = self.get_analyses()
        h = self.get_headers()
        m = self.get_mask()
        assert len(a) == len(h) == len(m)
        return a, h, m


# Part 2: We must update the `Datum` object to hold multiple signal values
class Datum(NamedTuple):
    """ Stores the data discernible from the file name and the spectrum"""
    nominal: SVSpecDescription
    actual: SVSpecDescription
    signal_value: Sequence[float]  # <-- Was `signal_value: float`                                            # CHANGE #
    quencher_concentration: float
    catalyst_concentration: float
    spectral_segment: Spectrum


# Part 3: When extracting the data, we must account for there being multiple signal values.
#         The two changes to this function are called out with right-aligned comments.
def extract_data(from_files: list[str],
                 apellomancer: SVApellomancer,
                 cat_src_conc: float,
                 qch_src_conc: float,
                 peak_args: SpectralProcessingSpec,
                 nom2actual: Callable[[float], float] = None
                 ) -> list[Datum]:
    """ Converts files into data objects for processing

    :param from_files: A list of data files
    :param apellomancer: A file manager
    :param cat_src_conc: The catalyst source concentration
    :param qch_src_conc: The quencher source concentration (in the same units as the previous)
    :param peak_args: The lower [0] and upper [1] bounds (in nm) for spectral analysis and a function called on that
      range [2] which returns the intensity value (such as numpy.nanmax).
    :param nom2actual: A function that converts the nominal volumes to actual volumes.
    """
    if nom2actual is None:
        nom2actual = lambda x: x

    data_points = []

    for file in from_files:
        print(f"On {file}")
        try:
            description = apellomancer.parse_file_name(file)
        except (ValueError, TypeError) as err:
            print("\t" + repr(err))
            continue

        spec_fact = SpectrumFactory()
        try:
            open(file, 'r')
        except FileNotFoundError:
            print(f"\tFile '{file}' was hidden, ignoring.")
            continue
        with open(file, "r") as csv:
            latch = False
            for _line in csv:
                if not latch:
                    if "wavelength" not in _line:
                        continue
                    else:
                        latch = True
                        continue

                w, *_, p =  _line.split(", ")
                try:
                    wavelength = float(w)
                except ValueError:
                    continue
                try:
                    absorbance = float(p)
                except ValueError:
                    absorbance = np.nan

                spec_fact.add_point(wavelength, absorbance)

        this_spectrum: Spectrum = spec_fact.create_spectrum()
        smooth(this_spectrum, sigma=3.0)

        this_segment = this_spectrum.segment(**peak_args.segment_kwargs())  # renamed                         # CHANGE #
        # This variable has been renamed from 'rubpy3_segment' to 'this_segment' as the multi-peak
        # analyte may not be Rubpy.

        # I have formatted this as an IF statement to give it backwards compatibility.                        # CHANGE #
        # Now, whether peak_args.analysis is a Callable[[Spectrum], float] -- the old way -- or a
        # Sequence[Callable[[Spectrum], float]] -- the new way, this `extract_data` method will still
        # work fine.
        if isinstance(peak_args.analysis, Sequence):
            peak_values = [analysis(this_segment) for analysis in peak_args.analysis]
        else:
            peak_values = [peak_args.analysis(this_segment), ]
        # ^ this block used to be:
        # `peak_value = peak_args.analysis(rubpy3_segment)`

        actual_description = description.apply_calibration(nom2actual)

        droplet_volume = actual_description.total_volume
        quencher_volume = 0 if actual_description.quencher is None else actual_description.quencher
        catalyst_volume = 0 if actual_description.catalyst is None else actual_description.catalyst
        diluent_volume = actual_description.diluent

        if diluent_volume is None:
            _cat_conc = (quencher_volume + catalyst_volume) * cat_src_conc / droplet_volume
        else:
            _cat_conc = catalyst_volume * cat_src_conc / droplet_volume

        entry = Datum(
            description,
            actual_description,
            peak_values,
            quencher_volume * qch_src_conc / droplet_volume,
            _cat_conc,
            this_segment
        )

        data_points.append(entry)
        print(f"\tAdded {os.path.basename(file)}")

    return data_points


# Part 4: When determining I_0 for Stern-Volmer analysis, the I_0 should be for each wavelength.
# To account for this, we will add an argument to `determine_base_intensity` to select which wavelength.      # CHANGE #
def determine_base_intensity(*data: Datum, method: Literal['min', 'max', 'avg'] = 'avg', data_idx: int = 0
                             ) -> tuple[float, list[int]]:
    """ Provides a value for the base intensity and the indices used for calculation """
    pure_catalyst_indices: list[int] = []
    pure_catalyst_signals: list[float] = []
    for idx, datum in enumerate(data):
        nom_qch_vol = datum.nominal.quencher
        if nom_qch_vol:  # If it's neither None nor 0
            continue
        pure_catalyst_signals.append(datum.signal_value[data_idx])  # <-- was 'pure_catalyst_signals.append(datum.signal_value[0])'
        pure_catalyst_indices.append(idx)
    if not pure_catalyst_signals:
        raise ValueError("No pure catalyst signals detected!")
    if method == 'min':
        return min(pure_catalyst_signals), pure_catalyst_indices
    if method == 'max':
        return max(pure_catalyst_signals), pure_catalyst_indices
    if method == 'avg':
        return sum(pure_catalyst_signals)/len(pure_catalyst_signals), pure_catalyst_indices
    raise ValueError(f"the method must be min/max/avg, not '{method}'")

#                                                                                                         # BIG CHANGE #
# Part 5: The data summary must now be flexible to any number of spectral analyses and subsets of which that are
#   subject to Stern-Volmer data processing
def save_data_summary(data: list[Datum], to_file: str, description: LedgerLine):
    # Check that the lists match and pull them out for quick use.
    _, analysis_headers, analysis_masks = description.validate()

    # Figure out the headers
    # Break into three parts. The base headers are the entries that are always present. The include the volumes and
    #   concentrations.
    # Then, the added headers are the headers for each analysis specified in the experimental description.
    #   These are given in order with their user-given name.
    # Finally, for each analysis which will be processed as Stern-Volmer data, add additional columns which are
    #   the user-given name plus the string "I_0/I"
    # For example if our analyses were:
    #     take_signal_near(610, 10), find_wavelength_of_max_signal(610, 10), take_sigal_at(500)
    #     Peak_Height_Near610,       True_610_Wavelength,                    Peak_Height_At500
    #     True,                      False,                                  True
    # Then we would want our headers to be:
    #     "Cat_Volume_uL", "Quench_Volume_uL", "Diluent_Volume_uL", "[Q]", "[Cat]",
    #     "Peak_Height_Near610", "True_610_Wavelength", "Peak_Height_At500",
    #     "Peak_Height_Near610 I_0/I", "Peak_Height_At500 I_0/I",
    base_headers = ["Cat_Volume_uL", "Quench_Volume_uL", "Diluent_Volume_uL", "[Q]", "[Cat]", ]
    added_headers = list(analysis_headers)
    further_analysis = [f"{header} I_0/I" for header in itertools.compress(analysis_headers, analysis_masks)]
    header = ', '.join(base_headers + added_headers + further_analysis)
    # For the Lehrer-adjusted Stern-Volmer analysis, we would replace "I_0/I" with "I_0/(I_0 - I)"

    # Collect I_0 values for all analyses so the indices remain consistent
    i_0_values = [
        determine_base_intensity(*data, data_idx=idx)[0]
        for idx in range(len(description.get_analyses()))
    ]
    # Grab the quencher concentrations present in `data`
    x_data = [entry.quencher_concentration for entry in data]

    # Save the data and perform the analyses
    with open(to_file, 'w+') as output_file:
        # Create the Table
        output_file.write(header + "\n")
        for datum in data:
            # Following a similar pattern as before, identify the common data, the raw signals, and the Stern-Volmer
            #   -processed data, then write them to a file.
            base_data = [
                datum.actual.catalyst, datum.actual.quencher, datum.actual.diluent,
                datum.quencher_concentration, datum.catalyst_concentration,
            ]
            added_data = [
                signal for signal in datum.signal_value
            ]
            if len(datum.signal_value) != len(analysis_masks):
                print(f"Error in '{to_file}': datum and description disagree on the number of analyses.")
                continue
            further_data = [
                i_0_values[idx]/signal
                for idx, signal in itertools.compress(enumerate(datum.signal_value), analysis_masks)
                # For each element in datum.signal_value for which the corresponding element in analysis_masks is true
            ]
            data_to_write = base_data + added_data + further_data
            datum_line = ", ".join([str(d) for d in data_to_write])
            output_file.write(f"{datum_line}\n")
        # With the summary table complete, let's write the regressions:
        output_file.write("\nRegressions")

        for idx, analyzed_header in itertools.compress(enumerate(analysis_headers), analysis_masks):
            y_data = [i_0_values[idx] / entry.signal_value[idx] for entry in data]
            # Note: If using Lehrer Stern-Volmer:
            # y_data = [i_0_values[idx] / (i_0_values[idx] - entry.signal_value[idx]) for entry in data]
            slr_results = slr(x_data, y_data)
            output_file.write(
                f"\n{analyzed_header}\n"
                f"slope, {slr_results.slope}, {slr_results.slope_uncertainty}\n"
                f"intercept, {slr_results.intercept}, {slr_results.intercept_uncertainty}\n"
                f"pearsons_r2, {slr_results.pearsons_r2}\n"
                f"rmse, {slr_results.rmse}\n"
                f"mae, {slr_results.mae}\n"
            )

        if description.spectral_analysis:
            output_file.write(f"\n{description.spectral_analysis.tag_repr()}\n")


#                                                                                                         # BIG CHANGE #
# Part 6: This part is very similar to Part 5.
# There are decisions to make here regarding the Quality of Fit.
# To determine IF the system should run another two experiments:
#   a) Base the quality of fit on a single measurement (for example, the first analysis)
#   b) Base the quality of fit on the worst measurement
#   c) Variants of (b) with the best, the average, etc. measurement
#   d) Other...
# But with multiple analyses, WHICH experiment should be selected?
#   i)   Base selection on a single measurement's most surprising point
#   ii)  Base selection on the worst/best/mean measurement's most surprising point
#   iii) Base selection on the most surprising point overall
#   iv)  Other...
# For this, we will determine IF using the worst R^2 and Intercept metrics
# and then WHICH using the overall most surprising point overall.
# The others can be derived from these by fixing the indices.
def validation_study(factory: SVSpecFactory,
                     using_calibration: Callable[[float], float],
                     description: LedgerLine,
                     cat_loc: Placeable,
                     quench_loc: Placeable,
                     dil_loc: Placeable,
                     req_threshold: float = 1.0,
                     intercept_check: float = None) -> Generator[SVSpec, Any, None]:
    apellomancer = factory.name_wizard
    data_files = get_files(directory=apellomancer.project_directory, key="_PL_")
    data_entries = extract_data(data_files, apellomancer,
                                description.catalyst_concentration, description.quencher_concentration,
                                description.spectral_analysis, using_calibration)
    if not data_entries:
        print("No data found for automatic_study()...")
        return

    data_entries.sort(key=lambda d: d.quencher_concentration)

    save_data_summary(data_entries,
                      os.path.join(
                          name_wizard.project_directory,
                          f"{description.catalyst_name}_{description.quencher_name}_summary.csv"
                      ),
                      description)

    # Perform (prelim) regression to determine if this is even necessary
    i_0_set: list[tuple[float, list[int]]] = [
        determine_base_intensity(*data_entries, data_idx=idx)
        for idx in range(len(description.get_analyses()))
    ]
    # each element of i_0_set is a tuple:
    # (The numerical value of I_0 , A list of indices for the data used to generate I_0)
    # Each of these tuples correspond to a different analysis. Again, i_0_set will be calculated
    # for all data, regardless of whether it is to under Stern-Volmer analysis.
    # Due to the nature of I_0 being the No-Quencher sample, every tuple in this list *should* have the same
    # list of indices--they will all have their own numerical values of I_0 but all have the same list of
    # indices used to generate I_0.
    all_i_0_indices = set(itertools.chain.from_iterable(idx_list for _, idx_list in i_0_set))

    x_data = [entry.quencher_concentration for entry in data_entries]

    worst_r2: tuple[RegressionReport, int, list[float]] | None = None
    worst_intercept: tuple[RegressionReport, int, list[float]] | None = None
    all_slr_results: list[tuple[RegressionReport, list[float]]] = []

    for idx, analyzed_header in itertools.compress(enumerate(description.get_headers()), description.get_mask()):
        y_data = [i_0_set[idx][0] / entry.signal_value[idx] for entry in data_entries]
        # Note: If using Lehrer Stern-Volmer:
        # y_data = [i_0_values[idx] / (i_0_values[idx] - entry.signal_value[idx]) for entry in data]
        slr_results = slr(x_data, y_data)
        all_slr_results.append((slr_results, y_data))
        # If you only cared about the regressions where something failed, you could move this append statement to the
        # end of the loop

        r2_is_good = (req_threshold is None) or (slr_results.pearsons_r2 >= req_threshold)
        intercept_is_good = (intercept_check is None) or ((1 - intercept_check) <= slr_results.intercept <= (1 + intercept_check))

        if r2_is_good and intercept_is_good:  # Skip ahead if they are both good
            continue
        # Move append to here if you only wanted to calculate surprise for the poorly fit regression
        if not intercept_is_good:
            if worst_intercept is None:
                worst_intercept = (slr_results, idx, y_data)
            else:
                if abs(slr_results.intercept - 1) > abs(worst_intercept[0].intercept - 1):
                    worst_intercept = (slr_results, idx, y_data)
        if not r2_is_good:
            if worst_r2 is None:
                worst_r2 = (slr_results, idx, y_data)
            else:
                if slr_results.pearsons_r2 < worst_r2[0].pearsons_r2:
                    worst_r2 = (slr_results, idx, y_data)
    # If neither worst was ever set, then all the R2 and intercepts were good
    overall_r2_is_good = worst_r2 is None
    overall_intercept_is_good = worst_intercept is None
    if overall_r2_is_good and overall_intercept_is_good:
        print("Both R2 and y(0) are good for all analyses!")
        return

    print(f"Performing check experiments [{overall_r2_is_good=}, {overall_intercept_is_good=}]")

    # We always redo the I_0 test, so
    for _, i_0_indices in i_0_set:
        if i_0_indices:
            check_i_0 = data_entries[i_0_indices[0]]
            yield factory.make_from_description(check_i_0.nominal, cat_loc, quench_loc, dil_loc)
            break  # Break after just one, otherwise it will do a No-Quencher measurement for every analysis.

    # Since we want the most surprising point overall, we will iterate over the results first to find all candidates.
    candidates_for_retesting: list[tuple[int, float]] = []
    for slr_report, y_data in all_slr_results:
        surprises = slr_report.surprise(x_data, y_data)
        try:
            # We want to ignore any suggestions to redo a No-quencher measurement, since we've already added that one.
            retest, score = surprises.pop(0)
            while retest in all_i_0_indices:
                retest, score = surprises.pop(0)
            candidates_for_retesting.append((retest, score))
        except IndexError:
            pass
    retest, _ = max(candidates_for_retesting, key=lambda x: x[1])
    # `key=lambda x: x[1]` means that max will look at element 1 (the score) when finding the max. It will still return
    # the whole tuple[index, score]
    # Now, is it fair to compare surprises between different data sets? Probably not great, but
    yield factory.make_from_description(data_entries[retest].nominal, cat_loc, quench_loc, dil_loc)


if __name__ == '__main__':
    umbrella_project_name = "Expanded_SternVolmer"
    name_wizard = SVApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name=umbrella_project_name,
        file_header="sva3_advanced__var__",
        mode='w'
    )

    abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False, wavelength_calibration=-5, slit="L10")
    pl_opt_specs = OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000, correct_dark_counts=True, wavelength_calibration=-5, slit="L10")
    calibration: Callable[[float], float] = lambda x: max(0.0, 0.9765 * float(x) - 0.2440)  # Set Feb 4, 2025 from "Manuscript Figures Data.xlsx"

    default_factory = SVSpecFactory(
        name_wizard,
        3,
        None,  # abs_opt_specs (ABS measurements could be used for inner-filter effect corrections if applicable)
                        #   For examples on how to combine PL and ABS data, see the PLQY workflow.
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
    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    # Example experimental campaign showing three modes of analysis
    ledger: list[LedgerLine] = [
        LedgerLine(rack="pos_1_rack",
                   catalyst_id="A1", catalyst_name="rubpy", catalyst_concentration=5.0,
                   quencher_id="A2", quencher_name="anethol", quencher_concentration=3.33,
                   diluent_id="A4",
                   # A classic example, single analysis
                   spectral_analysis=SpectralProcessingSpec(None, None, take_sigal_at(610)),
                   analysis_headers="Peak_610",
                   analysis_mask=True
                   ),
        LedgerLine("pos_1_rack",
                   "B1", "osbpy", 5.0,
                   "B2", "styrene", 1.39,
                   "B4",
                   # In this case, we have two analyses but only one is for Stern-Volmer.
                   # Because the first analysis is take_signal_*near*, the second method allows us
                   #   to record the actual wavelength used. (E.g., Near 750 --> 748 nm).
                   SpectralProcessingSpec(None, None, (take_sigal_near(750, 50), find_wavelength_of_max_signal(750, 50))),
                   ("Peak_Near750", "Wavelength"),
                   (True, False)
                   ),
        LedgerLine("pos_1_rack",
                   "C1", "IrppyFF", 5.0,
                   "C2", "pyrene", 1.00,
                   "C4",
                   # In this case, we want to perform Stern-Volmer analyses at multiple wavelengths
                   SpectralProcessingSpec(None, None,
                                          (take_sigal_near(475, 15), find_wavelength_of_max_signal(475, 15),
                                           take_sigal_near(500, 15), find_wavelength_of_max_signal(500, 15),
                                           take_sigal_at(540))
                                          ),
                   ("Peak_Near475", "Wavelength", "Peak_Near500", "Wavelength", "Peak_540"),
                   (True, False, True, False, True)
                   ),
        # and so on...
    ]

    # # # # START # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    prime(glh, WASTE, 1400)
    global_index = 0  # Remember to set if Resuming a campaign #
    try:
        for q_idx, line in enumerate(ledger):
            print(f"Current sample = {line.catalyst_name}_{line.quencher_name}")
            name_wizard.file_header = f"sva3_{line.catalyst_name}_{line.quencher_name}"
            name_wizard.update_sub_directory(f"{line.catalyst_name}_{line.quencher_name}")
            my_spectrometer.measure_average_reference('pl', 'dark', **pl_opt_specs)
            my_spectrometer.measure_average_reference('pl', 'light', **pl_opt_specs)

            # Primary study
            global_index = run_campaign(
                primary_study(
                    default_factory,
                    glh.locate_position_name(line.rack, line.catalyst_id),
                    glh.locate_position_name(line.rack, line.quencher_id),
                    glh.locate_position_name(line.rack, line.diluent_id),
                    cat_aliquot=10,
                    min_aliquot=10,
                    n_samples=4,
                    max_total=50
                ),  # V(Q) = 0 | 10  16.67  23.33  30 | 40
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
                validation_study(
                    default_factory,
                    calibration,
                    line,
                    glh.locate_position_name(line.rack, line.catalyst_id),
                    glh.locate_position_name(line.rack, line.quencher_id),
                    glh.locate_position_name(line.rack, line.diluent_id),
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
                my_data_entries = extract_data(my_data_files, name_wizard,
                                               line.catalyst_concentration, line.quencher_concentration,
                                               line.spectral_analysis,
                                               calibration)
                if my_data_entries:
                    my_data_entries.sort(key=lambda d: d.quencher_concentration)
                    save_data_summary(my_data_entries,
                                      os.path.join(name_wizard.project_directory, f"{line.catalyst_name}_{line.quencher_name}_summary.csv"),
                                      line)
                else:
                    print(f"No data found for {line.catalyst_name}_{line.quencher_name}?")
            except Exception as e:
                print(f"The following error prevented saving summary data for {line.catalyst_name}_{line.quencher_name}")
                print(repr(e))
    except KeyboardInterrupt:
        print("User exited the loop early")
    except StopIteration:
        print("Exiting early due to system volume concerns.")
    clean_up(glh, WASTE)

    # ID of vial cap is 6 mm
    # Access ID is 6.2 mm
    # Vial cap taurus width: 2.6 mm