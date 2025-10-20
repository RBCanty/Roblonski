from typing import Callable, Any, Iterable

from aux_devices.ocean_optics_spectrometer import SpectrometerSystem
from deck_layout.handler_bed import Placeable, DEFAULT_SYRINGE_FLOWRATE, SYSTEM_AIR_GAP
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from liquid_handling.liquid_handling_specification import DispensePipettingSpec, ComponentSpec, TipExitMethod, \
    AspiratePipettingSpec, MixingSpec, AirGap, InternalClean, ArmSpec, AspirateSystemSpec
from workflows.common_abstractions import DilutionTracker
from workflows.common_macros import inter_clean, test_well
from workflows.serial_measurement.abstractions import Mixing
from workflows.serial_measurement.constants import MIXING_RATE, MIN_PIPETTE_VOLUME, NEW_VIAL_VOLUME, MAX_VIAL_VOLUME, \
    MAX_MOVE_VOLUME, BACK_AIR_GAP, FRONT_AIR_GAP
from workflows.serial_measurement.serial_spec import Experiment
from workflows.serial_measurement.support_methods import measure_spectrum, SpectralMeasurementArgs, \
    calculate_new_vial_mixing_parameters


def calculate_new_vial_parameters(target_to_actual_ratio: float,
                                  new_vial_volume: float,
                                  min_pipettable_volume: float
                                  ) -> tuple[float, float, float]:
    """ Calculates the volumes for a new vial stock solution: (total, dye_component, diluent_component). """

    total_parts = 1 / min(target_to_actual_ratio, 1 - target_to_actual_ratio)
    volume_per_part = new_vial_volume / total_parts
    if volume_per_part < 2 * min_pipettable_volume:
        volume_per_part = 2 * min_pipettable_volume

    print(f"DEBUG: Preparing new well: {target_to_actual_ratio=}, {total_parts=}, {volume_per_part=}")

    total_new_stock_volume = volume_per_part * total_parts
    new_stock_dye_volume = volume_per_part * (target_to_actual_ratio * total_parts)
    new_stock_dil_volume = volume_per_part * ((1 - target_to_actual_ratio) * total_parts)

    return total_new_stock_volume, new_stock_dye_volume, new_stock_dil_volume


def prepare_new_stock_in_vial(glh: Gilson241LiquidHandler,
                              new_stock_dye_volume: float,
                              new_stock_dil_volume: float,
                              mixing_spec: Mixing,
                              back_airgap: float,
                              front_airgap: float,
                              waste: Placeable,
                              ex_wash: Placeable,
                              source: Placeable,
                              diluent: Placeable | None,
                              destination: Placeable,
                              mixing_rate: float = 4 * DEFAULT_SYRINGE_FLOWRATE,
                              blowout_volume: float = 20,
                              wash_volume: float = 200,
                              tracker: DilutionTracker = None):
    """ Calls glh.prepare_vial_diluted_stock() and then inter_clean(). Needle exits Clean and with System
    airgap restored. """
    if diluent is None:
        print("Preparing system-diluted stock")
        glh.prepare_system_diluted_stock(
            source=source,
            destination=destination,
            total_volume=new_stock_dye_volume + new_stock_dil_volume,
            dilution_factor=new_stock_dye_volume / (new_stock_dye_volume + new_stock_dil_volume),
            aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
            mix_displacement=mixing_spec.displacement,
            mix_rate=mixing_rate,
            mix_iterations=mixing_spec.iterations,
            back_air_gap=back_airgap,
            front_air_gap=front_airgap,
            air_rate=DEFAULT_SYRINGE_FLOWRATE,
            waste_pos=waste
        )
    else:
        print("Preparing vial-diluted stock")
        glh.prepare_vial_diluted_stock(
            source=source,
            diluent=diluent,
            destination=destination,
            volume_source=new_stock_dye_volume,
            volume_diluent=new_stock_dil_volume,
            aspirate_rate=DEFAULT_SYRINGE_FLOWRATE,
            mix_displacement=mixing_spec.displacement,
            mix_rate=mixing_rate,
            mix_iterations=mixing_spec.iterations,
            back_air_gap=back_airgap,
            front_air_gap=front_airgap,
            air_rate=DEFAULT_SYRINGE_FLOWRATE,
            wash_protocol=lambda: inter_clean(glh, waste, ex_wash, wash_volume),
            blowout_volume=blowout_volume
        )
    inter_clean(glh, waste, ex_wash, wash_volume)
    if tracker is not None:
        tracker.transfer(new_stock_dye_volume, new_stock_dil_volume)
    return


