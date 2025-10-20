# In this tutorial, the use of the spectrometer in conjunction with the liquid handler will be demonstrated.
# The previous tutorial demonstrated how to use the liquid handler to prepare vials; in this tutorial,
# we will focus on just the spectrometer and will assume there are four vials which are to be sampled
# then measured.

# (Just importing some modules for this tutorial)
from typing import NamedTuple
from aux_devices.ocean_optics_spectrometer import OpticalSpecs, SpectrometerSystem
from aux_devices.spectra import ZipSpectra
import time

# Connecting to the spectrometer requires a single line of code (creating a SpectrometerSystem object)
# and will require knowing the DAQ lines for the absorbance and photoluminescence light sources.
# For this example 'Dev1/port0/line1' will control the broadband light source used in ABS measurements
# and 'Dev1/port0/line0' will control the UV LED source used in PL measurements.

# Example:
# my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))

# Defining how the spectrometer should perform measurements is accomplished using OpticalSpecs objects.
# As with many other objects, this is for bookkeeping, defining these settings in code does not
# reify them in the spectrometer. We will need to tell the spectrometer to use these settings.

# Example (of creation):
#     abs_optical_specifications = OpticalSpecs(count=30, interval=0.1, integration_time=10_000)
#     pl_optical_specifications = OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000)

# These OpticalSpecs objects can be supplemented with additional options; however, this information is supplemental
# unless explicitly used to reconfigure the spectrometer.
# For example:
#     pl_opt_specs = OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000, correct_dark_counts=True)
#                                                                                    ^^^^^^^^^^^^^^^^^^^^^^^^
# In order to have the spectrometer actually use this 'correct_dark_counts' feature, we will need to tell
# the spectrometer so.

# With these specifications defined, we can tell the spectrometer their values as follows:


def demo_record_pl_spectrum(spectrometer: SpectrometerSystem,
                            pl_opt_specs: OpticalSpecs):
    """ Measures a PL spectrum. """
    # To tell the Spectrometer to use the correct_dark_counts value specified in pl_opt_specs
    spectrometer.backend.correct_dark_counts = pl_opt_specs.correct_dark_counts
    # It is advised to give the spectrometer a second to process this information
    time.sleep(1)
    # When calling the measure_pl_spectra (or measure_abs_spectra) method, we can 'unpack' the
    # OpticalSpecs object into the arguments for the method by using the double asterisk (**) prefix.
    # The measure_pl_spectra (or measure_abs_spectra) method will handle the rest.
    return spectrometer.measure_pl_spectra(**pl_opt_specs)

