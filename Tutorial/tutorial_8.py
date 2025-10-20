# This file will be less a tutorial and more a walkthrough of the Stern-Volmer assay presented in the associated
# manuscript.  This file will combine naming.py, stern_volmer_3src.py, stern_volmer_core.py, and stern_volmer.py
# into a single file so we can step through each decision and explain them one by one.

# Note some names had to be tweaked to address scope issues that arise when everything is moved into a single file.
# In addition, things were reordered to make more sense in this context and methods which were not used in the final
# version of the code were omitted.

# There will be a reflection at the end which should be a springboard to understanding the decisions made in the
# serial_measurement workflow used in the BL and PLQY workflows.


import datetime
import random
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from os import PathLike, path
from typing import Generator, Any, Callable, Iterable, Literal, NamedTuple

import numpy as np

from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from aux_devices.signal_processing import smooth
from aux_devices.spectra import Spectrum, SpectrumFactory
from data_management.apellomancer import Apellomancer, ApellOpenMode, serialize_number, parse_int_string, \
    parse_float_string, SequentialApellomancer
from data_management.common_dp_steps import get_files, take_sigal_at, SpectralProcessingSpec
from data_management.simple_linear_regression import slr
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE, Placeable, HandlerBed
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from misc_func import Number, shuffle_study
from workflows.common_macros import prime, clean_up, inter_clean, volume_to_center_droplet, record_spectrum


# Thinking backwards, at the end of everything, we want a table of I_0/I values vs [Quencher].
# For each data point I want the signal value (I) and the quencher concentration. But I would also like
# to keep on record the catalyst concentration, a copy of the spectrum used to calculate I, and the
# specified and calibration-corrected version of the experimental specifications that created this datum.

# Of note, those things are numbers, Spectra (so import Spectrum from aux_devices.spectra), and an experimental
# specification (So we will make that first).

# To describe a SV measurement (not the whole assay, just a single data point), I want to know
# how much catalyst, quencher, and diluent are present in my sample. It would also be nice to record when the
# measurement was taken, whether it was ABS or PL (even though SV is only PL), some global experimental index
# to help keep track of experiments, and (since mixing was not yet pinned down when this code was originally written)
# how many mixing iterations were used to mix the droplet.
# I can describe an SV measurement as follows (using the nominal volumes)
@dataclass
class SVSpecDescription:
    """ Description of a Stern-Volmer--style experiment.

     - timestamp: str
     - spectral_type: "PL" or "ABS"
     - instance: int
     - catalyst: Number | None
     - quencher: Number | None
     - diluent: Number | None
     - mixing_iteration: int | None
    """
    timestamp: str
    spectral_type: str
    instance: int
    catalyst: Number | None
    quencher: Number | None
    diluent: Number | None
    mixing_iteration: int | None

    # To get the calibration-corrected version of this SVSpecDescription object, let's create a method which
    # can do this conversion for us. The method nom2actual() (sc. "nominal to actual") is a method which takes in a
    # volume in uL and returns a calibrated volume in uL. (I say 10 uL, it's actually 9.978 uL).
    # There is some protection around None values here as it's possible for a sample to not have any quencher
    # (for example) in it by design (i.e., None means "None was added" allowing 0 then to mean "So little was added that
    # the calibration-corrected volume was at or below 0 uL").
    def apply_calibration(self, nom2actual: Callable[[Number], float]):
        return SVSpecDescription(
            timestamp=self.timestamp,
            spectral_type=self.spectral_type,
            instance=self.instance,
            catalyst=None if self.catalyst is None else nom2actual(self.catalyst),
            quencher=None if self.quencher is None else nom2actual(self.quencher),
            diluent=None if self.diluent is None else nom2actual(self.diluent),
            mixing_iteration=self.mixing_iteration,
        )

    # To get the total volume of the droplet being measured:
    @property
    def total_volume(self):
        return sum([_v for _v in [self.catalyst, self.quencher, self.diluent] if _v is not None], start=0)
    # Unfortunately, ```return self.catalyst + self.quencher + self.diluent``` would not work because
    #   each of those variables could be None, and Python will not allow you to "add None to a Number".


# With this description complete, we can return to the definition of a single datum:
class Datum(NamedTuple):
    """ Stores the data discernible from the file name and the spectrum"""
    nominal: SVSpecDescription
    actual: SVSpecDescription
    signal_value: float
    quencher_concentration: float
    catalyst_concentration: float
    spectral_segment: Spectrum


