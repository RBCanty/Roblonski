from itertools import pairwise
from typing import Self, TextIO, Iterable, TYPE_CHECKING, Union
from collections import deque
if TYPE_CHECKING:
    from _typeshed import SupportsWrite  # noqa
Stream = Union["SupportsWrite[str]", TextIO]

import numpy as np


class Spectrum:
    """ Holder for a pair of wavelengths and signal values.

     - Unpacks as wavelength-signal pairs.
     - Addition/Subtraction with a scalar shifts the signal, addition/subtraction with another Spectrum adds/subtracts
       the signals.  When operating on multiple spectra, the wavelengths must match.
     - Multiplication with a scalar scales the signal.
     - Division is accomplished via multiplication with (1/divisor).
    """
    def __init__(self, wavelengths: np.ndarray, signal: np.ndarray):
        self.wavelengths = wavelengths
        self.signal = signal
        # Should we also include information such as integration time and averaging details?

    def __iter__(self):
        iterable = (self.wavelengths, self.signal)
        return zip(*iterable)

    def segment(self, *, lower_bound: float = None, upper_bound: float = None) -> Self:
        """ Creates a smaller Spectrum object with a restricted wavelength range """
        if lower_bound is None:
            lower_bound = float("-inf")
        if upper_bound is None:
            upper_bound = float("+inf")
        mask = np.where((lower_bound <= self.wavelengths) & (self.wavelengths < upper_bound))
        return Spectrum(
            self.wavelengths[mask],
            self.signal[mask]
        )

    def signal_at(self, wavelength: float):
        """ Returns the signal closest to the provided wavelength. If the wavelength is perfectly between two values
         in the array, it will return the average. (returns a float) """
        left_idx = np.searchsorted(self.wavelengths, wavelength, side='left')
        if left_idx == len(self.wavelengths):
            return self.signal[left_idx - 1]
        if left_idx == 0:
            return self.signal[left_idx]
        # idx must be 1--(Len - 1):
        _wv1, _wv2 = self.wavelengths[left_idx - 1], self.wavelengths[left_idx]
        if wavelength - _wv1 < _wv2 - wavelength:
            return self.signal[left_idx - 1]
        elif wavelength - _wv1 == _wv2 - wavelength:
            return (self.signal[left_idx - 1] + self.signal[left_idx])/2
        return self.signal[left_idx]

    def signal_near(self, wavelength: float, tolerance: float | tuple[float, float]):
        """ Returns the peak signal with +/-tolerance of the provided wavelength. (returns a float) """
        if not isinstance(tolerance, tuple):
            tolerance = (tolerance, tolerance)
        temp_spectrum = self.segment(lower_bound=wavelength - tolerance[0], upper_bound=wavelength + tolerance[1])
        return np.nanmax(temp_spectrum.signal)

    def peak_position_near(self, wavelength: float, tolerance: float | tuple[float, float]):
        """ Returns the wavelength at peak signal with +/-tolerance of the provided wavelength. (returns a float) """
        if not isinstance(tolerance, tuple):
            tolerance = (tolerance, tolerance)
        temp_spectrum = self.segment(lower_bound=wavelength - tolerance[0], upper_bound=wavelength + tolerance[1])
        return temp_spectrum.wavelengths[np.nanargmax(temp_spectrum.signal)]

    def stick(self, wavelength: float) -> Self:
        """ Returns a Spectrum with a single wavelength-signal pair. """
        return Spectrum(
            np.array([wavelength, ]),
            np.array([self.signal_at(wavelength), ])
        )

    def sticks(self, *wavelengths: float) -> Self:
        """ Returns a Spectrum with specific wavelength-signal pairs. """
        return Spectrum(
            np.array(wavelengths),
            np.array([self.signal_at(wavelength) for wavelength in wavelengths])
        )

    def wavelengths_at(self, threshold: float) -> list[float]:
        """ Provides the wavelengths at or just below (when crossing) the threshold signal value. """
        wavelengths: set[float] = set()
        for (left_wv, left_s), (right_wv, right_s) in pairwise(self):
            # Rising
            if (left_s <= threshold) and (right_s >= threshold):
                wavelengths.add(left_s)
                continue
            # Falling
            if (left_s >= threshold) and (right_s <= threshold):
                wavelengths.add(right_s)
                continue
        return sorted(list(wavelengths))

    def integral(self) -> float:
        """ Provides the integrated area (uses numpy's trapz() method) """
        return np.trapz(y=self.signal, x=self.wavelengths)

    def integrate(self, wv_lb: float, wv_ub: float) -> float:
        """ Shorthand for: Spectrum.segment(**bounds).integral() """
        integral_segment = self.segment(lower_bound=wv_lb, upper_bound=wv_ub)
        return integral_segment.integral()

    def threshold(self, *, lower_bound: float = None, upper_bound: float = None) -> Self:
        """ Creates a smaller Spectrum object comprising only values between two signal values
        The resulting Spectrum may no longer be contiguous in wavelength. """
        if lower_bound is None:
            lower_bound = float("-inf")
        if upper_bound is None:
            upper_bound = float("+inf")
        mask = np.where((lower_bound <= self.signal) & (self.signal < upper_bound))
        return Spectrum(
            self.wavelengths[mask],
            self.signal[mask]
        )

    def __add__(self, other: Self | int | float) -> Self:
        if isinstance(other, (int, float)):
            return Spectrum(
                self.wavelengths.copy(),
                self.signal.copy() + other
            )
        if not isinstance(other, Spectrum):
            raise ValueError(f"Cannot add Spectrum and type '{type(other)}'")
        if not np.array_equal(self.wavelengths, other.wavelengths):
            raise ValueError(f"Cannot add two Spectrum objects with different wavelengths")
        return Spectrum(
            self.wavelengths.copy(),
            self.signal + other.signal
        )

    def __radd__(self, other: Self | int | float) -> Self:
        return self + other

    def __sub__(self, other: Self | int | float) -> Self:
        return self + -1 * other

    def __mul__(self, other: Self | int | float) -> Self:
        if isinstance(other, (int, float)):
            return Spectrum(
                self.wavelengths.copy(),
                other * self.signal.copy()
            )
        if not isinstance(other, Spectrum):
            raise ValueError(f"Cannot multiply Spectrum and type '{type(other)}'")
        if not np.array_equal(self.wavelengths, other.wavelengths):
            raise ValueError(f"Cannot multiply two Spectrum objects with different wavelengths")
        return Spectrum(
            self.wavelengths.copy(),
            np.multiply(self.signal, other.signal)
        )

    def __rmul__(self, other: Self | int | float) -> Self:
        return self * other

    def intersection(self, other: Self) -> tuple[Self, Self]:
        """ Returns copies of Spectrum segments where the two Spectra overlap """
        if not isinstance(other, Spectrum):
            raise ValueError(f"Cannot intersect a Spectrum with a {type(other)}")
        if (not self.wavelengths.size) or (not other.wavelengths.size):
            blank = Spectrum(wavelengths=np.array([]), signal=np.array([]))
            return blank, blank.copy()
        if np.isnan(self.wavelengths).any() or np.isnan(other.wavelengths).any():
            raise ValueError(f"Cannot intersect Spectra with NaN in their Wavelengths")
        # Arrays are guaranteed to have at least one element each and not contain NaNs
        #   Ergo, np.nanmax and np.nanmin should return floats
        intersect_lb = max(np.nanmin(self.wavelengths), np.nanmax(self.wavelengths))
        intersect_ub = min(np.nanmin(other.wavelengths), np.nanmax(other.wavelengths))
        self_segment = self.segment(lower_bound=intersect_lb, upper_bound=intersect_ub)
        other_segment = other.segment(lower_bound=intersect_lb, upper_bound=intersect_ub)
        if not np.array_equal(self_segment.wavelengths, other_segment.wavelengths):
            print(f"Warning, intersection has created segments with inequivalent wavelength axes")
        return self_segment, other_segment

    def save_to_file(self, file_path: str):
        """ Writes to a file using ', ' as the delimiter and '\\\\n' between each wavelength-signal pair.
         Provides no header. """
        with open(file_path, 'w+') as out_file:
            for _w, _s in self:
                out_file.write(f"{_w}, {_s}\n")

    @classmethod
    def load_from_file(cls, file_path: str, n_header_rows: int = 0) -> Self:
        """ Reads a file of the form 'wavelength, signal'-per line and returns a Spectrum """
        with open(file_path, 'r') as input_file:
            file_iterator = iter(input_file)
            [next(file_iterator, None) for _ in range(n_header_rows)]
            data = [list(map(float, line.split(", "))) for line in file_iterator if line]
            _w, _s = zip(*data)
        return cls(np.fromiter(_w, dtype=np.float64), np.fromiter(_s, dtype=np.float64))

    def copy(self) -> Self:
        """ Provides a copy of a spectrum """
        return Spectrum(
            self.wavelengths.copy(),
            self.signal.copy()
        )