# It is also probably a good idea to save the spectrum. (A richer version of this can be found in common_macros.py
# in the record_spectrum() method).
def demo_record_and_save_pl_spectrum(spectrometer: SpectrometerSystem,
                                     pl_opt_specs: OpticalSpecs,
                                     save_to: str):
    """ Measures a PL spectrum and saves it to the path specified by `save_to`. """
    # To tell the Spectrometer to use the correct_dark_counts value specified in pl_opt_specs
    spectrometer.backend.correct_dark_counts = pl_opt_specs.correct_dark_counts
    # It is advised to give the spectrometer a second to process this information
    time.sleep(1)
    # When calling the measure_pl_spectra (or measure_abs_spectra) method, we can 'unpack' the
    # OpticalSpecs object into the arguments for the method by using the double asterisk (**) prefix.
    # The measure_pl_spectra (or measure_abs_spectra) method will handle the rest.
    pl_spectrum = spectrometer.measure_pl_spectra(**pl_opt_specs)

    # While the following will work:
    # pl_spectrum.save_to_file(save_to)
    #
    # This will just save the PL spectrum itself. (Which could be sufficient). For additional record-keeping,
    # we may wish to save the light and dark references associated with this spectrum alongside it.
    # (This would be particularly diagnostic for ABS spectra).
    # Step 1: group the PL spectra with the references used by the spectrometer for pl
    spectrum_group = ZipSpectra(pl_spectrum, spectrometer.pl)  # If using ABS, then `spectrometer.abs` would be used instead.
    with open(save_to, 'w+') as _file:  # see below
        spectrum_group.print(file_stream=_file)  # Saves the PL spectrum and references in one file
    # The `with open(...) as name:` syntax is called a context manager. Its job is to manage the opening and closing
    # of a file in a manner that is "safe".
    # The Olde Fashion way of writing to a file was (and this still works):
    # [This will create/overwrite the file at "C:/Directories/Etc/file_name.extension" with the data "Hello world"
    # ```
    # file_path = "C:/Directories/Etc/file_name.extension"
    # mode = 'w+'  # Write to file, create it if necessary
    # data_to_be_written = "Hello world"
    # file_object = open(file_path, mode)
    # file_object.write(data_to_be_written)
    # file_object.close()
    # ```
    # However, if something bad happened during the write() method or otherwise between open() and close(), the
    # the file may not be closed properly and there could be data loss or the OS might think the file is in use
    # and prevent other processes from opening the file.
    # To fix this problem, the context manager syntax was introduced which will make sure that the file gets
    # closed properly if something happens inside the code block (the indented code under the WITH statement).

    return pl_spectrum
    # We could conceivable improve this code by giving `save_to` a default value of None
    # ```save_to: str = None):```
    # and only doing the save-to-file thing if a file path were given:
    # ```
    # if save_to:
    #     spectrum_group = ZipSpectra(pl_spectrum, spectrometer.pl)
    #     with open(save_to, 'w+') as _file:  # see below
    #         spectrum_group.print(file_stream=_file)
    # ```

# Now, to demonstrate this in practice.

# (Note that since this "tell the Spectrometer to use certain hardware parameters then measure a spectrum using certain
#  spectral parameters, and save the data" procedure is so common, you will see it grouped together into a single method
#  throughout this code repository).

# We will have the liquid handler sample 4 vials and perform measurements on each vial, saving to files as we go.
#
# Steps:
# 1) Connect to the Spectrometer
# 2) Define any common spectrometer parameters
# 3) Connect to Liquid Handler
# 4) Load in the current deck layout and syringe size
# 5) Define any common liquid handler locations (like waste and wash stations)
# 6) Prime liquid handler
# 7) Measure our light and dark references
# 8) Aspirate 50 uL from the first vial
# 9) Move the droplet into the flow cell
# 10) Measure the spectrum (ABS, PL, or both)
# 11) Clean the needle and flow cell
# 12) Repeat steps 7--11* for the second, third, and fourth vials
# 13) Clean up

# *If the solvents of all vials are the same as the system fluid and spectrometer drift is not an issue (option 0),
# then step 7 does not need to be repeated. If each vial uses a different solvent, then we will either need
# to measure the light and dark references in a pure sample of each vial's solvent or measure the light and
# dark references in the system solvent but take a background measurement in a pure sample of each vial's
# solvent. I.e.
# Assuming: System fluid is water, Vial 1 is in methanol, vial 2 is in acetonitrile
# Option 1
# Measure Light and Dark references in Methanol, measure a sample of Vial 1
# Measure Light and Dark references in acetonitrile, measure a sample of Vial 2
# Option 2
# Measure Light and Dark references in water, measure a sample of Methanol, measure a sample of Vial 1
# Optionally re-measure Light and Dark references in water, then measure a sample of Acetonitrile, measure a sample of Vial 2
# In this tutorial, we will show approaches 0 and 1 (the serial_measurement example in workflows shows Option 2).


# We will need to insert steps between steps 6 and 7 to define which vials to sample and organize things for the
# looping of what is currently steps 7--11

from typing import Iterable, Callable
from aux_devices.ocean_optics_spectrometer import LightSource
from deck_layout.handler_bed import Placeable, DEFAULT_SYRINGE_FLOWRATE
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import ComponentSpec, AirGap
from workflows.common_macros import boot_with_user, volume_to_center_droplet, record_spectrum, inter_clean, clean_up

