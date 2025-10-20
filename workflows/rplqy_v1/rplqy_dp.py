import os
from collections.abc import Callable
from typing import NamedTuple

import numpy as np

from aux_devices.signal_processing import smooth
from aux_devices.spectra import Spectrum, SpectrumFactory, SpectraStack
from data_management.simple_linear_regression import slr
from data_management.common_dp_steps import take_sigal_at, SpectralProcessingSpec
from workflows.rplqy_v1.naming import RPLQYSpecDescription, RPLQYApellomancer


class Datum(NamedTuple):
    """ Stores the data discernible from the file name and the spectrum"""
    nominal: RPLQYSpecDescription
    signal_value: tuple[float, float]
    spectral_segment: Spectrum


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
        if _key in ["Conc_0", "nFRAC", "aFRAC", "FRAC"]:
            return _key, float(_value)
        if "nConc_(" in _key:
            return "nConc", float(_value)
        if "aConc_(" in _key:
            return "aConc", float(_value)
        if "Conc_(" in _key:
            return "Conc", float(_value)
        return None, None

    return {k: v for k, v in [normalize(s) for s in line.split(",") if s] if k is not None}


def extract_background(from_files: list[str],
                       apellomancer: RPLQYApellomancer):
    for file in from_files:
        try:
            description = apellomancer.parse_file_name(file)
        except (ValueError, TypeError) as err:
            print("\t" + repr(err))
            continue
        if description.instance is not None:
            continue

        spec_fact = SpectrumFactory()
        serial_dilution_tag: dict[str, float] | None = None
        is_not_reference_dil_tag: Callable[[dict[str, float]], bool] = \
            lambda dt: (dt is None) or (dt.get("Conc", None) != 0) or (dt.get("aConc", None) != 0)
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
                    if is_not_reference_dil_tag(serial_dilution_tag):
                        break
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

        if is_not_reference_dil_tag(serial_dilution_tag):
            continue

        this_spectrum: Spectrum = spec_fact.create_spectrum()
        smooth(this_spectrum, sigma=3.0)
        return this_spectrum
    return None


def extract_data(from_files: list[str],
                 apellomancer: RPLQYApellomancer,
                 dye_src_conc: float,
                 peak_args: SpectralProcessingSpec,
                 background: Spectrum = None
                 ) -> list[Datum]:
    data_points = []

    for file in from_files:
        print(f"On {file}")
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
        if background is not None:
            this_spectrum = this_spectrum - background
        this_segment = this_spectrum.segment(**peak_args.segment_kwargs())
        peak_value = peak_args.analysis(this_segment)

        if serial_dilution_tag is None:
            entry = Datum(
                description,
                (dye_src_conc, peak_value),
                this_segment
            )
        elif "Conc" in serial_dilution_tag.keys():
            entry = Datum(
                description,
                (serial_dilution_tag['Conc'], peak_value),
                this_segment
            )
        elif "aConc" in serial_dilution_tag.keys():
            entry = Datum(
                description,
                (serial_dilution_tag['aConc'], peak_value),
                this_segment
            )
        else:
            entry = Datum(
                description,
                (dye_src_conc, peak_value),
                this_segment
            )

        data_points.append(entry)
        print(f"\tAdded {os.path.basename(file)}")

    return data_points


def save_data_summary(data: list[Datum], to_file: str, peak_args: SpectralProcessingSpec = None):
    data.sort(key=lambda d: -1 if d.nominal.dil_seq is None else d.nominal.dil_seq)
    x_data = [d.signal_value[0] for d in data] + [0, ]
    y_data = [d.signal_value[1] for d in data] + [0, ]

    with open(to_file, "w") as output_file:
        output_file.write("Concentration, " + ", ".join(str(x) for x in x_data) + "\n")
        output_file.write("Signal, " + ", ".join(str(y) for y in y_data) + "\n")
        headers = ["Wavelength_nm", ] + [f"S{d.nominal.dil_seq}" for d in data]
        SpectraStack(*[d.spectral_segment for d in data]).print(output_file, header=headers)
        output_file.write("\n" * 4)

    idx_check = [d.nominal.dil_seq for d in data]
    if 0 in idx_check:
        data = [d for d in data if d.nominal.dil_seq is not None]
    else:
        for d in data:
            if d.nominal.dil_seq is None:
                d.nominal.dil_seq = 0
                break

    data.sort(key=lambda d: d.nominal.dil_seq)
    x_data = [0, ] + [d.signal_value[0] for d in data]
    y_data = [0, ] + [d.signal_value[1] for d in data]
    slr_results = slr(x_data, y_data)

    with open(to_file, "a+") as output_file:
        output_file.write(
            f"slope, {slr_results.slope}, {slr_results.slope_uncertainty}\n"
            f"intercept, {slr_results.intercept}, {slr_results.intercept_uncertainty}\n"
            f"pearsons_r2, {slr_results.pearsons_r2}\n"
            f"rmse, {slr_results.rmse}\n"
            f"mae, {slr_results.mae}\n"
        )
        if peak_args:
            output_file.write(f"\n{peak_args.tag_repr()}\n")


if __name__ == '__main__':
    from data_management.common_dp_steps import get_files

    my_dye_name, my_dye_src_conc, my_abs_peak_method = "rubpy", 0.20, SpectralProcessingSpec(350, 650, take_sigal_at(452))
    MODE = "ABS"

    my_name_wizard = RPLQYApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name="New Beer-Lambert Study (2025 Apr 25)",
        file_header="",
        mode='r'
    )
    my_name_wizard.sub_directory = "rubpy2"

    my_data_files = get_files(
        directory=my_name_wizard.project_directory,
        key=f"_{MODE}_"
    )
    bkg = extract_background(my_data_files, my_name_wizard)
    my_data_entries = extract_data(
        my_data_files,
        my_name_wizard,
        my_dye_src_conc,
        my_abs_peak_method,
        bkg
    )
    if my_data_entries:
        save_data_summary(
            my_data_entries,
            os.path.join(my_name_wizard.project_directory, f"{my_dye_name}_{MODE.lower()}_summary.csv"),
            my_abs_peak_method
        )
        # Connected to device