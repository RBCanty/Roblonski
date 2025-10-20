import os
from typing import NamedTuple, Callable, Sequence, Literal

import numpy as np
from scipy.optimize import minimize

from aux_devices.signal_processing import smooth
from aux_devices.spectra import Spectrum, SpectrumFactory, SpectraStack
from data_management.common_dp_steps import get_files, SpectralProcessingSpec, take_sigal_near, \
    find_wavelength_of_max_signal, take_sigal_at
from data_management.simple_linear_regression import slr
from misc_func import silence
from workflows.serial_measurement.naming import SMSpecDescription, SMApellomancer
from workflows.serial_measurement.serial_spec import Experiment


class Datum(NamedTuple):
    """ Stores the data discernible from the file name and the spectrum.

     - nominal: SMSpecDescription
     - signal_value: tuple[float, Sequence[float]]
     - spectral_segment: Spectrum
     - bkg_sub: bool
     """
    nominal: SMSpecDescription
    signal_value: tuple[float, Sequence[float]]
    spectral_segment: Spectrum
    bkg_sub: bool


def parse_concentration_tag(line: str) -> dict[str, float] | None:
    line = line.strip()
    if not line.startswith("Conc_0="):
        return None

    def normalize(sub: str):
        sub = sub.strip()
        # print(f"DEBUG: on '{sub}'")
        _key, _value, *_ = sub.split("=")
        _key = _key.strip()
        _value = _value.strip()
        value = None if _value == "None" else float(_value)
        if _key in ["Conc_0", "nFRAC", "aFRAC", "FRAC"]:
            return _key, value
        if "nConc_(" in _key:
            return "nConc", value
        if "aConc_(" in _key:
            return "aConc", value
        if "Conc_(" in _key:
            return "Conc", value
        return None, None

    return {k: v for k, v in [normalize(s) for s in line.split(",") if s] if k is not None}


def extract_background(from_files: list[str],
                       apellomancer: SMApellomancer):
    for file in from_files:
        try:
            description = apellomancer.parse_file_name(file)
        except (ValueError, TypeError) as err:
            print("\t" + repr(err))
            continue

        if description.flag != "REF":
            continue

        spec_fact = SpectrumFactory()
        try:
            open(file, 'r')
        except FileNotFoundError:
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
                # print(f"DEBUG: {line=}")
                w, _, _, p, *_ = line.split(",")
                try:
                    wavelength = float(w.strip())
                except ValueError:
                    continue
                try:
                    absorbance = float(p.strip())
                except ValueError:
                    # print(f"ValErr on '{p.strip()}'")
                    absorbance = np.nan

                spec_fact.add_point(wavelength, absorbance)

        this_spectrum: Spectrum = spec_fact.create_spectrum()
        smooth(this_spectrum, sigma=3.0)
        yield this_spectrum
    return None


def extract_data(from_files: list[str],
                 apellomancer: SMApellomancer,
                 dye_src_conc: float,
                 peak_args: SpectralProcessingSpec | Sequence[SpectralProcessingSpec],
                 advanced_bkg_subtraction: tuple[Callable[[np.ndarray, Spectrum, Spectrum], Spectrum], Callable[[Spectrum], float], np.ndarray] = None
                 ) -> list[Datum]:
    data_points = []

    backgrounds = list(extract_background(from_files, apellomancer))
    if backgrounds:
        background: Spectrum | None = (1/len(backgrounds)) *  sum(backgrounds[1:], start=backgrounds[0])
    else:
        background = None

    for file in from_files:
        # print(f"On {file}")
        try:
            description = apellomancer.parse_file_name(file)
        except (ValueError, TypeError) as err:
            print("\t" + repr(err))
            continue

        spec_fact = SpectrumFactory()
        serial_dilution_tag: dict[str, float] | None = None
        try:
            open(file, 'r')
        except FileNotFoundError:
            print(f"\tFile '{file}' was hidden, ignoring.")
            continue
        with open(file, "r") as csv:
            latch = False
            for line in csv:
                if serial_dilution_tag is None:
                    serial_dilution_tag = parse_concentration_tag(line)
                if not latch:
                    if "wavelength" not in line:
                        continue
                    else:
                        latch = True
                        continue
                # print(f"DEBUG: {line=}")
                w, _, _, p, *_ =  line.split(",")
                try:
                    wavelength = float(w.strip())
                except ValueError:
                    continue
                try:
                    absorbance = float(p.strip())
                except ValueError:
                    # print(f"ValErr on '{p.strip()}'")
                    absorbance = np.nan

                spec_fact.add_point(wavelength, absorbance)

        this_spectrum: Spectrum = spec_fact.create_spectrum()
        smooth(this_spectrum, sigma=3.0)
        sub_bkg = ((description.flag == "EXP") or (description.flag is None)) and (background is not None)
        if sub_bkg:
            if advanced_bkg_subtraction is None:
                this_spectrum = this_spectrum - background
            else:
                _bkg_sub, _fold, _x0 = advanced_bkg_subtraction
                alpha = minimize(lambda a: _fold(_bkg_sub(a, this_spectrum, background)), x0=_x0)
                if not alpha.success:
                    print(f"BKG ERROR: {alpha.message}")
                # else:
                #     print(f"{file} --> {alpha.x}")
                this_spectrum = _bkg_sub(alpha.x, this_spectrum, background)
        this_segment = this_spectrum.segment(**peak_args.segment_kwargs())
        if isinstance(peak_args.analysis, Sequence):
            peak_values = [analysis(this_segment) for analysis in peak_args.analysis]
        else:
            peak_values = [peak_args.analysis(this_segment), ]

        if serial_dilution_tag is None:
            entry_conc = dye_src_conc
        elif description.flag == "REF":
            entry_conc = 0.0
        elif "Conc" in serial_dilution_tag.keys():
            entry_conc = serial_dilution_tag['Conc']
        elif "aConc" in serial_dilution_tag.keys():
            entry_conc = serial_dilution_tag['aConc']
        else:
            entry_conc = dye_src_conc

        entry = Datum(
            description,
            (entry_conc, peak_values),
            this_segment,
            sub_bkg
        )

        data_points.append(entry)
        print(f"\tAdded {os.path.basename(file)}")

    return data_points


