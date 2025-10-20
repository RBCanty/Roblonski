from itertools import batched
from typing import Iterable, Literal

import numpy as np
import pandas as pd
import peakutils
from scipy import sparse
import scipy.ndimage as sn
import scipy.signal as ss
from scipy.integrate import simpson
from scipy.optimize import curve_fit
from scipy.sparse.linalg import spsolve

from aux_devices.spectra import Spectrum


def gauss(x, amplitude, center, sigma):
    """ y = amplitude * (2.71828 ** -((x - center)**2 / (2 * sigma**2))"""
    return amplitude * (2.71828 ** -((x - center)**2 / (2 * sigma**2)))


def multi_gauss(x, *g):
    """ g: via gauss(x, *_g) for _g in g"""
    return sum([gauss(x, *_g) for _g in g], start=0.0)


def measure_baseline(spectrum: Spectrum, baseline_polynomial_degree: int = 1) -> Spectrum:
    """ Applies a polynomial baseline estimate via peakutils.baseline. (+/-Inf --> 4000 mOD) """
    y_interp = pd.Series(spectrum.signal).replace([np.Inf, -np.Inf], 4000).interpolate().values
    baseline = peakutils.baseline(y_interp, baseline_polynomial_degree, max_it=100)
    return Spectrum(spectrum.wavelengths.copy(), baseline)


def measure_asls_baseline(
        spectrum: Spectrum,
        p_asym: float = 0.01,
        p_fit_smooth_1: float = 1e-4,
        p_fit_smooth_2: float = 1e6,
        tol_r: float = 0.001,
        max_it: int = 50
) -> tuple[Spectrum, float]:
    """
    He, S., et al. Baseline correction for raman spectra using an improved asymmetric least squares method,
    Analytical Methods, 2014, 6(12), 4402-4407

    :param spectrum: Spectrum in which to calculate baseline spectrum
    :param p_asym: (0 - ignore data above / 1 - ignore data below)
    :param p_fit_smooth_1:
    :param p_fit_smooth_2:
    :param tol_r:
    :param max_it:
    :return:
    """
    if not (0 < p_asym < 1):
        raise ValueError(f"Asymmetry parameter must be between 0 and 1 not {p_asym}")
    spec = spectrum.signal
    dim = len(spec)
    weights = np.ones(dim)
    _d1 = sparse.diags([0.5, 0, -0.5], [0, -1, -2], shape=(dim, dim - 2))
    d1_matrix = p_fit_smooth_1 * _d1.dot(_d1.transpose())
    _d2 = sparse.diags([1, -2, 1], [0, -1, -2], shape=(dim, dim - 2))
    d2_matrix = p_fit_smooth_2 * _d2.dot(_d2.transpose())

    diagonal = sparse.spdiags(weights, 0, dim, dim)

    _it = 0
    while True:
        diagonal.setdiag(weights)
        baseline = spsolve(diagonal + d1_matrix + d2_matrix, (diagonal + d1_matrix) * spec)
        _weights = p_asym * (spec > baseline) + (1 - p_asym) * (spec <= baseline)
        rel_err = np.linalg.norm(weights - _weights, 2) / np.maximum(np.linalg.norm(weights, 2), np.finfo(float).eps)
        weights = _weights
        _it += 1
        if rel_err < tol_r:
            break
        if _it > max_it:
            print("Exhausted max iterations")
            break

    return Spectrum(spectrum.wavelengths.copy(), baseline), rel_err


