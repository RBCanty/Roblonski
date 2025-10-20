## Overview ##
These files specify the low-level commands of the gilson. Each file is a translation of
the Gilson API documentation into Python code. In short, the Gilson liquid handler
expects commands as string sent over a serial connection is a very specific format.

The general user should not need to understand this file beyond "This file translates instructions into the
specific format that the device expects".


>**If your Gilson Liquid Handler is not a GX241**, then you may need to modify the syntax of these messages.\
To do this, you will need a technical manual for your specific liquid handler\
For a copy of the manual, please contact your local Gilson technical support representative.\
\
Alternatively, this directory and the liquid_handling/gilson_connection.py file can be replaced
with a new GSIOC (Gilson Serial Input Output Channel) module should one be provided for your instrument.
The associated liquid_handling/gilson_liquid_handling_backend.py file may need to be updated depending
on the features present/missing from the new communication module or the new device.


## File Descriptions ##

### command_abc.py ###
There are two types of command that the Gilson expects: a Buffered command and an Immediate command. In 
general, a buffered command involves robotics whereas an immediate command involves reading statuses.

All immediate commands are all a single character long, buffered commands are multiple characters long.

Immediate commands may generate a response message from the device, buffered commands will not.

### direct_inject_codex.py ###
Not implemented. The codex is kept here if you, brave coder, would like to implement a Gilson injector module.

### gx241_codex.py ###
This is the codex for the liquid handler arm.  All the classes present in this file correspond to either
a Buffered or Immediate command that the device supports.

All immediate commands will define a command character ```cmd_str``` (named for harmony with Buffered commands) 
as an attribute. Immediate commands may also have a ```rsp_fmt``` attribute (response format) which documents
the expected format of the device's response message.
All buffered commands will define a command string ```cmd_str``` as a property. The property syntax is used 
because the content of the command string changes (e.g., move to x position 100 vs move to x position 90 are 
"X100" and "X90", respectively).  The attribute cmd_str at the top of each buffered command class is there
for documentation purposes (showing the overall format of the command strig as specified in the manual) 
and is not used (the Property is used instead of the Attribute).

### pump_codex.py ###
This file is analogous to the gx241_codex.py file but for the Verity pump that the Gilson liquid handler 
connects to and controls.