def simple_background_subtraction(alpha: np.ndarray[tuple[1, ], np.float64], spectrum: Spectrum, bkg: Spectrum):
    """ signal - factor * background """
    _alpha = float(alpha[0])
    return spectrum - _alpha * bkg


def simple_asymmetric_least_squares(spectrum: Spectrum, beta: float):
    """ ALS: beta is the weight of negative entries; (1 - beta) the weight of positive entries. """
    signal = np.copy(spectrum.signal)
    signal[signal > 0] = (1 - beta) * np.sqrt(np.square(signal[signal > 0]))
    signal[signal <= 0] = beta * np.square(signal[signal <= 0])
    return np.nansum(signal)


def save_data_summary(data: list[Datum], to_file: str, peak_args: SpectralProcessingSpec = None):
    bkgs = [d for d in data if d.nominal.flag == "REF"]
    bkg_x = sum([0.0 for _ in bkgs], start=0.0) / max(1, len(bkgs))
    was_bkg_sub = any(d.bkg_sub for d in data)

    bkg_y_set = [
        sum([x if not was_bkg_sub else 0.0], start=0.0)/max(1, len(bkgs))
        for x in zip(*[d.signal_value[1] for d in bkgs])
    ]

    data.sort(key=lambda d: -1 if d.nominal.dil_seq is None else d.nominal.dil_seq)
    x_data = [d.signal_value[0] for d in data] + [bkg_x, ]
    y_dataset = [d.signal_value[1] for d in data] + [bkg_y_set, ]
    y_dataset = [list(ys) for ys in zip(*y_dataset)]

    with open(to_file, "w") as output_file:
        output_file.write("Concentration, " + ", ".join(str(x) for x in x_data) + "\n")
        for y_data in y_dataset:
            output_file.write("Signal, " + ", ".join(str(y) for y in y_data) + "\n")
        headers = ["Wavelength_nm", ] + [f"S-{d.nominal.flag}{"" if d.nominal.dil_seq is None else d.nominal.dil_seq}" for d in data]
        SpectraStack(*[d.spectral_segment for d in data]).print(output_file, header=headers)
        output_file.write("\n" * 4)

    data = [d for d in data if d.nominal.flag == "EXP"]
    data.sort(key=lambda d: d.nominal.dil_seq)

    x_data = [bkg_x, ] + [d.signal_value[0] for d in data]
    for bkg_y, y_data in zip(bkg_y_set, y_dataset):
        slr_results = slr(x_data, [bkg_y, ] + y_data[2:-1] )

        with open(to_file, "a+") as output_file:
            output_file.write(
                f"slope, {slr_results.slope}, {slr_results.slope_uncertainty}\n"
                f"intercept, {slr_results.intercept}, {slr_results.intercept_uncertainty}\n"
                f"pearsons_r2, {slr_results.pearsons_r2}\n"
                f"rmse, {slr_results.rmse}\n"
                f"mae, {slr_results.mae}\n"
            )
    with open(to_file, "a+") as output_file:
        if peak_args:
            output_file.write(f"\n{peak_args.tag_repr()}\n")


