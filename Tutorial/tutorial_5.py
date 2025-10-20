# In this tutorial, we will go through turning a checklist into a program.

# If a comment will span multiple lines, triple quotes can be used instead of putting a '#' at the start of each line.
#   This works anywhere except under a variable, method, or object declaration (as Python will think that the text
#   is actually a description of the variable, method, or object.

"""
Let's say we have a liquid handler, and three vials.
We would like to have the liquid handler take 100 uL from the first two vials (each) and deposit these volumes into the
third vial.

If we load these vials into positions A1 (source), A2 (source), and A3 (destination), then our steps would be:
1) Aspirate 100 uL from A1
2) Dispense 100 uL into A3
3) Aspirate 100 uL form A2
4) Dispense 100 uL into A3

Great.
However, in order to aspirate and dispense, we need to first connect to the liquid handler. In addition, in order
to refer to our samples by the name A1, A2, and A3, we need to load the deck layout into the liquid handler.

1) Connect to Liquid Handler
2) Load in the current deck layout
3) Aspirate 100 uL from A1
4) Dispense 100 uL into A3
5) Aspirate 100 uL form A2
6) Dispense 100 uL into A3

In addition, we would probably want to prime the system before running these steps and clean up the needle afterwards
as well.

1) Connect to Liquid Handler
2) Load in the current deck layout
3) Prime liquid handler
4) Aspirate 100 uL from A1
5) Dispense 100 uL into A3
6) Aspirate 100 uL form A2
7) Dispense 100 uL into A3
8) Clean up

While this would be sufficient, when performing transfers on a liquid handler, it is a good idea to take a small
air gap to ensure that the contents of the needle do not drip out during movement.

1) Connect to Liquid Handler
2) Load in the current deck layout
3) Prime liquid handler
4) Aspirate 100 uL from A1
5) Take a small airgap
6) Dispense 100 uL into A3
7) Aspirate 100 uL form A2
8) Take a small airgap
9) Dispense 100 uL into A3
10) Clean up

This should be enough to start writing a program in Python.
"""
# Set-up: Import the necessary tools from other python files in the code repository.
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import AspiratePipettingSpec, AirGap, ComponentSpec, DispensePipettingSpec, Comment
from workflows.common_macros import prime, clean_up
# When files are organized by folders, the dot notation is used to reflect that organization. For example,
# `from liquid_handling.gilson_handler` directs to the file 'gilson_handler.py' located in the folder 'liquid_handling'.

# All the methods we need are already provided by the imports, so no additional methods need to be created

