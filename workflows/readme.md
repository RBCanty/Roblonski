## Overview ##
This directory contains the workflows and assays presented in the associated manuscript.

### Modifications to make before you run ###
The main blocks reference paths which will need to be updated to match your local file structure.
Any modifications necessary for the liquid handler and spectrometer initializations which have 
been described in their README files will also be required.
You will need to measure the volumes of the needle, tube, and flow cell on your platform to ensure
that any droplet created will be properly located in the flow cell.
If running your own experiments, the experimental specification of the main blocks will need to 
be updated to match your experimental design.

## File Descriptions ##

### common_abstractions.py ###
This file defines three abstractions which were used throughout the project.
- ```Dilution```: A Dilution (and its two children: Volumetric and Fractional) are used to define 
    how a dilution is to be carried out on the liquid handler and provide a way to record these 
    details in the metadata saved alongside datafiles.
  - Volumetric dilutions are specified by a fixed volume (e.g., replace 10 uL with each dilution)
  - Fractional dilutions are specified by a fixed relative volume (value between 0 and 1; e.g., 
      value=0.3333 --> replace 1/3rd of the total volume with each dilution).
- ```DilutionTracker```: This is a bookkeeping class which tracks the operations performed on a
    sample in order to determine the concentration at each step. This keeps track of both the
    nominal and "actual" dilution at each step. Nominal is based on the volumes specified (e.g., 
    10 uL) whereas the actual values is based on the calibration-corrected volumes (e.g., 9.998
    uL). 
- ```Calibration```: This class provides a way to convert nominal volumes to their estimated
    actual values as well as record this relationship in the metadata saved alongside datafiles.
    If no calibration is provided, it will default to a y=x relationship. Otherwise, the
    calibration can be provided as a polynomial of arbitrary degree. The polynomial is 
    in ascending order (it starts with x^0 and the power of x increases with each term). For 
    example: y=x^2 - 2x + 3 would be represented as the tuple (3, -2, 1).
  - This class implements the ```__call__()``` dunder method, this allows an object of this type
      to be called like a method.  For example: if a calibration object, cal, is created
      with ```cal = Calibration(3, -2, 1)``` (i.e., y=x^2 - 2x + 3), then ```cal(4.5)``` 
      will return 14.25. This can be called an arbitrary number of times with an arbitrary input
      value.
  - A Calibration also supports the imposition of bounds on the translated value. For example, a
      floor of 0 would replace and negative predicted actual volume with 0.

### common_macros.py ###
This file provides some helpful methods which were commonly used throughout the project:
- ```boot_with_user()```: Prompts user to define prime volume and to specify system liquid level.
- ```prime()```: Primes the pump with a specified volume of system fluid.
  - If the volume is large (e.g., larger than the volume of the syringe), the operation can
      automatically be broken down into smaller partial priming operations (controlled by the
      `chunk_size` parameter.)
- ```clean_up()```: Dispenses 200 uL of system fluid three times, then homes the arm
- ```inter_clean()```: Empties the syringe, internal washes, external washes, internal washes 
    again, then restores the system airgap.
- ```volume_to_center_droplet()```: Based on measured system parameters and the current droplet,
    this method calculates how much air should be aspirated to center the droplet in the flow
    cell for spectral measurement.
- ```test_well()```: Grabs a droplet form the specified well then measures it on the spectrometer.
- ```record_spectrum()```: Calls the provided spectrometer to perform a measurement and both saves 
    the spectrum to a file and returns said spectrum.
  - If the file is currently open, it will **prompt the user to close the file**. It will do so
      only once. Note: User intervention will cause the program to pause indefinitely until input
      is provided.
  - If the `file_path` keyword is an empty string, the file-saving aspect will be ignored.
- ```record_reference()```: Similar to record_spectrum(), but will measure two spectra (a dark then
    a light reference). These reference spectra will be bound to the spectrometer (used in all 
    future scans until new references are loaded).
- The main block of this file is a demonstration of all of these methods where the liquid handler
    will sample and measure spectra for a set of five samples. Paths and DAQ ports will need to be
    updated to match your device.
  - This block uses the depreciated ```RPLQYApellomancer``` class from 
      workflows/rplqy_v1/naming.py to name its data files, but is still sufficient for 
      demonstration purposes.