# To get all the data together, we will need a way to collate the data into a single location.
# However, before any of that, we would have needed a way to save the data.
# To begin with saving the data, we'll need a file name.
class SVApellomancer(Apellomancer):
    def __init__(self, directory: PathLike | str, project_name: str, file_header: str, mode: ApellOpenMode  = 'r'):
        """ Creates a file manager

        :param directory: Where project directories should be
        :param project_name: The name (template) for a project directory
        :param file_header: The file name template
        :param mode: 'r' (Read), use the project name as-is. 'w' (Write), check the project name [requires user input].
          'a' (Append), check the project name and use the first available [no user input].
        """
        super().__init__(directory, project_name, file_header, mode)

    def __repr__(self):
        return f"<SVApellomancer object for '{self.project_directory}'>"

    def make_file_name(self,
                       cat: Number = None,
                       quench: Number = None,
                       dil: Number = None,
                       mix: int = None,
                       spec: Literal['PL', 'ABS'] = "PL",
                       seq: int = 0):
        # This part of the name shall always be present
        tag = f"__{self._file_timestamp}_{spec}_i{seq}"
        # Add tags for the catalyst, quencher, diluent, and mix iterations provided that they are not None-valued.
        if cat is not None:
            tag += f"_c{serialize_number(cat)}"
        if quench is not None:
            tag += f"_q{serialize_number(quench)}"
        if dil is not None:
            tag += f"_d{serialize_number(dil)}"
        if mix is not None:
            tag += f"_m{mix}"
        return self.file_header + tag

    @staticmethod
    def parse_file_name(file_path: str) -> SVSpecDescription:
        full_file_name = path.basename(file_path)
        file_name, _ = path.splitext(full_file_name)
        *_, tag = file_name.split('__')  # Anything before the last "__" was custom (not parseable)
        # From make_file_name() we know that the tag is of the form f"{self._file_timestamp}_{spec}_i{seq}"
        # So we can split on "_" and get the file timestamp as well as the spectral mode (ABS or PL)
        # Everything else is some variable number of tags
        timestamp, spec, *vargs = tag.split('_')
        # Set the default values for all these tags to None
        seq = cat = quench = dil = mix = None
        # For each tag key and value, update the corresponding tag variable to match
        for (h, *v) in vargs:
            match h:  # See below for the "match" syntax
                case 'i':
                    seq = parse_int_string("".join(v))
                case 'c':
                    cat = parse_float_string("".join(v))
                case 'q':
                    quench = parse_float_string("".join(v))
                case 'd':
                    dil = parse_float_string("".join(v))
                case 'm':
                    mix = parse_int_string("".join(v))
        return SVSpecDescription(
            timestamp=timestamp,
            spectral_type=spec,
            instance=seq,
            catalyst=cat,
            quencher=quench,
            diluent=dil,
            mixing_iteration=mix
        )
    # This is actually a bad use of the `match` statement in Python.
    # The intended use of match was if you had something which could have different forms,
    # for example: var could be of the form tuple(Number), tuple(Number, Units), or tuple(Number, Units, Uncertainty)
    # Then you could use match on var with the following cases:
    # case value, units, sigma:
    #   print(f"{value} +/ {sigma} {units}")
    # case value, units:
    #   print(f"{value} {units}")
    # case value:
    #   print(f"{value}")
    # case _:
    #   print(f"Error, variable 'var' was not of the expected form")
    #
    # But the lesson in match statements aside, the match-case code in parse_file_name() is equivalent to
    # if h == 'i':
    #   seq = parse_int_string("".join(v))
    # elif h == 'c':
    #   cat = parse_float_string("".join(v))
    # elif h == 'q':
    #   quench = parse_float_string("".join(v))
    # ...and so forth
    #
    # As an additional note: Since we are taking in a file name and splitting the file name on underscore characters,
    # the values associated with each flag (the 'i', 'c', 'q', 'd', 'm') will be read in as tuples instead of strings.
    # So "c13-33" is read as h = 'c' and v = ('1', '3', '-', '3', '3'). To Turn v back into a string, we call
    # ``` "".join(v) ``` which will join each element of v together with "" (nothing) as the delimiter--producing
    # the string "13-33".


# Now that we have a way to get and recall file names, we can use get_files() from the
# data_management/common_dp_steps.py file to grab all the data files.  So no new code to add.

# We will then want to extract the data from these files.
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

        spec_fact = SpectrumFactory()  # Since we will be reconstructing the spectral data line-by-line
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
            # This is not obvious: when diluent_volume is None (not 0, but None), it means that we are in 2-vial mode
            # and so the quencher and catalyst vials both contain catalyst (same concentration).
            _cat_conc = (quencher_volume + catalyst_volume) * cat_src_conc / droplet_volume
        else:
            # This is the 3-vial mode where only the catalyst vial has catalyst in it
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
        print(f"\tAdded {path.basename(file)}")

    return data_points


# With all the data loaded, we can return to the data table idea. If we have I values but we want I_0/I values,
#   then we need to find the value of I_0. In most experiments there should be only one quencher-free measurement;
#   however, the platform is allowed to remeasure I_0 when the y-intercept or R^2 values are bad, so some may have
#   multiple I_0 values to contend with.
# Let us define a method which will take in all the data, find all data where the concentration of quencher is
#   0 (or None), and then combine these data (if there are multiple) using a method that is specified by the
#   caller (use the min, max, or average of all potential I_0 values).
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
    raise ValueError(f"the method must be min/max/avg, not '{method}'")  # noqa: code is reachable if method is invalid


# With all that, it should be possible to create (and save) that data table.
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


