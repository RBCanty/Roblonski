import os
from typing import Callable, Iterable, NamedTuple, Sequence

import numpy as np

from aux_devices.signal_processing import detect_peaks
from aux_devices.spectra import Spectrum


def get_files(directory: str, key: str = None):
    """ Gets all files in a directory (can downselect to those with `key` in their names, if `key` is specified) """
    files: list[str] = []
    for *_, file_names in os.walk(directory):
        for file_name in file_names:
            if key and (key not in file_name):
                continue
            files.append(os.path.join(directory, file_name))
            print(f"Grabbed {file_name}")
    return files


class SpectralProcessingSpec(NamedTuple):
    """ Specifications for spectral processing.

     - wavelength_lower_limit: Allows the analyzed region to be a subset of the entire spectrum (None = no lower limit)
     - wavelength_upper_limit: Allows the analyzed region to be a subset of the entire spectrum (None = no upper limit)
     - analysis: A method (or sequence of methods) which is/are called on the segment of the spectrum between the
         lower and upper bounds. The first analysis in the sequence is accessible via the `primary_analysis` property.
     """
    wavelength_lower_limit: float | None
    wavelength_upper_limit: float | None
    analysis: Callable[[Spectrum], float] | Sequence[Callable[[Spectrum], float]]

    @property
    def primary_analysis(self) -> Callable[[Spectrum], float]:
        """ Provides the first analysis method specified by self.analysis """
        if isinstance(self.analysis, Sequence):
            return self.analysis[0]
        return self.analysis

    def tag_repr(self):
        """ Provides details about the analysis which can be saved alongside the data. """
        line_1 = f"Lambda_Range, {self.wavelength_lower_limit}, {self.wavelength_upper_limit}\n"
        if isinstance(self.analysis, Sequence):
            line_n = [f"FOLD, {type(analysis)}:{getattr(analysis, '__name__', '<Anonymous>')}" for analysis in self.analysis]
        else:
            line_n = [f"FOLD, {type(self.analysis)}:{getattr(self.analysis, '__name__', '<Anonymous>')}", ]
        return line_1 + "\n" + "\n".join(line_n)

    def segment_kwargs(self):
        """ Returns a dictionary with the lower and upper bounds which matches the `Spectrum.segment()` method. """
        return {'lower_bound': self.wavelength_lower_limit, 'upper_bound': self.wavelength_upper_limit}


# ## ANALYSIS METHODS ## #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### #### ####

def take_sigal_at(wv: float):
    """ Created a partial function of which takes a Spectrum object (s) and returns s.signal_at(wv) """
    _func: Callable[[Spectrum], float] = lambda _s: _s.signal_at(wv)
    _func.__name__ = f"take_signal_at({wv})"
    return _func


def take_sigal_near(wv: float, tol: float):
    """ Created a partial function of which takes a Spectrum object (s) and returns s.signal_near(wv, tol) """
    _func: Callable[[Spectrum], float] = lambda _s: _s.signal_near(wv, tol)
    _func.__name__ = f"take_signal_near({wv}; {tol})"
    return _func


def find_wavelength_of_max_signal(wv: float, tol: float):
    """ Created a partial function of which takes a Spectrum object (s) and returns s.peak_position_near(wv, tol) """
    _func: Callable[[Spectrum], float] = lambda _s: _s.peak_position_near(wv, tol)
    _func.__name__ = f"find_wavelength_of_max_signal({wv}; {tol})"
    return _func


def take_integral(wv_lb: float, wv_ub: float):
    """ Created a partial function of which takes a Spectrum object (s) and returns s.integrate(wv_lb, wv_ub) """
    _func: Callable[[Spectrum], float] = lambda _s: _s.integrate(wv_lb, wv_ub)
    _func.__name__ = f"integrate({wv_lb}; {wv_ub})"
    return _func


def take_max_signal():
    """ Created a partial function of which takes a Spectrum object (s) and returns np.nanmax(s.signal) """
    _func: Callable[[Spectrum], float] = lambda _s: np.nanmax(_s.signal)
    _func.__name__ = f"numpy.nanmax"
    return _func


def take_most_prominent_peak(filter_sigma: float | Iterable = 3):
    """ Created a partial function of which takes a Spectrum object (s) and returns
    max(detect_peaks(s, filter_sigma)[1], default=0.0) / 1000

    detect_peaks from aux_devices.signal_processing.py """
    _func: Callable[[Spectrum], float] = lambda _s: max(detect_peaks(_s, filter_sigma)[1], default=0.0) / 1000
    _func.__name__ = f"detect_peaks({filter_sigma=})"
    return _func