**Recommendation for how to measure the parameters referenced in `volume_to_center_droplet()`**:
For measuring the volumes of the needle, tube, and flow cell, we recommend using the GUI 
provided to assist in making these measurement. An iterative approach of aspirating and dispensing
fluid until the edge of the liquid lines up with the measurement points is good for a quick rough
estimate. Final values should be from a single aspirate taken from a freshly primed system to avoid
any accumulation of errors during the estimation phase. For example:
1) Prime the needle, restore the system airgap.
2) Aspirate 100 uL. The liquid exceeded the needle volume by a few uL.
3) Dispense 5 uL. The liquid level is now barely within the needle.
4) Aspirate 1 uL. The liquid level is flush with the needle-tube interface.
5) Prime the needle, restore the system airgap.
6) Aspirate 96 uL. The liquid level is about 1 uL past the needle and into the tube.
7) Prime the needle, restore the system airgap.
8) Aspirate 95.5 uL. The liquid level is flush with the needle-tube interface.
9) Record 95.5 uL as the volume of the needle.
10) Prime the needle, restore the system airgap.
11) Aspirate 125.5 uL. The liquid level is a few uL short of the flow cell.
12) Aspirate 3 uL. The liquid level is flush with the flow cell.
13) Prime the needle, restore the system airgap.
14) Aspirate 122.5 uL. The liquid level has gone a small ways into the flow cell.
15) Prime the needle, restore the system airgap.
16) Aspirate 122 uL. The liquid level is flush with the flow cell.
17) Record 26.5 uL as the volume of the tube.
18) Prime the needle, restore the system airgap.
19) ...and similarly for the flow cell volume.

Note that the volume of the flow cell is based on the entrance and exit, not the small segment of the
flow cell which is exposed to the UV-Vis light. It also assumes that the beam path is centered in the
flow cell. The lag parameter can be used to tune the location of the beam path relative to the center
of the flow cell.


### map_assay.py ###
This file is not used in the associated manuscript. Nevertheless, it is included as a helpful
tool to anyone using this code base who just wants the liquid handler to prepare vials/wells
based on volumetric specifications of components.

**The script provided generates the steps to perform**. The user is charged with walking through
these steps and issuing the appropriate liquid handler actions*. These steps are formated to
be plug-n-play with the ```Gilson241LiquidHandler.prepare_vial()``` method. (*It is not known 
how and when the user would wish to perform cleaning/mixing/measurement operations)

This protocol will read in a CSV file and then have the liquid handler prepare each non-stock
vial according the file's specification. A vial created in the process can be used as the stock
for a subsequent vial. The code will automatically reorder vials into an order that is sensible.

The CSV file should be of the form (whitespace around delimiters is ignored):
```
TYPE  ,NAME    ,RACK      ,VIAL  ,COMP1N  ,COMP1V  ,COMP2N  ,COMP2V,COMP3N ,COMP3V

stock ,catalyst,pos_1_rack,A1    ,        ,        ,        ,      ,       ,
stock ,diluent ,pos_1_rack,A2    ,        ,        ,        ,      ,       ,
stock ,quencher,pos_1_rack,A3    ,        ,        ,        ,      ,       ,
sample,sample1 ,pos_1_rack,B1    ,catalyst,100     ,quencher,200   ,diluent,100
sample,sample2 ,pos_1_rack,B2    ,catalyst,200     ,quencher,100   ,diluent,150
sample,sample3 ,pos_1_rack,B3    ,sample1 ,150     ,sample2 ,150   ,diluent,175
sample,sample4 ,pos_1_rack,E1    ,catalyst,200     ,sample2 ,100   ,diluent,125
sample,sample5 ,pos_1_rack,E2    ,sample1 ,150     ,sample3 ,150   ,diluent,200
sample,sample6 ,pos_1_rack,E3    ,sample5 ,150     ,diluent ,100   ,       ,
```
All volumes are in microlitres and any non-empty line which does not start with either 'stock' or
'sample' will be treated as a comment and printed to the console when `read_csv()` is called. The number
of columns can be extended to any number on a line-by-line basis.


## Workflow Descriptions ##