# So we can now go from having data files of raw spectra to having a nice SV table which we can perform
#   linear regression on to get the K_SV constant.
# It would then be time to figure out how these data get generated in the first place.
# We need a way to fully specify an experiment (instructions)
# We would need to specify how much catalyst, quencher, and diluent to use (and where they are on the platform).
# In addition, mixing information (displacement and number of iterations), how to perform the spectral measurements,
#   and how to handle the file naming convention.
#
# Of those items, we can note that the How much chemical and where is it can be summarized by a simple type annotation
#   and doesn't require its own data class for organization:
COMPONENT_TYPE = tuple[Placeable, Number]
""" (Location, volume) """


# Otherwise, we can organize this experimental specification into a nice dataclass
@dataclass
class SVSpec:
    """ Description of SV-style experiment.

     - mix_iterations: int
     - mix_displacement: float
     - catalyst: COMPONENT_TYPE | None
     - quencher: COMPONENT_TYPE | None
     - diluent: COMPONENT_TYPE | None
     - spec_abs: OpticalSpecs | None
     - spec_pl: OpticalSpecs | None
     - name_wizard: SVApellomancer
    """
    mix_iterations: int = 0
    """ Number of mixing iterations """
    mix_displacement: float = -1.4
    """ (+ for absolute)/(- for relative to droplet)"""
    catalyst: COMPONENT_TYPE = None
    quencher: COMPONENT_TYPE = None
    diluent: COMPONENT_TYPE = None
    spec_abs: OpticalSpecs | None = None
    """ If (None-ness) and how to measure absorbance spectra """
    spec_pl: OpticalSpecs | None = None
    """ If (None-ness) and how to measure photoluminescence spectra """
    name_wizard: SVApellomancer | SequentialApellomancer = SequentialApellomancer("./", "Test", "test", "r")
    """ Object for determining how to save the file """

    @property
    def components(self) -> tuple[COMPONENT_TYPE, ...]:
        """ Should match Gilson241LiquidHandler.prepare_droplet_in_liquid_line() """
        return tuple(c for c in (self.catalyst, self.quencher, self.diluent) if c)

    # These three properties are to have easy access to the volumes of each component while handling the possibility
    #   that each one could be None instead of a COMPONENT_TYPE
    @property
    def cat_vol(self) -> None | int | float:
        return None if self.catalyst is None else self.catalyst[1]

    @property
    def quench_vol(self) -> None | int | float:
        return None if self.quencher is None else self.quencher[1]

    @property
    def dil_vol(self) -> None | int | float:
        return None if self.diluent is None else self.diluent[1]

    # uses the Apellomancer to generate a file name
    def prepare_name(self, spectral_mode: Literal['ABS', 'PL'], seq: int, override_name_wizard: SVApellomancer = None):
        _name_wizard = self.name_wizard if override_name_wizard is None else override_name_wizard
        if isinstance(_name_wizard, SequentialApellomancer):
            return _name_wizard.make_file_name(spectral_mode, seq)
        return _name_wizard.make_file_name(
            cat=self.cat_vol,
            quench=self.quench_vol,
            dil=self.dil_vol,
            mix=self.mix_iterations,
            spec=spectral_mode,
            seq=seq,
        )

    # Generates a string of metadata which can be saved alongside the spectral data
    def generate_tag(self):
        return (f"mix_iter={self.mix_iterations}, mix_disp={self.mix_displacement}, "
                f"vC={self.cat_vol}, vQ={self.quench_vol}, vD={self.dil_vol}")


# This SVSpec class really only specifies the experiment for a single point in an SV plot.
# For such a plot, everything would be the same except for the volumes of the catalyst, quencher, and diluent.
# So it would be nice to have a way of loading in all the constant data first, then generating each variation
# based on that volume information as needed.
# So we'll make a factory:
class SVSpecFactory:
    # The INIT method will take all the parameters which are constant.
    def __init__(self,
                 name_wizard: SVApellomancer | SequentialApellomancer = None,
                 mix_iterations: int = 0,
                 spec_abs: OpticalSpecs = None,
                 spec_pl: OpticalSpecs = None,
                 mix_disp: float = -1.4):  # See below
        if name_wizard is None:
            name_wizard = SequentialApellomancer("./", "Test", "test", "r")
        self.name_wizard = name_wizard
        self.mix_iterations = mix_iterations
        self.mix_disp = mix_disp
        self.spec_abs = spec_abs
        self.spec_pl = spec_pl
        # I have elected to use a non-obvious scheme for defining the mixing displacement (the volume moved when mixing)
        # When the displacement is a positive number, then that is the number of uL that will be moved during a mix.
        # When the displacement is a negative number, then that fraction of the droplet volume will be moved
        #   during a mix. So the default value of -1.4 would mean that a 100 uL droplet will be mixed with 140 uL
        #   displacements. A 50 uL droplet, 70 uL of displacement.
        # When the displacement is 0, then no displacement is used (conforms to both + and - cases)

    # Provided with just the bit that changes experiment to experiment, make a full SVSpec
    def make(self,
             catalyst: COMPONENT_TYPE = None,
             quencher: COMPONENT_TYPE = None,
             diluent: COMPONENT_TYPE = None,
             supress_measurement: bool = False):
        return SVSpec(
            mix_iterations=self.mix_iterations,
            mix_displacement=self.mix_disp,
            catalyst=catalyst,
            quencher=quencher,
            diluent=diluent,
            spec_abs=None if supress_measurement else self.spec_abs,
            spec_pl=None if supress_measurement else self.spec_pl,
            name_wizard=self.name_wizard
        )

    # There are times when it would be nice to reconstruct a SVSpec from its description, so that will be defined here:
    def make_from_description(self,
                              description: SVSpecDescription,
                              cat: Placeable, qch: Placeable, dil: Placeable
                              ):
        return SVSpec(
            mix_iterations=description.mixing_iteration,
            mix_displacement=self.mix_disp,
            catalyst=None if description.catalyst is None else (cat, description.catalyst),
            quencher=None if description.quencher is None else (qch, description.quencher),
            diluent=None if description.diluent is None else (dil, description.diluent),
            spec_abs=self.spec_abs,
            spec_pl=self.spec_pl,
            name_wizard=self.name_wizard
        )