def perform_dilution_in_needle(glh: Gilson241LiquidHandler,
                               replaced_volume: float,
                               front_air_gap: float,
                               mixing: Mixing | None,
                               waste: Placeable,
                               diluent: Placeable,
                               mixing_rate: float = 4 * DEFAULT_SYRINGE_FLOWRATE,
                               tracker: DilutionTracker = None):
    """ Removes a volume of sample from the Needle and replaces it with an equivalent volume from diluent.
     Needle exits with the sample with its front air gap. """
    if mixing is None:
        mixing = Mixing(0,0)

    glh.chain_pipette(
        DispensePipettingSpec(
            component=ComponentSpec(position=waste, volume=front_air_gap),
            free_dispense=True,
            tip_exit_method=TipExitMethod.CENTER
        ),
        DispensePipettingSpec(
            component=ComponentSpec(position=waste, volume=replaced_volume),
            free_dispense=True,
            tip_exit_method=TipExitMethod.TIP_TOUCH
        ),
        AspiratePipettingSpec(
            component=ComponentSpec(position=diluent, volume=replaced_volume)
        ),
        AspiratePipettingSpec(
            component=AirGap(volume=front_air_gap)
        ),
        MixingSpec(
            mixing_displacement=mixing.displacement,
            rate=mixing_rate,
            n_iterations=mixing.iterations
        ),
    )
    if tracker is not None:
        tracker.replace(replaced_volume)
    return


def perform_dilution_in_vial(glh: Gilson241LiquidHandler,
                             spectrometer: SpectrometerSystem,
                             replaced_volume: float,
                             front_air_gap: float,
                             mixing: Mixing | None,
                             working: Placeable,
                             waste: Placeable,
                             diluent: Placeable | None,
                             system_center_droplet_callable: Callable[[float, float], float],
                             mixing_rate: float = 4 * DEFAULT_SYRINGE_FLOWRATE,
                             tracker: DilutionTracker = None):
    """ Removes a volume of sample from the Vial and replaces it with an equivalent volume from diluent/System.
         Needle exits with the sample with its front air gap. """
    if mixing is None:
        mixing = Mixing(0,0)
    glh.chain_pipette(
        InternalClean(  # throws test_well()'s 'replaced_volume' from the working vial away
            cleaning_volume=min(max(200.0, 2 * replaced_volume), MAX_MOVE_VOLUME),
            location=waste,
            free_dispense=True,
            tip_exit_method=TipExitMethod.TIP_TOUCH,
            pre_flush=True
        )  # restores system airgap
    )
    if tracker is not None:
        tracker.remove(replaced_volume)

    # Add 'replaced_volume' to the working vial...
    if isinstance(diluent, Placeable):  # ... (1/2) using a vial
        glh.chain_pipette(
            AspiratePipettingSpec(
                component=ComponentSpec(position=diluent, volume=replaced_volume)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=front_air_gap)
            ),
            DispensePipettingSpec(
                component=ComponentSpec(position=working, volume=front_air_gap + replaced_volume)
            ),
        )
    else:  # ... (2/2) using the system fluid
        glh.chain_pipette(
            AspirateSystemSpec(volume=replaced_volume),
            DispensePipettingSpec(
                component=ComponentSpec(position=working, volume=SYSTEM_AIR_GAP + replaced_volume)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=SYSTEM_AIR_GAP)
            )
        )
    if tracker is not None:
        tracker.add_direct(0, replaced_volume)

    glh.chain_pipette(
        MixingSpec(
            mixing_displacement=mixing.displacement,
            rate=mixing_rate,
            n_iterations=mixing.iterations,
            location=(working, ArmSpec(), TipExitMethod.CENTER),
            blowout_volume=min(20.0 + mixing.displacement, MAX_MOVE_VOLUME - mixing.displacement - BACK_AIR_GAP)
        )
    )

    test_well(
        glh,
        spectrometer,
        working,
        replaced_volume,
        system_center_droplet_callable,
        air_gaps=(BACK_AIR_GAP, front_air_gap)
    )