### system_characterization\\... ###
This directory contains the scripts used to characterize the platform.
- Measuring cross-contamination: Use contamination_study_v2.py
- Measuring the pipetting calibarion: Use graviometric_test.py
- Measuring signal dependency on location/movement of the flow cell: Use light_source_consistency.py
- Measuring mixing properties: Use droplet_size_and_mixing_study.py and mixing_dp.py
  - As an quick alternative, use extinction_assay.py playing with the mixing parameters. If the
      mixing is not sufficient, a linear absorbance response with a serial dilution should be highly 
      improbable.
- The file 'exposure_study.py' was used to see how the observed PL intensities were
    affected by the exposure time (e.g., could high exposure values be bleaching the dyes).

### stern_volmer\\... ###
The version of the SV assay used in the associated manuscript is stern_volmer_3src.py.
The other versions presented were explorations of other means by which to make the measurement
more efficient. 2src requires a quencher vial loaded with catalyst so that no diluent vial is
needed. The 3binary version used the partial replacement of the current droplet with fresh quencher
and catalyst to conserve material and time.

The naming, stern_volmer_core, and stern_volmer_dp files are used in the SV assays as means to
specify, annotate, process, and save the experiments and the generated data. 
- Naming defines the ```SVSpecDescription``` class which records information such as:
  - Timestamps
  - Spectral measurement type (ABS or PL; in practice, always PL)
  - A counter (ID) to avoid overwriting data files and knowing the order of experiments
  - The catalyst, quencher, and diluent used
  - How many mixing iterations were used
- Naming also defines the ```SVApellomancer``` class which handles the creating and interpretation
    of data files. It embeds the timestamp, experimental ID, the volumes of catalyst, diluent, 
    and quencher, and number of mixing iterations into the file name.
- Core defines the ```SVSpec``` class which specifies information such as:
  - The number of mixing iterations
  - The mixing displacement
  - The catalyst, quencher, and diluent used
  - The ABS spectroscopy parameters
  - The PL spectroscopy parameters
  - Which SVApellomancer to use when generating files
- Core also defines the `measure_pl_spectrum()` and `measure_abs_spectrum()` methods which handle
    making the calls to the SVApellomancer and `record_spectrum()` method (from common_macros.py)
    to properly create and format a datafile of the spectra.
- Core defines the `grab_droplet_fixed()` method which is effectively an early version of
    `test_well()` from common_macros.py in that it just calls prepare_droplet_in_liquid_line 
    then calls utilize_spectrometer (both defined in the GilsonLiquidHandler class)
- Core, finally, defines the ```run_campaign()``` method which runs through an iterable of
    experimental specifications and performs each as an experiment. 
- DP (data processing) defines a container for the signal data used in SV analysis along with two
    copies of a SVSpecDescription object (one with nominal values, one with calibration-corrected
    values).
  - The rest of the file concerns loading data files, reading the spectral data from them, 
      determining baselines, processing the data into I_0 and I vs \[Quencher\] data and saving
      a table of such data alongside copies of (smoothed, baseline subtracted) spectra into a
      summary file for the user.
  - The Main block can be used to re-process data.

### serial_measurement\\... ###
This directory contains the code used to perform the BL and PLQY assays in the associated
manuscript.
- abstractions.py: This defines the `LedgerLine` class which fully specifies an experiment.
- constants.py: This is a collection of constants used to parameterize the preparation of new
    vials based.
- naming.py: This defines the `SMSpecDescription` class and the `SMApellomancer` class.
  - SMSpecDescription records the basic description of the serial dilution--based experiment.
  - SMApellomancer defines how datafiles are named and how those names can be decoded.
- serial_spec.py: This defines how an experiment is defined using the `Experiment` class. 
    LedgerLine objects are converted into Experiment objects and annotated as the experiment
    is conducted. 
  - Experiment also provides the auto and span_[...] methods to make the definition of replicates
      easier.
