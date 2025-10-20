## Overview ##
These files specify how the liquid handler locates items and positions on the liquid handling bed.
The files are in hierarchical ordering rather than alphabetic.

### Modifications to make before you run ###
In rack.py, there are three parameters which may need to be adjusted depending on your setup:
- ```CANNULA_DIAMETER_MM```: (Our value: 1.44 mm) This is the diameter of the cannula/needle on the liquid 
       handler.
- ```DEFAULT_SAFE_Z_TRAVEL_OFFSET``` (Our value: 5 mm) Any travel operation will add this to the calculated 
       Z-height to ensure the cannula/needle can safely pass over items.
- ```DEFAULT_SAFE_Z_PIPETTE_OFFSET``` (Our value: 1 mm) Aspirations and dispenses at the "bottom" of the well 
       will be located this distance above the calcualted position to ensure the cannula/needle does not hit 
       the bottom of the vial.

In handler_bed.py there are a set of parameters (variables with ALLCAPS names at the top of the file) 
which may need to be adjusted to match your platform.
- ```MAX_Z_HEIGHT```: (Our value 125 mm) The maximum value that a Z-height move operation can take
- ```MAX_SYRINGE_VOL```: (Our value: 1000 uL) The volume of the syringe pump.
- ```SYSTEM_AIR_GAP```: (Our value: 20 uL) The default airgap between the system fluid and any liquid taken into 
    the cannula.
- ```DEFAULT_SYRINGE_FLOWRATE```: (Our value: 1.0 mL/min) The default flow rate to use during liquid handling.
- ```PRIMING_FLOWRATE```: (Our value: 5 mL/min) The default flow rate to use when priming/cleaning the cannula.
- ```DEFAULT_XY_SPEED```: (Our value: 50 mm/s) The default speed for moving the arm in the XY plane
- ```DEFAULT_Z_SPEED```: (Our value: 25 mm/s) The default speed for moving the cannula up/down
- ```DEFAULT_WASTE_LOC```: (Our value: Coordinate(Point2D(100, 100), 90)) \[Unlike the other parameters which are
    located at the top of the file, this is located at the bottom of the file--because it uses a Coordinate
    object which is defined in this file.\]  This is a XYZ coordinate defining a default location for where
    to perform priming/discarding operations in the absence of a Deck configuration.

In addition, you will need to define a Deck Layout Directory (see below). (This is optional if you are okay
with addressing all positions by XYZ coordinates; however, this is not recommended as it will be tedious).
This Directory determines which items the code thinks are present. If a location is referenced without there
being an associated rack and vial file, then the code will halt with an error that there is no resource there.
While this is intended as a safety feature (different Deck Layout Directories can be used to represent different
deck layouts for different projects), it can be annoying during method development when you want to jump to any
and all positions. For this reason, in vial.py a method, ```sandbox()``` is provided. Fill out the 
parameters in the function, then run the sandbox() method. This will create a vial file for every vial for 
that rack in the corresponding rack_vial directory.

