## Overview ##
These files are used to great graphic user interfaces to help with operating the liquid
handler programmatically. None of the tools provided are sufficient for workflows; however,
they facilitate training positions on the liquid handler (e.g., measuring distances and 
volumes) as well as maintenance.

### Modifications to make before you run ###
The main blocks of pilot_arm.py and quick_gui.py reference paths which will need to be updated
to match your local file structure.

## File Descriptions ##

### pilot_arm.py ###
This provides a simple GUI for controlling the robotic arm and pump on a liquid handler.
This GUI is particularly useful for the following actions:
- Moving the arm out of the way
- Priming the pumps
- Measuring the XYZ coordinates of key locations without the use of a ruler or calipers.
- Measuring the volumes of the needle, tubing, and flow cell (see recommended protocol below).
- Loading sample into the flow cell for measurement when debugging the spectrometer code or
    tuning spectroscopy parameters for good measurements.

The GUI will appear with its "manual" on the right-hand side. A copy of this manual is presented 
below. While the arrows are useful in niche cases, in most cases the direct jump buttons are the
most useful.
```
Use arrows to move arm
⌂ will home the arm
'max' will move the arm to max Z height.
X, Y, and Z will show the position, requires manual update
Sxy and Sz are for arm movement speeds
Step adjust the movement when using the arrows

Jx, Jy, and Jz will jump the arm (One axis at a time)
(Note: when moving in X/Y, Jumps will raise to max z first before returning to the previous z height)

Volume (mL) is for the pump
AR/AN - Aspirate from Reservoir/Needle
DN - Dispense to Needle
⌂ will home the pump (Pay attention to where the needle is!)
```

The Main block of this file can be reduced to:
```
Seahorse(
    tk.Tk(),
    Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
).run()
```

The version of the Main block presented includes some (situationally helpful) actions in 
are commented out. These include the loading of a bed configuration, the user-guided priming 
of the fluid lines, and the automatic movement to a named location upon startup (but after homing
the arm). 

### quick_gui.py ###
Three templates for pop-up dialogue boxes which request user input. These templates can be
executed without knowledge of tkinter beyond providing a tkinter instance as the root (which
in many cases is as simple as providing ```tkinter.Tk()``` as the root argument).
- QuickButtonUI: Creates a dialog box with a collection of buttons which can be pressed.
- QuickEntryUI: Creates a dialog box which presents a single entry field for the user to 
    input a number of small string of text.
- QuickSelectUI: Creates a dialog box with a collection of options for the user to select from.

### style.py ###
A collection of constants and argument defaults for the tkinter module as well as
formatting commands for bolding and coloring of text printed to the console.