def check_source(glh: Gilson241LiquidHandler,
           spectrometer: SpectrometerSystem,
           design: Experiment,
           sample_volume: float,
           system_center_droplet_callable: Callable[[float, float], float],
           global_counter: int):
    """ returns None (stop checking) or a ration (target signal / actual signal).
    Leaves with the droplet in the needle (with airgap). """
    spec_m_args = SpectralMeasurementArgs(
        spec=design,
        global_counter=global_counter,
        dilution_counter=None,
        net_dilution=1.0,
        mix_details=None,
        flag="CHK"
    )
    test_spectra = test_well(
        glh,
        spectrometer,
        design.source,
        sample_volume,
        system_center_droplet_callable,
        absorbance=(design.abs_optic_spec, lambda _ms: measure_spectrum(_ms, 'ABS', spec_m_args)),
        photoluminescence=(design.pl_optic_spec, lambda _ms: measure_spectrum(_ms, 'PL', spec_m_args)),
        air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
    )
    if design.target_abs_signal and design.target_pl_signal:
        test_abs_spectrum, test_pl_spectrum = test_spectra[0], test_spectra[1]
    elif design.target_abs_signal:
        test_abs_spectrum, test_pl_spectrum = test_spectra[0], None
    elif design.target_pl_signal:
        test_abs_spectrum, test_pl_spectrum = None, test_spectra[0]
    else:
        return None

    return design.targeted_ratio(test_abs_spectrum, test_pl_spectrum)


def case_n1(glh: Gilson241LiquidHandler,
            spectrometer: SpectrometerSystem,
            design: Experiment,
            sample_volume: float,
            system_center_droplet_callable: Callable[[float, float], float]):
    """ Working is Needle, No Target: Just sample the source  """
    test_well(
        glh,
        spectrometer,
        design.source,
        sample_volume,
        system_center_droplet_callable,
        air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
    )
    design.dilution_tracker.transfer(sample_volume, 0.0)


def case_n4(glh: Gilson241LiquidHandler,
            spectrometer: SpectrometerSystem,
            design: Experiment,
            sample_volume: float,
            system_center_droplet_callable: Callable[[float, float], float],
            global_counter: int,
            waste: Placeable):
    """ Targeted, Alt. Source is (become) Needle, and Working is Needle: Sample source, Check signal,
    (Dilute in Needle) """
    selected_ratio = check_source(glh, spectrometer,
                                  design, sample_volume,
                                  system_center_droplet_callable, global_counter)
    design.dilution_tracker.transfer(sample_volume, 0.0)
    if selected_ratio is None or selected_ratio >= 1.0:
        return

    replaced_volume = design.sample_volume * (1 - selected_ratio)
    if (replaced_volume < MIN_PIPETTE_VOLUME) or ((design.sample_volume - replaced_volume) < MIN_PIPETTE_VOLUME):
        replaced_volume = min(max(replaced_volume, MIN_PIPETTE_VOLUME), design.sample_volume - replaced_volume)
        effective_ratio = 1 - (replaced_volume / design.sample_volume)
        print(f"Failed to dilute in needle to desired target (desired ratio = {selected_ratio} vs "
              f"actual ratio = {effective_ratio})")

    perform_dilution_in_needle(
        glh,
        replaced_volume,
        FRONT_AIR_GAP,
        Mixing(3, 3 * design.sample_volume),
        waste,
        design.diluent,
        mixing_rate=MIXING_RATE,
        tracker=design.dilution_tracker
    )


