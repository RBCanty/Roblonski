from collections import namedtuple
from typing import Iterable

from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import AspiratePipettingSpec, AirGap, ComponentSpec, DispensePipettingSpec
from workflows.common_macros import prime, clean_up

# Based on the previous example, one can imagine how, if we wanted to repeat this procedure for each row,
#   it would be tedious to implement.  In this tutorial, we will transform the general workflow in tutorial_5.py into
#   something that can be re-used.

# Let's look at the code from tutorial_5.py

# def short_version_of_tutorial_5():
#     glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
#     glh.load_bed(
#         directory=r"C:/Users/User/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
#         bed_file="Gilson_Bed.bed"
#     )
#
#     waste = glh.locate_position_name('waste', "A1")
#     v_a1 = glh.locate_position_name("pos_1_rack", "A1")
#     v_a2 = glh.locate_position_name("pos_1_rack", "A2")
#     v_a3 = glh.locate_position_name("pos_1_rack", "A3")
#     air_gap = 10
#     transfer = 100
#
#     prime(glh, waste)
#     glh.chain_pipette(
#         AspiratePipettingSpec(component=ComponentSpec(position=v_a1, volume=transfer)),
#         AspiratePipettingSpec(component=AirGap(volume=air_gap)),
#         DispensePipettingSpec(component=ComponentSpec(position=v_a3, volume=air_gap + transfer)),
#         AspiratePipettingSpec(component=ComponentSpec(position=v_a2, volume=transfer)),
#         AspiratePipettingSpec(component=AirGap(volume=air_gap)),
#         DispensePipettingSpec(component=ComponentSpec(position=v_a3, volume=air_gap + transfer)),
#     )
#     clean_up(glh, waste)

# Connecting to the liquid handler, defining the bed, and some of the locations are consistent regardless of which
#   row we are operating on.  This leaves

# def the_parts_that_could_change():
#     v_a1 = glh.locate_position_name("pos_1_rack", "A1")
#     v_a2 = glh.locate_position_name("pos_1_rack", "A2")
#     v_a3 = glh.locate_position_name("pos_1_rack", "A3")
#     air_gap = 10
#     transfer = 100
#
#     glh.chain_pipette(
#         AspiratePipettingSpec(component=ComponentSpec(position=v_a1, volume=transfer)),
#         AspiratePipettingSpec(component=AirGap(volume=air_gap)),
#         DispensePipettingSpec(component=ComponentSpec(position=v_a3, volume=air_gap + transfer)),
#         AspiratePipettingSpec(component=ComponentSpec(position=v_a2, volume=transfer)),
#         AspiratePipettingSpec(component=AirGap(volume=air_gap)),
#         DispensePipettingSpec(component=ComponentSpec(position=v_a3, volume=air_gap + transfer)),
#     )

# We can take this, and turn it into its own method. Anything missing (like glh) or that could change (like "A1") should
# be replaced by an argument to the method:

def two_to_one_transfer(glh: Gilson241LiquidHandler,
                        source_1: str,
                        source_2: str,
                        destination: str,
                        transfer_volume: float,
                        air_gap: float = 10):
    src_1 = glh.locate_position_name("pos_1_rack", source_1)
    src_2 = glh.locate_position_name("pos_1_rack", source_2)
    dest = glh.locate_position_name("pos_1_rack", destination)
    # Observations:
    # - This is locked into the pos_1_rack rack
    # - The volume transferred has to be the same for the two sources
    # - There can only be exactly two sources
    # We can address these problems after this example.

    glh.chain_pipette(
        AspiratePipettingSpec(component=ComponentSpec(position=src_1, volume=transfer_volume)),
        AspiratePipettingSpec(component=AirGap(volume=air_gap)),
        DispensePipettingSpec(component=ComponentSpec(position=dest, volume=air_gap + transfer_volume)),
        AspiratePipettingSpec(component=ComponentSpec(position=src_2, volume=transfer_volume)),
        AspiratePipettingSpec(component=AirGap(volume=air_gap)),
        DispensePipettingSpec(component=ComponentSpec(position=dest, volume=air_gap + transfer_volume)),
    )

