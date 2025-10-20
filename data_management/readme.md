## Overview ##
These files concerning the handling of data files in the file system and the processioning of numerical data.
For other spectral data-processing see the aux_devices folder (general) and the workflows folder 
(workflow-specific).


## File Descriptions ##

### apellomancer.py ###
This file contains general functions for turning numbers into strings which can appear in file names (and
reversing the transformation).

This file also defines the Apellomancer abstract class. Deriving its name from a name wizard
(cf. install wizard), these objects are responsible for creating valid file and folder names, pathing 
to said files and folders, and translating any data stored in the file name.

An Apellomancer is given a root directory (all items will be saved therein) and a mutable project name
(which can be used to group related files into folders).  When an Apellomancer is created it will perform
checks on the provided data paths in accordance to the opening mode:

 - 'r' (Read): The Apellomancer should use the names/paths provided as-is. Used for reading an existing project.
 - 'w' (Write): The Apellomancer should check to see if the names/paths already exist. If so, then 
      **user input is requested** to determine if new data should be added to the existing directories
      (Potentially overwriting old data) or if new data should be added to new directories.
 - 'a' (Append): Same as 'w' but will replace user input with an automatic choice to place new data
      into a new directory (No user input involved).

When new directories are created, their names will be the original name + "(Date r#)" where Date is (by default)
of the form "%Y %b %d" (e.g., "2025 Jan 12"") and # is an increment starting at 1. For example: "Example", 
"Example (2025 Jan 12 r1)", "Example (2025 Jan 12 r2)".

Changes to the project directory should be performed using the ```update_sub_directory()``` function.

A basic implementation of an Apellomancer is provided with the SequentialApellomancer class which
saves files in the format "example__timestamp_spectralmode_i#" where timestamp is of the form
"%Y-%m-%d--%H-%M-%S" (e.g., "2025-01-12--13-12-02"), spectralmode is "ABS" or "PL", and # is a 
caller-specified number.

### common_dp_steps.py ###
This file provides three resources: a means to grab all files in a directory (```os.walk(...)```) with the option to 
only include files who name contains a specified substring (```get_files(directory, key)```), a data structure to
organize the specifications for how spectra are to be analyzed as a single number (SpectralProcessingSpec), 
and common methods for converting a spectrum into a single number.

```get_files(directory: str, key: str = None)```
Calls ```os.walk(...)``` on the directory (explores the directory and all subfolders thereof, recursively).
If key is none, all file paths (not just names) will be returned as a list. If key is a string, then only
files whose name contains the substring specified by key will be included in the returned list.

```SpectralProcessingSpec(NamedTuple)```
This tuple is defined by three values: a lower and upper limit on wavelength (all analyses are restricted
to this range; a None-value is treated as no-bound on that end) and an analysis method (or methods if given
a Sequence of analysis methods). Analysis methods must be functions which take a Spectrum object as their 
first and only argument and return a float.

The property ```primary_analysis``` will always return the first (or only) analysis function. (Many of the
workflows will use the primary_analysis method for prechecks of concentration or signal).

As a tool for documentation, the method '```tag_repr()```' is provided. This will return multiple lines of
comma-separated values (delimiter: ', ' with a space) which summarize the wavelength range parameters and 
will provide a quick summary of the analysis methods.  If an analysis method has not been configures to have
a '\_\_name\_\_' attribute, then the string "\<Anonymous\>" will be used instead.

The analysis methods are mostly wrappers of methods inherent to the ```Spectrum``` class (aux_devices/spectra.py). 
These wrappers store arguments provided at the creation of the analysis method so that when it comes time
for this method to be called, it takes only a Spectrum as an argument. These wrappers also provide a 
human-readable name ('\_\_name\_\_' attribute) to be included in the tag_repr() function described above.\
For example, the method ```take_sigal_near(wv: float, tol: float)``` will return a function which when provided
a Spectrum, s, will call: ```s.signal_near(wv, tol)``` and which when asked for a name will return 
f"take_signal_near(wv; tol)" (these method names use a semicolon as they are embedded in CSV files).  
For another example, ```take_max_signal()``` will, provided a Spectrum, s, will call 
```numpy.nanmax(s.signal)```.

### simple_linear_regression.py ###
This file is provided for transparency, anyone seeking to extend this code to cover more intricate data
fitting (polynomials, Leher-corrected Stern-Volmer analyses, etc.) should use an existing data processing
module like numpy and scipy.

The core function of this module is the ```slr()``` method which takes a set of X and Y data and returns
a ```RegressionReport``` object. A RegressionReport object is a container (dataclass) which retains
valuable information about the fitting without storing X and Y.  In addition, this container provides
access to the fitted function as a python callable (```predictor``` attribute or by directly calling
the RegressionReport object on an X datum) as well as a measure of surprise for a set of XY data.