if __name__ == '__main__':
    def basic_example():
        """ This will sample four vials (A1, B1, C1, and D1) and measure the ABS spectrum of each using the system fluid
        as the light and dark references for each sample. Only valid if the samples and system fluid use the same
        solvent (Option 0)."""
        # Step 1
        my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
        # Step 2
        abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False)
        # Step 3
        glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
        # Step 4
        glh.load_bed(
            directory="C:/Users/User/Documents/Gilson_Deck_Layouts/Example_Deck",
            bed_file="Gilson_Bed.bed"
        )
        glh.set_pump_to_volume(1_000)
        # Step 5
        WASTE = glh.locate_position_name('waste', "A1")
        EX_WASH = glh.locate_position_name('wash', "A1")
        # Step 6
        boot_with_user(glh, WASTE)  # Defined in common_macros.py, it will ask the user how much liquid to use when priming
                                    #   the system and will ask for how much system fluid is available to the liquid handler

        # Since steps 7--11 are repeated, we should put them in a loop
        # To put them in a loop, we should get things organized so the code can step through each iteration
        sample_1_vial = glh.locate_position_name('pos_1_rack', "A1")
        sample_1_file = "./vial_a1.csv"
        sample_2_vial = glh.locate_position_name('pos_1_rack', "B1")
        sample_2_file = "./vial_b1.csv"
        sample_3_vial = glh.locate_position_name('pos_1_rack', "C1")
        sample_3_file = "./vial_c1.csv"
        sample_4_vial = glh.locate_position_name('pos_1_rack', "D1")
        sample_4_file = "./vial_d1.csv"

        vials_to_sample: list[tuple[Placeable, str]] = [
            (sample_1_vial, sample_1_file),
            (sample_2_vial, sample_2_file),
            (sample_3_vial, sample_3_file),
            (sample_4_vial, sample_4_file),
        ]
        sample_volume = 50
        front_air_gap_volume = 20

        # Steps 7--11
        for vial_location, data_file in vials_to_sample:
            # Step 7
            my_spectrometer.measure_average_reference('abs', 'dark', **abs_opt_specs)
            my_spectrometer.measure_average_reference('abs', 'light', **abs_opt_specs)
            # Step 8 (+ an airgap to keep the droplet seated inside the needle)
            glh.aspirate(ComponentSpec(vial_location, sample_volume), DEFAULT_SYRINGE_FLOWRATE)
            glh.aspirate(AirGap(front_air_gap_volume), DEFAULT_SYRINGE_FLOWRATE)
            # Step 9
            # calculate the distance the droplet needs to move
            displacement_to_center_droplet_in_flowcell = volume_to_center_droplet(46, 146, 21, front_air_gap_volume, sample_volume, lag=2)
            # aspirate that amount of air to center the droplet (moving a bit more slowly to avoid breaking up the droplet)
            glh.aspirate(AirGap(displacement_to_center_droplet_in_flowcell), DEFAULT_SYRINGE_FLOWRATE * 2/3)
            # Step 10 (+ an annotation to the data file to help us read it later)
            file_header = "wavelength (nm), dark reference (int), light reference (int), abs (mAU)\n"
            record_spectrum(my_spectrometer, abs_opt_specs, mode='ABS', file_path=data_file, file_header=file_header)
            # Step 11
            inter_clean(glh, WASTE, EX_WASH)  # Defined in common_macros.py, it will clean the inside and outside of the needle
        # Thus concludes step 12 "Repeat steps 7--11"

        # Step 13
        clean_up(glh, WASTE)

