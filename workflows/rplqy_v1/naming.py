from dataclasses import dataclass
from os import PathLike, path
from typing import Literal

from data_management.apellomancer import Apellomancer, ApellOpenMode, serialize_number, parse_int_string, \
    parse_float_string
from misc_func import Number


@dataclass
class RPLQYSpecDescription:
    """ Description of a Relative PLQY experiment.

     - timestamp: str
     - instance: int
     - dil_seq: int
     - dye_concentration: Number | None
     - total_volume: Number | None
     - mixing_iteration: int | None
    """
    timestamp: str
    instance: int
    dil_seq: int
    dye_concentration: Number | None
    total_volume: Number | None
    mixing_iteration: int | None


class RPLQYApellomancer(Apellomancer):
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
        return f"<RPLQYApellomancer object for '{self.project_directory}'>"

    def make_file_name(self,
                       spec: Literal['ABS', 'PL'],
                       dye_concentration: Number = None,
                       total_volume: Number = None,
                       mix: int = None,
                       instance_idx: int = 0,
                       dil_seq_idx: int = None):
        tag = f"__{self._file_timestamp}_{spec}"
        if instance_idx is not None:
            tag += f"_i{instance_idx}"
        if dil_seq_idx is not None:
            tag += f"_s{dil_seq_idx}"
        if dye_concentration is not None:
            tag += f"_d{serialize_number(dye_concentration, True)}"
        if total_volume is not None:
            tag += f"_t{serialize_number(total_volume)}"
        if mix is not None:
            tag += f"_m{mix}"
        return self.file_header + tag

    @staticmethod
    def parse_file_name(file_path: str) -> RPLQYSpecDescription:
        full_file_name = path.basename(file_path)
        file_name, _ = path.splitext(full_file_name)
        *_, tag = file_name.split('__')
        timestamp, spec, *vargs = tag.split('_')
        instance_idx = dil_seq_idx = dye_concentration = total_volume = mix = None
        for (h, *v) in vargs:
            match h:
                case 'i':
                    instance_idx = parse_int_string("".join(v))
                case 's':
                    dil_seq_idx = parse_int_string("".join(v))
                case 'd':
                    dye_concentration = parse_float_string("".join(v))
                case 't':
                    total_volume = parse_float_string("".join(v))
                case 'm':
                    mix = parse_int_string("".join(v))
        return RPLQYSpecDescription(
            timestamp=timestamp,
            instance=instance_idx,
            dil_seq=dil_seq_idx,
            dye_concentration=dye_concentration,
            total_volume=total_volume,
            mixing_iteration=mix
        )
