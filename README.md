# Neptune

A Python-based control system for photochemical experiments performed on a Gilson liquid
handler.  While Gilson's trident is the alchemical symbol for Essence, we saw the 
opportunity to connect another trident associated with handling liquids: ♆

### Objectives

- To provide python-level control over a Gilson liquid handler and peripheral devices.
- To facilitate automated experimental design and specification.
- To provide but not require more nuanced control (such as air gaps, tip techniques, flow rates)
    for common liquid handling operations.

### Dependencies

| Module    | Author                    | Version      | Notes             |
|-----------|---------------------------|--------------|-------------------|
| python    | ...                       | 3.12         |                   |
| pyserial  | Chris Liechti             | 3.5          |                   |
| nidaqmx   | National Instruments (NI) | 1.0.1        | *                 |
| numpy     | Travis E. Oliphant &a.    | 1.26.4       | Must be pre 2.0** |
| seabreeze | Andreas Poehlmann         | 2.9.2        | ***               |
| scipy     | ...                       | 1.14.1       |                   |
| peakutils | Lucas Hermann Negri       | 1.3.5        |                   |
| pandas    | ...                       | 2.2.3        |                   |
| pyusb     | Jonas Malaco              | 1.2.1        |                   |
| libusb    | Adam Karpierz             | 1.0.27.post1 |                   |

&ast; nidaqmx will require a subsequent driver installation ```$ python -m nidaqmx installdriver``` (see: 
[nidaqmx-python](https://nidaqmx-python.readthedocs.io/en/stable/#installation) )

** Limitation due to seabreeze

*** Need to install pyusb and libusb then copy \
" ...\venv\Lib\site-packages\libusb\_platform\_windows\x64\libusb-1.0.dll "\
into \
" C:/Windows/System32 "

Depending on your OS, you may need to install the USB driver for the spectrometer.\
https://zadig.akeo.ie/ has many of the drivers for Ocean Optics

We apologize to our potential Linux and Mac users as your method for installing and 
accessing these USB drivers may be substantially different.

Please note that OceanOptics now provides a Python SDK called OceanDirect which should be 
significantly more powerful than the seabreeze module used in this project (and avoid the wierd driver
installation steps and escape the numpy version restriction). If you are able to refactor code and 
know how to connect Python to .NET, then this is the recommended path forward.

### Organization
Each folder will contain a readme.md file which will provide more details on the contents of each
folder. The exceptions are the Tutorial folder (which begins with introduction.md) and the example
Deck Layout directory (which is explained in the deck_layout folder's readme)

#### Top-Level
 - **Tutorial**: A set of Python files which seek to explain how to use this code base for someone with minimal
     Python experience. The hope is that if you can write out your operations as a checklist, you can make
     the corresponding python file to run in this codebase.
 - aux_devices: Control code for the spectrophotometer and light sources.
 - data_management: Contains unit annotations, linear regression tools, 
     and common data-processing (and file management) methods.
 - deck_layout: Organizational code for managing resources on the liquid handler bed. (See: GilsonDatabase)
 - gilson_codexes: Communication protocols for the Gilson liquid handler.
 - liquid_handling: Control code for the liquid handler.
 - user_interface: A minimal GUI for manual liquid handler control.
 - workflows: Examples of the code used to characterize the platform and run experiments.
 - GilsonDatabase: Example of how the control code organizes items on the liquid handler bed.

#### The 'workflows' folder
 - serial_measurement: Contains the code for performing Beer-Lambert and Thermoluminescence quantum yield
     experiments and initial, automated data processing. Most of the contents of this folder
     are for bookkeeping. The actual workflow is contained within **sm_assay_core.py** and 
     **serial_measurement_assay.py**.  The latter contains the 'green go button' for this experimental workflow.
 - stern_volmer: Contains the code for performing a Stern--Volmer assay.  Multiple approaches are
     presented depending on the number of source vials being used. The method used in [publication reference]
     is **stern_volmer_3src.py**.
 - system_characterization: Contains the code for performing platform characterization studies such as
     cross-contamination, pipetting calibration, mixing, _etc_.
 - The **common_X.py** files in this directory are for organizing repeated operations across workflows
     into one location.  **common_macros.py** is for mechanical operations and **common_abstractions.py**
     is for handling calibration curves and their effects on serial dilutions.

### Notes
Many of these concepts are explained in more detail in the Tutorial. To see example code immediately, view
the workflows folder.
 1. What is an "apellomancer" and why does it keep showing up? This is a humorous term meaning
    "name wizard" (compare: installation wizard). They are code objects designed to help manage
    files (where to save them, what to call them, how to read them). Given the unique needs of
    different experiments, each workflow's apellomancer makes sure that each file name is 
    meaningful, unique, and organized sensibly into folders. One crucial function is their ability
    to ensure that a datafile/datafolder is not overwritten during operation.
 2. Why are workflows specified by *.py files and not a more human-readable scripting language?
    In general, this is to allow the user to make full use of Python's control flow as well as the
    user's code editor to help autofill and check the workflows. It also makes the code base more extensible,
    as a user can have direct access to data generated by the platform, create and reuse their own methods at
    will, and embed their workflows into other python libraries (custom or existing).
 3. "Can I use this code to make the platform act like a normal liquid handler?" Yes, see the map_assay.py file in
    workflows folder. This will take in a CSV of vial IDs and component volumes and prepare them as such.