# Reflection. We may want a better way to define the four experiments.

    def example_of_option_1():
        """ This will sample four vials (A1, B1, C1, and D1) and measure the ABS spectrum of each using a pure sample of
        each samples' solvent (located in vials A2, B2, C2, and D2, respectively) as the light and dark references for
        each sample."""
        # Steps 1--6 are the same as before:
        my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
        abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False)
        glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
        glh.load_bed(
            directory="C:/Users/User/Documents/Gilson_Deck_Layouts/Example_Deck",
            bed_file="Gilson_Bed.bed"
        )
        glh.set_pump_to_volume(1_000)
        WASTE = glh.locate_position_name('waste', "A1")
        EX_WASH = glh.locate_position_name('wash', "A1")
        boot_with_user(glh, WASTE)

        # Since each sample needs a sample vial, a vial of pure solvent for reference, and a file, let's create a
        #   class to organize this for us.
        class ExperimentSpecification(NamedTuple):
            sample_location: Placeable
            solvent_location: Placeable
            file_name: str
            # Since this may be useful later, let's also store the name of the solvent
            solvent_name: str
        # Now we can define our list of experiments:
        experiments: list[ExperimentSpecification] = [
            ExperimentSpecification(
                sample_location=glh.locate_position_name('pos_1_rack', "A1"),
                solvent_location=glh.locate_position_name('pos_1_rack', "A2"),
                file_name="./vial_a1.csv",
                solvent_name="methanol"
            ),
            ExperimentSpecification(
                sample_location=glh.locate_position_name('pos_1_rack', "B1"),
                solvent_location=glh.locate_position_name('pos_1_rack', "B2"),
                file_name="./vial_b1.csv",
                solvent_name="acetonitrile"
            ),
            # We do not need the keywords if we get the order correct.
            # Examples below are to show we can do this--it can make it harder to read at times so this is do-at-your-own-risk
            ExperimentSpecification(
                glh.locate_position_name('pos_1_rack', "C1"),
                glh.locate_position_name('pos_1_rack', "C2"),
                "./vial_c1.csv",
                "toluene"
            ),
            ExperimentSpecification(
                glh.locate_position_name('pos_1_rack', "D1"),
                glh.locate_position_name('pos_1_rack', "D2"),
                "./vial_c1.csv",
                "ethanol"
            )
        ]

        sample_volume = 50
        front_air_gap_volume = 20

        # Our Looped steps will be different this time:
        # 7) Aspirate 50 uL from the first experiment's solvent vial
        # 8) Move the droplet into the flow cell
        # 9) Measure our light and dark references
        # 10) Clean the needle and flow cell
        # 11) Aspirate 50 uL from the first experiment's sample vial
        # 12) Move the droplet into the flow cell
        # 13) Measure the spectrum (ABS, PL, or both)
        # 14) Clean the needle and flow cell
        # 15) Repeat steps 7--14 for the second, third, and fourth experiments
        # 16) Clean up

        for experiment in experiments:
            # Step 7 (+ an airgap to keep the droplet seated inside the needle)
            glh.aspirate(ComponentSpec(experiment.solvent_location, sample_volume), DEFAULT_SYRINGE_FLOWRATE)  # Uses solvent_location
            glh.aspirate(AirGap(front_air_gap_volume), DEFAULT_SYRINGE_FLOWRATE)
            # Step 8
            # calculate the distance the droplet needs to move
            displacement_to_center_droplet_in_flowcell = volume_to_center_droplet(46, 146, 21, front_air_gap_volume, sample_volume, lag=2)
            # aspirate that amount of air to center the droplet (moving a bit more slowly to avoid breaking up the droplet)
            glh.aspirate(AirGap(displacement_to_center_droplet_in_flowcell), DEFAULT_SYRINGE_FLOWRATE * 2 / 3)
            # Step 9
            my_spectrometer.measure_average_reference('abs', 'dark', **abs_opt_specs)
            my_spectrometer.measure_average_reference('abs', 'light', **abs_opt_specs)
            # Step 10
            inter_clean(glh, WASTE, EX_WASH)

            # Step 11 (+ an airgap to keep the droplet seated inside the needle)
            glh.aspirate(ComponentSpec(experiment.sample_location, sample_volume), DEFAULT_SYRINGE_FLOWRATE)  # Uses sample_location
            glh.aspirate(AirGap(front_air_gap_volume), DEFAULT_SYRINGE_FLOWRATE)
            # Step 12
            # calculate the distance the droplet needs to move
            displacement_to_center_droplet_in_flowcell = volume_to_center_droplet(46, 146, 21, front_air_gap_volume, sample_volume, lag=2)
            # aspirate that amount of air to center the droplet (moving a bit more slowly to avoid breaking up the droplet)
            glh.aspirate(AirGap(displacement_to_center_droplet_in_flowcell), DEFAULT_SYRINGE_FLOWRATE * 2 / 3)
            # Step 13 (+ an annotation to the data file to help us read it later)
            file_header = (f"solvent {experiment.solvent_name}\n"
                           f"wavelength (nm), dark reference (int), light reference (int), abs (mAU)\n")
            record_spectrum(my_spectrometer, abs_opt_specs, mode='ABS', file_path=experiment.file_name, file_header=file_header)
            # Step 14
            inter_clean(glh, WASTE, EX_WASH)
        # Thus concludes step 15 "Repeat steps 7--14"

        # Step 16
        clean_up(glh, WASTE)