### Deck Layout Directory Format ###
A handler bed will be a directory on the host computer of the form:\
Note the names of the rack can be anything provided that the name of the *.rak file
matches the name of the associated directory (e.g., "name.rak" --> "name_vials\\". \
The names of the vials must be of the form f"vial_{ID}.vil" where ID is a standard "A1", "A2", "H12", "AB99"
-style name (A sequence of letters followed by a sequence of numbers). \
The name of the bed file can be anything provided it is the name given to ```load_from_file()```. 

```
RootDirectory\
├─ g241_deck.bed
├─ main_rack.rak
├─ wash_rack.rak
├─ resources_cfg.json  # This is not required and will be generated automatically if HandlerBed.write_resource_cfg() is ever called. Do not make and empty file with this name.
├─ main_rack_vials\
│  ├─ vial_A1.vil
│  ├─ vial_A2.vil
│  ├─ vial_B1.vil
│  └─ vial_B3.vil
└─ wash_rack_vials\
   ├─ vial_A1.vil
   └─ vial_A2.vil
```


## File Descriptions ##

### coordinates.py ###
This file encodes points in 1 to 3 dimensions. (Sc. this code was created before it was known exactly how
points in space would be encoded. Ultimately, the 2D point was selected to isolate Z-travel \[up/down\] from 
the XY coordinates on the liquid handler bed.). Ultimately only the ```Point2D``` class is of relevance;
however, it is described in an abstract manner in by repeatedly extending the ```_Point``` class in a manner
that while I, the coder, find really satisfying, I recognize is not easily readable to someone new to Python.
Fortunately, the Point2D class can be summarized as: It is a pair of values, x and y, which can be 
added/subtracted with other Point2D objects (element-wise). (x1, y1) + (x2, y2) = (x1+x2, y1+y2).

### vial.py ###
A ```Vial``` object encodes five key parameters about the vial's geometry. Of importance here is that a "vial"
is simply the vessel containing a liquid (it can, in practice, be a well, bottle, trough, etc.). They key 
values are:
- access_height: The distance between the base of the container and the highest point (in mm).
- base_offset: The thickness of the base of the container  (in mm).
- volumetric_height: \[See Note 1\] The distance between the (internal) bottom of the container and highest 
    point before which the cross-sectional area of the container changes (often the bottom of a vial to its 
    neck)  (in mm).
- volumetric_diameter: \[1\] The diameter of the container throughout the span of volumetric_height (in mm). 
- access_diameter: The diameter of the container at its highest point (in mm).
- meta_data: (Optional) A dictionary of whatever additional information you wish to store about the vial.

Note 1: While included and required, these parameters were intended for having the needle move up/down with
the changing liquid level for improved pipetting performance with a liquid-level detection. Liquid-level 
detection, while possible, was never implemented in this application. As such, these values are not used
anywhere, and can be given dummy values (0 is recommended).

A corresponding vial (*.vil) file is to be structured in JSON format (example below):
```JSON
{
  "access_height": 30,
  "base_offset": 1,
  "volumetric_height": 25,
  "volumetric_diameter": 0,
  "access_diameter": 10,
  "meta_data": {
    "Type": "GC Vial (Part No. ###)",
    "cap": false
  }
}
```
Additional note because JSON has a pesky detail. If the meta_data parameter is removed, the trailing 
comma after the access_diameter value must also be removed (alt. the last parameter in a JSON file
cannot have a trailing comma):
```JSON
{
  "access_height": 23.7,
  "base_offset": 1.1,
  "volumetric_height": 23.7,
  "volumetric_diameter": 21.7,
  "access_diameter": 21.7
}
```
**Recommendation if using a well plate:**
- access_height: The depth of the well in mm.
- base_offset: 0.
- volumetric_height: 0 (see Note 1 above).
- volumetric_diameter: 0 (see Note 1 above). 
- access_diameter: The diameter at the top of the well in mm.

Then in the Rack file (see below), set all parameters normally with the exception(s) of:
- base_z_height:  The distance between the base of the well plate and the bottom of each well (in mm).
- travel_z_height: The distance between the base of the well plate and the highest point on the plate (in mm).
    Most well plates do not have features extending above the tops of each well, so travel_z_height is likely
    just the thickness of the well plate. But if there are any protrusions which could collide with the needle
    if the needle were moving just above each well, then include their height in this parameter.

### rack.py ###
This file specifies the ```Rack``` class. A Rack is any gird of point which contain ```Vial```s.  Again, it will
be noted that while a Rack must be in a rectangular-grid configuration, the objects located on a Rack do not 
have to be vials (they can be bottles, wells, troughs, etc.). In fact, a Rack need not be a rack at all,
a bare bottle located on the liquid handler deck is encoded as a vial in a rack where the rack has no dimensions.
(This is how the wash and waste locations are specified in the published work).

A Rack object encodes its geometry. By using the data in itself and in each vial file, it can provide
the XY positions of each vial as addressed by a (Row-Letter)(Column-Number) ID: both the center of the vial
as well as the vial's internal edge position. In addition, three Z-heights will be provided: a safe travel height, 
an access height for each vial, and an aspirate/dispense height at the bottom of each vial. The key values are:

- origin_x: The X coordinate of the center of vial A1 on this rack (in mm).
- origin_y: The Y coordinate of the center of vial A1 on this rack (in mm).
- rack_pos_x_spacing: The center-to-center spacing of vials in the X axis (in mm).
- rack_pos_y_spacing: The center-to-center spacing of vials in the Y axis (in mm).
- num_rows: The number of rows on the rack (a row is a single Y coordinate spanning multiple X values) (in mm).
- num_cols: The number of columns on the rack (a column is a single X coordinate spanning multiple Y values) (in mm).
- base_z_height: The distance between the base of the rack and the surface on which vials rest (in mm).
- travel_z_height: The distance between the base of the rack and the highest point on the rack (in mm).
- meta_data: (Optional) A dictionary of whatever additional information you wish to store about the vial.

If using a well plate, see the vial.py section above for our recommendation.

A corresponding rack (*.rak) file is to be structured in JSON format (example below):
```JSON
{
  "rack_pos_x_spacing": 18,
  "rack_pos_y_spacing": 12.8125,
  "num_rows": 16,
  "num_cols": 4,
  "base_z_height": 82,
  "origin_x": 8,
  "origin_y": 248,
  "travel_z_height": 115
}
```

Additional notes:
- If a physical rack has multiple sections for multiple different vial types, treat this one physical object
    as multiple Rack objects. The sole exception is the improbable case where the center-to-center spacing
    of the vials remains unchanged.
- A triangular-gird rack can be emulated by using two racks (for the two rectangular-grid subsets of the
    triangular grid)
- It is possible to have the platform perform aspiration/dispensing to phases in a multiphase liquid if
    the height of the lower phase is known a priori and consistent across vials in a rack by duplicating
    the rack (where the vial files in the upper phase have had their base_offset increased by the height of
    the lower liquid phase + some adjustment to avoid pipetting at the liquid-liquid interface).

### handler_bed.py ###
A ```HandlerBed``` is used to define the arrangement of racks on the liquid handler deck.  A HandlerBed should
be created with the ```load_from_file()``` method rather than a direct call to the ```__init__()``` method.
The primary function of a HandlerBed is to locate racks and vials on the liquid handler deck and to bound all
movements within the accessible range of the platform to avoid any motor hitting a limit.

When loading from a file, the *.bed file is a JSON file of the following form:
```JSON
{
  "x_bounds": [1, 162],
  "y_bounds": [1, 249],
  "z_bounds": [1, 125]
}
```
The values presented are lower (left) and upper (right) bounds for each axis. These should be the last coordinate
value before the liquid handler encounters and error. If the manual says that the liquid handler can move between
Z values of 0 and 126, then use 1 and 125. Note that even if a coordinate is technically valid, it is possible 
for the inertia of the arm to bring it ~1 mm further, which will put the system into an error state.

The HandlerBed also manages an optional resources file. This file can be specified by the user but will
default to "./resources_cfg.json" relative to the directory where the *.bed file is located. If the HandlerBed
object was not created with a *.bed file, this functionality is ignored.  The resource file is a JSON
object which will support any key-value pairs the user wishes to place there.  The 
```update_resource_cfg_value()``` method can be used to update the values and add key-value pairs during 
operation. These values will be persistent in this file and will be saved between instances of the code being
executed. By default, whenever the platform aspirates from its reservoir, a 'system_fluid_volume_mL' key will 
have its value decremented by the volume aspirated. This is intended to provide a functionality whereby the 
platform can be aware if it has run out of system fluid and stop a long campaign before running dry.

**Placeables**\
This pythong file also defines the Placeable abstraction. Any location on the liquid handler bed is represented
as a Placeable object. (Locatable would have been a good alternate name for this). All Placeable objects
can provide the XY or Z coordinates of their center, their access point, their transfer point, and their edge.
(These are often the locations provided by a Rack object). There are subtypes of Placeable: A Coordinate
defines these positions with numerical values for the XYZ coordinates, a NamePlace defines these locations
with a rack name and a vial ID, and a ShiftingPlaceable allows for multiple Placeable objects to be grouped 
together but treated as one Placeable object (this can provide a means for defining a series of vials for a 
resource, then moving between them at a pace irrespective of the iteration of experiments; such as a set of 
solvent reservoirs which can be freely switched between as each is used up--combined with the resource file, 
ShiftingPlaceable objects can be quite powerful). 

### pprint_rack.py ###
This is included for purely aesthetic reasons and can (should) be ignored. This code will inspect all the
vials on a rack when a rack is loaded in from its file and then print a summary of the rack's vial 
configuration to the console during startup.  This provides a quick way of knowing which racks and vials
the platform thinks are currently present.  The ~160 lines of code are for the weird math of saying:
"If Rack 1 uses vials A1, A2, A3, A4, B1, B2, B3, B4, C1, E2, E3, and E4, then I want it to summarize this info
as something like 'Rack 1 is using vials A1:B4, C1, and E2:E4'". The name is taken from the pprint python 
module which prints objects like dictionaries in a much prettier (pretty print --> pprint) format than
normal python.