def case_n6(glh: Gilson241LiquidHandler,
            spectrometer: SpectrometerSystem,
            design: Experiment,
            sample_volume: float,
            system_center_droplet_callable: Callable[[float, float], float],
            global_counter: int,
            waste: Placeable,
            wash: Placeable,
            default_new_working_volume: float):
    """ Targeted, Alt. Source is Vial, and Working is Needle: Sample source, Check signal, (Prepare Alt. Stock,
    Sample Alt. Source) """
    assert isinstance(design.alt_source, Placeable)
    selected_ratio = check_source(glh, spectrometer,
                                  design, sample_volume,
                                  system_center_droplet_callable, global_counter)
    if selected_ratio is None or selected_ratio >= 1.0:
        design.dilution_tracker.transfer(sample_volume, 0.0)
        return

    total_new_stock_volume, new_stock_dye_volume, new_stock_dil_volume = calculate_new_vial_parameters(
        selected_ratio,
        default_new_working_volume,
        MIN_PIPETTE_VOLUME
    )

    enough_volume_in_vial = total_new_stock_volume <= MAX_VIAL_VOLUME
    enough_volume_in_syr = (new_stock_dye_volume <= MAX_MOVE_VOLUME) and (new_stock_dil_volume <= MAX_MOVE_VOLUME)
    if not (enough_volume_in_vial and enough_volume_in_syr):
        print(f"Not enough volume to prepare a new stock solution:\n"
              f"\t{total_new_stock_volume <= MAX_VIAL_VOLUME = }\n"
              f"\t{new_stock_dye_volume <= MAX_MOVE_VOLUME = }\n"
              f"\t{new_stock_dil_volume <= MAX_MOVE_VOLUME = }\n"
              f"\tSkipping...")
        raise RuntimeError("Insufficient volume to prep Alt. Stock")

    mix_details = calculate_new_vial_mixing_parameters(total_new_stock_volume)
    mix_details = Mixing(
        iterations=mix_details.iterations,
        displacement=max(0.0, min(mix_details.displacement, MAX_MOVE_VOLUME - BACK_AIR_GAP))
    )
    inter_clean(glh, waste, wash, 200)

    prepare_new_stock_in_vial(glh,
                              new_stock_dye_volume, new_stock_dil_volume,
                              mix_details,
                              BACK_AIR_GAP, FRONT_AIR_GAP,
                              waste, wash,
                              design.source,
                              design.diluent,
                              design.alt_source,
                              mixing_rate=MIXING_RATE,
                              tracker=design.dilution_tracker)

    test_well(
        glh,
        spectrometer,
        design.alt_source,
        sample_volume,
        system_center_droplet_callable,
        air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
    )
    design.dilution_tracker.transfer(sample_volume, 0.0)


def case_v7(glh: Gilson241LiquidHandler,
            spectrometer: SpectrometerSystem,
            design: Experiment,
            system_center_droplet_callable: Callable[[float, float], float],
            default_new_working_volume: float,
            *,
            already_in_needle: float = 0.0):
    """ Not targeted and Working is Vial: Transfer to Working, Sample Working """
    if already_in_needle:
        glh.chain_pipette(
            DispensePipettingSpec(
                component=ComponentSpec(position=design.working, volume=FRONT_AIR_GAP + already_in_needle)
            )
        )
    move_volume = default_new_working_volume - already_in_needle
    assert move_volume > 0, "Volume in needle larger than an initializing volume for a vial?"
    glh.chain_pipette(
        AspiratePipettingSpec(
            component=ComponentSpec(position=design.source, volume=move_volume)
        ),
        AspiratePipettingSpec(
            component=AirGap(volume=FRONT_AIR_GAP)
        ),
        DispensePipettingSpec(
            component=ComponentSpec(position=design.working, volume=FRONT_AIR_GAP + move_volume)
        )
    )
    if not already_in_needle:
        design.dilution_tracker.transfer(default_new_working_volume, 0.0)
    else:
        design.dilution_tracker.transfer(already_in_needle, 0.0)
        design.dilution_tracker.add_relative(design.source_concentration, move_volume)
    design.working_volume = default_new_working_volume

    test_well(
        glh,
        spectrometer,
        design.working,
        design.dilution_spec.get_volume(design.working_volume ),
        system_center_droplet_callable,
        air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
    )