def detect_peaks(spectrum: Spectrum,
                 filter_sigma: float | Iterable,
                 filter_kwargs: dict = None,
                 find_peaks_kwargs: dict = None
                 ) -> tuple[np.ndarray, np.ndarray, Spectrum]:
    """ Provides the indices for the peaks, their prominences, and a copy of the filtered spectrum.

    filter_sigma is the standard deviation for the 1d Gaussian kernel used in smoothing/filtering the spectrum.

    For filter_kwargs, see: scipy.ndimage.gaussian_filter1d()

    - axis: The axis of input along which to calculate. Default is -1.
    - order: An order of 0 corresponds to convolution with a Gaussian kernel. A positive order corresponds to
      convolution with that derivative of a Gaussian.
    - mode: How the input array is extended beyond its boundaries: reflect, constant, nearest, mirror, or wrap.
      Default is 'reflect'
    - cval: Value to fill past edges of input if mode is ‘constant’. Default is 0.0.
    - truncate: Truncate the filter at this many standard deviations. Default is 4.0.
    - radius: Radius of the Gaussian kernel. If specified, the size of the kernel will be 2*radius + 1, and
      truncate is ignored. Default is None.

    For find_peaks_kwargs, see: scipy.signal.find_peaks()

    - height: Required height of peaks. Either a number, None, an array matching x or a 2-element sequence of
      the former. The first element is always interpreted as the minimal and the second, if supplied, as the
      maximal required height.
    - threshold: Required threshold of peaks, the vertical distance to its neighboring samples. Either a number,
      None, an array matching x or a 2-element sequence of the former. The first element is always interpreted
      as the minimal and the second, if supplied, as the maximal required threshold.
    - distance: Required minimal horizontal distance (>= 1) in samples between neighbouring peaks. Smaller peaks
      are removed first until the condition is fulfilled for all remaining peaks.
    - prominence: Required prominence of peaks. Either a number, None, an array matching x or a 2-element sequence
      of the former. The first element is always interpreted as the minimal and the second, if supplied, as the
      maximal required prominence.
    - width: Required width of peaks in samples. Either a number, None, an array matching x or a 2-element
      sequence of the former. The first element is always interpreted as the minimal and the second, if supplied,
      as the maximal required width.
    - plateau_size: Required size of the flat top of peaks in samples. Either a number, None, an array matching x
      or a 2-element sequence of the former. The first element is always interpreted as the minimal and the second,
      if supplied as the maximal required plateau size.
    """
    if filter_kwargs is None:
        filter_kwargs = {}
    if find_peaks_kwargs is None:
        find_peaks_kwargs = {}

    filtered_data = sn.gaussian_filter1d(spectrum.signal, filter_sigma, **filter_kwargs)
    peak_idxs, *_ = ss.find_peaks(filtered_data, **find_peaks_kwargs)
    prominences, *_ = ss.peak_prominences(filtered_data, peak_idxs)

    return peak_idxs, prominences, Spectrum(spectrum.wavelengths, filtered_data)


def get_full_widths_at_half_max(spectrum: Spectrum,
                                filter_sigma: float | Iterable,
                                filter_kwargs: dict = None,
                                find_peaks_kwargs: dict = None):
    """
    FWHM estimation using multi-gaussian regression

    return keywords:

    - 'peaks': The centers of each peak in the spectrum
    - 'widths': The widths for each FWHM in spectrum
    - 'heights': The peak values of the spectrum

    Return also includes a copy of the filtered/smoothed spectrum for reference, and the covariance matrix of the
      regressed parameters used during FWHM calculation
    """
    peak_idxs, prominences, reference_filtered_spectrum = detect_peaks(spectrum,
                                                                       filter_sigma,
                                                                       filter_kwargs,
                                                                       find_peaks_kwargs)

    summary: dict[str, list[float]] = {
        'peaks': [],
        'widths': [],
        'heights': []
    }
    p0 = []
    for prom_i in prominences:
        p0.extend([prom_i, 5.0])

    def rearrange(*parameters):
        for peak_i, (_amp, _sig) in zip(peak_idxs, batched(parameters, 2)):
            yield _amp, spectrum.wavelengths[peak_i], _sig

    p_opt, covar_p_opt = curve_fit(  # noqa: signature is wrong
        lambda x, *p: multi_gauss(x, *list(rearrange(*p))),
        spectrum.wavelengths,
        spectrum.signal,
        p0=p0
    )

    for (_amp_opt, _sig_opt), _peak_i in zip(batched(p_opt, 2), peak_idxs):
        summary['widths'].append(2.354820045031*_sig_opt)  # 2 * sqrt( 2 * Ln( 2 ) ) * sigma
        summary['peaks'].append(spectrum.wavelengths[_peak_i])
        summary['heights'].append(_amp_opt)

    return summary, reference_filtered_spectrum, covar_p_opt


def integrate(spectrum: Spectrum) -> float:
    """ Provides the area under the curve. """
    return simpson(y=spectrum.signal, x=spectrum.wavelengths)