# With a way to specify each experimental data point, we will want a way to measure their spectra.
# The following two methods are almost identical. I could have made a single method, but there was
# no great need to do so. In fact, having the two methods helps the code be more readable at times
# because the method's name says exactly what it will do.
# These two methods will prepare a file name and any metadata for the file, measure a spectrum, then
#   save that spectrum alongside its metadata in the designated file.
# These methods spend most of their time preparing the metadata and then rely on the record_spectrum() method
#   from common_macros.py to measure and save the data.
def measure_pl_spectrum(my_spec: SpectrometerSystem,
                        spec: SVSpec,
                        counter: int):
    file_name = spec.prepare_name("PL", counter)
    file_path = spec.name_wizard.make_full_path(file_name, ".csv")

    spec_tag = spec.generate_tag()
    tag = spec.spec_pl.generate_tag()
    cor_tag = spec.spec_pl.generate_corrections_tag()
    file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n"
                   f"wavelength (nm), dark reference (int), light reference (int), pl (int)\n")

    return record_spectrum(my_spec, spec.spec_pl, 'PL', file_path, file_header)

def measure_abs_spectrum(my_spec: SpectrometerSystem,
                         spec: SVSpec,
                         counter: int):
    file_name = spec.prepare_name("ABS", counter)
    file_path = spec.name_wizard.make_full_path(file_name, ".csv")

    spec_tag = spec.generate_tag()
    tag = spec.spec_abs.generate_tag()
    cor_tag = spec.spec_abs.generate_corrections_tag()
    file_header = (f"{datetime.datetime.now()}\n{spec_tag}\n{tag}\n{cor_tag}\n"
                   f"wavelength (nm), dark reference (int), light reference (int), abs (mAU)\n")

    return record_spectrum(my_spec, spec.spec_abs, 'ABS', file_path, file_header)


# Just a little bit to go.
# We will need to prepare and center a droplet before we can measure the spectra.
# To do this, let us define a method which will prepare the droplet, center it, and then measure it:
def grab_droplet_fixed(lh: Gilson241LiquidHandler,
                       spec: SVSpec,
                       wash: Placeable,  # noqa
                       waste: Placeable,  # noqa
                       my_spec: SpectrometerSystem,
                       counter: int,
                       ):
    back_air_gap = 20
    front_airgap = 10

    print(f"Preparing droplet {counter}")
    with redirect_stdout(StringIO()):  # read as "Don't bother printing anything to the console for these lines of code"
        droplet_volume = lh.prepare_droplet_in_liquid_line(
            components=spec.components,
            back_air_gap=back_air_gap,
            front_air_gap=front_airgap,
            air_rate=DEFAULT_SYRINGE_FLOWRATE,
            aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
            mix_iterations=spec.mix_iterations,
            mix_displacement=spec.mix_displacement,
            mix_rate=4*DEFAULT_SYRINGE_FLOWRATE,
            # If we wanted to wash the needle betweeen sampling each vial,
            # there are keyword arguments to lh.prepare_droplet_in_liquid_line() that we could
            # place here.
            # dip_tips=ExternalWash(
            #     positions=wash,
            #     tip_exit_method=TipExitMethod.DRAG,
            #     air_gap=AspiratePipettingSpec(
            #         component=AirGap(position=waste, volume=10)
            #     ),
            #     n_iter=2
            # )
            # However, it was found that this makes cross-contamination worse, so we don't do that.
            # Regardless, to facilitate switching between these modes of cleaning/not-cleaning, we will
            # keep the wash and waste arguments to grab_droplet_fixed() even though they are not
            # always used.
            # A better choice would be to let them be None then add logic to prepare_droplet_in_liquid_line()
            # which would simply not wash/clean when these arguments are None.
        )
    # The use of with redirect_stdout(StringIO()) effectively silences the prepare_droplet_in_liquid_line() operation
    #   to prevent a spam of text in the console.
    # the `silence` decorator would later be added to misc_func.py because this behaviour turned out to be
    #   desirable in many more places.
    # For reference, the core bit of the silence decorator:
    # ```
    #     with redirect_stdout(StringIO()):
    #         return func(*args, **kwargs)  # <-- where func is the decorated function
    # ```

    lh.utilize_spectrometer(
        my_spec,
        volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2),
        # ^ A better choice would be to make a configuration file which populates these values so that
        # the user would not need to change them out whenever they adjust the flow cell tubing or needle.
        (spec.spec_abs, lambda _s: measure_abs_spectrum(_s, spec, counter)),
        (spec.spec_pl, lambda _s: measure_pl_spectrum(_s, spec, counter))
    )