def intensity_to_absorbance(wavelengths: np.ndarray, light_reference: np.ndarray, dark_reference: np.ndarray, broadband_intensity: np.ndarray):
    """ Provides the spectrum (wavelengths in nm and absorbance in mAU) """
    try:
        true_sample_intensity = broadband_intensity - dark_reference
        true_reference_intensity = light_reference - dark_reference
    except TypeError:
        raise RuntimeError(f"Cannot convert to Absorbance without light and dark references")
    transmittance = np.divide(
        true_sample_intensity,
        true_reference_intensity
    )
    absorbance = -np.log10(transmittance)
    absorbance[absorbance == np.inf] = np.nan
    return Spectrum(
        wavelengths=wavelengths,
        signal=1000 * absorbance
    )


class SpectrumFactory:
    """ used to build a Spectrum point-by-point. """
    def __init__(self):
        self.x = []
        self.y = []

    def add_point(self, x, y):
        self.x.append(x)
        self.y.append(y)

    def create_spectrum(self) -> Spectrum:
        x = np.array(self.x)
        y = np.array(self.y)
        spec = Spectrum(wavelengths=x, signal=y)
        self.x = []
        self.y = []
        return spec


class RunningSpectra:
    """ A collection of Spectra with a fixed size (new spectra kick out the oldest spectra). """
    def __init__(self, size: int):
        self.spectra: deque[Spectrum] = deque(maxlen=size)

    def __len__(self):
        return len(self.spectra)

    def add_spectrum(self, spectrum: Spectrum):
        self.spectra.append(spectrum)

    def average_value(self) -> Spectrum:
        """ Provides a signal-averaged spectrum """
        n_spectra = len(self.spectra)
        if n_spectra < 1:
            raise ValueError("Cannot take average of empty deque")
        spectral_iterator = iter(self.spectra)
        running_sum = next(spectral_iterator).copy()
        for spectrum in spectral_iterator:
            running_sum = running_sum + spectrum
        return running_sum * (1/n_spectra)

    def weighted_average(self, weights: list[float | int] = None):
        """ Provides a weighted signal-averaged spectrum using `weights`.

         - If `weights` is None, all weights are assumed equal (RunningSpectra.average_value() is called)
         - If |`weights`| < the number of spectra, the remaining weights are assumed 0.
         - If |`weights`| > the number of spectra, the excess weights are ignored (the weights are renormalized)
         - If `weights` is empty, it is replaced by [1.0, ]
        """
        if weights is None:
            return self.average_value()

        n_spectra = len(self.spectra)
        if n_spectra < 1:
            raise ValueError("Cannot take average of empty deque")

        n_weights = len(weights)
        if n_weights < 1:
            weights = [1.0, ]
        weights = weights[:n_spectra]
        if n_weights != len(weights):
            _w_sum = sum(weights)
            weights = [w/_w_sum for w in weights]

        spectral_iterator = zip(self.spectra, weights)
        initial = next(spectral_iterator)
        return sum([w*s for s, w in spectral_iterator], start=initial[1] * initial[0])

    def create_geometric_weighting(self, ratio: float, n: int = None):
        """ Generates a list which can be used in weighted_average() for the weights based on a geometric series.
        :param ratio: A scalar which generates the raw weights [1, ratio, ratio^2, ratio^3, ...]
        :param n: How many terms to include. None will use the number of spectra loaded (at call time) --
                  i.e., `len(self.spectra)`. Negative values will use the max number of spectra possible --
                  i.e., `self.spectra.maxlen`.
        """
        if n is None:
            n = len(self.spectra)
        if n < 0:
            n = self.spectra.maxlen
        weights = [(ratio**i) for i in range(n)]
        total_weight = sum(weights)
        return [w/total_weight for w in weights]


