import os
from operator import itemgetter
from typing import Callable, Literal, NamedTuple

import numpy as np

from aux_devices.signal_processing import smooth
from aux_devices.spectra import Spectrum, SpectrumFactory
from data_management.common_dp_steps import get_files, take_sigal_at, SpectralProcessingSpec
from workflows.stern_volmer.naming import SVSpecDescription, SVApellomancer
from data_management.simple_linear_regression import slr


class Datum(NamedTuple):
    """ Stores the data discernible from the file name and the spectrum"""
    nominal: SVSpecDescription
    actual: SVSpecDescription
    signal_value: float
    quencher_concentration: float
    catalyst_concentration: float
    spectral_segment: Spectrum


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
            for line in csv:
                if not latch:
                    if "wavelength" not in line:
                        continue
                    else:
                        latch = True
                        continue

                w, *_, p =  line.split(", ")
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
        smooth(this_spectrum, sigma=3.0)  # NOTE:  To help fight against
        #  noise, I am using a moving average (gaussian-weighted) of the data +/- 3 data points (roughly +/- 1 nm).
        #  This gets rid of those single points that go super high or low.

        rubpy3_segment = this_spectrum.segment(**peak_args.segment_kwargs())  # i.e. @ 610 nm (610.23 nm)
        # rubpy3_segment = this_spectrum.segment(lower_bound=525, upper_bound=700)  # NOTE: Where should the peak be
        #  You can reduce this to like 600--613 to cut of the mini-peak at 618, though it doesn't actually help all
        #  that much, since it's just a constant +100 to all the spectra.
        peak_value = peak_args.analysis(rubpy3_segment)

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
            peak_value,
            quencher_volume * qch_src_conc / droplet_volume,
            _cat_conc,
            rubpy3_segment
        )

        data_points.append(entry)
        print(f"\tAdded {os.path.basename(file)}")

    return data_points


def determine_base_intensity(*data: Datum, method: Literal['min', 'max', 'avg'] = 'avg'):
    """ Provides a value for the base intensity and the indices used for calculation """
    pure_catalyst_indices = []
    pure_catalyst_signals = []
    for idx, datum in enumerate(data):
        nom_qch_vol = datum.nominal.quencher
        # nom_qch_vol = datum.actual.quencher
        if nom_qch_vol:  # If it's neither None nor 0
            continue
        pure_catalyst_signals.append(datum.signal_value)
        pure_catalyst_indices.append(idx)
    # print(f"DEBUG: {pure_catalyst_signals}, {pure_catalyst_indices}")
    if not pure_catalyst_signals:
        raise ValueError("No pure catalyst signals detected!")
    if method == 'min':
        return min(pure_catalyst_signals), pure_catalyst_indices
    if method == 'max':
        return max(pure_catalyst_signals), pure_catalyst_indices
    if method == 'avg':
        return sum(pure_catalyst_signals)/len(pure_catalyst_signals), pure_catalyst_indices
    raise ValueError(f"the method must be min/max/avg, not '{method}'")


def get_data(from_files: list[str], apellomancer: SVApellomancer):
    data_points = []
    segments = []
    nom2actual: Callable[[str], float] = lambda x: max(0.0, 0.9765 * x - 0.2440)

    for file in from_files:
        print(f"On {file}")
        try:
            file_name = os.path.basename(file).split(".")[-2]
            description = apellomancer.parse_file_name(file)
            cat_volume = nom2actual(description.catalyst)
            quench_volume = nom2actual(description.quencher)
            diluent_volume = nom2actual(description.diluent)
        except (ValueError, TypeError) as err:
            print("\t" + repr(err))
            continue

        spec_fact = SpectrumFactory()
        with open(file, "r") as csv:
            latch = False
            for line in csv:
                if not latch:
                    if "wavelength" not in line:
                        continue
                    else:
                        latch = True
                        continue

                try:
                    w, d, l, p = line.split(", ")  # NOTE: Wavelength, light reference, PL
                except ValueError:
                    continue

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
        smooth(this_spectrum, sigma=3.0)  # NOTE:  To help fight against
        #  noise, I am using a moving average (gaussian-weighted) of the data +/- 3 data points (roughly +/- 1 nm).
        #  This gets rid of those single points that go super high or low.

        rubpy3_segment = this_spectrum.segment(lower_bound=525, upper_bound=700)  # NOTE: Where should the peak be
        #  You can reduce this to like 600--613 to cut of the mini-peak at 618, though it doesn't actually help all
        #  that much, since it's just a constant +100 to all the spectra.
        peak_value = np.nanmax(rubpy3_segment.signal)

        droplet_volume = cat_volume + quench_volume + diluent_volume
        segments.append((f"[Q]={quench_volume * quench_conc / droplet_volume:.3f}", rubpy3_segment))

        if "sva2" in file_name:
            _cat_conc = (quench_volume + cat_volume) * cat_conc / droplet_volume
        elif "sva3" in file_name:
            _cat_conc = cat_volume * cat_conc / droplet_volume
        else:
            _cat_conc = -1

        entry = (
            cat_volume,
            quench_volume,
            diluent_volume,
            peak_value,
            quench_volume * quench_conc / droplet_volume,
            _cat_conc
        )

        data_points.append(entry)
        print(f"\tAdded {file_name}")

    data_points.sort(key=lambda x: x[1])
    segments.sort(key=lambda x: float(x[0][4:]))

    return data_points, segments


