from aux_devices.ocean_optics_spectrometer import LightSource, SpectrometerSystem, OpticalSpecs
from aux_devices.spectra import ZipSpectra
from deck_layout.handler_bed import DEFAULT_SYRINGE_FLOWRATE
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import AspiratePipettingSpec, DispensePipettingSpec, MixingSpec
from liquid_handling.liquid_handling_specification import ComponentSpec, AirGap, TipExitMethod
from liquid_handling.liquid_handling_specification import ExternalWash, Comment
from workflows.common_abstractions import Dilution, Volumetric
from workflows.common_macros import prime, clean_up, inter_clean, volume_to_center_droplet
from misc_func import safe_project_dir


def core_loop(iteration: int, total_volume: int | float, n_dilutions: int, dilution: Dilution):
    replaced_volume = dilution.get_volume(total_volume)
    back_air_gap = 20
    front_air_gap = 10

    print(f"On iteration {iteration}")
    glh.aspirate(AirGap(volume=back_air_gap), DEFAULT_SYRINGE_FLOWRATE)
    glh.aspirate(ComponentSpec(position=DYE, volume=total_volume), DEFAULT_SYRINGE_FLOWRATE, tip_method=TipExitMethod.TIP_TOUCH)
    glh.aspirate(AirGap(volume=front_air_gap), DEFAULT_SYRINGE_FLOWRATE)
    measure_absorbance(total_volume, front_air_gap, template, f"{iteration}_{0}", 1)

    for dil_dx in range(n_dilutions):
        glh.chain_pipette(
            Comment(message=f"Dilution step {dil_dx+1}"),
            DispensePipettingSpec(
                component=ComponentSpec(position=WASTE, volume=front_air_gap + replaced_volume),
                free_dispense=True,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            ),
            ExternalWash(
                positions=EX_WASH,
                air_gap=AspiratePipettingSpec(
                    component=AirGap(position=EX_WASH, volume=front_air_gap)
                ),
                tip_exit_method=TipExitMethod.DRAG,
                n_iter=2
            ),
            AspiratePipettingSpec(
                component=ComponentSpec(position=DILUENT, volume=replaced_volume)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=front_air_gap)
            ),
            MixingSpec(
                mixing_displacement=2.0 * total_volume,
                rate=2 * DEFAULT_SYRINGE_FLOWRATE,
                n_iterations=3
            )
        )
        net_fraction = (1 - (replaced_volume / total_volume)) ** (dil_dx + 1)
        measure_absorbance(total_volume, front_air_gap, template, f"{iteration}_{dil_dx + 1}", net_fraction)


def measure_absorbance(droplet_volume: int | float, front_airgap: int | float, save_to_template: str, save_iter: int | str, frac: float):
    my_spec.measure_average_reference(**abs_opt_specs, light="dark", mode="abs")
    my_spec.measure_average_reference(**abs_opt_specs, light="light", mode="abs")

    _move = volume_to_center_droplet(46, 146, 21, front_airgap, droplet_volume, 2)
    glh.aspirate_from_curr_pos(_move, 0.5 * DEFAULT_SYRINGE_FLOWRATE)
    abs_spectrum = my_spec.measure_abs_spectra(**abs_opt_specs)
    glh.dispense_to_curr_pos(_move, 0.5 * DEFAULT_SYRINGE_FLOWRATE)

    tag = abs_opt_specs.generate_tag()
    with open(f"{save_to_template}_{save_iter}.csv", "w+") as _file:
        _file.write(f"name, {save_to_template}_{save_iter}.csv\n{tag}\nFraction, {frac}\n")
        _file.write(f"wavelength (nm), dark reference (int), light reference (int), absorbance (mAU)\n")
        ZipSpectra(abs_spectrum, my_spec.abs).print(file_stream=_file)


if __name__ == '__main__':
    template = safe_project_dir(parent_dir="C:/Users/cbe.mabolha.shared/Documents/Gilson Spectroscopy Project/Path Length Study",
                                project_header="Extinction Tests",
                                exp_header="sd_rubpy_MeCN")

    my_spec = SpectrometerSystem(LightSource("Dev1/port0/line1", "Dev1/port0/line0"))
    abs_opt_specs = OpticalSpecs(count=45, interval=0.05, integration_time=13_000, correct_dark_counts=False)

    glh = Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    glh.load_bed(
        directory="C:/Users/cbe.mabolha.shared/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
        bed_file="Gilson_Bed.bed"
    )
    glh.set_pump_to_volume(1_000)

    DYE = glh.locate_position_name("pos_1_rack", "A1")
    DILUENT = glh.locate_position_name("pos_1_rack", "A2")

    WASTE = glh.locate_position_name('waste', "A1")
    EX_WASH = glh.locate_position_name('wash', "A1")

    n_replicates = 1
    prime(glh, WASTE, 200)
    try:
        for rep in range(n_replicates):
            core_loop(rep, 30 * (5/3), 6, Volumetric(10 * (5 / 3)))  # 6 dilutions: 100%, 67%, ..., 13%, 9%
        inter_clean(glh, WASTE, EX_WASH)
    except KeyboardInterrupt:
        print("User exited the loop early")
    clean_up(glh, WASTE)
