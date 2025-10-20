import datetime
import os
import random
from contextlib import redirect_stdout
from functools import wraps
from io import StringIO
from itertools import islice
from math import cos
from typing import Callable, Generator, Iterable, Literal

from user_interface.style import warning_text


Number = float | int


def silence(func):
    """ Decorator which suppresses output to the console. (Redirects stdout to an anonymous StringIO object for the
    duration of the function call) """
    try:
        func_name = func.__name__
    except:  # noqa: Do not care, this is an embelleshment
        func_name = "Anonymous"

    @wraps(func)
    def inner(*args, **kwargs):
        try:
            _args_repr = "(" + ", ".join([repr(a) for a in args] + [f"{k}={v}" for k, v in kwargs.items()]) + ")"
        except:  # noqa: Do not care, this is an embelleshment
            _args_repr = ""

        print(f"Executing silenced function: {func_name}{_args_repr}")
        with redirect_stdout(StringIO()):
            return func(*args, **kwargs)
    return inner


def safe_project_dir(parent_dir,
                     project_header,
                     exp_header):
    """ Provides {parent dir}/{project header} ({Date} r{Revision#})/{exp_header}_{date} """
    folder_date_tag = datetime.datetime.now().strftime("%b %d")
    file_date_tag = datetime.datetime.now().strftime("%d%m%Y")
    project_dir = os.path.join(parent_dir, f"{project_header} ({folder_date_tag})")
    increment = 0
    while os.path.exists(project_dir):
        msg = warning_text("Folder i={increment} already exists. Add to folder (may overwrite spectra files)? (Y/y-yes, else-no)\n")
        if input(msg).strip().lower() == "y":
            break
        increment += 1
        project_dir = os.path.join(parent_dir, f"{project_header} ({folder_date_tag} r{increment})")
    os.makedirs(project_dir, exist_ok=True)

    return os.path.join(project_dir, f"{exp_header}_{file_date_tag}")


def linear_compliment_space(lower_bound: int, total: int, interval: int):
    """ Provides a linear sampling from lower_bound [inclusive] to (total - lower_bound) [exclusive] with spacing
    specified by interval.  Each pair (a, b) is such that a+b = total.

    Order:
    (low, _) -> (high, _)
    """
    yield from [
        (val, total - val)
        for val in range(lower_bound, total - lower_bound, interval)
    ]


def chebyshev_compliment_space(lower_bound: int | float, total: int | float, n_samples: int):
    """ Provides Chebyshev sampling from lower_bound [inclusive] to (total - lower_bound) [inclusive] with spacing
    determined by the number of samples.  Each pair (a, b) is such that a+b = total

    Order:
    (low, _) -> (high, _)
    """
    mid = total/2
    span = mid - lower_bound
    pi = 3.141_592_653_589_793_115_997_963_468_54
    generator: Callable[[int], float] = lambda k: mid + span*cos((2*k + 1) * pi / (2 * n_samples))
    _temp = [generator(i) for i in range(n_samples)]
    yield from [
        (total - val, val)
        for val in _temp
    ]


def shuffle_study(study: list | tuple | Generator, n_init: int, n_close: int = 0):
    """ Shuffles a list/tuple of studies but can hold the first n_init and last n_close constant. """
    if isinstance(study, Generator):
        study = list(study)
    if n_init + n_close >= len(study) - 1:
        return study
    chunck_sizes = [n_init, len(study) - n_init - n_close, n_close]
    _temp = iter(study)
    _init, _remainder, _tail = [list(islice(_temp, n)) for n in chunck_sizes]
    random.shuffle(_remainder)
    return _init + _remainder + _tail


def format_as_table[T](table: Iterable[Iterable[T]], interspace: int = 1, justification: Literal["L", "R"] = "L") -> str:
    """ Returns a string representation of a nested list of the form:

     - `table` = [row_1, row_2, row_3, ..., row_i]
     - row_n = [col_1, col_2, col_3, ..., col_j]

     Where `interspace` controls the spacing between columns and `justification` controls the alignment of text within
     the columns.
     """
    col_widths: dict[int, int] = {}
    if justification == "R":
        justify = lambda e, j: str(e).rjust(col_widths[j], " ")
    else:
        justify = lambda e, j: str(e).ljust(col_widths[j], " ")

    for row in table:
        for idx, element in enumerate(row):
            col_widths[idx] = max(len(str(element)), col_widths.get(idx, 0))

    _table = [
        [justify(element, idx) for idx, element in enumerate(row)]
        for row in table
    ]
    return "\n".join([(" " * interspace).join(row) for row in _table])
