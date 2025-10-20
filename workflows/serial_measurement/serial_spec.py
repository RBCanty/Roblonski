from dataclasses import dataclass, field, InitVar, replace
from typing import Literal, Callable

from aux_devices.ocean_optics_spectrometer import OpticalSpecs
from aux_devices.spectra import Spectrum
from data_management.common_dp_steps import SpectralProcessingSpec, take_sigal_near
from deck_layout.handler_bed import Placeable, NamePlace
from deck_layout.rack import WELL_ID
from workflows.common_abstractions import Dilution, Volumetric, DilutionTracker, Calibration
from workflows.serial_measurement.abstractions import Mixing
from workflows.serial_measurement.naming import SMApellomancer


@dataclass
class Experiment:
    """ INIT:
     - name: str
     - dilution: tuple[Dilution, int]
     - name_wizard: SMApellomancer
     - source_init: InitVar[tuple[str, str]]
     - locator: Callable[[str, str], Placeable] | None = None
     - diluent_init: InitVar[tuple[str, str] | None] = None
     - working_init: InitVar[tuple[str, str] | None] = None
     - alt_source_init: InitVar[tuple[str, str] | Literal["Needle"] | None] = None
     - abs_optic_spec: OpticalSpecs | None = None
     - pl_optic_spec: OpticalSpecs | None = None
     - abs_spec_processing: SpectralProcessingSpec | None = None  (req. abs_optic_spec)
     - pl_spec_processing: SpectralProcessingSpec | None = None  (req. pl_optic_spec)
     - target_abs_signal: None | float | tuple[float, float] = None  (req. abs_spec_processing)
     - target_pl_signal: None | float | tuple[float, float] = None  (req. pl_spec_processing)
     - solvent: str = "Not Specified"
     - measure_reference: Literal['Vial', 'Needle', 'No'] = "No"

    POST:
     - source: Placeable
     - diluent: Placeable | None  (None --> System fluid)
     - working: Placeable | None  (None --> In Needle)
     - alt_source: Placeable | Literal["Needle"] | None  (None --> Not allowed)
     - source_volume: float = -1  (The volume of original stock used)
     - working_volume: float = -1  (The volume of the working vial)
     - standard_abs_peak: float = 0.0  (Background value for target_abs_signal)
     - standard_pl_peak: float = 0.0  (Background value for target_pl_signal)
     - dilution_tracker: DilutionTracker | None = None
    """
    name: str
    """ Name for the experiment """
    sample_volume: float
    """ How much volume to use in samples (doubles as the working volume if using the Needle) """
    dilution: tuple[Dilution, int]
    """ (How to perform the dilution, how many dilutions) """
    name_wizard: SMApellomancer
    """ Object for managing files """

    source_init: InitVar[tuple[str, str]]
    """ Which vial is the source (init only) """
    source: Placeable = field(init=False)
    """ Which vial is the source """

    locator: Callable[[str, str], Placeable] | None = None
    """ Device plug-in (for resolving locations) """

    diluent_init: InitVar[tuple[str, str] | None] = None
    """ Which vial is the diluent (None --> System fluid) """
    diluent: Placeable | None = field(init=False)
    """ Which vial is the diluent (None --> System fluid) """

    working_init: InitVar[tuple[str, str] | None] = None
    """ Which vial is the working vial (None --> In needle) """
    working: Placeable | None = field(init=False)
    """ Which vial is the working vial (None --> In needle) """

    alt_source_init: InitVar[tuple[str, str] | Literal["Needle"] | None] = None
    """ Is the system allowed to prepare an alternate stock solution?
    
     - tuple --> Yes, Prepare the new stock solution in this vial
     - "Needle" --> Yes, Prepare the new stock solution in the needle
     - None --> No. (Falls back on Working if there is a target)
     """
    alt_source: Placeable | Literal["Needle"] | None = field(init=False)
    """ Is the system allowed to prepare an alternate stock solution?
    
     - Placeable --> Yes, Prepare the new stock solution in this vial
     - "Needle" --> Yes, Prepare the new stock solution in the needle
     - None --> No. (Falls back on Working if there is a target)
     """

    abs_optic_spec: OpticalSpecs | None = None
    """ How to measure absorbance (None --> do not measure) """
    pl_optic_spec: OpticalSpecs | None = None
    """ How to measure photoluminescence (None --> do not measure) """

    abs_spec_processing: SpectralProcessingSpec | None = None
    """ How to process absorbance signals (ignored if abs_optic_spec is None) """
    pl_spec_processing: SpectralProcessingSpec | None = None
    """ How to process photoluminescence signals (ignored if pl_optic_spec is None) """

    target_abs_signal_init: InitVar[None | float | tuple[float, float]] = None
    """ If the ABS signal (in OD) of the stock is greater than this, then prepare a new stock solution at this OD. 

     - None --> Ignore
     - Float --> Targets this value
     - Tuple --> (Target this value, accept up to this value)

    Requires that abs_spec_processing and thus abs_optic_spec are specified (otherwise ignored). In addition, if a new
    stock is to be prepared (is not None), then either the Needle or a Vial must be specified as the alt_source.
    """
    target_abs_signal: tuple[float, float] | None = field(init=False)
    """ If the ABS signal (in mOD) of the stock is greater than this, then prepare a new stock solution at this OD. 
    
     - None --> Ignore
     - Tuple --> (Target this value, accept up to this value)
    """
    target_pl_signal_init:  InitVar[None | float | tuple[float, float]] = None
    """ If the PL signal (in Counts) of the stock is greater than this, then prepare a new stock solution at this 
    signal. 

     - None --> Ignore
     - Float --> Targets this value
     - Tuple --> (Target this value, accept up to this value)

    Requires that pl_spec_processing and thus pl_optic_spec are specified (otherwise ignored).  In addition, if a new
    stock is to be prepared (is not None), then either the Needle or a Vial must be specified as the alt_source.
    """
    target_pl_signal: tuple[float, float] | None = field(init=False)
    """ If the PL signal (in Counts) of the stock is greater than this, then prepare a new stock solution at this 
    signal. (Mostly here if you want to prevent saturation, since PL is rarely targeted to a value)
    
     - None --> Ignore
     - Tuple --> (Target this value, accept up to this value)
    """

    solvent: str = "Not Specified"
    """ What solvent is being used """
    measure_reference: Literal['Vial', 'Needle', 'No'] = "No"
    """ Whether to explicitly measure an analytical reference spectrum (must match the diluent specification) """

    source_concentration: float = 1.0
    """ The concentration of the source vial """

    calibration: Calibration = Calibration()
    """ Fluidic calibration (nominal -> actual) """

    def __post_init__(self, source_init, diluent_init, working_init, alt_source_init, target_abs_signal_init, target_pl_signal_init):
        self.source = self._translate_to_placeable(source_init)
        self.diluent = self._translate_to_placeable(diluent_init)
        self.working = self._translate_to_placeable(working_init)
        if isinstance(alt_source_init, tuple):
            self.alt_source = self._translate_to_placeable(alt_source_init)
        elif alt_source_init == "Needle":
            self.alt_source = alt_source_init
            assert self.diluent is not None, "If the needle is used as the alternate source, there must be a diluent vial."
        else:
            self.alt_source = None
        if self.working is None:
            assert self.diluent is not None, "If the needle is used as the working volume, there must be a diluent vial."

        self.target_abs_signal = self._init_target(target_abs_signal_init)
        self.target_pl_signal = self._init_target(target_pl_signal_init)

        if self.abs_optic_spec is None:
            self.abs_spec_processing = None
        if self.abs_spec_processing is None:
            self.target_abs_signal = None
        if self.pl_optic_spec is None:
            self.pl_spec_processing = None
        if self.pl_spec_processing is None:
            self.target_pl_signal = None

        if (self.target_abs_signal is not None) and (self.target_pl_signal is not None):
            print("WARNING: Cannot target both a PL and ABS value at once. Will use whichever requires more dilution.")
        if (self.target_abs_signal or self.target_pl_signal) and (self.alt_source is None):
            print("WARNING: Target specified, but no alt_source (Using Working as Alt. Source)")
            self.alt_source = "Needle" if self.working is None else self.working
        assert not (self.alt_source == "Needle" and isinstance(self.working, Placeable) and self.has_target), \
            ("Sensible behavior not determinable for an experiment with a target, using the needle as an alternate "
             "source but a vial as the working volume.")

        if self.target_abs_signal is not None:
            assert self.working is not None or self.alt_source is not None, "Cannot prepare at a target ABS signal without a working/alt_source vial/Needle."
        if self.target_pl_signal is not None:
            assert self.working is not None or self.alt_source is not None, "Cannot prepare at a target PL signal without a working/alt_source vial/Needle."

        self._init_vars = (source_init, diluent_init, working_init, alt_source_init, target_abs_signal_init, target_pl_signal_init)
        """ (post_var) Copy of the InitVars for use in span_const_source() """
        self.working_volume: float = -1
        """ (post_var) The volume of the working vial """
        self.standard_abs_peak: float = 0.0
        """ (post_var) Background value for target_abs_signal """
        self.standard_pl_peak: float = 0.0
        """ (post_var) Background value for target_pl_signal """
        self.dilution_tracker: DilutionTracker | None = None

    def _translate_to_placeable(self, rack_and_vial: tuple[str, str] | None):
        if rack_and_vial is None:
            return None
        if not self.locator:
            raise RuntimeError("Cannot use tuple-locations without supplying an instrument!")
        return self.locator(*rack_and_vial)

    @property
    def post_vars(self):
        return {
            'working_volume': self.working_volume,
            'standard_abs_peak': self.standard_abs_peak,
            'standard_pl_peak': self.standard_pl_peak,
            'dilution_tracker': self.dilution_tracker
        }

    @staticmethod
    def _init_target(target: None | float | tuple[float, float]):
        if target is None:
            return None
        if isinstance(target, float | int):
            return target, target + 10
        if isinstance(target, tuple):
            return target
        raise ValueError(f"target_abs_signal is not None | float | tuple[float, float]: {target}")

    @property
    def has_target(self):
        return (self.target_abs_signal is not None) or (self.target_pl_signal is not None)

    @property
    def dilution_spec(self):
        return self.dilution[0]

    @property
    def n_dilutions(self):
        return self.dilution[1]

    @property
    def alt_is_working(self) -> bool:
        if isinstance(self.alt_source, Placeable) and isinstance(self.working, Placeable):
            return self.alt_source == self.working
        if self.working is None and self.alt_source == "Needle":
            return True
        return False

    @staticmethod
    def auto(rack: str,
             row: str,
             include_alt_source: bool | None = False,
             include_working: bool | None = False,
             include_diluent: bool | None = False):
        """ provides the source, (alt_source), (working_vial), and (diluent) kwargs.

        None sets to None, True includes it in the order, False does neither

        All will use the form (rack, f"{row}#") where # is 1--4 for source, alt_source, working, and diluent,
        in-order (not respectively) as requested.
        """
        counter = 1
        auto_dict: dict[str, tuple[str, str] | None] = {'source_init': (rack, f"{row}{counter}"), }
        counter += 1

        if include_alt_source is None:
            auto_dict.update(alt_source_init=None)
        elif include_alt_source:
            auto_dict.update(alt_source_init=(rack, f"{row}{counter}"))
            counter += 1

        if include_working is None:
            auto_dict.update(working_init=None)
        elif include_working:
            auto_dict.update(working_init=(rack, f"{row}{counter}"))
            counter += 1

        if include_diluent is None:
            auto_dict.update(diluent_init=None)
        elif include_diluent:
            auto_dict.update(diluent_init=(rack, f"{row}{counter}"))
            counter += 1

        return auto_dict

    def span_const_source(self, rack: str, *into: str):
        source_init, diluent_init, working_init, alt_source_init, target_abs_signal_init, target_pl_signal_init = self._init_vars
        update_kwargs = {'source_init': source_init,
                         'diluent_init': diluent_init,
                         'working_init': working_init,
                         'alt_source_init': alt_source_init}
        const_kwargs = {'target_abs_signal_init': target_abs_signal_init,
                        'target_pl_signal_init': target_pl_signal_init}
        # if isinstance(source_init, tuple):
        #     new_row_id = source_init[1].replace(WELL_ID.match(source_init[1]).groups()[0], "$row$")
        #     update_kwargs['source_init'] = (rack, new_row_id)
        if isinstance(diluent_init, tuple):
            new_row_id = diluent_init[1].replace(WELL_ID.match(diluent_init[1]).groups()[0], "$row$")
            update_kwargs['diluent_init'] = (rack, new_row_id)
        if isinstance(working_init, tuple):
            new_row_id = working_init[1].replace(WELL_ID.match(working_init[1]).groups()[0], "$row$")
            update_kwargs['working_init'] = (rack, new_row_id)
        if isinstance(alt_source_init, tuple):
            new_row_id = alt_source_init[1].replace(WELL_ID.match(alt_source_init[1]).groups()[0], "$row$")
            update_kwargs['alt_source_init'] = (rack, new_row_id)

        return [
            replace(self, name=f"{self.name}1", source_init=source_init, diluent_init=diluent_init, working_init=working_init, alt_source_init=alt_source_init, **const_kwargs)
        ] + [
            replace(self, name=f"{self.name}{j}", **{k: (v[0], v[1].replace("$row$", str(row))) if isinstance(v, tuple) else v for k, v in update_kwargs.items()}, **const_kwargs)
            for j, row in enumerate(into,start=2)
        ]

    def span_repl_row(self, rack: str, *into: int):
        source_init, diluent_init, working_init, alt_source_init, target_abs_signal_init, target_pl_signal_init = self._init_vars
        if (working_init is not None) or (alt_source_init is not None):
            raise ValueError(f"span_repl_row() cannot be invoked when a working vial or alt_source are specified")
        if diluent_init is None:
            raise ValueError(f"span_repl_row() cannot be invoked without a diluent specified")
        update_kwargs = {'source_init': source_init,
                         'diluent_init': diluent_init,
                         'working_init': working_init,
                         'alt_source_init': alt_source_init}
        const_kwargs = {'target_abs_signal_init': target_abs_signal_init,
                        'target_pl_signal_init': target_pl_signal_init}

        new_col_id = diluent_init[1].replace(WELL_ID.match(diluent_init[1]).groups()[1], "$col$")
        update_kwargs['diluent_init'] = (rack, new_col_id)

        return [
            replace(self, name=f"{self.name}1", source_init=source_init, diluent_init=diluent_init, working_init=working_init, alt_source_init=alt_source_init, **const_kwargs)
        ] + [
            replace(self, name=f"{self.name}{j}", **{k: (v[0], v[1].replace("$col$", str(col))) if isinstance(v, tuple) else v for k, v in update_kwargs.items()}, **const_kwargs)
            for j, col in enumerate(into, start=2)
        ]

    def targeted_ratio(self, test_abs_spectrum: Spectrum | None, test_pl_spectrum: Spectrum | None):
        """ Given spectra, returns the most extreme signal ratio (target / actual) """
        ratio_abs: float | None = None
        if self.target_abs_signal is not None:
            target_abs_signal, max_workable_abs_signal = self.target_abs_signal
            highest_abs_peak = self.abs_spec_processing.primary_analysis(
                test_abs_spectrum.segment(**self.abs_spec_processing.segment_kwargs())
            ) - self.standard_abs_peak
            print(f"Targeting ABS ({highest_abs_peak=} vs {target_abs_signal=})")
            if highest_abs_peak > max_workable_abs_signal:
                ratio_abs = target_abs_signal/highest_abs_peak

        ratio_pl: float | None = None
        if self.target_pl_signal is not None:
            target_pl_signal, max_workable_pl_signal = self.target_pl_signal
            highest_pl_peak = self.pl_spec_processing.primary_analysis(
                test_pl_spectrum.segment(**self.pl_spec_processing.segment_kwargs())
            ) - self.standard_pl_peak
            print(f"Targeting PL ({highest_pl_peak=} vs {target_pl_signal=})")
            if highest_pl_peak > max_workable_pl_signal:
                ratio_pl = target_pl_signal/highest_pl_peak

        print(f"Dilution ratios: ABS={ratio_abs}, PL={ratio_pl}")
        if (ratio_abs is not None) and (ratio_pl is not None):
            selected_ratio: float | None = min(ratio_abs, ratio_pl)
        elif ratio_abs is not None:
            selected_ratio = ratio_abs
        elif ratio_pl is not None:
            selected_ratio = ratio_pl
        else:
            selected_ratio = None

        return selected_ratio

    def prepare_name(self, mode: Literal['ABS', 'PL'], instance_idx: int, mixing: Mixing | None, dil_seq_idx: int | None, flag: Literal['EXP', 'CHK', 'REF']):
        if mixing is None:
            mixing_kwargs = {'n_mix': 0, 'mix_disp': 0}
        else:
            mixing_kwargs = {'n_mix': mixing.iterations, 'mix_disp': mixing.displacement}
        return self.name_wizard.make_file_name(
            spec=mode,
            dye_concentration=self.source_concentration,
            total_volume=self.working_volume,
            **mixing_kwargs,
            instance_idx=instance_idx,
            dil_seq_idx=dil_seq_idx,
            flag=flag
        )

    def generate_tag(self, mix_iterations: int, mix_displacement: float):
        """ Produces a comma-separated tag of the form 'var=value, ...' """
        return (f"mix_iter={mix_iterations}, mix_disp={mix_displacement}\n"
                f"droplet_volume={self.sample_volume}, working_volume={self.working_volume}\n"
                f"dilution_scheme={self.dilution_spec!r}, n_dil={self.n_dilutions}\n"
                f"calibration={self.calibration!r}")

    @classmethod
    def data_processing_recovery_object(cls,
                                        name: str,
                                        name_wizard: SMApellomancer,
                                        source_concentration: float,
                                        abs_optic_spec: OpticalSpecs = None,
                                        pl_optic_spec: OpticalSpecs = None,
                                        abs_spec_processing: SpectralProcessingSpec = None,
                                        pl_spec_processing: SpectralProcessingSpec = None):
        """ Makes an Experiment for re-processing data (not viable for execution). """
        recovery_object = cls.__new__(cls)
        recovery_object.name = name
        recovery_object.sample_volume = 0
        recovery_object.name_wizard=name_wizard
        recovery_object.source_concentration=source_concentration
        recovery_object.abs_optic_spec=abs_optic_spec
        recovery_object.abs_spec_processing=abs_spec_processing
        recovery_object.pl_optic_spec=pl_optic_spec
        recovery_object.pl_spec_processing=pl_spec_processing
        return recovery_object

    def __str__(self):
        _tab = "\n" + " "*4
        field_values = {k: v for k, v in self.__dict__.items()}
        field_str = (',' + _tab).join(f'{k}={repr(v)}' for k, v in field_values.items())
        post_str = (',' + _tab).join(f'{k}={repr(v)}' for k, v in self.post_vars.items())
        init_k = ['source_init', 'diluent_init', 'working_init', 'alt_source_init', 'target_abs_signal_init', 'target_pl_signal_init']
        init_values = {k: v for k, v in zip(init_k, self._init_vars)}
        init_str = (',' + _tab).join(f'{k}={repr(v)}' for k, v in init_values.items())
        return f'{self.__class__.__name__}({_tab}{init_str},\n{_tab}{field_str},\n{_tab}{post_str}\n)'