def map_peaks(expected_peaks: dict[str, float],
              actual_spectrum: Spectrum,
              observed_peaks: np.ndarray
              ) -> dict[str, tuple[int, float, float]]:
    """ Attempts to name peaks based on some expectation.  Mapping is to closest and is not 1-to-1.
    Provides a mapping {name of peak: (idx in actual spectrum, wavelength in actual spectrum, wavelength difference)}

    :param expected_peaks: Expected as {name of peak : expected wavelength}
    :param actual_spectrum: The true spectrum
    :param observed_peaks: Array of indices (e.g. from detect_peaks()) for the peaks
    """
    _observed_peaks = [(_i, _w) for _i, _w in zip(observed_peaks, actual_spectrum.wavelengths[observed_peaks])]
    peak_map = {}
    for peak_name, peak_value in expected_peaks.items():  # type: str, float
        closest_idx, closest_w = min(_observed_peaks, key=lambda x: abs(x[1] - peak_value))  # type: int, float
        peak_map[peak_name] = (closest_idx, closest_w, closest_w - peak_value)

    return peak_map

def smooth(spectrum: Spectrum,
           sigma: int | float | complex = 3.0,
           order: int | None = 0,
           mode: Literal["reflect", "constant", "nearest", "mirror", "wrap"] = "reflect",
           cval: int | float | complex = 0.0,
           truncate: float | None = 4.0,
           radius: int | None = None
           ) -> None:
    """ Smooths a spectrum in-place with a 1-D Gaussian kernel.
    :param spectrum: The spectrum being smoothed.
    :param sigma: Standard deviation for Gaussian kernel.
    :param order: An order of 0 corresponds to convolution with a Gaussian kernel.
      A positive order corresponds to convolution with that derivative of a Gaussian.
    :param mode: The mode parameter determines how the input array is extended beyond its boundaries.
    :param cval: Value to fill past edges of input if mode is ‘constant’.
    :param truncate: Truncate the filter at this many standard deviations.
    :param radius: Radius of the Gaussian kernel. If specified, the size of the kernel will be
      2*radius + 1, and truncate is ignored.
    """
    spectrum.signal = sn.gaussian_filter1d(
        spectrum.signal,
        sigma=sigma,
        order=order,
        mode=mode,
        cval=cval,
        truncate=truncate,
        radius=radius
    )
    return None


def smoothed(spectrum: Spectrum,
             sigma: int | float | complex = 3.0,
             order: int | None = 0,
             mode: Literal["reflect", "constant", "nearest", "mirror", "wrap"] = "reflect",
             cval: int | float | complex = 0.0,
             truncate: float | None = 4.0,
             radius: int | None = None
             ) -> Spectrum:
    """ Provides a smoothed copy of a spectrum with a 1-D Gaussian kernel. (not in-place)
    :param spectrum: The spectrum being smoothed.
    :param sigma: Standard deviation for Gaussian kernel.
    :param order: An order of 0 corresponds to convolution with a Gaussian kernel.
      A positive order corresponds to convolution with that derivative of a Gaussian.
    :param mode: The mode parameter determines how the input array is extended beyond its boundaries.
    :param cval: Value to fill past edges of input if mode is ‘constant’.
    :param truncate: Truncate the filter at this many standard deviations.
    :param radius: Radius of the Gaussian kernel. If specified, the size of the kernel will be
      2*radius + 1, and truncate is ignored.
    """
    smoothed_spectrum = spectrum.copy()
    smooth(smoothed_spectrum, sigma, order, mode, cval, truncate, radius)
    return smoothed_spectrum


if __name__ == '__main__':
    from random import random
    from spectra import SpectraStack

    # spec_file = "./real_spectra.spec"
    spec_file = "./sim_spectra.spec"  # created in spectra.py
    my_spectrum = Spectrum.load_from_file(spec_file).segment(lower_bound=450, upper_bound=950)

    filtered_spectrum = smoothed(my_spectrum)

    spec_baseline, tol_baseline = measure_asls_baseline(
        filtered_spectrum,
        p_asym=0.01,
        p_fit_smooth_1=1e-3,
        p_fit_smooth_2=1e7,
        tol_r=0.001,
        max_it=50
    )
    print(f"Fit baseline within tolerance of {tol_baseline:.3%}")
    my_new_spectrum = filtered_spectrum - spec_baseline

    peakutils_baseline = measure_baseline(filtered_spectrum, 2)
    my_other_new_spectrum = filtered_spectrum - peakutils_baseline

    with open("./test.spec", "w+") as _file:
        SpectraStack(my_spectrum, filtered_spectrum, my_new_spectrum, my_other_new_spectrum).print(_file)

    def print_peak_data(peak_data):
        for peak_wv, pw, ph in zip(*peak_data.values()):
            print(f"Peak at {peak_wv:.4}, with a width of {pw:.4} and height of {ph:.4}")
