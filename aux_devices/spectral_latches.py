"""
EXPERIMENTAL DRAFT - part of the effort to enable the spectrometer to detect droplets.
"""


from abc import ABC, abstractmethod
from enum import Enum
from operator import lt, gt
from typing import Callable, Iterable, Protocol, TypeVar

import numpy as np

from aux_devices.spectra import Spectrum


class Criterion(Enum):
    ALL_GT: (all, gt)
    ALL_LT: (all, lt)
    ANY_GT: (any, gt)
    ANY_LT: (any, lt)


T = TypeVar("T")


class _COMPARABLE(Protocol[T]):
    def __le__(self: T, other: T) -> bool: ...
    def __lt__(self: T, other: T) -> bool: ...
    def __ge__(self: T, other: T) -> bool: ...
    def __gt__(self: T, other: T) -> bool: ...


_GENERAL_OUTER = Callable[[Iterable[object]], bool]
_GENERAL_INNER = Callable[[_COMPARABLE, _COMPARABLE], bool]
GENERAL_CRITERION = tuple[_GENERAL_OUTER, _GENERAL_INNER]


class SpectralLatch(ABC):
    def __init__(self, signal_threshold: float, criterion: Criterion | GENERAL_CRITERION):
        self.threshold = signal_threshold
        self.c_outer, self.c_inner = criterion.value  # type: _GENERAL_OUTER, _GENERAL_INNER

    @abstractmethod
    def __bool__(self) -> bool: ...
    @abstractmethod
    def add_spectra(self, *spectra: Spectrum) -> None: ...


class SignalValueLatch(SpectralLatch):
    def __init__(self, signal_threshold: float, criterion: Criterion | GENERAL_CRITERION):
        super().__init__(signal_threshold, criterion)
        self.spectrum: Spectrum = Spectrum(wavelengths=np.array([]), signal=np.array([]))
        self.reference: Spectrum | None = None

    def add_spectra(self, *spectra: Spectrum) -> None:
        """ If provided multiple Spectra, it will use the last one """
        self.spectrum = spectra[-1]

    def add_reference(self, *spectra: Spectrum):
        """ If provided multiple Spectra, it will use the last one """
        self.reference = spectra[-1]

    def __bool__(self):
        if self.reference is not None:
            using_spectrum = self.spectrum.signal - self.reference.signal
        else:
            using_spectrum = self.spectrum.signal
        return self.c_outer(
            [self.c_inner(np.nanmean(using_spectrum), self.threshold), ]
        )


class SignalVarLatch(SpectralLatch):
    def __init__(self, signal_threshold: float, criterion: Criterion | GENERAL_CRITERION):
        super().__init__(signal_threshold, criterion)
        self.spectrum: Spectrum = Spectrum(wavelengths=np.array([]), signal=np.array([]))
        self.reference: Spectrum | None = None
        self.wavelength_focus_lower_bound: float | None = None
        self.wavelength_focus_upper_bound: float | None = None

    @property
    def _segment_kwargs(self):
        return {
            'lower_bound': self.wavelength_focus_lower_bound,
            'upper_bound': self.wavelength_focus_upper_bound
        }

    def add_spectra(self, *spectra: Spectrum) -> None:
        """ If provided multiple Spectra, it will use the last one """
        self.spectrum = spectra[-1]

    def add_reference(self, *spectra: Spectrum):
        """ If provided multiple Spectra, it will use the last one """
        self.reference = spectra[-1]

    def _calculate_variance(self, spectrum: Spectrum):
        mean = np.nanmean(spectrum.signal)
        variance_segment = spectrum.segment(**self._segment_kwargs)
        bessel_n = np.sum(~np.isnan(variance_segment.signal)) - 1
        partial_variance = np.nansum(np.power(variance_segment.signal - mean, 2)) / bessel_n
        return partial_variance

    def __bool__(self):
        if self.reference is not None:
            using_spectrum = self.spectrum - self.reference
        else:
            using_spectrum = self.spectrum

        standard_deviation = self._calculate_variance(using_spectrum)**0.5

        return self.c_outer(
            [self.c_inner(standard_deviation, self.threshold), ]
        )
