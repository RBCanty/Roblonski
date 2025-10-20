from contextlib import redirect_stdout
from io import StringIO
from typing import NamedTuple

from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE, SYSTEM_AIR_GAP
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import AspiratePipettingSpec, DispensePipettingSpec, UserIntervention
from liquid_handling.liquid_handling_specification import ComponentSpec, TipExitMethod


class ExperimentSpecification(NamedTuple):
    n_iterations: int
    transfer_volume: int | float
    free_dispense: bool
    tip_exit_method: TipExitMethod


def one_transfer_step(volume_size: int | float, free_dispense: bool, exit_method: TipExitMethod):
    glh.chain_pipette(
        AspiratePipettingSpec(
            component=ComponentSpec(position=RESERVOIR, volume=volume_size)
        ),
        DispensePipettingSpec(
            component=ComponentSpec(position=CONTAINER, volume=volume_size),
            free_dispense=free_dispense,
            tip_exit_method=exit_method
        ),
        UserIntervention(
            title="Check Mass",
            prompt="Please record the mass of the CONTAINER vial",
            home_arm=True
        )
    )


def transfer_experiment(design: ExperimentSpecification, verbose: bool):
    n_iterations = design.n_iterations
    volume_size = design.transfer_volume
    free_dispense = design.free_dispense
    exit_method = design.tip_exit_method

    for iteration in range(n_iterations):
        print(f"\tSTEP::{iteration + 1}")
        with redirect_stdout(StringIO()) as sub_stream:
            one_transfer_step(volume_size, free_dispense, exit_method)
        if verbose:
            print(sub_stream.getvalue())


def transfer_campaign(*designs: ExperimentSpecification, verbose: bool = False):
    for design in designs:
        print(f"Running {design.n_iterations} iterations of {design.transfer_volume} uL")
        transfer_experiment(design, verbose)


if __name__ == '__main__':
    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/Graviometric_Deck",
        bed_file="Gilson_Bed.bed"
    )

    glh.set_pump_to_volume(1_000)

    RESERVOIR = glh.locate_position_name("pos_1_rack", "H2")
    CONTAINER = glh.locate_position_name("pos_1_rack", "H3")
    WASTE = glh.locate_position_name('waste', "A1")

    glh.dispense_all(WASTE)
    glh.aspirate_from_reservoir(200, DEFAULT_SYRINGE_FLOWRATE)
    glh.dispense_to_curr_pos(200, DEFAULT_SYRINGE_FLOWRATE)
    glh.aspirate_from_curr_pos(SYSTEM_AIR_GAP, DEFAULT_SYRINGE_FLOWRATE)

    input(f"Make sure to measure the initial mass! (Press enter to continue)")
    # test_volumes = [20.0, 19.6, 18.8, 17.8, 16.4, 14.8, 13.1, 11.2, 9.3, 7.4, 5.7, 4.1, 2.7, 1.7, 0.9, 0.5]
    # test_volumes = [20, 30, 40, 50]
    test_volumes = [0.5, 0.1]  # [0.1, 0.5, 1, 2.5, 5, 7.5, 10, 15, 20, 50]
    for _volume in test_volumes:
        transfer_campaign(
            ExperimentSpecification(
                n_iterations=5,
                transfer_volume=_volume,
                free_dispense=False,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            ),
            verbose=False
        )

    glh.dispense_all(WASTE)
    glh.home_arm()