class ZipSpectra:
    """ Organizes related spectra (Wavelength, Dark Reference, Light Reference, Signal) """
    class NullIter:
        def __init__(self, null_value=""):
            self._null = null_value

        def __next__(self):
            return self._null

        def __iter__(self):
            return self

    def __init__(self, spectrum: Spectrum, sub_spectrometer):
        """ Creates a ZipSpectra and attempts to load (Wavelength, Dark Reference, Light Reference, Signal).
        The `sub_spectrometer` must have attributes `light_reference` and `dark_reference` which are of
        type None | numpy.ndarray"""
        self.wavelengths = spectrum.wavelengths
        self.signal = spectrum.signal
        self.light_ref: np.ndarray | None = sub_spectrometer.light_reference
        self.dark_ref: np.ndarray | None = sub_spectrometer.dark_reference
        if self.light_ref is None:
            self.light_ref = self.NullIter()
        if self.dark_ref is None:
            self.dark_ref = self.NullIter()

    def __iter__(self):
        return zip(self.wavelengths, self.dark_ref, self.light_ref, self.signal)

    def print(self, file_stream: Stream = None, flush=False):
        """ Prints (to a file if `file_stream` is a Stream; to the console if None) a ', '-delimited file of
        wavelength, dark-reference, light-reference, and signal. The file includes a header.

        The `flush` kwarg is passed into print(). """
        print("W, D, L, S", file=file_stream, flush=flush)
        for w, d, l, s in self:
            print(w, d, l, s, sep=", ", file=file_stream, flush=flush)

    @classmethod
    def read(cls, file_path: str, n_header_rows: int = 1) -> Self:
        """ Reads a file generated by ZipSpecta.print() """
        with open(file_path, 'r') as input_file:
            file_iterator = iter(input_file)
            [next(file_iterator, None) for _ in range(n_header_rows)]
            data = [list(map(float, line.split(", "))) for line in file_iterator if line]
            _w, _d, _l, _s = zip(*data)
        major_spectrum = Spectrum(np.fromiter(_w, dtype=np.float64), np.fromiter(_s, dtype=np.float64))
        dark_ref = np.fromiter(_d, dtype=np.float64)
        light_ref = np.fromiter(_l, dtype=np.float64)
        sub_spec = type('', (), {})()
        sub_spec.light_reference = light_ref
        sub_spec.dark_reference = dark_ref
        return cls(major_spectrum, sub_spec)


