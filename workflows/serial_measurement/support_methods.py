import datetime
from typing import Literal, NamedTuple

from aux_devices.ocean_optics_spectrometer import SpectrometerSystem
from workflows.common_macros import record_spectrum, record_reference
from workflows.serial_measurement.abstractions import Mixing
from workflows.serial_measurement.serial_spec import Experiment


def calculate_new_vial_mixing_parameters(vial_volume: float) -> Mixing:
    """
    :param vial_volume: The volume of the vial being mixing
    """
    # A good rule of thumb is to mix at least 50-75% of the total volume
    new_stock_mixing_displacement = 175 + (vial_volume - 250) * 0.75
    # This will range from 175 (70%) to 740 (74%) as vial_volume varies from 250 to 1000.
    new_stock_mixing_displacement = min(new_stock_mixing_displacement, 425.0)

    new_stock_mixing_iterations = 3 + int(0.67 + 3 * vial_volume / new_stock_mixing_displacement)
    # This will range from 3 + (8 to 15) as vial_volume varies from 250 to 1000.

    return Mixing(new_stock_mixing_iterations, new_stock_mixing_displacement)


def _make_concentration_tag(spec: Experiment,
                            global_counter: int,
                            dilution_counter: int | None,
                            net_dilution: float | tuple | None):
    if net_dilution is None:
        return (f"Conc_0={spec.source_concentration}, FRAC={net_dilution}, "
                f"Conc_({global_counter};{dilution_counter})={net_dilution}")
    elif isinstance(net_dilution, tuple):
        return (f"Conc_0={spec.source_concentration}, nFRAC={net_dilution[0]}, "
                f"nConc_({global_counter};{dilution_counter})={net_dilution[0] * spec.source_concentration}, "
                f"aFRAC={net_dilution[1]}, "
                f"aConc_({global_counter};{dilution_counter})={net_dilution[1] * spec.source_concentration}")
    else:
        return (f"Conc_0={spec.source_concentration}, FRAC={net_dilution}, "
                f"Conc_({global_counter};{dilution_counter})={net_dilution * spec.source_concentration}")


class SpectralMeasurementArgs(NamedTuple):
    """ Args for measure_spectrum(SpectrometerSystem, ...)

     - spec: Experiment
     - global_counter: int | None
     - dilution_counter: int | None
     - net_dilution: float | tuple = 1.0
     - mix_details: Mixing = None
     - flag: Literal['EXP', 'CHK', 'REF'] = "EXP"
    """
    spec: Experiment
    global_counter: int | None
    dilution_counter: int | None
    net_dilution: float | tuple | None = 1.0
    mix_details: Mixing | None = None
    flag: Literal['EXP', 'CHK', 'REF'] = "EXP"


# # Replaced by the measure_spectrum() method below.
# def measure_abs_spectrum(my_spec: SpectrometerSystem,
#                          measurement: SpectralMeasurementArgs):
#     specification = measurement.spec
#     name_wizard = specification.name_wizard
#     global_counter = measurement.global_counter
#     dilution_counter = measurement.dilution_counter
#
#     file_name = specification.prepare_name("ABS", global_counter, measurement.mix_details, dilution_counter, measurement.flag)
#     file_path = name_wizard.make_full_path(file_name, ".csv")
#
#     if measurement.mix_details:
#         spec_tag = specification.generate_tag(measurement.mix_details.iterations, measurement.mix_details.displacement)
#     else:
#         spec_tag = ""
#     tag = specification.abs_optic_spec.generate_tag()
#     cor_tag = specification.abs_optic_spec.generate_corrections_tag()
#     conc_tag = _make_concentration_tag(specification, global_counter, dilution_counter, measurement.net_dilution)
#     file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n{conc_tag}\n"
#                    f"wavelength (nm), dark reference (int), light reference (int), abs (mAU)\n")
#
#     return record_spectrum(my_spec, specification.abs_optic_spec, 'ABS', file_path, file_header)
#
#
# def measure_pl_spectrum(my_spec: SpectrometerSystem,
#                         measurement: SpectralMeasurementArgs):
#     spec = measurement.spec
#     global_counter = measurement.global_counter
#     dilution_counter = measurement.dilution_counter
#
#     file_name = spec.prepare_name("PL", global_counter, measurement.mix_details, dilution_counter, measurement.flag)
#     file_path = spec.name_wizard.make_full_path(file_name, ".csv")
#
#     if measurement.mix_details:
#         spec_tag = spec.generate_tag(measurement.mix_details.iterations, measurement.mix_details.displacement)
#     else:
#         spec_tag = ""
#     tag = spec.pl_optic_spec.generate_tag()
#     cor_tag = spec.pl_optic_spec.generate_corrections_tag()
#     conc_tag = _make_concentration_tag(spec, global_counter, dilution_counter, measurement.net_dilution)
#     file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n{conc_tag}\n"
#                    f"wavelength (nm), dark reference (int), light reference (int), pl (int)\n")
#
#     return record_spectrum(my_spec, spec.pl_optic_spec, 'PL', file_path, file_header)


def measure_spectrum(my_spec: SpectrometerSystem,
                     mode: Literal['ABS', 'PL'],
                     measurement: SpectralMeasurementArgs,
                     is_reference: bool = False):
    specification = measurement.spec
    global_counter = measurement.global_counter
    dilution_counter = measurement.dilution_counter
    mix_details = measurement.mix_details
    if mode == "PL":
        units = "int"
        optic_spec = specification.pl_optic_spec
    elif mode == "ABS":
        units = "mOD"
        optic_spec = specification.abs_optic_spec
    else:
        raise ValueError(f"Parameter 'mode' must be 'ABS' or 'PL' not '{mode}'")

    file_name = specification.prepare_name(mode, global_counter, mix_details, dilution_counter, measurement.flag)
    file_path = specification.name_wizard.make_full_path(file_name, ".csv")

    if mix_details:
        spec_tag = specification.generate_tag(mix_details.iterations, mix_details.displacement)
    else:
        spec_tag = ""
    tag = optic_spec.generate_tag()
    cor_tag = optic_spec.generate_corrections_tag()
    conc_tag = _make_concentration_tag(specification, global_counter, dilution_counter, measurement.net_dilution)
    file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n{conc_tag}\n"
                   f"wavelength (nm), dark reference (int), light reference (int), {mode.lower()} ({units})\n")

    if is_reference:
        return record_reference(my_spec, optic_spec, mode, file_path, file_header)
    else:
        return record_spectrum(my_spec, optic_spec, mode, file_path, file_header)