def case_v14(glh: Gilson241LiquidHandler,
            spectrometer: SpectrometerSystem,
            design: Experiment,
            sample_volume: float,
            system_center_droplet_callable: Callable[[float, float], float],
            global_counter: int,
            waste: Placeable,
            wash: Placeable,
            default_new_working_volume: float):
    """ Targeted and Working is Vial: Sample source, Check signal, Prepare Working, ((do cutback), sample Working) """
    assert isinstance(design.alt_source, Placeable)
    selected_ratio = check_source(glh, spectrometer,
                                  design, sample_volume,
                                  system_center_droplet_callable, global_counter)
    # There is Stock in the Needle
    if selected_ratio is None or selected_ratio >= 1.0:
        case_v7(glh, spectrometer, design, system_center_droplet_callable, default_new_working_volume, already_in_needle=sample_volume)
        return

    total_new_stock_volume, new_stock_dye_volume, new_stock_dil_volume = calculate_new_vial_parameters(
        selected_ratio,
        default_new_working_volume,
        MIN_PIPETTE_VOLUME
    )

    enough_volume_in_vial = total_new_stock_volume <= MAX_VIAL_VOLUME
    enough_volume_in_syr = (new_stock_dye_volume <= MAX_MOVE_VOLUME) and (new_stock_dil_volume <= MAX_MOVE_VOLUME)
    if not (enough_volume_in_vial and enough_volume_in_syr):
        print(f"Not enough volume to prepare a new working solution:\n"
              f"\t{total_new_stock_volume <= MAX_VIAL_VOLUME = }\n"
              f"\t{new_stock_dye_volume <= MAX_MOVE_VOLUME = }\n"
              f"\t{new_stock_dil_volume <= MAX_MOVE_VOLUME = }\n"
              f"\tSkipping...")
        raise RuntimeError("Insufficient volume to prepare new working solution")

    mix_details = calculate_new_vial_mixing_parameters(total_new_stock_volume)
    mix_details = Mixing(
        iterations=mix_details.iterations,
        displacement=max(0.0, min(mix_details.displacement, MAX_MOVE_VOLUME - BACK_AIR_GAP))
    )
    inter_clean(glh, waste, wash, 200)

    prepare_new_stock_in_vial(glh,
                              new_stock_dye_volume, new_stock_dil_volume,
                              mix_details,
                              BACK_AIR_GAP, FRONT_AIR_GAP,
                              waste, wash,
                              design.source,
                              design.diluent,
                              design.working,
                              mixing_rate=MIXING_RATE,
                              tracker=design.dilution_tracker)

    if total_new_stock_volume > default_new_working_volume + 2 * MIN_PIPETTE_VOLUME:
        move_volume = total_new_stock_volume - default_new_working_volume
        glh.chain_pipette(
            AspiratePipettingSpec(
                component=ComponentSpec(position=design.working, volume=move_volume)
            ),
            AspiratePipettingSpec(
                component=AirGap(volume=FRONT_AIR_GAP)
            ),
            DispensePipettingSpec(
                component=ComponentSpec(position=waste, volume=FRONT_AIR_GAP + move_volume),
                free_dispense=True,
                tip_exit_method=TipExitMethod.TIP_TOUCH
            )
        )
        design.working_volume = default_new_working_volume
        design.dilution_tracker.remove(move_volume)
    else:
        design.working_volume = total_new_stock_volume

    test_well(
        glh,
        spectrometer,
        design.working,
        design.dilution_spec.get_volume(design.working_volume),
        system_center_droplet_callable,
        air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
    )


