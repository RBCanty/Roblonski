from dataclasses import dataclass
from os import PathLike, path
from typing import Literal

from data_management.apellomancer import Apellomancer, ApellOpenMode, serialize_number, parse_int_string, \
    parse_float_string
from misc_func import Number


@dataclass
class SMSpecDescription:
    """ Description of a serial dilution experiment.

     - timestamp: str
     - instance: int
     - dil_seq: int
     - dye_concentration: Number | None
     - total_volume: Number | None
     - mixing_displacement: Number | None
     - mixing_iteration: int | None
     - mode: str["ABS", "PL"]
     - flag: str['EXP', 'CHK', 'REF']
    """
    timestamp: str
    instance: int
    dil_seq: int
    dye_concentration: Number | None
    total_volume: Number | None
    mixing_displacement: Number | None
    mixing_iteration: int | None
    mode: Literal["ABS", "PL"] | None
    flag: Literal['EXP', 'CHK', 'REF'] | None = "EXP"


class SMApellomancer(Apellomancer):
    def __init__(self, directory: PathLike | str, project_name: str, file_header: str, mode: ApellOpenMode = 'r'):
        """ Creates a file manager

        :param directory: Where project directories should be
        :param project_name: The name (template) for a project directory
        :param file_header: The file name template
        :param mode: 'r' (Read), use the project name as-is. 'w' (Write), check the project name [requires user input].
          'a' (Append), check the project name and use the first available [no user input].
        """
        super().__init__(directory, project_name, file_header, mode)

    def __repr__(self):
        return f"<SMApellomancer object for '{self.project_directory}'>"

    def make_file_name(self,
                       spec: Literal['ABS', 'PL'],
                       dye_concentration: Number = None,
                       total_volume: Number = None,
                       n_mix: int = None,
                       mix_disp: Number = None,
                       instance_idx: int = 0,
                       dil_seq_idx: int = None,
                       flag: Literal['EXP', 'CHK', 'REF'] = None):
        tag = f"__{self._file_timestamp}_a{spec}"
        if instance_idx is not None:
            tag += f"_i{instance_idx}"
        if flag is not None:
            tag += f"_e{flag}"
        if dil_seq_idx is not None:
            tag += f"_s{dil_seq_idx}"
        if dye_concentration is not None:
            tag += f"_d{serialize_number(dye_concentration, True)}"
        if total_volume is not None:
            tag += f"_t{serialize_number(total_volume)}"
        if n_mix is not None:
            tag += f"_m{n_mix}"
        if mix_disp is not None:
            tag += f"_v{serialize_number(mix_disp)}"
        return self.file_header + tag

    @staticmethod
    def parse_file_name(file_path: str) -> SMSpecDescription:
        full_file_name = path.basename(file_path)
        file_name, _ = path.splitext(full_file_name)
        *_, tag = file_name.split('__')
        timestamp, spec, *vargs = tag.split('_')
        spec = instance_idx = dil_seq_idx = dye_concentration = total_volume = mdisp = mix = flag = None
        for (h, *v) in vargs:
            value = "".join(v)
            match h:
                case 'a':
                    spec: Literal['ABS', 'PL'] | None = value  # noqa
                case 'i':
                    instance_idx = parse_int_string(value)
                case 'e':
                    flag: Literal['EXP', 'CHK', 'REF'] | None = value  # noqa
                case 's':
                    dil_seq_idx = parse_int_string(value)
                case 'd':
                    dye_concentration = parse_float_string(value)
                case 't':
                    total_volume = parse_float_string(value)
                case 'm':
                    mix = parse_int_string(value)
                case 'v':
                    mdisp = parse_float_string(value)
        return SMSpecDescription(
            timestamp=timestamp,
            instance=instance_idx,
            dil_seq=dil_seq_idx,
            dye_concentration=dye_concentration,
            total_volume=total_volume,
            mixing_displacement=mdisp,
            mixing_iteration=mix,
            mode=spec,
            flag=flag
        )
