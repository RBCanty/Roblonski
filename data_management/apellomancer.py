import abc
import datetime
from os import PathLike, path, makedirs
from typing import Literal, Callable, Any, NamedTuple

from user_interface.style import warning_text
from misc_func import Number


ApellOpenMode = Literal['r', 'w', 'a']


def serialize_number(number: Number, use_sci_notation: bool = False) -> str:
    """ Takes an int/float and formats it as a string.  Decimal points are replaced with a hyphen. """
    if isinstance(number, int):
        return str(number)
    if use_sci_notation:
        return f"{number:.2e}".replace(".", "")
    return str(round(number, 3)).replace(".", "-")


def parse_int_string(raw_int: str) -> int:
    """ Converts a string representing an integer into an integer """
    return int(raw_int)


def parse_float_string(raw_number: str) -> float:
    """ Converts a string representing a float (normal or scientific notation) and converts it into a float """
    if "e" in raw_number:
        if raw_number.startswith("-"):
            temp = raw_number[:2] + "." + raw_number[2:]
        else:
            temp = raw_number[0] + "." + raw_number[1:]
        return float(temp)
    else:
        temp = raw_number
        if temp.startswith("-"):
            return -float(temp.replace("-", "."))
        return float(temp.replace("-", "."))


class Apellomancer(abc.ABC):
    """ Abstract class of the Apellomancer (name-wizard) hierarchy. """

    def __init__(self, directory: PathLike | str, project_name: str, file_header: str, mode: ApellOpenMode = 'r'):
        """ Creates a file manager

        :param directory: Where project directories should be
        :param project_name: The name (template) for a project directory
        :param file_header: The file name template
        :param mode: 'r' (Read), use the project name as-is. 'w' (Write), check the project name [requires user input].
          'a' (Append), check the project name and use the first available [no user input].
        """
        self._folder_date_tag_format = "%Y %b %d"  # "2025 Jan 12"
        self._file_date_tag_format = "%d%m%Y"   # "12012025"

        self.directory = directory
        self.project_header = project_name
        if mode == 'w':
            self._check_project_dir()
        elif mode == 'a':
            self._first_available_dir()
        self.file_header = file_header
        self.sub_directory: str | None = None

    def __repr__(self):
        return f"<Apellomancer object for '{self.project_directory}'>"

    def update_sub_directory(self, sub_name: str, mode: Literal['append', 'new'] = 'append'):
        """ Setter for the sub_directory instance attribute; creates the path if it does not already exist.

        mode: (append) if the sub_directory already exists, it is okay to keep using it.  (new) if the sub_directory
        already exists make a new sub_directory of the name f"{sub_name}{integer}" starting from integer=2 to 99. Either
        mode, if the sub_directory does not exist, make it using the provided name (no integer).
        """
        if mode == 'append':
            self.sub_directory = sub_name
            makedirs(self.project_directory, exist_ok=True)
            return
        _suffix: int  = 1
        while _suffix < 100:
            use_suffix = "" if _suffix==1 else str(_suffix)
            self.sub_directory = sub_name + use_suffix
            try:
                makedirs(self.project_directory, exist_ok=False)
                # it's all good
                return
            except OSError:
                _suffix += 1
        else:
            raise TimeoutError(f"Failed to find a valid name for {sub_name}.")

    def _check_project_dir(self):
        folder_date_tag = datetime.datetime.now().strftime(self._folder_date_tag_format)
        temp_header = f"{self.project_header} ({folder_date_tag})"
        project_dir = path.join(self.directory, temp_header)
        increment = 0
        while path.exists(project_dir):
            msg = warning_text(f"Folder ({folder_date_tag} r{increment}) already exists. Add to folder "
                               f"(may overwrite files)? (Y/y-yes, X/x-abort, else-no)\n")
            resp = input(msg).strip().lower()
            if resp == "y":
                break
            elif resp == "x":
                raise KeyboardInterrupt("User aborted definition of directory creation")
            increment += 1
            temp_header = f"{self.project_header} ({folder_date_tag} r{increment})"
            project_dir = path.join(self.directory, temp_header)
        makedirs(project_dir, exist_ok=True)
        self.project_header = temp_header

    def _first_available_dir(self):
        folder_date_tag = datetime.datetime.now().strftime(self._folder_date_tag_format)
        temp_header = f"{self.project_header} ({folder_date_tag})"
        project_dir = path.join(self.directory, temp_header)
        increment = 0
        while path.exists(project_dir):
            increment += 1
            temp_header = f"{self.project_header} ({folder_date_tag} r{increment})"
            project_dir = path.join(self.directory, temp_header)
        makedirs(project_dir, exist_ok=True)
        self.project_header = temp_header

    @property
    def _file_timestamp(self):
        return datetime.datetime.now().strftime(self._file_date_tag_format)

    @property
    def project_directory(self):
        """ If a sub_directory is defined, this will include it """
        if self.sub_directory is None:
            return path.join(self.directory, self.project_header)
        else:
            return path.join(self.directory, self.project_header, self.sub_directory)

    def make_full_path(self, file_name: str, extension: str = None):
        """ If a sub_directory is defined, this will include it """
        if (extension is not None) and not extension.startswith("."):
            extension = "." + extension
        if extension is None:
            extension = ""
        return path.join(self.project_directory, file_name + extension)

    @abc.abstractmethod
    def make_file_name(self, *args, **kwargs) -> str:
        ...

    @staticmethod
    @abc.abstractmethod
    def parse_file_name(*args, **kwargs) -> Any:
        ...


class SequentialApellomancer(Apellomancer):
    def __init__(self, directory: PathLike | str, project_name: str, file_header: str, mode: ApellOpenMode = 'r'):
        """ Creates a file manager (Base class; needs make_file_name() and parse_file_name())

        :param directory: Where project directories should be
        :param project_name: The name (template) for a project directory
        :param file_header: The file name template
        :param mode: 'r' (Read), use the project name as-is. 'w' (Write), check the project name [requires user input].
          'a' (Append), check the project name and use the first available [no user input].
        """
        super().__init__(directory, project_name, file_header, mode)

    @property
    def _file_timestamp(self):
        return datetime.datetime.now().strftime("%Y-%m-%d--%H-%M-%S")

    def make_file_name(self,
                       spec: Literal['PL', 'ABS'] = "PL",
                       seq: int = 0):
        return f"{self.file_header}__{self._file_timestamp}_{spec}_i{seq}"

    @staticmethod
    def parse_file_name(file_name: str):
        *_, timestamp, spec, i_seq = file_name.split('_')
        # return None SVSpecDescription(
        #     timestamp=timestamp,
        #     spectral_type=spec,
        #     instance=parse_int_string(i_seq[1:]),
        #     catalyst=None,
        #     quencher=None,
        #     diluent=None,
        #     mixing_iteration=None
        # )