# This method can then be used:
def example_use():
    # Imagine this were in the Main block
    # (It's not, because this will not be how we want to do this)
    lh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    lh.load_bed(
        directory=r"C:/Users/User/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )

    # Define convenience variables
    waste = lh.locate_position_name('waste', "A1")
    prime(lh, waste)
    two_to_one_transfer(lh, "A1", "A2", "A3", 100, 10)
    two_to_one_transfer(lh, "B1", "B2", "B3", 200, 10)
    two_to_one_transfer(lh, "C1", "C2", "C3", 50, 10)
    two_to_one_transfer(lh, "D1", "D2", "D3", 150, 10)
    two_to_one_transfer(lh, "E1", "E2", "E3", 100, 10)
    clean_up(lh, waste)

# While this is certainly easier to read and write than having all those lines of code repeated with minor changes
#   between each copy, it's still leaves something to be desired.
# Wouldn't it be nice to be able to specify, almost like a table:
#
# Row | rack.src_vial & volume |  ...other sources...  | rack.destination vial |
# 1   | "pos_1_rack" "A1" 100  | "pos_1_rack" "A2" 200 | "pos_1_rack" "A3"     |
# 2   | "pos_1_rack" "B1" 300  | ...                   | "pos_1_rack" "B3"     |
# 3   | "pos_1_rack" "C1" 150  | "pos_1_rack" "D1" 150 | "pos_1_rack" "C2"     |
# 4   | ...                    | ...                   | ...                   |
# ... | ...                    | ...                   | ...                   |
#
# Then just say:
# Run(that table)
# ?

# To help keep track of all that data, we can organize it into pieces:
# Sources require: a rack, a vial, and a volume
# Destinations require: a rack and a vial
# The table has some number of Sources and one Destination (per row)
# To help with this, we will use the `namedtuple`, which is just a convenient way to organize data.
# Like a tuple, it has values and cannot be changed, but unlike a tuple (which addresses its contents with a number),
#   a namedtuple can do so with the names. In addition, the namedtuple lets us create a new data structure without
#   having to even write out an __init__() method!  (It takes care of building all of that for us)

class SourceSpec(namedtuple):
    rack: str
    vial: str
    volume: float

class DestinationSpec(namedtuple):
    rack: str
    vial: str

class TransferSpecificationRow(namedtuple):
    sources: Iterable[SourceSpec]  # <-- Iterable[SourceSpec] Is a type-hint that means that `sources` will be
                                   # something which can not only contain multiple SourceSpecs, but that we will
                                   # be able to iterate over each of the SourceSpecs (in order) using a FOR loop.
    destination: DestinationSpec

# We don't need to actually make a "table" per se (we can just use a List of TransferSpecificationRow objects)

# With these to help organize the inputs and the use of a FOR loop, we can make a general method:
# This performs the transfer specified by a single Row, we can then call this method for each row.
def many_to_one_transfer(glh: Gilson241LiquidHandler,
                         transfers: TransferSpecificationRow,
                         air_gap: float = 10):
    dest = glh.locate_position_name(transfers.destination.rack, transfers.destination.vial)

    for source_spec in transfers.sources:
        source = glh.locate_position_name(source_spec.rack, source_spec.vial)
        glh.chain_pipette(
            AspiratePipettingSpec(component=ComponentSpec(position=source, volume=source_spec.volume)),
            AspiratePipettingSpec(component=AirGap(volume=air_gap)),
            DispensePipettingSpec(component=ComponentSpec(position=dest, volume=air_gap + source_spec.volume)),
        )
    # Details that are easy to miss:
    # If the row specifies NO source vials, this method will simply return (exit) without doing anything.
    # This code has no protections for what happens if the `volume` is bad (negative or zero).
    # ((Technically, the underlying code will try to catch these errors, but that's the backup safety net))
    # In addition, there are no protections for if the location is bad (the rack or vial is not valid).

    # Given how it is still possible that a volume is negative or zero, to improve the safety of this
    #   method we could add the following code to the FOR loop:
    # for source_spec in transfers.sources:
    #     if source_spec.volume <= 0:  # NEW CODE: check to make sure the volume is positive and not zero
    #         continue                 # NEW CODE: skip ahead to the next source_spec in transfers.sources
    #                                  #           without running any of the following code in the FOR loop
    #     source = glh.locate_position_name(source_spec.rack, source_spec.vial)
    #     glh.chain_pipette(
    #         AspiratePipettingSpec(component=ComponentSpec(position=source, volume=source_spec.volume)),
    #         AspiratePipettingSpec(component=AirGap(volume=air_gap)),
    #         DispensePipettingSpec(component=ComponentSpec(position=dest, volume=air_gap + source_spec.volume)),
    #     )
    # Doing so would mean that the method ignores any items in the table where the transfer volume is invalid.

    # (!) But what if I want to be alerted that the volumes specified were bad instead of having the program ignore it?
    #     Or what if I don't want it running any rows with a bad volume specification?
    # That can also be done:
    # for source_spec in transfers.sources:                                            # NEW CODE: Check all values first
    #     if source_spec.volume <= 0:                                                  # NEW CODE
    #         raise ValueError(f"Nonphysical volume specified: {source_spec.volume}")  # NEW CODE
    # # We can FOR-loop over the same thing multiple times.
    # for source_spec in transfers.sources:
    #     source = glh.locate_position_name(source_spec.rack, source_spec.vial)
    #     glh.chain_pipette(
    #         AspiratePipettingSpec(component=ComponentSpec(position=source, volume=source_spec.volume)),
    #         AspiratePipettingSpec(component=AirGap(volume=air_gap)),
    #         DispensePipettingSpec(component=ComponentSpec(position=dest, volume=air_gap + source_spec.volume)),
    #     )
    # This version will prevent the entire row from being executed if a single entry in that row has a bad volume.
    #   By raising and Exception, however, the caller (the method `example()` in the Main block below) should
    #   use a `try: ... except: ...` construction to handle the ValueError (or else the entire program will stop
    #   when a bad volume is encountered).


if __name__ == '__main__':
    def example():
        glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
        glh.load_bed(
            directory=r"C:/Users/User/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
            bed_file="Gilson_Bed.bed"
        )

        # Define convenience variables
        waste = glh.locate_position_name('waste', "A1")

        # Make our table:
        # Each row will be used to show that we can change experimental parameters freely.
        transfers_table: list[TransferSpecificationRow] = [
            TransferSpecificationRow(  # Row 1, the familiar example
                [
                    SourceSpec("rack_1_pos", "A1", 100),
                    SourceSpec("rack_1_pos", "A2", 100),
                ],
                DestinationSpec("rack_1_pos", "A3")
            ),
            TransferSpecificationRow(  # Row 2, we can change the volume per source
                [
                    SourceSpec("rack_1_pos", "B1", 125),
                    SourceSpec("rack_1_pos", "B2", 175),
                ],
                DestinationSpec("rack_1_pos", "B3")
            ),
            TransferSpecificationRow(  # Row 3, we can change which rack is used
                [
                    SourceSpec("rack_2_pos", "A1", 100),
                    SourceSpec("rack_1_pos", "A2", 100),
                ],
                DestinationSpec("rack_1_pos", "C1")
            ),
            TransferSpecificationRow(  # Row 4, we can change how many sources there are
                [
                    SourceSpec("rack_1_pos", "D1", 75),
                    SourceSpec("rack_1_pos", "D2", 100),
                    SourceSpec("rack_1_pos", "D3", 125),
                ],
                DestinationSpec("rack_1_pos", "C2")
            )
        ]

        prime(glh, waste)
        # Then the method can be called in a For loop, iterating over each row
        for transfer in transfers_table:
            many_to_one_transfer(glh, transfer, 10)
        clean_up(glh, waste)

    # TODO: Update the path to the bed file. Once done, uncomment the following line (remove the leading "# ")
    #   to execute this example (Depending on your deck layout, you may need to change 'rack_2_pos' to 'rack_1_pos'):
    # example()

    # At this point, beyond how to manage the spectrometer measurement and data, the basis for how all the demonstrated
    # workflows in the workflows folder has been explained.

    #
