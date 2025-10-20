### Overview ###
This folder contains the code for controlling an OceanOptics spectrometer and 
light source as well as basic signal processing.

signal_processing.py and spectra.py can be used to generate and test analyses on 
simulated spectral data. ocean_optics_spectrometer.py can be used to generate 
real spectral data (Absorbance or Photoluminescence) x (Cuvette mode or Flow cell mode).

### Modifications to make before you run ###
In ocean_optics_spectrometer.py some items may need to be changed before the module
can be executed on your computer.
The definitions for the ABS and PL light sources are given as NI DAQ addresses in:
```LightSource("Dev1/port0/line1", "Dev1/port0/line0")```. These addresses should be
updated to the addresses used on your DAQ device.

The subsequent lines:
``` 
my_spec.abs.backend.correct_dark_counts = False
my_spec.abs.backend.correct_nonlinearity = False

optical_abs_specs = {'count': 30, 'interval': 0.1, 'integration_time': 20_000}
optical_pl_specs = {'count': 3, 'interval': 0.1, 'integration_time': 2_000_000}
```
Will need to be adjusted in accordance with your light source, flow cell, fiber optics,
and spectrometer.  Not all OceanOptics spectrometers support ```correct_dark_counts```
and ```correct_nonlinearity```. If one of these settings is not supported, the
spectrometer should display an error saying so.

Finally, for the cuvette-mode, absorbance measurement, a light reference will need to be
provided. Please update the path and file name to match your light reference for that 
cuvette.  (The file should be two columns: wavelength, absorbance in mOD; and use "," as 
the delimiter).
```
my_dir = r"C:\Users\User\Documents\Gilson Spectroscopy Project"
my_spec.load_reference(os.path.join(my_dir, r"1mm_cuvette_light_reference_MeCN_v2.csv"), mode="abs", light="light")
```

### WIP: spectral_latches.py ###
This python file is a foray into having the spectrometer detect and center the droplet.
This should in principle be possible, but we had success with using a pre-measured volume
being used to center the droplet in the flow cell. This code stub is included as a 
jumping-off point if you would like to implement such functionality.