def core_loop(glh: Gilson241LiquidHandler,
              spectrometer: SpectrometerSystem,
              global_counter: int,
              design: Experiment,
              cleaning: tuple[Placeable, Placeable],
              system_center_droplet_callable: Callable[[float, float], float],
              cutback_to: float = None,
              inter_callables: Iterable[Callable[[Experiment], Any]] = None):
    waste, wash = cleaning
    if cutback_to is None:
        default_new_working_volume = NEW_VIAL_VOLUME
    else:
        default_new_working_volume = max(NEW_VIAL_VOLUME, cutback_to)
    if inter_callables is None:
        inter_callables = []
    calibration = design.calibration
    sample_volume = design.sample_volume

    # #### Measuring an Analytical Reference ####                                           Measure Analytic Reference #
    if design.measure_reference == "Needle":
        spec_m_args = SpectralMeasurementArgs(
            spec=design,
            global_counter=global_counter,
            dilution_counter=None,
            net_dilution=0.0,
            mix_details=None,
            flag="REF"
        )
        if design.pl_optic_spec is not None:
            measure_spectrum(spectrometer, 'PL', spec_m_args, is_reference=True)
        if design.abs_optic_spec is not None:
            measure_spectrum(spectrometer, 'ABS', spec_m_args, is_reference=True)
    elif design.measure_reference == "Vial":
        spec_m_args = SpectralMeasurementArgs(
            spec=design,
            global_counter=global_counter,
            dilution_counter=None,
            net_dilution=None,
            mix_details=None,
            flag="REF"
        )
        if design.pl_optic_spec is not None:
            measure_spectrum(spectrometer, 'PL', spec_m_args, is_reference=True)
        if design.abs_optic_spec is not None:
            measure_spectrum(spectrometer, 'ABS', spec_m_args, is_reference=True)

        if design.diluent and (design.abs_optic_spec or design.pl_optic_spec):
            ref_m_args = SpectralMeasurementArgs(
                spec=design,
                global_counter=global_counter,
                dilution_counter=None,
                net_dilution=0.0,
                mix_details=None,
                flag="REF"
            )
            standard_spectra = test_well(
                glh,
                spectrometer,
                design.diluent,
                sample_volume,
                system_center_droplet_callable,
                absorbance=(design.abs_optic_spec, lambda _ms: measure_spectrum(_ms, 'ABS', ref_m_args)),
                photoluminescence=(design.pl_optic_spec, lambda _ms: measure_spectrum(_ms, 'PL', ref_m_args)),
                air_gaps=(BACK_AIR_GAP, FRONT_AIR_GAP)
            )

            if design.abs_optic_spec and design.pl_optic_spec:
                std_abs_spectrum, std_pl_spectrum = standard_spectra[0], standard_spectra[1]
            elif design.abs_optic_spec and design.abs_spec_processing:
                std_abs_spectrum, std_pl_spectrum = standard_spectra[0], None
            elif design.pl_optic_spec and design.pl_spec_processing:
                std_abs_spectrum, std_pl_spectrum = None, standard_spectra[0]
            else:
                std_abs_spectrum, std_pl_spectrum = None, None

            if design.abs_spec_processing and std_abs_spectrum:
                std_abs_spectrum = standard_spectra[0]
                design.standard_abs_peak = design.abs_spec_processing.primary_analysis(
                    std_abs_spectrum.segment(**design.abs_spec_processing.segment_kwargs())
                )
            if design.abs_spec_processing and std_pl_spectrum:
                std_pl_spectrum = standard_spectra[0]
                design.standard_pl_peak = design.abs_spec_processing.primary_analysis(
                    std_pl_spectrum.segment(**design.abs_spec_processing.segment_kwargs())
                )

            inter_clean(glh, waste, wash)
    else:
        pass

    design.dilution_tracker = DilutionTracker(calibration, design.source_concentration, 1000)
    # #### Targeting Adjustments ####                                                            Targeting Adjustments #
    if design.working is None:
        design.working_volume = sample_volume
        if not design.has_target:
            case_n1(glh, spectrometer, design,
                    sample_volume, system_center_droplet_callable)
        elif design.has_target and (design.alt_source is None or design.alt_source == "Needle"):
            case_n4(glh, spectrometer, design,
                    sample_volume, system_center_droplet_callable,
                    global_counter, waste)
        elif design.has_target and isinstance(design.alt_source, Placeable):
            case_n6(glh, spectrometer, design,
                    sample_volume, system_center_droplet_callable,
                    global_counter, waste, wash, default_new_working_volume)
        else:
            raise RuntimeError("Working Volume is Needle but logic failed to classify as cases 1, 4, or 6")
    else:  # working volume is a Vial
        # design.working_volume = ... (solved for in the cases below)
        if not design.has_target:
            case_v7(glh, spectrometer, design,
                    system_center_droplet_callable, default_new_working_volume)
        elif design.has_target and (design.alt_source is None or design.alt_source == design.working):
            case_v14(glh, spectrometer, design,
                     sample_volume, system_center_droplet_callable,
                     global_counter, waste, wash, default_new_working_volume)
        elif design.has_target and (design.alt_source != design.working):
            # case 12
            print(f"Should prepare an Alt. Source, but will then immediately transfer to Working "
                  f"(so skipping Alt. Source)")
            case_v14(glh, spectrometer, design,
                     sample_volume, system_center_droplet_callable,
                     global_counter, waste, wash, default_new_working_volume)
        else:
            raise RuntimeError("Working volume is Vial but logic failed to classify as cases 7, 12, or 14")

    # We now have a sample_size-sized (by Needle) or dilution_volume-sized (by Vial) volume in the needle, buffered by
    #   a front airgap
    # We need to: Measure_0, Dilute, (Measure_i, [Dilute if i < N])_i=1...N

    # #### Core Loop ####                                                                                    Core Loop #
    if design.working is None:
        mix_details = Mixing(
            iterations=3,
            displacement=3 * design.sample_volume
        )
        replaced_volume = design.dilution_spec.get_volume(design.sample_volume)

        for dil_dx in range(design.n_dilutions + 1):  # TODO: If CHK is okay, do we need that +1 there?
            last_iteration = dil_dx == design.n_dilutions
            exp_m_args = SpectralMeasurementArgs(
                spec=design,
                global_counter=global_counter,
                dilution_counter=dil_dx,
                net_dilution=design.dilution_tracker.dilution_factor,
                mix_details=mix_details,
                flag="EXP"
            )
            glh.utilize_spectrometer(
                spectrometer,
                system_center_droplet_callable(FRONT_AIR_GAP, replaced_volume),
                absorbance=(design.abs_optic_spec, lambda _ms: measure_spectrum(_ms, 'ABS', exp_m_args)),
                photoluminescence=(design.pl_optic_spec, lambda _ms: measure_spectrum(_ms, 'PL', exp_m_args)),
                measurement_spacing=1.0
            )

            if inter_callables:
                [post(design) for post in inter_callables]

            if not last_iteration:
                perform_dilution_in_needle(
                    glh,
                    replaced_volume,
                    FRONT_AIR_GAP,
                    mix_details,
                    waste,
                    design.diluent,
                    MIXING_RATE,
                    design.dilution_tracker
                )
    else:
        mix_details = calculate_new_vial_mixing_parameters(design.working_volume)
        mix_details = Mixing(
            iterations=mix_details.iterations,
            displacement=max(0.0, min(mix_details.displacement, MAX_MOVE_VOLUME - BACK_AIR_GAP))
        )
        replaced_volume = design.dilution_spec.get_volume(design.working_volume)
        for dil_dx in range(design.n_dilutions + 1):
            last_iteration = dil_dx == design.n_dilutions
            exp_m_args = SpectralMeasurementArgs(
                spec=design,
                global_counter=global_counter,
                dilution_counter=dil_dx,
                net_dilution=design.dilution_tracker.dilution_factor,
                mix_details=mix_details,
                flag="EXP"
            )
            glh.utilize_spectrometer(
                spectrometer,
                system_center_droplet_callable(FRONT_AIR_GAP, replaced_volume),
                absorbance=(design.abs_optic_spec, lambda _ms: measure_spectrum(_ms, 'ABS', exp_m_args)),
                photoluminescence=(design.pl_optic_spec, lambda _ms: measure_spectrum(_ms, 'PL', exp_m_args)),
                measurement_spacing=1.0
            )

            if inter_callables:
                [post(design) for post in inter_callables]

            if not last_iteration:
                perform_dilution_in_vial(
                    glh,
                    spectrometer,
                    replaced_volume,
                    FRONT_AIR_GAP,
                    mix_details,
                    design.working,
                    waste,
                    design.diluent,
                    system_center_droplet_callable,
                    MIXING_RATE,
                    design.dilution_tracker
                )
    inter_clean(glh, waste, wash, 200)