# With that, we need a way to run all the experiments making a single K_SV measurement
# My apologies in advance for this method, especially if you are new to Python.
def run_campaign[T](study: Iterable[T],  # The study will be defined by some specification T
                    do_droplet_thing: Callable[[T, int], ...],  # Each experiment will take that specification, T, and an ID number
                    post: Callable[[], ...],  # Run this method (which takes no argument, and we don't care about what it returns) after each experiment in the study
                    start_at: int = 0,  # Start at this experimental ID number
                    handler_bed: HandlerBed = None) -> int:
    """
    :param study: Iterable of experimental specification. Must match signature of do_droplet_thing
      and contain a 'name_tag'.
    :param do_droplet_thing: Given study and its index as the only two arguments.
    :param post: Runs after do_droplet_thing(), intended for washing
    :param start_at: Used to offset the sequence counter
    :param handler_bed: Used for resource tracking
    :return: start_index + (consumed indices) + 1, i.e., what to pass into the next run_campaign(start_at=...) call
    """
    # SAFETY: Try to keep track of how much system fluid is remaining so the system never runs dry
    current_volume: float | None = None
    # Since run_campaign can be used to add experiments (such as the poor y-intercept or poor R^2 correction
    #   experiments) or since we may be recovering from a crash/broken vial/etc. We will allow the index
    #   keeping track of the experiment order (the experimental ID) to start from a "where we left off" value.
    last_idx = start_at - 1
    for idx, test in enumerate(study, start=start_at):
        # SAFETY: Check the volume of system fluid remaining
        if handler_bed:
            current_volume = handler_bed.read_resource_cfg().get('system_fluid_volume_mL', current_volume)
        if (current_volume is not None) and (current_volume <= 0):
            print("Safe volume exhausted, exiting.")
            raise StopIteration  # This will only do what we want if we "catch" it in the method that
                                 # calls run_campaign(). So keep a pin in that.

        try:
            name_tag = test['name_tag']
        except TypeError:
            name_tag = ""

        print(f"Running {name_tag}  ({current_volume} mL remaining) : {datetime.datetime.now()}")
        do_droplet_thing(test, idx)
        post()
        last_idx = idx
    return last_idx + 1
# In reality, all this method does is (a) do a safety check that we have not run out of system fluid and (b)
#   keep track of the experiment ID.  All the actual functionality is requested as inputs (dependency injection).
# The method is parameterized using the type variable T. This was because we had not yet settled on an experimental
#   specification just yet (3-vial vs 2-vial, SV with just PL, SV with PL and ABS just to run diagnostics, etc.)
# So rather than making a new method for each specification or trying to type-hint all options (A | B | C | ...),
#   and especially since things would have to match the items of `study` must match the first argument of
#   `do_droplet_thing()`, we chose to make this a parameterized function.


# One last thing. For each K_SV value, we need to know what volumes of catalyst, quencher, and diluent to use.
#   We could hard-code that (write it down in the code explicitly) or we can have the code generate these values
#   for us based on things like min and max volumes and the number of data points we want per K_SV.
# First up, let us define a method which will take some min/max/N parameters to create the full set of experiments
#   required for a K_SV campaign.
# This is called "manual" because the values are manually specified. Its sister method, automatic_study(), is the
#   method we will use when the platform automatically redoes the I_0 and most surprising data point if the
#   y-intercept or R^2 value is bad.
# This method will introduce a new Python syntax: The Generator Function (known by its use of `yield` instead (or in
#   addition to) `return`).
# A generator can be given to a FOR loop (or while loop), and it will define what values the FOR loop iterates over.
# The method will run until it hits a yield expression. It will pass this value to the FOR loop. The FOR loop will
#   do whatever it will do. Then, when the FOR loop asks for another value, the method will resume until it hits
#   another yield expression, and the cycle repeats.  When the generator returns (in this case returns None implcitly;
#   recall that all functions will return None if they do not encounter a return statement), then the FOR loop will
#   stop and exit the loop.
# So, manual study can be used with a FOR loop to first run a No-quencher experiment, then a max-quencher experiment,
#   then n experiments of varying quencher loading. (so n = 4 will produce a 6-point SV plot)
def manual_study(factory: SVSpecFactory,
                 cat_aliquot: int = 10,
                 min_aliquot: int = 7,
                 n_samples: int = 4,  # The number of samples with quencher in it in addition to [Q] = 0 and [Q] = max
                 max_total: int = 50
                 ) -> Generator[SVSpec, Any, None]:
    available = max_total - cat_aliquot
    yield factory.make(catalyst=(CATALYST, cat_aliquot), quencher=(QUENCH, 0), diluent=(DILUENT, available))
    yield factory.make(catalyst=(CATALYST, cat_aliquot), quencher=(QUENCH, available), diluent=(DILUENT, 0))

    interval = (available - 2 * min_aliquot) / (n_samples - 1)
    q_values = [round(min_aliquot + idx * interval, 3) for idx in range(0, n_samples)]
    for q in q_values:
        yield factory.make(catalyst=(CATALYST, cat_aliquot), quencher=(QUENCH, q), diluent=(DILUENT, available - q))