# Reflection: Steps 7--10 are almost identical to Steps 11--14, it may make sense to try and reduce them to a common
    # abstraction. This will be demonstrated below and also give a primer on Callable objects and a cool thing you
    # can do in Python called dependency injection. The specific flavor of dependency injection show below is the
    # ability to pass entire methods as the arguments to other methods. Cool stuff.

    def minimal_example_of_dependency_injection():
        # These are the common operations, with the bits that change being replaced by underscores:
        """
        glh.aspirate(ComponentSpec(____________1____________, sample_volume), DEFAULT_SYRINGE_FLOWRATE)
        glh.aspirate(AirGap(front_air_gap_volume), DEFAULT_SYRINGE_FLOWRATE)
        displacement_to_center_droplet_in_flowcell = volume_to_center_droplet(46, 146, 21, front_air_gap_volume, sample_volume, lag=2)
        glh.aspirate(AirGap(displacement_to_center_droplet_in_flowcell), DEFAULT_SYRINGE_FLOWRATE * 2 / 3)
        _______2_________
        inter_clean(glh, WASTE, EX_WASH)
        """
        # So we need a location for item 1 and we will need either two my_spectrometer.measure_average_reference() calls
        # when measuring the reference or one record_spectrum() call when measuring spectrum.
        # We could do an IF statement (are we measuring spectra or a reference). However, we will also need a way to
        # handle PL vs ABS (and what about both?)
        # like so:
        # def use_spectrometer(sample_location: Placeable, is_reference: bool, mode: Literal['ABS', 'PL']):
        #     glh.aspirate(ComponentSpec(sample_location, sample_volume), DEFAULT_SYRINGE_FLOWRATE)
        #     glh.aspirate(AirGap(front_air_gap_volume), DEFAULT_SYRINGE_FLOWRATE)
        #     displacement_to_center_droplet_in_flowcell = volume_to_center_droplet(46, 146, 21, front_air_gap_volume, sample_volume, lag=2)
        #     glh.aspirate(AirGap(displacement_to_center_droplet_in_flowcell), DEFAULT_SYRINGE_FLOWRATE * 2 / 3)
        #     if is_reference:
        #         my_spectrometer.measure_average_reference(mode.lower(), 'dark', **abs_opt_specs)
        #         my_spectrometer.measure_average_reference(mode.lower(), 'light', **abs_opt_specs)
        #     else:
        #         file_header = (f"solvent {experiment.solvent_name}\n"
        #                        f"wavelength (nm), dark reference (int), light reference (int), abs (mAU)\n")
        #         record_spectrum(my_spectrometer, abs_opt_specs, mode=mode, file_path=experiment.file_name, file_header=file_header)
        #     inter_clean(glh, WASTE, EX_WASH)

        # But there is another way:
        # To help with organization, let's put the sample and airgap volumes into the experimental specification
        class FullExperimentSpecification(NamedTuple):
            sample_location: Placeable
            solvent_location: Placeable
            file_name: str
            solvent_name: str
            sample_volume: float = 50
            front_air_gap_volume: float = 20

        def use_spectrometer(lh: Gilson241LiquidHandler,
                             experiment: FullExperimentSpecification,
                             vial_location: Placeable,
                             spectrometer_operations: Iterable[Callable]):
            lh.aspirate(ComponentSpec(vial_location, experiment.sample_volume), DEFAULT_SYRINGE_FLOWRATE)
            lh.aspirate(AirGap(experiment.front_air_gap_volume), DEFAULT_SYRINGE_FLOWRATE)
            displacement_to_center_droplet_in_flowcell = volume_to_center_droplet(46, 146, 21, experiment.front_air_gap_volume, experiment.sample_volume, lag=2)
            lh.aspirate(AirGap(displacement_to_center_droplet_in_flowcell), DEFAULT_SYRINGE_FLOWRATE * 2 / 3)
            for operation in spectrometer_operations:
                operation()
            # We'll take out the inter_clean() call here. We'll call it after use_spectrometer() instead.

        # So now, we can write the procedure as usual...
        my_spectrometer = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
        abs_opt_specs = OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False)
        glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
        glh.load_bed(
            directory="C:/Users/User/Documents/Gilson_Deck_Layouts/Example_Deck",
            bed_file="Gilson_Bed.bed"
        )
        glh.set_pump_to_volume(1_000)

        WASTE = glh.locate_position_name('waste', "A1")
        EX_WASH = glh.locate_position_name('wash', "A1")

        boot_with_user(glh, WASTE)

        # ...Until we define our experiments. We added sample_volume and front_air_gap_volume to the specification,
        # so let's add that in here and remove the variables sample_volume and front_air_gap_volume that would have
        # come after this list.
        experiments: list[FullExperimentSpecification] = [
            FullExperimentSpecification(
                sample_location=glh.locate_position_name('pos_1_rack', "A1"),
                solvent_location=glh.locate_position_name('pos_1_rack', "A2"),
                file_name="./vial_a1.csv",
                solvent_name="methanol",
                sample_volume=50,
                front_air_gap_volume=10
            ),
            FullExperimentSpecification(
                sample_location=glh.locate_position_name('pos_1_rack', "B1"),
                solvent_location=glh.locate_position_name('pos_1_rack', "B2"),
                file_name="./vial_b1.csv",
                solvent_name="acetonitrile",
                sample_volume=50,
                front_air_gap_volume=10
            ),  # .... etc.
        ]

        # In the FOR loop, things will diverge more significantly.
        for experiment_spec in experiments:
            # We create a list of methods
            # In this scenario, 'lambda: method()' can be read as "Don't call this method just yet, but this is the
            # method to call."  So instead of calling measure_average_reference() right now, it will wait until the
            # ```
            #     for operation in spectrometer_operations:
            #         operation()  # <-- Specifically, this call right here.
            # ```
            # in the use_spectrometer() method to actually call measure_average_reference
            solvent_vial_spectrometer_operations: list[Callable] = [
                lambda: my_spectrometer.measure_average_reference('abs', 'dark', **abs_opt_specs),
                lambda: my_spectrometer.measure_average_reference('abs', 'light', **abs_opt_specs)
            ]
            use_spectrometer(glh, experiment_spec, experiment_spec.solvent_location, solvent_vial_spectrometer_operations)
            inter_clean(glh, WASTE, EX_WASH)  # I like the washes to given their own line so it is clear whether
                                              #   the needle is clean or contaminated.

            sample_vial_file_header = f"solvent {experiment_spec.solvent_name}\nwavelength (nm), dark reference (int), light reference (int), abs (mAU)\n"
            sample_vial_spectrometer_operations: list[Callable] = [
                lambda: record_spectrum(my_spectrometer, abs_opt_specs, mode='ABS', file_path=experiment_spec.file_name, file_header=sample_vial_file_header)
            ]
            use_spectrometer(glh, experiment_spec, experiment_spec.sample_location, sample_vial_spectrometer_operations)
            inter_clean(glh, WASTE, EX_WASH)
        clean_up(glh, WASTE)

        # Note: You can provide more detail to the Callable type annotation. Callable[[float], int] is any method
        # which takes a float as its first argument and returns an int. Callable[[str, float], bool] is any method
        # that takes a string as its first argument and a float as its second argument and which returns either True
        # or False (the boolean values).

        # A version of this use_spectrometer() idea can be seen in the utilize_spectrometer() method of the
        # Gilson241LiquidHandler class.
        # In that method the caller specifies a spectrometer to use, the volume to center the droplet in the flow cell,
        # an optional tuple describing the ABS measurement specification and what method to call to perform said
        # measurement, ditto for PL, and a spacing parameter for the sample to rest between ABS and PL measurements.
        # It is copied below for reference:
        #
        # def utilize_spectrometer(self,
        #                          my_spec: SpectrometerSystem,
        #                          volume_to_center_droplet: Number,
        #                          absorbance: tuple[OpticalSpecs, Callable[['SpectrometerSystem'], Spectrum]] = None,
        #                          photoluminescence: tuple[OpticalSpecs, Callable[['SpectrometerSystem'], Spectrum]] = None,
        #                          measurement_spacing: float = 1.0
        #                          ) -> SpectraStack:
        #     """ Moves a droplet into the spectrometer and performs the designated measurements.
        #
        #     :param my_spec: The spectrometer to use
        #     :param volume_to_center_droplet: How far to move the droplet to center it in the spectrometer
        #     :param absorbance: How absorbance measurements should be conducted (None if not to be conducted) and what
        #       method to use to perform the measurement.
        #     :param photoluminescence: How photoluminescence measurements should be conducted (None if not to be conducted)
        #       and what method to use to perform the measurement.
        #     :param measurement_spacing: A wait time between absorbance and photoluminescence measurements.
        #
        #     :return: A SpectraStack.  If both ABS and PL were requested, ABS will be first.
        #     """
        #     if absorbance:
        #         spec_abs, measure_abs_spectrum = absorbance
        #     else:
        #         spec_abs, measure_abs_spectrum = (None, None)
        #     if photoluminescence:
        #         spec_pl, measure_pl_spectrum = photoluminescence
        #     else:
        #         spec_pl, measure_pl_spectrum = (None, None)
        #
        #     if spec_abs:
        #         my_spec.backend.correct_dark_counts = spec_abs.correct_dark_counts
        #         time.sleep(1)
        #         my_spec.measure_average_reference(**spec_abs, light="dark", mode="abs")
        #         my_spec.measure_average_reference(**spec_abs, light="light", mode="abs")
        #
        #     print(f"Centering droplet ({volume_to_center_droplet} uL)")
        #     with redirect_stdout(StringIO()):
        #         self.aspirate_from_curr_pos(volume_to_center_droplet, 0.5 * DEFAULT_SYRINGE_FLOWRATE)
        #
        #     print(f"Measuring spectra\n\tABS = {spec_abs}\n\tPL = {spec_pl}")
        #     ret = SpectraStack()
        #     if spec_abs is not None:
        #         ret.append(measure_abs_spectrum(my_spec))
        #     time.sleep(measurement_spacing)
        #     if spec_pl is not None:
        #         ret.append(measure_pl_spectrum(my_spec))
        #
        #     print(f"Returning droplet ({volume_to_center_droplet} uL)")
        #     with redirect_stdout(StringIO()):
        #         self.dispense_to_curr_pos(volume_to_center_droplet, 0.5 * DEFAULT_SYRINGE_FLOWRATE)
        #
        #     return ret
        #
        #
        # This method is, in turn, used in grab_droplet_fixed() located in stern_volmer_core.py
        # def grab_droplet_fixed(glh: Gilson241LiquidHandler,
        #                        spec: SVSpec,
        #                        wash: Placeable,
        #                        waste: Placeable,
        #                        my_spec: SpectrometerSystem,
        #                        counter: int,
        #                        ):
        #     back_air_gap = 20
        #     front_airgap = 10
        #
        #     print(f"Preparing droplet {counter}")
        #     with redirect_stdout(StringIO()):
        #         droplet_volume = glh.prepare_droplet_in_liquid_line(
        #             components=spec.components,
        #             back_air_gap=back_air_gap,
        #             front_air_gap=front_airgap,
        #             air_rate=DEFAULT_SYRINGE_FLOWRATE,
        #             aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
        #             mix_iterations=spec.mix_iterations,
        #             mix_displacement=spec.mix_displacement,
        #             mix_rate=4*DEFAULT_SYRINGE_FLOWRATE
        #         )
        #
        #     glh.utilize_spectrometer(
        #         my_spec,
        #         volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2),
        #         (spec.spec_abs, lambda _s: measure_abs_spectrum(_s, spec, counter)),
        #         (spec.spec_pl, lambda _s: measure_pl_spectrum(_s, spec, counter))
        #     )
        #
        #
        # Note: measure_abs_spectrum() and measure_pl_spectrum() are located in the same file (stern_volmer_core.py)
        # and they take care of figuring out the file name and any annotations (the header information) to save
        # alongside the spectra.
        #
        # grab_droplet_fixed() is used in stern_volmer_3src.py in a demonstration of another use of lambda:
        # # Recall that grab_droplet_fixed takes as arguments: a liquid handler, a spectrometer measurement
        #     specification, a wash location, a waste location, a spectrometer, and an experimental ID number
        # Based on this, the following lambda expression
        # ```
        # lambda x, y: grab_droplet_fixed(glh, x, EX_WASH, WASTE, my_spectrometer, y)
        # ```
        # Can be read as, "Do not call this method just yet. When you do, this is the method to use; however,
        # you must supply two arguments--in this case the spectrometer measurement specification (first) and
        # the experimental ID number (second)."
        # This lambda expression is called in the run_campaign() method [located in stern_volmer_core.py] using
        # the following syntax:
        # ```
        # do_droplet_thing(test, idx)
        # ```
        # Where `do_droplet_thing` is the variable name that the method was bound to (like `operation` in the example
        # in this tutorial), test is a spectrometer measurement specification, and idx is the ID number.