def save_data(data, to_file: str):
    sel_peak = itemgetter(3)
    intensity_naught = sel_peak(max(data, key=sel_peak))
    with open(to_file, 'w+') as output_file:
        output_file.write(f"Cat_Volume_uL, Quench_Volume_uL, Diluent_Volume_uL, Peak_au, "
                          f"[Q], [Cat], I_0/I\n")
        for datum in data:
            datum_line = ", ".join([str(d) for d in datum])
            output_file.write(f"{datum_line}, {intensity_naught / sel_peak(datum)}\n")


def save_data_summary(data: list[Datum], to_file: str, peak_args: SpectralProcessingSpec = None):
    i_0, _ = determine_base_intensity(*data)
    with open(to_file, 'w+') as output_file:
        output_file.write(f"Cat_Volume_uL, Quench_Volume_uL, Diluent_Volume_uL, Peak_au, "
                          f"[Q], [Cat], I_0/I\n")
        for datum in data:
            data_to_write = [
                datum.actual.catalyst, datum.actual.quencher, datum.actual.diluent, datum.signal_value,
                datum.quencher_concentration, datum.catalyst_concentration, i_0/datum.signal_value
            ]
            datum_line = ", ".join([str(d) for d in data_to_write])
            output_file.write(f"{datum_line}\n")
        output_file.write("\n\n\n")

        x_data = [entry.quencher_concentration for entry in data]
        y_data = [i_0 / entry.signal_value for entry in data]
        slr_results = slr(x_data, y_data)
        output_file.write(
            f"slope, {slr_results.slope}, {slr_results.slope_uncertainty}\n"
            f"intercept, {slr_results.intercept}, {slr_results.intercept_uncertainty}\n"
            f"pearsons_r2, {slr_results.pearsons_r2}\n"
            f"rmse, {slr_results.rmse}\n"
            f"mae, {slr_results.mae}\n"
        )

        if peak_args:
            output_file.write(f"\n{peak_args.tag_repr()}\n")


def save_segments(segments: list[tuple[str, Spectrum]], to_file: str):
    _headers = [_h for _h, _s in segments]
    _segments = [_s.signal for _h, _s in segments]
    _segments = [segments[0][1].wavelengths] + _segments
    with open(to_file, 'w+') as output_file:
        output_file.write("Wavelength (nm), " + ", ".join(_headers) + "\n")
        for spectra in zip(*_segments):
            data_line = ", ".join([str(d) for d in spectra])
            output_file.write(f"{data_line}\n")


if __name__ == '__main__':
    cat_conc = 5.0191
    calibration: Callable[[float], float] = lambda x: max(0.0, 0.9765 * float(x) - 0.2440)  # Set Feb 4, 2025 from "Manuscript Figures Data.xlsx"
    signal_method: SpectralProcessingSpec = SpectralProcessingSpec(None, None, take_sigal_at(610))  # Take the point closest to 610 nm

    quencher_name, quench_conc = "3-nitrobenzaldehyde", 499.5439
    name_wizard = SVApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name="Big SVA 2 (2025 Mar 14)",
        file_header="",
        mode='r'
    )
    name_wizard.sub_directory = quencher_name

    data_files = get_files(directory=name_wizard.project_directory, key="_PL_")
    data_entries = extract_data(data_files, name_wizard, cat_conc, quench_conc, signal_method, calibration)
    if data_entries:
        data_entries.sort(key=lambda d: d.quencher_concentration)
        save_data_summary(data_entries, os.path.join(name_wizard.project_directory, f"{quencher_name}_summary.csv"), signal_method)

        # my_files = get_files(name_wizard.project_directory, key="_PL_")
        # my_data, my_segments = get_data(my_files)

        # save_data(my_data, to_file=os.path.join(name_wizard.project_directory, f"{quencher_name}_summary.csv"))
        # save_segments(my_segments, to_file=os.path.join(my_directory, "overview.csv"))
    else:
        print("No data found for automatic_study()...")