# The "automatic study" is the 0 or 2 data points which are redone to improve the overall data quality of the
#   experiment.
# It will first determine if there is a need to redo experiments, and if so, it will yield instructions on which two
#   to redo (it will pick the I_0 point and the I(Q) point that was "most surprising").
def automatic_study(factory: SVSpecFactory,
                    _calibration: Callable[[float], float],
                    req_threshold: float = 1.0,
                    intercept_check: float = None) -> Generator[SVSpec, Any, None]:
    # Load in all the existing data so we can analyze it.
    apellomancer = factory.name_wizard
    data_files = get_files(directory=apellomancer.project_directory, key="_PL_")
    data_entries = extract_data(data_files, apellomancer, cat_conc, quench_conc, signal_method, _calibration)
    if not data_entries:
        print("No data found for automatic_study()...")
        return

    data_entries.sort(key=lambda d: d.quencher_concentration)

    save_data_summary(data_entries, path.join(my_name_wizard.project_directory, f"{q_name}_summary.csv"), signal_method)

    # Perform (prelim) regression to determine if this is even necessary
    i_0, i_0_idx = determine_base_intensity(*data_entries)
    x_data = [entry.quencher_concentration for entry in data_entries]
    y_data = [i_0 / entry.signal_value for entry in data_entries]
    slr_results = slr(x_data, y_data)

    r2_is_good = (req_threshold is not None) and (slr_results.pearsons_r2 >= req_threshold)
    intercept_is_good = (intercept_check is not None) and ((1-intercept_check) <= slr_results.intercept <= (1+intercept_check))
    if r2_is_good and intercept_is_good:
        print("Both R2 and y(0) are good!")
        return  # return, so the generator will exit and the calling LOOP will not run

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
        # ^ This while loop here is to ignore I_0 (since we already did it) if it were the most surprising point.
        # The "pop" is pretty much saying "next"
        # This iterative syntax is so that this code will continue to work even if there's only one data point in the
        #   entire experiment. While that shouldn't ever be the case, at least the code won't crash.
        yield factory.make_from_description(data_entries[retest].nominal, CATALYST, QUENCH, DILUENT)
    except IndexError:
        pass  # This tells Python that this code block is supposed to be empty. Without it, Python would think
              #   you left out some lines of code and would throw and error. Except+pass can be read as "Ignore this
              #   type of error".