def process_abs_data(line: Experiment):
    abs_opt_specs = line.abs_optic_spec
    absorption = line.abs_spec_processing
    concentration = line.source_concentration
    name = line.name
    name_wizard = line.name_wizard

    if not (abs_opt_specs and absorption):
        return
    try:
        _data_files = silence(get_files)(directory=name_wizard.project_directory, key="_aABS_")
        _x0 = np.array([1, ])
        _data_entries = extract_data(_data_files, name_wizard, concentration, absorption,
                                              advanced_bkg_subtraction=(
                                                  simple_background_subtraction,
                                                  # Callable[[np.ndarray, Spectrum, Spectrum], Spectrum]
                                                  lambda s: simple_asymmetric_least_squares(s, 0.98),
                                                  # Callable[[Spectrum], float]
                                                  _x0  # np.ndarray
                                              ))
        if _data_entries:
            save_data_summary(_data_entries,
                              os.path.join(name_wizard.project_directory, f"{name}_abs_summary.csv"),
                              absorption)
        else:
            print(f"No abs data found for {name}?")
    except Exception as e:
        print(f"The following error prevented saving ABS summary data for {name}")
        print(repr(e))


def process_pl_data(line: Experiment):
    pl_opt_specs = line.pl_optic_spec
    photoluminescence = line.pl_spec_processing
    concentration = line.source_concentration
    name = line.name
    name_wizard = line.name_wizard

    if not (pl_opt_specs and photoluminescence):
        return
    try:
        _data_files = silence(get_files)(directory=name_wizard.project_directory, key="_aPL_")
        _x0 = np.array([1, ])
        _data_entries = silence(extract_data)(_data_files, name_wizard, concentration, photoluminescence,
                                              advanced_bkg_subtraction=(
                                                  simple_background_subtraction,  # Callable[[np.ndarray, Spectrum, Spectrum], Spectrum]
                                                  lambda s: simple_asymmetric_least_squares(s, 0.98),  # Callable[[Spectrum], float]
                                                  _x0   # np.ndarray
                                              ))
        if _data_entries:
            save_data_summary(_data_entries,
                              os.path.join(name_wizard.project_directory, f"{name}_pl_summary.csv"),
                              photoluminescence)
        else:
            print(f"No pl data found for {name}?")
    except Exception as e:
        print(f"The following error prevented saving PL summary data for {name}")
        print(repr(e))


class ComparativeDatum(NamedTuple):
    mode: Literal['ABS', 'PL']
    conc: float
    signals: tuple[float, ...]
    data_type: Literal['CHK', 'REF', 'EXP', 'INT']
    idx: int | None

    @classmethod
    def from_column(cls, mode: Literal['ABS', 'PL'], column: tuple):
        _conc, *_signals, _def = column
        conc = float(_conc)
        signals = tuple(float(s) for s in _signals)
        if not _def.strip():
            dt = 'INT'
            idx = -1
        elif "CHK" in _def:
            dt = "CHK"
            idx = None
        elif "REF" in _def:
            dt = "REF"
            idx = None
        elif "EXP" in _def:
            dt = "EXP"
            *_, _idx = _def.strip().split("EXP")
            idx = int(_idx)
        else:
            raise ValueError(f"Could not process ({', '.join([str(e) for e in column])})")
        return cls(mode=mode, conc=conc, signals=signals, data_type=dt, idx=idx)


