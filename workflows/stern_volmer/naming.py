from dataclasses import dataclass
from os import PathLike, path
from typing import Callable, Literal

from data_management.apellomancer import Apellomancer, ApellOpenMode, serialize_number, parse_int_string, \
    parse_float_string
from misc_func import Number


@dataclass
class SVSpecDescription:
    """ Description of a Stern-Volmer--style experiment.

     - timestamp: str
     - spectral_type: "PL" or "ABS"
     - instance: int
     - catalyst: Number | None
     - quencher: Number | None
     - diluent: Number | None
     - mixing_iteration: int | None
    """
    timestamp: str
    spectral_type: str
    instance: int
    catalyst: Number | None
    quencher: Number | None
    diluent: Number | None
    mixing_iteration: int | None

    def apply_calibration(self, nom2actual: Callable[[Number], float]):
        return SVSpecDescription(
            timestamp=self.timestamp,
            spectral_type=self.spectral_type,
            instance=self.instance,
            catalyst=None if self.catalyst is None else nom2actual(self.catalyst),
            quencher=None if self.quencher is None else nom2actual(self.quencher),
            diluent=None if self.diluent is None else nom2actual(self.diluent),
            mixing_iteration=self.mixing_iteration,
        )

    @property
    def total_volume(self):
        return sum([_v for _v in [self.catalyst, self.quencher, self.diluent] if _v is not None], start=0)


class SVApellomancer(Apellomancer):
    def __init__(self, directory: PathLike | str, project_name: str, file_header: str, mode: ApellOpenMode  = 'r'):
        """ Creates a file manager

        :param directory: Where project directories should be
        :param project_name: The name (template) for a project directory
        :param file_header: The file name template
        :param mode: 'r' (Read), use the project name as-is. 'w' (Write), check the project name [requires user input].
          'a' (Append), check the project name and use the first available [no user input].
        """
        super().__init__(directory, project_name, file_header, mode)

    def __repr__(self):
        return f"<SVApellomancer object for '{self.project_directory}'>"

    def make_file_name(self,
                       cat: Number = None,
                       quench: Number = None,
                       dil: Number = None,
                       mix: int = None,
                       spec: Literal['PL', 'ABS'] = "PL",
                       seq: int = 0):
        tag = f"__{self._file_timestamp}_{spec}_i{seq}"
        if cat is not None:
            tag += f"_c{serialize_number(cat)}"
        if quench is not None:
            tag += f"_q{serialize_number(quench)}"
        if dil is not None:
            tag += f"_d{serialize_number(dil)}"
        if mix is not None:
            tag += f"_m{mix}"
        return self.file_header + tag

    @staticmethod
    def parse_file_name(file_path: str) -> SVSpecDescription:
        full_file_name = path.basename(file_path)
        file_name, _ = path.splitext(full_file_name)
        *_, tag = file_name.split('__')
        timestamp, spec, *vargs = tag.split('_')
        seq = cat = quench = dil = mix = None
        for (h, *v) in vargs:
            match h:
                case 'i':
                    seq = parse_int_string("".join(v))
                case 'c':
                    cat = parse_float_string("".join(v))
                case 'q':
                    quench = parse_float_string("".join(v))
                case 'd':
                    dil = parse_float_string("".join(v))
                case 'm':
                    mix = parse_int_string("".join(v))
        return SVSpecDescription(
            timestamp=timestamp,
            spectral_type=spec,
            instance=seq,
            catalyst=cat,
            quencher=quench,
            diluent=dil,
            mixing_iteration=mix
        )