- sm_assay_core.py: This file defines the actual steps of each serial dilution--based experiment.
  - `calculate_new_vial_parameters()`, `prepare_new_stock_in_vial()`, and `perform_dilution_in_needle()`
    are provided for preparing the Working vial (or modifying the droplet) based on initial 
    signal measurements made on the stock solution.
  - `perform_dilution_in_vial()` defines how to perform a serial dilution in a vial
  - `check_source()` defines how the source/stock solution should be checked for signal strength
    (precedes the creation of a working vial or modification of the droplet to meet initial
    signal targets)
  - There are various `case_[...]()` methods. A comment at the bottom of the file outlines these
      cases. In short, based on how the experiment is specified (is there a target signal value,
      which of Source, Working, and Diluent vials are defined and how, etc.) the behaviors change.
      These cases reduce to three unique needle-based procedures and two unique vial-based
      procedures.
  - `core_loop()` strings together the pre-check, creation of new samples (in needle or vial), 
      various cases (summarized above), measurements, serial dilutions, and cleaning for
      each experiment. The method is annotated with comments which identify what each section of
      the code does: measure initial signal, make adjustments for any target signal values, and the
      serial dilution experiment. This last section holds the needle and vial cases as two 
      branches of an IF statement.
- sm_dp.py: This file assists in the data processing of serial dilution--based experimental data.
    Similar to the stern_volmer_dp.py file, this defines how to save and load spectra files, how 
    to extract and subtract spectral backgrounds. In addition to providing summary datafiles for
    ABS and PL data individually, there are additional methods for loading both simultaneously 
    and performing joint analysis.
  - The Main block can be used to reprocess data.
- serial_measurement_assay.py: This file is the file which is run to perform the experiment.
  - It begins with a boot method which handles the creation of the apellomancer, and connecting
    the spectrometer and liquid handler (loading the bed files, setting the pump volume).
  - An `AbsorbanceFilter` class is defined which used to provide support to the 
    `process_rplqy_data()` method in sm_dp.py. (For example, ignore data where the ABS signal
    is below 6 mOD).
  - The first section of the Main block is labeled "Specifications". This is where the user
    can set project parameters such as:
    - The name of the project
    - Whether RPLQY should be calculated
    - Any filters for data processing
    - The system fluid
    - The volumes to use when centering a droplet in the spectrometer
    - Common (cross-experiment) experimental parameters such as
      - Initial sample volume
      - Dilution schedule
      - Apellomancer
      - How to locate items
      - ABS spectrometer specifications
      - PL spectrometer specifications
      - Target and threshold ABS and PL signals
      - Calibration data
    - The next section of the Main block is the definition of the ledger.
      - This is a list of `Experiment` objects. Each object is provided the common 
        (cross-experiment) experimental parameters described above as well as 
        experiment-specific parameters such as the name of the analyte, the location, the solvent
        to use, the source concentration, spectral processing methods, etc.
      - When a tool like span_const_source() is used, the line in the ledger must be
        prefixed with an asterisk. Similarly, when the source, working, and diluent locations
        are specified using auto() instead of individually, the auto() line must be prefixed
        with two asterisks. For example, most experiments are specified with span_const_source()
        and so use unpacking (the asterisk prefixes), but ZnPc (the last three) has each 
        replicate specified individually as an example of how to define a ledger line without 
        unpacking. In practice, this is because the ZnPc samples had to be arranged on the deck
        in a peculiar fashion to fit everything, and so the convenience methods of auto and 
        span_const_source were inapplicable.
    - The final section is the execution code (should not need to be modified). This code handles
      measuring the initial reference spectra, then iteratively executing each experiment and
      performing the post-processing required to obtain the extinction coefficient/RPLQY values.
      - It will also handle cleaning the needle between experiments and cleaning up the needle
        at the end of the experimental campaign.
- support_methods.py: This file provides some helper methods for determining in-vial mixing
    parameters and for generating the concentration metadata provided with each spectral data file
    generated during operation. It also provides a container for organizing the specifications for
    the `measure_spectrum()` method (also defined in this file).
  - the `measure_spectrum()` method handle the formatting of the data files and asking
    the spectrometer to measure spectra.

### rplqy_v1\\... ###
These files can serve as additional examples for how to use Neptune but are not used in the 
associated manuscript. Like other assays, it is divided into a file for naming conventions, a 
file for the assay, and a file for data processing. As an unfinished example, it is lacking the
further development which would see commonly performed, cross-file operations reorganized into 
a dedicated support abstractions and methods files.