if __name__ == '__main__':
    def foo(_r: str, _v:str) -> Placeable:
        return NamePlace(None, _r, _v)

    exp = Experiment(
        name="test",
        sample_volume=50,
        dilution=(Volumetric(50), 4),
        name_wizard=SMApellomancer("", "", "", 'r'),
        source_init=('rack_pos_1', 'A1'),
        locator=foo,
        diluent_init=('rack_pos_1', 'A2'),
        working_init=('rack_pos_1', 'A4'),
        abs_optic_spec=OpticalSpecs(30,0.1, 10_000),
        abs_spec_processing=SpectralProcessingSpec(350, 800, lambda _: 42),
        target_abs_signal_init=1000,
        solvent="MeCN",
        source_concentration=1.0
    )

    for test in exp.span_const_source('rack_pos_2', 'B', 'C', 'D'):
        print(test.source, test.working, test.diluent, test.alt_source)

    print()

    exp2 = Experiment(
        name="test",
        sample_volume=50,
        dilution=(Volumetric(50), 4),
        name_wizard=SMApellomancer("", "", "", 'r'),
        **Experiment.auto('rack_pos_1', 'A', False, True, True),
        locator=foo,
        abs_optic_spec=OpticalSpecs(30,0.1, 10_000),
        abs_spec_processing=SpectralProcessingSpec(350, 800, take_sigal_near(420, 5)),
        target_abs_signal_init=(100, 200),
        # target_pl_signal_init=300,
        solvent="MeCN",
        source_concentration=1.0
    )

    for test in exp2.span_const_source('rack_pos_2', 'B', 'C', 'D'):
        print(test.source, test.working, test.diluent, test.alt_source)

    print()

    print(exp2.generate_tag(42, 9001))

    print()

    exp3 = Experiment(
        name="test",
        sample_volume=50,
        dilution=(Volumetric(50), 4),
        name_wizard=SMApellomancer("", "", "", 'r'),
        # source_init=('rack_pos_1', 'A1'),
        # diluent_init=('rack_pos_1', 'A2'),
        **Experiment.auto('rack_pos_1', 'A', include_working=None, include_diluent=True),
        locator=foo,
        abs_optic_spec=OpticalSpecs(30,0.1, 10_000),
        abs_spec_processing=SpectralProcessingSpec(350, 800, take_sigal_near(420, 5)),
        target_abs_signal_init=(100, 200),
        # target_pl_signal_init=300,
        solvent="MeCN",
        source_concentration=1.0
    )

    for test in exp3.span_repl_row('rack_pos_2', 3, 4):
        print(test.name, test.source, test.working, test.diluent, test.alt_source)

    print("EXP 3 ==")
    print(repr(exp3))
    print("EXP 3 fin")


    # print(repr(exp2).replace(", ", ",\n\t"))

    # from collections import Counter
    #
    # def format_dc_repr(representation: str):
    #     vlad = Counter()
    #     opening = closing = 0
    #     for substring in representation.split(", "):
    #         vlad.update(substring)
    #         delta = opening - closing
    #         opening = vlad.get("(", 0)
    #         closing= vlad.get(")", 0)
    #         yield "\t"*delta + substring
    #
    # def format_dc_repr_2(_exp: Experiment):
    #     d_exp = asdict(_exp)
    #     d_exp.update(_exp.post_vars)
    #     return pprint.pformat(d_exp, indent=2, sort_dicts=False)
    #
    # print(format_dc_repr_2(exp2))
    #
    # print()
    #
    # common_kwargs = {
    #     'sample_volume': 50.0,
    #     'dilution': (Volumetric(50), 4),
    #     'name_wizard': SMApellomancer("", "", "", 'r'),
    #     'locator': foo,
    #     'abs_optic_spec': OpticalSpecs(count=30, interval=0.1, integration_time=10_000, correct_dark_counts=False,
    #                                    wavelength_calibration=-5),
    #     # 'pl_optic_spec': OpticalSpecs(count=5, interval=0.1, integration_time=2_000_000, correct_dark_counts=True,
    #     #                               wavelength_calibration=-5),
    #     'target_abs_signal_init': (100, 110),
    #     'calibration': Calibration(-0.2440, 0.9765, floor=0.0, meta='Set Feb 4, 2025 from "Manuscript Figures Data.xlsx"')
    # }
    # test = [*Experiment(
    #         name="RhodamineBVial",
    #         **Experiment.auto('pos_1_rack', 'A', include_working=None, include_diluent=True),
    #         abs_spec_processing=SpectralProcessingSpec(350, 800, take_sigal_near(546 - 5, 5)),
    #         pl_spec_processing=None,
    #         solvent="MeOH",
    #         measure_reference="Vial",
    #         source_concentration=0.009,
    #         **common_kwargs
    #     ).span_const_source('pos_1_rack', 'B', 'C')]
    #
    # for t in test:
    #     print(format_dc_repr_2(t))