# With all that preamble, we can finally define our main method, the thing that will be run to perform a full
#  SV assay on a batch of sample.
if __name__ == '__main__':
    from deck_layout.handler_bed import ShiftingPlaceable, Placeable
    from operator import itemgetter

    # NEW: Creating an Apellomancer:
    umbrella_project_name = "Big SVA 3"
    my_name_wizard = SVApellomancer(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project",
        project_name=umbrella_project_name,
        file_header="sva3_rubppy__var__",
        mode='w'
    )

    # SEEN BEFORE: Defining spectroscopy parameters for PL measurements.
    pl_opt_specs = OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)

    # NEW: Creating a Factory for SVSpecs.
    # We give it all the things that don't change
    # By giving it None for the spec_abs argument it will convert this to a SVSpec which will not take an ABS measurement.
    default_factory = SVSpecFactory(
        my_name_wizard,
        3,
        None,  # abs_opt_specs
        pl_opt_specs,
        mix_disp=-3.0  # Mix the droplet with a 300% displacement (50 uL droplet will be moved 150 uL)
    )

    # OLD: Connecting the Spectrometer and liquid handler
    my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    # NEW: To conserve on vials and catalyst, we will just load three vials of catalyst, and we will change the
    #      vial we're using after every four experiments.
    catalyst_wells = [
        glh.locate_position_name("pos_1_rack", "B1"),
        glh.locate_position_name("pos_1_rack", "D1"),
        glh.locate_position_name("pos_1_rack", "G1"),
    ]
    change_cat_vial_every_n_quenchers: int = 4

    # SEEN BEFORE: This is another table of specifying each experiment quickly.
    # From what we've learned in these tutorials, each line should be some sort of dataclass
    #   that keeps this info nicely organized and properly labeled for us.
    # Something like:
    # ```
    # class SVInputRow(NamedTuple):
    #   rack_name: str
    #   quencher_vial_id: str
    #   diluent_vial_id: str
    #   quencher_name: str
    #   quencher_concentration: float | int
    # ```
    # Sadly, that is not how the file was originally written, and as this was the code that was used to produce the
    #   data in the associated manuscript, this is the code that we will explain.
    # That said, these are effectively identical (NamedTuple is just a tuple), the only thing we lose is the ability
    #   to say things like `row.rack_name` to get the rack's name, instead we have to do 'rack[0]'.
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
    # Since these experiments were done in triplicate, the first rep had this next line commented out (so everything was
    #   done in the order described above). To avoid any systematic errors due to contamination or ordering, the
    #   second and third replicates were done in a random order. Here we can use random to shuffle the order of
    #   experiments.
    random.shuffle(ledger) # Rep 1 was in-oder, Reps 2 and 3 are shuffled.

    # Since tuples are addressed by index (e.g., row_of_ledger[0] is the rack name and row_of_ledger[3] is the name of
    #   the quencher; where row_of_ledger is an arbitrary element of `ledger`), to aid in readability, we use
    #   itemgetter here so that we can "name" the access of items.
    # For example,
    # get_quencher_name = itemgetter(3)  # This method grabs whatever's at the third index of its argument
    # quencher_name = get_quencher_name(row_of_ledger)  # For an arbitrary row of `ledger` called row_of_ledger
    # In this way, you can "name" the elements of tuple by naming the thing that grabs at that index.
    # ^ And all that is why we switched to dataclasses and NamedTuples in the latter workflows.
    # And if you want multiple items at once, you can do so by giving itemgetter multiple arguments.
    # So get_q_well and get_d_well will return a tuple with the rack name and the vial ID <-- which is exactly
    #   what glh.locate_position_name() wants for its arguments to find a location.
    get_q_well = itemgetter(0, 1)  # noqa: (rack name, quencher vial ID)
    get_d_well = itemgetter(0, 2)  # noqa: (rack name, diluent vial ID)
    get_details = itemgetter(3, 4)  # noqa: (quencher name, quencher concentration)
    # We can use these itemgetter objects to split apart the ledger into organized lists for the quencher,
    #   the metadata, and the diluent.
    quencher_wells: list[Placeable] = [glh.locate_position_name(*get_q_well(row)) for row in ledger]
    quencher_meta: list[tuple[str, float]] = [get_details(row) for row in ledger]
    diluent_wells: list[Placeable] = [glh.locate_position_name(*get_d_well(row)) for row in ledger]

    # (This is over-engineered, I'm so sorry)
    # We will let these constants be ShiftingPlaceable objects holding all the catalyst, quencher, and diluent wells
    #   This way everyone can just use CATALYST, QUENCH, and DILUENT as a single object, and we don't have to have new
    #   items for each experiment--especially since the quencher and diluent vials change every experiment but
    #   the catalyst changes every `change_cat_vial_every_n_quenchers` (i.e., 4) experiments.
    CATALYST = ShiftingPlaceable[Placeable](catalyst_wells)
    QUENCH = ShiftingPlaceable[Placeable](quencher_wells)
    DILUENT = ShiftingPlaceable[Placeable](diluent_wells)

    # These should have been part of that organizational data structure, instead we are defining these variables
    #   in the Main block and exploiting how Python handles scope to allow automatic_study() to use these values
    #   (READ ONLY) without us having to pass the value to it.
    cat_conc = 5.0191
    quench_conc = 1

    # In the published code this data was moved to the Calibration.xlsx file.
    calibration: Callable[[float], float] = lambda x: max(0.0, 0.9765 * float(x) - 0.2440)  # Set Feb 4, 2025 from "Manuscript Figures Data.xlsx"
    signal_method: SpectralProcessingSpec = SpectralProcessingSpec(None, None, take_sigal_at(610))  # Take the point closest to 610 nm

    # SEEN BEFORE: Defining waste and wash locations as constants.
    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    # # # # START # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    prime(glh, WASTE, 1400)
    global_index = 0                                                          # Remember to set if Resuming a campaign #
    try:
        for q_idx, (q_name, q_conc) in enumerate(quencher_meta):
            # This loop always starts with the liquid line being primed (system fluid; acetonenitrile) in the flow cell.
            print(f"Current quencher = {q_name}")
            my_name_wizard.file_header = f"sva3_rubppy_{q_name}"
            my_name_wizard.update_sub_directory(q_name)  # Let the Apellomancer (name wizard) know which quencher we're working with

            # Measure the light and dark references in system fluid (acetonenitrile)
            my_spectrometer.measure_average_reference('pl', 'dark', **pl_opt_specs)
            my_spectrometer.measure_average_reference('pl', 'light', **pl_opt_specs)

            # Update quench_conc with what was specified in `ledger`. This way automatic_study() -- which uses
            #   `quench_conc` not `q_conc` also gets updated.
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
                do_droplet_thing=lambda x, y: grab_droplet_fixed(  # Syntax explained in tutorial_7.py
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

            # Now that the experiments are complete, we can do data processing.  As previously discussed,
            # we get all the data files, then extract the data from them.
            # We can sort by quencher concentration to get things read for the data table
            # Then we save the I_0/I vs [Quencher] data table (data summary)
            try:
                my_data_files = get_files(directory=my_name_wizard.project_directory, key="_PL_")
                my_data_entries = extract_data(my_data_files, my_name_wizard, cat_conc, quench_conc, signal_method, calibration)
                if my_data_entries:
                    my_data_entries.sort(key=lambda d: d.quencher_concentration)
                    save_data_summary(my_data_entries, path.join(my_name_wizard.project_directory, f"{q_name}_summary.csv"), signal_method)
                else:
                    print(f"No data found for {q_name}?")
            except Exception as e:
                print(f"The following error prevented saving summary data for {q_name}")
                print(repr(e))

            # We have finished a quencher, update
            qc = QUENCH.next()  # Start using the next quencher vial
            dc = DILUENT.next()  # Start using the next diluent vial
            # For the catalyst, we only use the next vial every change_cat_vial_every_n_quenchers experiments.
            cc = None
            if q_idx % change_cat_vial_every_n_quenchers == (change_cat_vial_every_n_quenchers - 1):
                # A % B is "A mod B" it is the remainder when you divide A by B. (5 mod 3 is 2, 7 % 2 is 1)
                # so q_idx will be 0, 1, and 2 without catalyst moving to the next vial, but after the fourth experiment
                #   at this point in the code q_idx will be 3, and so q_idx % 4 == 3, and we go onto the next catalyst
                #   vial.
                cc = CATALYST.next()
            print(f"Changing analyte [debug: {qc=}, {dc=}, {cc=}]")
    except KeyboardInterrupt:  # to allow the user to press Ctrl-C or the interrupt button to stop things early.
        print("User exited the loop early")
    except StopIteration:  # Recall how run_campaign() could rase a StopIteration exception if we ran out of system fluid?  We will catch that here.
        print("Exiting early due to system volume concerns.")
    # Once complete (or the user terminated it early, or the system fluid level warning was set off), close out by
    #   cleaning up the needle.
    # It is possible that this clean would be done dry, which isn't great, but it will at least eject the current
    #   droplet to waste and home the arm (move the arm out of the way).
    clean_up(glh, WASTE)


# Reflection:
"""
(You can also use triple quotes for block comments in Python. I have avoided these throughout the tutorial to 
avoid confusion with doc-strings. In the event this got wordy, I have made this a triple-quote block comment
instead of having to put '#' in front of each line.)

The big deficiency of this code is in the experimental specification. We have an unlabeled tuple
as our input, which is turned into an SVSpec by an SVSpecFactory, which then gets converted into two versions
of an SVDescription, which are then stored together inside a single Darum object. It's quite a lot of transformations
of organization without really doing much to add value. It was sensible when stepping through what we needed at each
step, but it becomes clear that a more singular Prescription and Description object for the experiment would have been
better. In addition, the ambiguity over whether a SV experiment was referring to the generation of a single data point
or the whole plot was never quite clear.

As a result, some things became a little kludgey (the use of itemgetter, using a ShiftingPlaceable in this context,
having the user input data into rows of a table only for the code to immediately break it apart into multiple
lists, the fact that the catalyst concentration was defined in a separate location away from all other specifications,
how the spectrometer settings were also set far away from the rest of the experimental specifications and are fixed
over all experiments, etc.).  This would prove difficult to use if the user wanted to test multiple catalysts.  Not
only are some variables named after rubpy (which does not matter to the code, but does matter to the human reading it), 
but there's no way to easily update the catalyst name and concentration in this data input format or update the 
spectroscopy parameters to align with the new catalyst. In addition, there is no way to accommodate samples which are in
a solvent that does not match the system fluid--such baseline shifts would need to be corrected in post-processing.

These factors motivated the use of the Experiment class in serial_measurement_assay.py.  While this class is heftier 
with some 16 input parameters and 9 post-init parameters, it does organize things better and allows for all the code
related to liquid handler specifications to be located in one spot. It even allows for common practices to be automated
such as the specification of replicates (e.g., instead of three Experiments, just one can be used and the locations
for each replicate can be auto-filled with a little bit of prompting from the user during setup).
Take, for example:
```
*Experiment(
    name="RhodamineB",
    **Experiment.auto('pos_1_rack', 'M', include_working=True, include_diluent=True),
    abs_spec_processing=SpectralProcessingSpec(350, 800, take_rough_signal(546 - 5, 5)),
    solvent="Methanol",
    measure_reference="Vial",
    source_concentration=0.009,
    **common_kwargs
).span_const_source('pos_1_rack', 'N', 'O'),
```
Which indicates that this RhodamineB experiment starts on row M, then is replicated on rows N and O while holding
the analyte (RhodamineB) source vial constant on row M. In addition, this auto-fills that the source is in M1, the
working vials are M2, N2, and O2, and that the diluent vials are in M3, N2, and O3 all without heavy repetition.


All of this does, however, highlight a challenge of coding which cannot be taught well in a tutorial.
Code really just is a series of steps that are performed in order + structures used to organize data, and while
that should be accessible to many early programmers, what specific order of steps, what flexibility in the order and 
compositions of steps, and what specific data structures is in no way obvious without having encountered or having 
studied a similar problem before. Moreover, many of those decisions fall onto problems and answers which arise during 
testing and the ever-shifting demands of a project. A single catalyst is fine, until you need to study multiple. The 
workflow can be built for PL measurements, until it needs to also handle ABS measurements. A project can be thought 
through and decisions made for the immediate answer only for the needs of the project to change and the code has to be 
re-worked.  Alternatively, something that you provide the flexibility to accommodate ends up being something that was 
never needed.

I hope this tutorial has been helpful in, at the very least, making coding in Python not scary or in
revealing that coding is not insurmountable for anyone--it really is just writing down a check-list for the most 
particular and incapable-of-assuming thing you've ever met. And I wish you the best in all your future coding endeavors.
"""