# Let's go through the steps defined above:
# As a quick note, if you are using an IDE (e.g, PyCharm), if you hover your cursor over something, any notes provided
#   will appear in a small tool-tip.  Try hovering over `Gilson241LiquidHandler` or `prime`. You can click on the
#   pencil in the bottom right of the tool-tip to view the code behind it as well.
if __name__ == '__main__':
    # Step 1: Connect to Liquid Handler                                                                         Step 1 #
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    # The creation of a Gilson241LiquidHandler object will take care of connecting to the liquid handler
    # We save this object to `glh` (a variable) as this will be our handle for using the liquid handler later

    # Step 2: Load in the current deck layout                                                                   Step 2 #
    # TODO: Please replace the example path the location of your deck layout folder and bed file
    glh.load_bed(
        directory=r"C:/Users/User/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    # If your bed file does not contain a 'syringe_volume_uL' parameter, then the liquid handler's pump volume can be
    #   set manually using:
    # glh.set_pump_to_volume(1_000)

    # Adjustment
    # The prime and cleanup steps will need to know the waste location.
    # It is perfectly acceptable to just say:
    #   prime(glh, glh.locate_position_name('waste', "A1"))
    #   clean_up(glh, glh.locate_position_name('waste', "A1"))
    # But to make things easier to read, we can create a variable, waste, which stores this location
    waste_location = glh.locate_position_name('waste', "A1")

    # Step 3: Prime liquid handler                                                                              Step 3 #
    prime(glh, waste_location)

    # Adjustment
    # Steps 4-9 also use locations and volume pretty consistently
    # While we could enter these numbers/locations in full as needed, again we can make things a bit more readable by
    #   defining some variables
    source_vial_1 = glh.locate_position_name("pos_1_rack", "A1")
    source_vial_2 = glh.locate_position_name("pos_1_rack", "A2")
    sample_vial = glh.locate_position_name("pos_1_rack", "A3")
    air_gap_volume = 10
    transfer_volume = 100

    # Steps 4-9: In these steps, 100 uL of sample are transferred from A1 and A2 into A3 (using an airgap).
    # This code base provides two ways for accomplishing these kinds of tasks
    # Option A (Demonstrated on Steps 4, 5, and 6): Directly calling the liquid handler for each step:
    print("Transferring 100 uL from A1 to A3")                                                             # Steps 4-6 #
    glh.aspirate(ComponentSpec(position=source_vial_1, volume=transfer_volume), DEFAULT_SYRINGE_FLOWRATE)
    glh.aspirate(AirGap(volume=air_gap_volume), DEFAULT_SYRINGE_FLOWRATE)
    glh.dispense(ComponentSpec(position=sample_vial, volume=air_gap_volume + transfer_volume), DEFAULT_SYRINGE_FLOWRATE)
    # Option B (Demonstrated on Steps 7, 8, and 9): Create a list of operations, then have the liquid handler run them
    #   in order:
    transfer_operations = [                                                                                # Steps 7-9 #
        Comment("Transferring 100 uL from A2 to A3"),
        AspiratePipettingSpec(component=ComponentSpec(position=source_vial_2, volume=transfer_volume)),
        AspiratePipettingSpec(component=AirGap(volume=air_gap_volume)),
        DispensePipettingSpec(component=ComponentSpec(position=sample_vial, volume=air_gap_volume + transfer_volume)),
    ]
    glh.chain_pipette(*transfer_operations)
    # Option A is simpler and allows for more precise debugging if there's an error.
    # Option B can be quite powerful as the list can be built up, piece by piece, until it represents a complex workflow
    # Note: When expressions use []s or ()s, you can often break them out into separate lines if it helps
    # with legibility. For example, the following is still valid Python syntax:
    # DispensePipettingSpec(
    #     component=ComponentSpec(
    #         position=sample_vial,
    #         volume=air_gap_volume + transfer_volume
    #     )
    # )

    # Step 10: Clean up                                                                                        Step 10 #
    clean_up(glh, waste_location)

    # Since the above has quite a lot of comments for explanation, to show how directly the checklist translated
    # into code, see the following (note, the names of variables had to be changed to avoid naming conflicts)
    def example_without_comments():
        # Steps 1 & 2
        lh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
        lh.load_bed(
            directory=r"C:/Users/User/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
            bed_file="Gilson_Bed.bed"
        )

        # Define convenience variables
        waste = lh.locate_position_name('waste', "A1")
        v_a1 = lh.locate_position_name("pos_1_rack", "A1")
        v_a2 = lh.locate_position_name("pos_1_rack", "A2")
        v_a3 = lh.locate_position_name("pos_1_rack", "A3")
        air_gap = 10
        transfer = 100

        # Step 3
        prime(lh, waste)

        # Steps 4-9:
        lh.chain_pipette(
            AspiratePipettingSpec(component=ComponentSpec(position=v_a1, volume=transfer)),
            AspiratePipettingSpec(component=AirGap(volume=air_gap)),
            DispensePipettingSpec(component=ComponentSpec(position=v_a3, volume=air_gap + transfer)),
            AspiratePipettingSpec(component=ComponentSpec(position=v_a2, volume=transfer)),
            AspiratePipettingSpec(component=AirGap(volume=air_gap)),
            DispensePipettingSpec(component=ComponentSpec(position=v_a3, volume=air_gap + transfer)),
        )
        # Step 10
        clean_up(lh, waste)

# Post Note: This example does not include doing any measurements. This requires connecting to the spectrometers,
#   defining how measurements are to be carried out, and defining how to handle/save the data. This complexity will
#   be addressed in a later tutorial.