"""
Case, Target, Alt.Source, Working, Diluent, Can, Can't, Unique Scenarios, , , , , , , , 
1, No, No, Needle, Vial, 1, , 1, Sample Source, , , , , Measure[EXP], Dilute in Needle, Repeat(2,1+N)
2, Yes, No, Needle, Vial, goto 4, , , , , , , , , , 
3, No, Needle, Needle, Vial, 1, , , , , , , , , , 
4, Yes, Needle, Needle, Vial, 4, 1, 4-CAN, Sample Source, Measure[CHK] -> get D, Dilute in Needle, , , Measure[EXP], Dilute in Needle, Repeat(2,1+N)
5, No, Vial, Needle, Vial, 1, , , , , , , , , , 
6, Yes, Vial, Needle, Vial, 6, 1, 6, Sample Source, Measure[CHK] -> get D, , Transfer to Alt Src Vial, Sample Alt. Src, Measure[EXP], Dilute in Needle, Repeat(2,1+N)
7, No, No, Vial, Vial, 7, , 7, , , , Transfer to Wrk Vial, Sample Wrk, Measure[EXP], Dilute Wrk, Repeat(3,1+N)
8, Yes, No, Vial, Vial, goto 14, , , , , , , , , , 
9, No, Needle, Vial, Vial, 7, , , , , , , , , , 
11, No, Vial, Vial, Vial, 7, , , , , , , , , , 
12, Yes, Vial, Vial, Vial, 12, 7, 12, Sample Source, Measure[CHK] -> get D, Transfer to Alt Src Vial, Transfer to Wrk Vial, Sample Wrk, Measure[EXP], Dilute Wrk, Repeat(3,1+N)
13, No, Vial, , Vial, 7, , , , , , , , , , 
14, Yes, Vial, , Vial, 14, 7, 14-CAN, Sample Source, Measure[CHK] -> get D, , Transfer to Wrk Vial, Sample Wrk, Measure[EXP], Dilute Wrk, Repeat(3,1+N)
21, No, No, Vial, Sys.Fluid, 21, , 21, , , , Transfer to Wrk Vial, Sample Wrk, Measure[EXP], Dilute Wrk, Repeat(3,1+N)
22, Yes, No, Vial, Sys.Fluid, goto 28, , , , , , , , , , 
23, No, Needle, Vial, Sys.Fluid, 21, , , , , , , , , , 
25, No, Vial, Vial, Sys.Fluid, 21, , , , , , , , , , 
26, Yes, Vial, Vial, Sys.Fluid, 26, 21, 26, Sample Source, Measure[CHK] -> get D, Transfer to Alt Src Vial, Transfer to Wrk Vial, Sample Wrk, Measure[EXP], Dilute Wrk, Repeat(3,1+N)
27, No, Vial, , Sys.Fluid, 21, , , , , , , , , , 
28, Yes, Vial, , Sys.Fluid, 28, 21, 28-CAN, Sample Source, Measure[CHK] -> get D, , Transfer to Wrk Vial, Sample Wrk, Measure[EXP], Dilute Wrk, Repeat(3,1+N)
"""