# Below is a snippet of code to show an alternative way to connect to the spectrometer which may be useful if you
#   have multiple spectrometers connected to a single computer.
# By default (i.e., the way used in these tutorials and in all workflows), Python will auto-detect the spectrometer.
#   If there are multiple spectrometers, it picks the "first" one (arbitrarily determined).
def alternative_way_to_connect_to_the_spectrometer():
    from aux_devices.ocean_optics_spectrometer import Spectrometer
    # You can (but probably shouldn't) import from within a method.

    my_light_sources = LightSource("Dev1/port0/line1", "Dev1/port0/line0")
    # If you have multiple spectrometers connected to the same computer, you may address them by serial number:
    spectrometer_backend = Spectrometer.from_serial_number("F12345")
    # You can then provide that specific spectrometer to the SpectrometerSystem constructor alongside your
    #   light source controller
    my_spectrometer = SpectrometerSystem(my_light_sources, using=spectrometer_backend)

    # you can then use `my_spectrometer` normally

# Word of caution when using `lambda`.
# Because lambda can delay the execution of a method, weirdness can happen when variable which can change value
# are given to the method inside the lambda expression.
#
# # Note the str() method takes any argument and attempts to make a string representation of it.
# # str(4) = "4", str('three') = 'three', str(my_light_sources) = "<LightSource object at 0x0000016EE1EB99F0>"
#
# variable = 1
# method_one = lambda: str(variable)
# method_two = lambda x=variable: str(x)
# variable = 2
# print(f"method_one returned {method_one()}, method_two returned {method_two()}")
# ^ This will print "method_one returned 2, method_two returned 1" to the console
#
# So method_one(), who was primed with the method str() taking `variable` as its first and only argument, is shown
# the value of `variable` at the moment in time when it is **called**. Whereas method_two, who was primed with the
# value of `variable` as the default value of x which is in turn provided as the first and only argument to the str()
# method, uses the value of `variable` at the moment in time when method_two() is **defined** (rather than called).