def process_rplqy_data(line: Experiment,
                       abs_sel_idx: int = 1,
                       pl_sel_idx: int = 1,
                       abs_filter: Callable[[ComparativeDatum], bool] = None,
                       pl_filter: Callable[[ComparativeDatum], bool] = None):
    if abs_filter is None:
        abs_filter = lambda _: True
    if pl_filter is None:
        pl_filter = lambda  _: True
    name = line.name
    name_wizard = line.name_wizard
    abs_data_file = os.path.join(name_wizard.project_directory, f"{name}_abs_summary.csv")
    pl_data_file = os.path.join(name_wizard.project_directory, f"{name}_pl_summary.csv")
    _abs_data_set: list[tuple[float | str, ...]] = []
    try:
        with open(abs_data_file, 'r') as _abs_file:
            for _line in _abs_file:
                row_name, *row_data = _line.strip().split(", ")
                _abs_data_set.append(row_data)
                if "Wavelength" in row_name:
                    break
    except FileNotFoundError:
        print("(rPLQY) No ABS summary file for rPLQY data processing")
        return
    _pl_data_set: list[tuple[float | str, ...]] = []
    try:
        with open(pl_data_file, 'r') as _pl_file:
            for _line in _pl_file:
                row_name, *row_data = _line.strip().split(", ")
                _pl_data_set.append(row_data)
                if "Wavelength" in row_name:
                    break
    except FileNotFoundError:
        print("(rPLQY) No PL summary file for rPLQY data processing")
        return
    abs_data_set = [ComparativeDatum.from_column('ABS', _col) for _col in zip(*_abs_data_set)]
    pl_data_set = [ComparativeDatum.from_column('PL', _col) for _col in zip(*_pl_data_set)]
    abs_data_set = [cd for cd in abs_data_set if cd.data_type in ['EXP', 'INT'] and abs_filter(cd)]
    pl_data_set = [cd for cd in pl_data_set if cd.data_type in ['EXP', 'INT'] and pl_filter(cd)]
    common_idx = {cd.idx for cd in abs_data_set} & {cd.idx for cd in pl_data_set}
    abs_data_set = [cd for cd in abs_data_set if cd.idx in common_idx]
    pl_data_set = [cd for cd in pl_data_set if cd.idx in common_idx]
    abs_data_set.sort(key=lambda cd: cd.idx)
    pl_data_set.sort(key=lambda cd: cd.idx)
    i_data = [cd.idx for cd in  pl_data_set]
    x_data = [1.0 - 10.0**(-cd.signals[abs_sel_idx]/1000.0) for cd in abs_data_set]
    y_data = [cd.signals[pl_sel_idx] for cd in pl_data_set]

    if len(i_data) < 2:
        print("(rPLQY) No data survived pre-processing")
        return
    slr_results = slr(x_data, y_data)
    rplqy_data_file = os.path.join(name_wizard.project_directory, f"{name}_rplqy_summary.csv")

    with open(rplqy_data_file, "w+") as output_file:
        output_file.write("ExpIdx, "   + ", ".join(str(i) for i in i_data) + "\n")
        output_file.write("Abscissa, " + ", ".join(str(x) for x in x_data) + "\n")
        output_file.write("Ordinate, " + ", ".join(str(y) for y in y_data) + "\n")
        output_file.write("\n")
        output_file.write(
            f"slope, {slr_results.slope}, {slr_results.slope_uncertainty}\n"
            f"intercept, {slr_results.intercept}, {slr_results.intercept_uncertainty}\n"
            f"pearsons_r2, {slr_results.pearsons_r2}\n"
            f"rmse, {slr_results.rmse}\n"
            f"mae, {slr_results.mae}\n"
        )
        output_file.write(
            f"ABS_data_src, {abs_data_file}\n"
            f"PL_data_src, {pl_data_file}\n"
            f"abs_sel_idx, {abs_sel_idx}, pl_sel_idx, {pl_sel_idx}\n"
            f"abs_filter, {abs_filter.serialize() if hasattr(abs_filter, 'serialize') else 'NA'}\n"
            f"pl_filter, {pl_filter.serialize() if hasattr(pl_filter, 'serialize') else 'NA'}\n"
        )


if __name__ == '__main__':
    from aux_devices.ocean_optics_spectrometer import OpticalSpecs

    # my_dye_name, my_dye_src_conc, my_abs_peak_method = "rubpy", 0.20, (350, 650, take_sigal_at(452))
    MODE = "ABS"

    my_name_wizard = SMApellomancer(
        # directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        directory=r"D:\Canty\Documents\Occupations\Post Doc\Gilson Project",
        project_name="BLS2 (2025 May 14)",
        file_header="",
        mode='r'
    )
    my_name_wizard.sub_directory = "Perylene2"

    dp_line = Experiment.data_processing_recovery_object(
        name="Perylene2",
        name_wizard=my_name_wizard,
        source_concentration=0.03,
        abs_optic_spec=OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False,
                                    wavelength_calibration=-5),
        pl_optic_spec=None,
        abs_spec_processing=SpectralProcessingSpec(350, 800, (  # take_sigal_near(435.75 - 5, 5)),
            take_sigal_near(435.75 - 5, 5),
            find_wavelength_of_max_signal(435.75 - 5, 5),
            take_sigal_at(430.5)
        )),
    )

    process_abs_data(dp_line)

    # my_data_files = get_files(
    #     directory=my_name_wizard.project_directory,
    #     key=f"_a{MODE}_"
    # )
    # bkg = extract_background(my_data_files, my_name_wizard)
    # my_data_entries = extract_data(
    #     my_data_files,
    #     my_name_wizard,
    #     my_dye_src_conc,
    #     my_abs_peak_method,
    # )
    # if my_data_entries:
    #     save_data_summary(
    #         my_data_entries,
    #         os.path.join(my_name_wizard.project_directory, f"{my_dye_name}_{MODE.lower()}_summary.csv"),
    #         my_abs_peak_method
    #     )
        # Connected to device