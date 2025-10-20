from typing import NamedTuple
from enum import IntEnum

from aux_devices.ocean_optics_spectrometer import OpticalSpecs
from data_management.common_dp_steps import SpectralProcessingSpec
from workflows.common_abstractions import Dilution
from misc_func import Number


class Mixing(NamedTuple):
    """ tuple(iterations, displacement) """
    iterations: int = 0
    displacement: Number = 0.0


class DilutionPermission(IntEnum):
    NEEDLE_OR_VIAL = 1
    NEEDLE_ONLY = 2
    VIAL_ONLY = 3


class LedgerLine(NamedTuple):
    """
     - name: str
     - concentration: float
     - source: tuple[str, str]
     - working_vial: tuple[str, str]
     - diluent: tuple[str, str]
     - abs_opt_specs: OpticalSpecs
     - absorption: PEAK_ARGS_TYPE
     - abs_target_val: None | float | tuple[float, float]
     - solvent: str
     - dilution_spec: tuple[Dilution, int]
     - pl_opt_specs: OpticalSpecs | None = None
     - photoluminescence: PEAK_ARGS_TYPE | None = None
     - diluting_mode: DilutionPermission = DilutionPermission.NEEDLE_OR_VIAL
    """
    name: str
    concentration: float
    source: tuple[str, str]
    working_vial: tuple[str, str]
    diluent: tuple[str, str]
    abs_opt_specs: OpticalSpecs
    absorption: SpectralProcessingSpec
    abs_target_val: None | float | tuple[float, float]
    solvent: str
    dilution_spec: tuple[Dilution, int]
    pl_opt_specs: OpticalSpecs | None = None
    photoluminescence: SpectralProcessingSpec | None = None
    diluting_mode: DilutionPermission = DilutionPermission.NEEDLE_OR_VIAL

    @property
    def meta(self):
        return self.name, self.concentration, self.solvent

    @staticmethod
    def auto(rack: str, row: str):
        """ provides the source, working_vial, and diluent kwargs

        All will use the form (rack, f"{row}#") where # is 1, 2, 3 for source, working, and diluent, respectively.
        """
        return {
            'source': (rack, f"{row}1"),
            'working_vial': (rack, f"{row}2"),
            'diluent': (rack, f"{row}3"),
        }

    def span_const_source(self, rack: str, *into: str):
        return [
            LedgerLine(**{
                **self._asdict(),
                **{'name': f"{self.name}1"}
            })
                ] + [
            LedgerLine(**{
                **self._asdict(),
                **{'working_vial': (rack, f"{row}2"), 'diluent': (rack, f"{row}3"), 'name': f"{self.name}{j}"}
            })
            for j, row in enumerate(into,start=2)
        ]