class SpectraStack:
    """ Container for multiple spectra """
    def __init__(self, *spectra: Spectrum):
        """ Provide Spectrum objects as vargs """
        if not spectra:
            self.spectra = []
            self.wavelengths = np.empty_like([])
        else:
            self.spectra = list(spectra)
            self.wavelengths = spectra[0].wavelengths

    def __iter__(self):
        return zip(self.wavelengths.tolist(), *[s.signal.tolist() for s in self.spectra])

    def __getitem__(self, item):
        return self.spectra[item]

    def append(self, spectrum: Spectrum):
        if not self.wavelengths.any():
            self.wavelengths = spectrum.wavelengths
        self.spectra.append(spectrum)

    def __add__(self, other: Self | Spectrum):
        if isinstance(other, SpectraStack):
            return SpectraStack(*self.spectra, *other.spectra)
        if isinstance(other, Spectrum):
            return SpectraStack(*self.spectra, other)
        raise ValueError(f"Unable to add/concatenate a SpectraStack with a {type(other)}")

    def print(self, file_stream: Stream = None, flush=False, header: Iterable[str] = None):
        if header is not None:
            print(*header, sep=", ", file=file_stream, flush=flush)
        for w, *s in self:
            print(w, *s, sep=", ", file=file_stream, flush=flush)

    def segment(self, *, lower_bound: float = None, upper_bound: float = None) -> Self:
        """ Creates a smaller SpectraStack object with a restricted wavelength range """
        return SpectraStack(*[s.segment(lower_bound=lower_bound, upper_bound=upper_bound) for s in self.spectra])

    @classmethod
    def read(cls, file_path: str, n_header_rows: int = 0) -> Self:
        """ Reads a file generated by SpectraStack.print() """
        with open(file_path, 'r') as input_file:
            file_iterator = iter(input_file)
            [next(file_iterator, None) for _ in range(n_header_rows)]
            data = [list(map(float, line.split(", "))) for line in file_iterator if line]
            _w, *_s = zip(*data)
        wavelengths = np.fromiter(_w, dtype=np.float64)
        spectra = [Spectrum(wavelengths, np.fromiter(__s, dtype=np.float64)) for __s in _s]
        return cls(*spectra)


if __name__ == '__main__':
    from random import random

    def make_spectrum():
        def gauss(_x, _a, _b, _c):
            return _a * 2.71828 ** -((_x - _b)**2 / (2 * _c**2))

        x_axis = [
            n + random()
            for n in range(1000)
        ]
        y_axis = [
            gauss(x, 1, 200, 5)
            + gauss(x, 0.5, 575, 15)
            + gauss(x, 1.25, 600, 10)
            + gauss(x, 0.25, 800, 6)
            + gauss(x, 0.25, 825, 7)
            + x / 5_000  # baseline drift
            + random() / 200  # noise
            + (random()*(random() - 0.5) * abs(x - 500)/500) / 10
            for x in x_axis
        ]

        return Spectrum(
            np.asarray(x_axis),
            np.asarray(y_axis)
        )

    def verify_spectra_save_load():
        my_spectrum = make_spectrum()
        my_spectrum.save_to_file("./sim_spectra.spec")
        reloaded_spectrum = Spectrum.load_from_file("./sim_spectra.spec")
        print(my_spectrum.signal)
        print(reloaded_spectrum.signal)

    def verify_making_a_stack():
        my_spectrum = make_spectrum()

        test_stack = SpectraStack()
        print("should be empty!", test_stack.wavelengths, test_stack.spectra)
        test_stack.append(my_spectrum + 10)
        test_stack.append(my_spectrum * 2 - 100)
        test_stack.append(my_spectrum)

        test_stack.print()

    def verify_stack_load():
        my_spectrum = SpectraStack.read("./test.spec", n_header_rows=0)  # generated in signal_processing.py
        my_spectrum.print()


    verify_stack_load()
