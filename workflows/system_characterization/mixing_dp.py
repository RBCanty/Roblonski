import os
from typing import Callable, NamedTuple

import numpy as np

from aux_devices.signal_processing import smooth
from aux_devices.spectra import Spectrum, SpectrumFactory
from workflows.stern_volmer.naming import SVSpecDescription, SVApellomancer


class Datum(NamedTuple):
    """ Stores the data discernible from the file name and the spectrum """
    nominal: SVSpecDescription
    actual: SVSpecDescription
    signal_value: float
    relative_concentration: float
    timestamp: str
    spectral_segment: Spectrum
    light_check: float
    mixing_displacement: float | int


def get_files(directory: str, key: str = None):
    files: list[str] = []
    for *_, file_names in os.walk(directory):
        for file_name in file_names:
            if key and (key not in file_name):
                continue
            files.append(os.path.join(directory, file_name))
            print(f"Grabbed {file_name}")
    return files



def extract_data(from_files: list[str], apellomancer: SVApellomancer, nom2actual: Callable[[float], float] = None):
    if nom2actual is None:
        nom2actual = lambda x: x

    data_points = []

    for file in from_files:
        print(f"On {file}")
        try:
            description = apellomancer.parse_file_name(file)
        except (ValueError, TypeError) as err:
            print("\t<parse_file_name>" + repr(err))
            continue

        spec_fact_abs = SpectrumFactory()
        spec_fact_ref = SpectrumFactory()
        with open(file, "r") as csv:
            file_iterator = iter(csv)
            _ = next(file_iterator)  # Filename
            timestamp = next(file_iterator)  # Timestamp
            basic_specs = next(file_iterator)  # Basic specs
            _ = next(file_iterator)  # Sequence counter
            _ = next(file_iterator)  # Spectral interval
            _ = next(file_iterator)  # Integration time
            _ = next(file_iterator)  # Corrections
            _ = next(file_iterator)  # Headers
            for line in file_iterator:
                w, *_, l, p =  line.split(", ")
                try:
                    wavelength = float(w)
                except ValueError:
                    continue
                try:
                    light_ref = float(l)
                except ValueError:
                    light_ref = np.nan
                try:
                    absorbance = float(p)
                except ValueError:
                    absorbance = np.nan

                spec_fact_abs.add_point(wavelength, absorbance)
                spec_fact_ref.add_point(wavelength, light_ref)

        abs_spectrum: Spectrum = spec_fact_abs.create_spectrum()
        ref_spectrum: Spectrum = spec_fact_ref.create_spectrum()
        smooth(abs_spectrum, sigma=3.0)
        smooth(ref_spectrum, sigma=3.0)

        me_blue_segment = abs_spectrum.segment(lower_bound=500, upper_bound=750)
        me_blue_baseline = abs_spectrum.segment(lower_bound=800, upper_bound=1000)

        me_blue_signal = np.nanmax(me_blue_segment.signal) - np.nanmean(me_blue_baseline.signal)
        light_check = np.nanmax(ref_spectrum.segment(lower_bound=900, upper_bound=1050).signal)

        actual_description = description.apply_calibration(nom2actual)

        droplet_volume = actual_description.total_volume
        cat_vol = 0 if actual_description.catalyst is None else actual_description.catalyst
        qch_volume = 0 if actual_description.quencher is None else actual_description.quencher
        dil_volume = 0 if actual_description.diluent is None else actual_description.diluent
        dye_conc = ((dye_conc_cat * cat_vol) + (dye_conc_qch * qch_volume) + (dye_conc_dil * dil_volume)) / droplet_volume

        try:
            _, raw_disp, *_ = basic_specs.strip().split(", ")
            _, mix_disp_str = raw_disp.strip().split("=")
            mix_disp = float(mix_disp_str)
        except (ValueError, TypeError) as err:
            print("\t<mixing_displacement>" + repr(err))
            continue

        entry = Datum(
            description,
            actual_description,
            me_blue_signal,
            dye_conc,
            timestamp.strip(),
            me_blue_segment,
            light_check,
            mix_disp
        )

        data_points.append(entry)
        print(f"\tAdded {os.path.basename(file)}")

    data_points.sort(key=lambda x: x.nominal.instance)
    data_points.sort(key=lambda x: abs(x.mixing_displacement))
    data_points.sort(key=lambda x: x.nominal.mixing_iteration)

    return data_points


