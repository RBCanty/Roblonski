## Overview ##
The underlying control code for a Gilson Liquid Handler. These files define the behaviors of a
Neptune-controlled liquid handler.

### Modifications to make before you run ###
In gilson_connection.py, there is a parameter at the top of the file ```USB_DEVICE_NAME```
which may need to be updated. Our value for this parameter is: 
"Prolific PL2303GS USB Serial COM Port"; but the device name should be updated to match the 
Hardware Device Name for whatever RS232-to-USB cable is being used to connect
the computer to the Gilson control module (for Windows, the device name in the Device Manager).
For further documentation on what value to use for ```USB_DEVICE_NAME``` see the documentation 
for ```serial.tools.list_ports.grep()```. If you wish to use a COM port by name
(e.g., "COM14" as used in ```serial.Serial()```), then the port keyword argument can be set to
the COM port's name when creating a ```Gilson241LiquidHandler``` object. When provided an
explicit COM port name, the value of ```USB_DEVICE_NAME``` will be ignored.

In gilson_liquid_handler_backend.py there are device IDs listed as defaults in the ```__init__()```
method for the ```_Gilson241LiquidHandler``` class. These numbers correspond to the values selected
by the dials on the back of each connected Gilson device. (There are little arrowed wheels 
recessed into the backs of each device where a number can be selected. Each device must have a 
unique ID value which must match the value in the code.) You can either use a screwdriver
to make your liquid handler, pump, and injector match the values in the code (30, 2, and 6 
respectively) or update the code. Alternatively, after creating a ```Gilson241LiquidHandler```
object (gilson_handler.py), you can set the attributes accoridngly. Example below:
```
glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
glh.handler_id = 30
glh.pump_id = 2
glh.injector_id = 6
```


## File Descriptions ##

### gilson_connection.py ###
This file codifies the Gilson Serial Input/Output Communication (GSIOC) protocol for use
in a Python environment using Serial objects.  This module also registers the ```Serial.close()``` 
method with ```atexit``` to help ensure proper and safe disconnections.

The ```print()``` statement in ```stamp(msg)``` may be replaced with a logger call or commented
out depending on your preferences with seeing the log of actions in the console. Note that
there are other methods for suppressing the console logs during operation defined in the misc_func.py
file (the ```silence``` decorator).

### gilson_handler_backend.py ###
This file contains the backend for control of the liquid handler. All methods in the 
```_Gilson241LiquidHandler``` class correspond to the atomic commands specified in the codex
files of the gilson_codexes folder.  These are separated from the codex files to provide a 
simpler interface and documentation in a code editor and to store device ID bindings.

This file also contains the ```Gilson241LiquidHandlerConfigurator``` class. This class
is given a ```_Gilson241LiquidHandler``` object and provides two helper methods (described below).
**This functionality is suppleted by the GUI provided in the user_interface directory,** but this 
provides a backup if tkinter (the GUI program) is acting up or if it is necessary to test a 
partially configured liquid handler.
- prime_pump_at_xy: Moves the arm to a location and primes a given amount of fluid
    through the system. The user is then asked if they wish to continue priming or exit.
- seek_positions: Provides a command-line interface for moving the robotic arm.

### liquid_handling_specification.py ###
This file contains definitions for routine actions on the liquid handler in a manner
that permits the ```chain_pipette``` protocol. 

### gilson_handler.py ###
This file provides the practical control of the liquid handler and peripheral devices. These
methods will impose safety constraints on parameters. In addition to all low-level actions
defined in gilson_handler_backend.py, a ```Gilson241LiquidHandler``` object has access to 
more intricate operations which are composed of multiple low-level actions. For example,
tip-touching, control over aspiration/dispense location, mixing, washing and cleaning, moving
the arm to a rack-vial location, priming, preparing droplets, transferring materials, etc.
In general, private methods (those starting with an underscore) should be invoked via the
```chain_pipette``` protocol or by other methods within the ```Gilson241LiquidHandler``` class
and public methods (all other methods) can be called by any means. Any and all actions of the
liquid handler can fundamentally be derived from the methods provided at the section labeled
"CORE USER-END" in this class (i.e., move_arm_to, aspirate, dispense, dispense_all, 
locate_position_xyz, and locate_position_name).

This class also defines the ```chain_pipette``` protocol. This method takes a sequence of
specifications and executes them in-order. It is equivalent to calling each method
directly in sequence but permits flexibility in the creation and modification of the sequence 
before execution.

If you add new functionality to the ```Gilson241LiquidHandler``` class and wish to incorporate 
it into ```chain_pipette``` protocol, then the new function should be included in 
the ```VALID_SPEC``` constant at the top of the file and given a branch in the 
```chain_pipette()``` method definition.