def analyze_data(data: list[Datum]):
    pure_signal: Datum | None = None
    for datum in data:
        if datum.nominal.mixing_iteration == 0:
            pure_signal = datum
            break
    if pure_signal is None:
        raise ValueError(f"Could not find the pure signal")
    expected_signal = [pure_signal.signal_value * datum.relative_concentration for datum in data]
    error = [expected - observed.signal_value for observed, expected in zip(data, expected_signal)]
    """ Unscaled deviation """
    _percent_difference = lambda x, y: 2*(x-y)/(x+y)
    diff = [_percent_difference(expected, observed.signal_value) for observed, expected in zip(data, expected_signal)]
    """ Relative deviation """

    sequence_indices = [datum.nominal.instance for datum in data]
    min_seq_idx = min(sequence_indices, default=0)
    max_seq_idx = max(sequence_indices, default=1)

    table_keys = {(datum.nominal.mixing_iteration, datum.mixing_displacement) for datum in data}
    table_keys = list(table_keys)
    table_keys.sort(key=lambda x: x[1], reverse=True)
    table_keys.sort(key=lambda x: x[0])
    table_data = {k: {'diff': list(), 'err': list(), 'seq': list(), 'chk': list()} for k in table_keys}
    for datum, _err, _diff in zip(data, error, diff):
        _key = (datum.nominal.mixing_iteration, datum.mixing_displacement)
        table_data[_key]['diff'].append(_diff)
        table_data[_key]['err'].append(_err)
        table_data[_key]['seq'].append((datum.nominal.instance - min_seq_idx)/max_seq_idx)
        table_data[_key]['chk'].append(datum.light_check)

    _mean_abs = lambda x: None if len(x) == 0 else sum([abs(y) for y in x])/len(x)
    _sstdev = lambda x: None if len(x) < 2 else ((sum([y**2 for y in x]) - sum(x)**2/len(x)) * (1/(len(x) - 1)))**0.5
    _cv = lambda x: None if len(x) < 2 else _sstdev(x) / _mean_abs(x)
    table_entries = {
        k: {
            'abs_diff': _mean_abs(td['diff']),
            'abs_err': _mean_abs(td['err']),
            'ssd_diff': _sstdev(td['diff']),
            'ssd_err': _sstdev(td['err']),
            'avg_seq': _mean_abs(td['seq']),
            'ssd_seq': _sstdev(td['seq']),
            'check_cv': _cv(td['chk'])
        }
        for k, td in table_data.items()
    }

    return table_entries


def save_data(data: list[Datum], apellomancer: SVApellomancer, file_name):
    summary_file = apellomancer.make_full_path(file_name, ".csv")
    _percent = lambda x: None if x is None else f"{100 * x}%"
    headers = [
        "Index", "TimeStamp", "LightCheck",
        "DropletVolumeNominal_uL", "DyeVolumeNominal_uL",
        "DropletVolumeActual_uL", "DyeVolumeActual_uL",
        "MixIterations", "MixDisplacement",
        "Signal", "RelativeConcentration"
    ]
    with open(summary_file, "w+") as _file:
        _file.write(", ".join(headers) + "\n")
        for datum in data:
            entries = [
                datum.nominal.instance, datum.timestamp, datum.light_check,
                datum.nominal.total_volume, datum.nominal.quencher,
                datum.actual.total_volume, datum.actual.quencher,
                datum.nominal.mixing_iteration, datum.mixing_displacement,
                datum.signal_value, _percent(datum.relative_concentration)
            ]
            _file.write(", ".join(str(x) for x in entries) + "\n")

    summary_table = analyze_data(data)
    headers = [
        "MixIterations", "MixDisplacement",
        "Avg_Position", "SSD_Position",
        "MAE", "MARE", "SSD_E", "SSD_RE",
        "Metric_E", "Metric_RE",
        "Light_Check"
    ]
    _metric = lambda mu, ssd: None if mu is None else None if ssd is None else mu + ssd
    with open(summary_file, "a+") as _file:
        _file.write("\n" + ", ".join(headers) + "\n")
        for (n_mix, d_mix), td in summary_table.items():
            entries = [
                n_mix, d_mix,
                td['avg_seq'], td['ssd_seq'],
                td['abs_err'], _percent(td['abs_diff']), td['ssd_err'], _percent(td['ssd_diff']),
                _metric(td['abs_err'], td['ssd_err']), _percent(_metric(td['abs_diff'], td['ssd_diff'])),
                _percent(td['check_cv']),
            ]
            _file.write(", ".join(str(x) for x in entries) + "\n")


if __name__ == '__main__':
    name_wizard = SVApellomancer(
        directory=r"C:\Users\User\Documents\Postdoc\Gilson\Mixing Studies",
        project_name="Mixing Study (2025 Feb 04) - 50 uL",
        file_header="sv_style_3src_mixing",
        mode='r'
    )

    dye_conc_cat = 0
    dye_conc_qch = 1
    dye_conc_dil = 0

    my_files = get_files(name_wizard.project_directory, key="_ABS_")
    my_data = extract_data(my_files, name_wizard, lambda x: max(0.0, 0.9765 * float(x) - 0.2440))  # Set Feb 4, 2025 from "Manuscript Figures Data.xlsx"

    save_data(my_data, name_wizard, "mixing_summary")
