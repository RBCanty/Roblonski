import datetime
import time
import typing
from collections.abc import Mapping
from enum import Flag, auto
from threading import Event, Lock
from typing import Literal

if typing.TYPE_CHECKING:
    pass

import nidaqmx
import numpy as np  # Must be pre v2.0 or else seabreeze will break due to type incompatibility

from aux_devices.spectra import Spectrum, intensity_to_absorbance, ZipSpectra
from aux_devices.spectral_latches import SpectralLatch

try:
    import seabreeze
    seabreeze.use('pyseabreeze')
    from seabreeze.spectrometers import Spectrometer
    # Need to install pyusb and libusb
    #  Then copy ...\venv\Lib
    #  \site-packages\libusb\_platform\_windows\x64\libusb-1.0.dll
    #  To C:/Windows/System32
    # Depending on your OS, you may need to install the USB driver for the spectrometer
    #  https://zadig.akeo.ie/ has many of the drivers for Ocean Optics
except ModuleNotFoundError as mnfe:
    print(mnfe)
    print(f"Failed to load seabreeze! Running in troubleshoot mode")

    class Spectrometer:
        def __init__(self):
            self.int_time = 0.0
            self.shape = (1, 4)

        def from_first_available(self):
            return self

        def integration_time_micros(self, integration_time_micros: int):
            self.int_time = integration_time_micros

        def wavelengths(self):
            return np.ndarray(shape=self.shape, dtype=float)

        def intensities(self, correct_dark_counts: bool = False, correct_nonlinearity: bool = False):  # noqa
            return np.ndarray(shape=self.shape, dtype=float)

        def close(self):
            return


class Light(Flag):
    """ Enum for identifying the illumination source. """
    NEITHER = 0
    ABS = auto()
    PL = auto()
    BOTH = ABS | PL


class State(Flag):
    """ Enum for the illumination state. """
    OFF = False
    ON = True


class LightSource:
    """ Context manager and controller for the illumination sources and their states. Imposes the rule that the ABS
     and PL light sources cannot both be on at the same time to avoid damaging the detector. """
    def __init__(self, abs_light_daq_path: str, pl_light_daq_path: str):
        self.abs_light_daq_path = abs_light_daq_path
        self.pl_light_daq_path = pl_light_daq_path
        self._context_light = Light.BOTH
        self.simulated = False

    def get_light_path(self, light: Light) -> tuple[str | None, str | None]:
        """ Provides a left-filled 2-tuple of the DAQ paths based on illumination source(s). """
        if light == Light.BOTH:
            return self.abs_light_daq_path, self.pl_light_daq_path
        if light == Light.ABS:
            return self.abs_light_daq_path, None
        if light == Light.PL:
            return self.pl_light_daq_path, None
        return None, None

    def _turn_light(self, _daq_path: str, _state: State) -> None:
        """ (Low-level) Turns the illumination source (_daq_path) to the specified state (_state).
        For the high-level version which uses Light and State (cf. a DAQ path and State), see turn_light().

        Can raise nidaqmx.DaqError """
        if self.simulated:
            print(f"{_daq_path} --> {_state}")
            return
        state_cmd = [_state.value, ]
        with nidaqmx.Task() as task:
            task.do_channels.add_do_chan(_daq_path)
            try:
                task.write(state_cmd)
                time.sleep(0.04)
            except nidaqmx.DaqError as e:
                raise e

    def turn_light(self, light: Light, state: State) -> None:
        """ Turns the illumination source (light) to the specified state (state).

        Can raise ValueError (if trying to turn both lights on at once) and nidaqmx.DaqError.
        If light is Neither, this command is ignored, only Both-Off will turn both lights off.
        Turns all other lights off before turning the specified one on.
        """
        if light == Light.NEITHER:
            return
        if (state == State.ON) and (light == Light.BOTH):
            raise ValueError("Cannot turn on both lights at once, may damage the spectrometer.")
        if state == State.OFF:
            [self._turn_light(_light, state) for _light in self.get_light_path(light) if _light is not None]
            return
        # Note: at this point for (Neither, ABS, PL, BOTH) x (ON, OFF), the only remaining states are:
        #   (ABS ON) and (PL ON).
        # ____|_N_|_A_|_P_|_B_|
        # ON  | 1 |   |   | 2 |
        # OFF | 1 | 3 | 3 | 3 |
        other_light = ~light  # Light.BOTH ^ light
        self._turn_light(self.get_light_path(other_light)[0], State.OFF)
        self._turn_light(self.get_light_path(light)[0], state)

    def __enter__(self):
        """ Context manager entrance point such that 'with LightSource.single_light_on():' functions as described in
        single_light_on(). """
        return self

    def single_light_on(self, light: Light):
        """ For use in a with statement "with self.single_light_on(light): ...".
        Turns the given light Off upon exiting the context.

        Note: If light is Neither, then it will turn Both lights Off. """
        self._context_light = light
        if light is Light.NEITHER:
            self.turn_light(Light.BOTH, State.OFF)
        else:
            self.turn_light(light, State.ON)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ Context manager exit point such that 'with LightSource.single_light_on():' turns the light off on exit. """
        self.turn_light(self._context_light, State.OFF)
        self._context_light = Light.BOTH


class _Spectrometer:
    """ Spectrometer backend. Used for controlling spectrometer settings as well as measuring raw intensities. """
    def __init__(self, integration_time: int = 10_000, using: Spectrometer = None):
        if using is None:
            self.spec = Spectrometer.from_first_available()
        else:
            self.spec = using
        self._int_time = None
        self._mutex = Lock()
        self.integration_time = integration_time
        self.correct_dark_counts = False
        self.correct_nonlinearity = False

    @property
    def integration_time(self) -> int:
        """ Integration time in microseconds """
        return self._int_time

    @integration_time.setter
    def integration_time(self, integration_time: int):
        """ This setter makes a call to the underlying spectrometer

        (Protected by 'with self._mutex:' for thread safety)

        :param integration_time: in microseconds """
        if self._int_time != integration_time:
            self._int_time = integration_time
            with self._mutex:
                self.spec.integration_time_micros(self._int_time)
            time.sleep(0.5)

    @property
    def wavelengths(self) -> np.ndarray:
        """ Returns an ndarray of the wavelengths (makes a call to the spectrometer)
        (Protected by 'with self._mutex:' for thread safety) """
        with self._mutex:
            return self.spec.wavelengths()

    @property
    def _intensities_kwargs(self) -> dict[str, bool]:
        return {
            'correct_dark_counts': self.correct_dark_counts,
            'correct_nonlinearity': self.correct_nonlinearity
        }

    def measure_intensities(self) -> np.ndarray:
        """ Measures intensities and returns them as an ndarray.

        (Protected by 'with self._mutex:' for thread safety) """
        with self._mutex:
            return self.spec.intensities(**self._intensities_kwargs)


class _PhotoluminescenceSpectrometer:
    """ Backend for spectrometers measuring Photoluminescences. Used to manage references and provide PL spectra
    in intensities. """
    def __init__(self, backend: _Spectrometer):
        self.backend = backend
        self.light_reference: np.ndarray = None  # noqa: up to the user to set manually
        self.dark_reference: np.ndarray = None  # noqa: up to the user to set manually

    def measure_light_reference(self) -> np.ndarray:
        """ Measures and saves the light reference. """
        self.light_reference = self.backend.measure_intensities()
        return self.light_reference

    def measure_dark_reference(self) -> np.ndarray:
        """ Measures and saves the dark reference. """
        self.dark_reference = self.backend.measure_intensities()
        return self.dark_reference

    def measure_photoluminescence_intensity(self) -> np.ndarray:
        """ Measures returns an array of intensities. """
        return self.backend.measure_intensities()

    def measure_photoluminescence_spectrum(self,
                                           subtract_reference: Literal[False, None, "light", "dark"] = False
                                           ) -> Spectrum:
        """ Provides the PL spectrum (nm vs intensity) """
        signal = self.measure_photoluminescence_intensity()
        if subtract_reference == "light":
            signal -= self.light_reference
        elif subtract_reference == "dark":
            signal -= self.dark_reference
        return Spectrum(
            wavelengths=self.backend.wavelengths,
            signal=signal
        )


class _AbsorbanceSpectrometer:
    """ Backend for spectrometers measuring Absorbance. Used to manage references and provide transmission (used to
    calculate ABS spectra). """
    def __init__(self, backend: _Spectrometer):
        self.backend = backend
        self.light_reference: np.ndarray = None  # noqa: up to the user to set manually
        self.dark_reference: np.ndarray = None  # noqa: up to the user to set manually

    def measure_light_reference(self) -> np.ndarray:
        """ Measures and saves the light reference (intensities). """
        self.light_reference = self.backend.measure_intensities()
        return self.light_reference

    def measure_dark_reference(self) -> np.ndarray:
        """ Measures and saves the dark reference (intensities). """
        self.dark_reference = self.backend.measure_intensities()
        return self.dark_reference

    def measure_broadband_intensity(self) -> np.ndarray:
        """ Measures and saves the intensity of transmitted light (intensities). """
        return self.backend.measure_intensities()


class SpectrometerSystem:
    """ Manager for a spectrometer capable of measuring ABS and PL spectra. """
    def __init__(self, lights: LightSource, using: Spectrometer = None):
        self.backend = _Spectrometer(using=using)
        self.lights = lights

        self.abs = _AbsorbanceSpectrometer(self.backend)
        self.pl = _PhotoluminescenceSpectrometer(self.backend)

        # The code is faster than the LED/Shutter on the light sources, observed spectra are noisier and less
        #   reproducible when these lag values are small.
        self._pl_light_lag = 4.0
        self._abs_light_lag = 3.0

    @property
    def light_pl_reference(self):
        """ Provides the light referenced saved for PL measurements (if present; otherwise returns None). """
        return self.pl.light_reference

    @light_pl_reference.setter
    def light_pl_reference(self, value: np.ndarray | None):
        """ Allows for setting the light referenced for PL measurements. """
        self.pl.light_reference = value

    @property
    def dark_pl_reference(self):
        """ Provides the dark referenced saved for PL measurements (if present; otherwise returns None). """
        return self.pl.dark_reference

    @dark_pl_reference.setter
    def dark_pl_reference(self, value: np.ndarray | None):
        """ Allows for setting the dark referenced for PL measurements. """
        self.pl.dark_reference = value

    @property
    def light_abs_reference(self):
        """ Provides the light referenced saved for ABS measurements (if present; otherwise returns None). """
        return self.abs.light_reference

    @light_abs_reference.setter
    def light_abs_reference(self, value: np.ndarray | None):
        """ Allows for setting the light referenced for ABS measurements. """
        self.abs.light_reference = value

    @property
    def dark_abs_reference(self):
        """ Provides the dark referenced saved for ABS measurements (if present; otherwise returns None). """
        return self.abs.dark_reference

    @dark_abs_reference.setter
    def dark_abs_reference(self, value: np.ndarray | None):
        """ Allows for setting the dark referenced for ABS measurements. """
        self.abs.dark_reference = value

    @property
    def integration_time(self) -> int:
        """ Gets the integration time in microseconds """
        return self.backend.integration_time

    @integration_time.setter
    def integration_time(self, integration_time: int):
        """ Sets the integration time (in microseconds) -- calls the spectrometer.

        :param integration_time: In microseconds """
        self.backend.integration_time = integration_time

    # GETTING REFERENCES ###############################################################################################
    @staticmethod
    def _load_reference(from_file: str, delimiter: str = ","):
        """ Backend for loading a reference. """
        wavelengths: list[float] = []
        signals: list[float] = []
        with open(from_file, 'r') as input_file:
            for line in input_file:  # type: str
                try:
                    w_raw, s_raw = line.strip().split(delimiter)
                    wavelengths.append(float(w_raw))
                    signals.append(float(s_raw))
                except ValueError as ve:
                    print(f"Skipping line: '{line.strip()}' ({ve!r}: {line.strip().split(delimiter)})")
                    continue
        return np.array(wavelengths), np.array(signals)

    def load_reference(self,
                       file_path: str,
                       mode: Literal[None, "abs", "pl"] = None,
                       light: Literal[None, "light", "dark"] = None,
                       tolerance: float = 1e-5):
        """ Specifying mode and light will save the spectrum to the reference (None will not set it).  It will return
         the Spectrum regardless.  Tolerance is for the differences between the file's wavelengths and the
         Spectrometer's wavelengths. """
        ref_w, ref_s = self._load_reference(file_path)
        spec_w = self.backend.wavelengths
        if (len(ref_w) != len(spec_w)) or any(abs(_w - __w) > tolerance for _w, __w in zip(ref_w, spec_w)):
            raise ValueError(f"The reference does not seem to match the spectrometer")
        if mode == "abs":
            if light == "light":
                self.light_abs_reference = ref_s
            elif light == "dark":
                self.dark_abs_reference = ref_s
        elif mode == "pl":
            if light == "light":
                self.light_pl_reference = ref_s
            elif light == "dark":
                self.dark_pl_reference = ref_s
        return Spectrum(wavelengths=spec_w, signal=ref_s)

    def measure_reference(self,
                          mode: Literal["abs", "pl"],
                          light: Literal["light", "dark"],
                          integration_time: int = None
                          ) -> Spectrum:
        """ Measures and saves a single reference (specified by the mode and light parameters). """
        if integration_time is not None:
            self.integration_time = integration_time
        if (mode == "abs") and (light == "dark"):
            _light = Light.NEITHER
            _call = self.abs.measure_dark_reference
        elif (mode == "abs") and (light == "light"):
            _light = Light.ABS
            _call = self.abs.measure_light_reference
        elif (mode == "pl") and (light == "dark"):
            _light = Light.NEITHER
            _call = self.pl.measure_dark_reference
        elif (mode == "pl") and (light == "light"):
            _light = Light.PL
            _call = self.pl.measure_light_reference
        else:
            raise ValueError(f"Invalid parameters: {mode=}, {light=}")
        with self.lights.single_light_on(light=_light):
            return Spectrum(wavelengths=self.backend.wavelengths, signal=_call())

    def measure_average_reference(self,
                                  mode: Literal["abs", "pl"],
                                  light: Literal["light", "dark"],
                                  count: int = 1,
                                  interval: float = 0.05,
                                  integration_time: int = None,
                                  lag: float = -1,
                                  ) -> Spectrum:
        """ Provides a multi-scan average of a PL or ABS scan either with or without the light active. """
        if integration_time is not None:
            self.integration_time = integration_time
        if lag < 0:
            if mode == "abs":
                lag = self._abs_light_lag
            elif mode == "pl":
                lag = self._pl_light_lag
            else:
                raise ValueError(f"Invalid parameters: {mode=}")

        if (mode == "abs") and (light == "dark"):
            _light = Light.NEITHER
            _call = self.abs.measure_dark_reference
            _setter = self.__class__.dark_abs_reference.fset
        elif (mode == "abs") and (light == "light"):
            _light = Light.ABS
            _call = self.abs.measure_light_reference
            _setter = self.__class__.light_abs_reference.fset
        elif (mode == "pl") and (light == "dark"):
            _light = Light.NEITHER
            _call = self.pl.measure_dark_reference
            _setter = self.__class__.dark_pl_reference.fset
        elif (mode == "pl") and (light == "light"):
            _light = Light.PL
            _call = self.pl.measure_light_reference
            _setter = self.__class__.light_pl_reference.fset
        else:
            raise ValueError(f"Invalid parameters: {mode=}, {light=}")

        with self.lights.single_light_on(light=_light):
            time.sleep(lag + interval)
            intensities_sum = _call()
            for _ in range(count - 1):
                time.sleep(interval)
                intensities_sum += _call()
        average_signal = intensities_sum / count

        _setter(self, average_signal)

        return Spectrum(wavelengths=self.backend.wavelengths, signal=average_signal)

    # GETTING ACTUAL SPECTRA ###########################################################################################
    def yield_pl_spectra(self, count: int = 1, interval: float = 0.05, integration_time: int = None):
        """ Generator for calling upon PL spectra (intensities) at will without changing the light source state
        between scans. """
        if integration_time is not None:
            self.integration_time = integration_time
        with self.lights.single_light_on(light=Light.PL):
            time.sleep(self._pl_light_lag)
            for _ in range(count):
                time.sleep(interval)
                yield self.pl.measure_photoluminescence_spectrum()

    def measure_pl_spectra(self, count: int = 1, interval: float = 0.05, integration_time: int = None):
        """ Takes `count` scans spaced `interval` seconds apart and returns the averaged PL spectrum.  (The integration
         time can be set using `integration_time` [microseconds]; None will use the previously set value) """
        if integration_time is not None:
            self.integration_time = integration_time
        with self.lights.single_light_on(light=Light.PL):
            time.sleep(interval + self._pl_light_lag)
            intensities_sum = self.pl.measure_photoluminescence_spectrum().signal
            for _ in range(count - 1):
                time.sleep(interval)
                intensities_sum += self.pl.measure_photoluminescence_spectrum().signal
        return Spectrum(wavelengths=self.backend.wavelengths, signal=intensities_sum / count)

    def yield_abs_spectra(self, count: int = 1, interval: float = 0.05, integration_time: int = None):
        """ Generator for calling upon ABS spectra (mOD) at will without changing the light source state between scans. """
        if integration_time is not None:
            self.integration_time = integration_time
        with self.lights.single_light_on(light=Light.ABS):
            time.sleep(self._abs_light_lag)
            for _ in range(count):
                time.sleep(interval)
                yield intensity_to_absorbance(
                    self.backend.wavelengths,
                    self.abs.light_reference,
                    self.abs.dark_reference,
                    self.abs.measure_broadband_intensity()
                )

    def measure_abs_spectra(self, count: int = 1, interval: float = 0.05, integration_time: int = None):
        """ Takes `count` scans spaced `interval` seconds apart and returns the averaged* ABS spectrum.
        (The integration time can be set using `integration_time` [microseconds]; None will use the previously set
        value).

        *The average is calculated using the averaged intensity of transmittance; averaging individual ABS spectra
        can lead to numerical instability and NaN values.

        Abs in mOD """
        if integration_time is not None:
            self.integration_time = integration_time
        with self.lights.single_light_on(light=Light.ABS):
            time.sleep(interval + self._abs_light_lag)
            intensities_sum = self.abs.measure_broadband_intensity()
            for _ in range(count - 1):
                time.sleep(interval)
                intensities_sum += self.abs.measure_broadband_intensity()
        return intensity_to_absorbance(
            self.backend.wavelengths,
            self.abs.light_reference,
            self.abs.dark_reference,
            intensities_sum / count
        )

    # DROPLET DETECTION ################################################################################################
    def detect_droplet_generic(self,
                               semaphore: Event,
                               latch: SpectralLatch,
                               temporal_threshold: float = 0.1,
                               timeout: float = 60):
        """ UNVERIFIED METHOD -- Not yet reliable: requires far too much fine-tuning of parameters to be practical.
        The intent of this method is to provide the ability to detect a droplet entering the spectrometer (then using
        the semaphore to signal the pump to stop). """
        global_timer = datetime.datetime.now()
        consecutive_timer = None

        with (self.lights.single_light_on(light=Light.ABS)):
            while (datetime.datetime.now() - global_timer).total_seconds() <= timeout:
                current_spectrum = self.measure_abs_spectra()
                latch.add_spectra(current_spectrum)
                if not latch:
                    consecutive_timer = datetime.datetime.now()
                    continue
                if (datetime.datetime.now() - consecutive_timer).total_seconds() > temporal_threshold:
                    semaphore.set()
                    return
            else:
                error = TimeoutError(f"Did not detect any droplet over {timeout} seconds")
                semaphore.is_bad = error
                semaphore.set()
                raise error

    def detect_droplet_double_latch(self,
                                    semaphore: Event,
                                    lambda_min: float | None,
                                    lambda_max: float | None,
                                    signal_threshold: float = 300,
                                    variance_threshold: float = 15,
                                    temporal_threshold: float = 0.1,
                                    timeout: float = 60,
                                    verbose=True):
        """ UNVERIFIED METHOD -- Not yet reliable: requires far too much fine-tuning of parameters to be practical.
        The intent of this method is to provide the ability to detect a droplet entering the spectrometer (then using
        the semaphore to signal the pump to stop). """
        global_timer = datetime.datetime.now()
        consecutive_timer = None
        latch = 0

        with (self.lights.single_light_on(light=Light.ABS)):
            while (datetime.datetime.now() - global_timer).total_seconds() <= timeout:
                current_spectrum = self.measure_abs_spectra()
                current_segment = current_spectrum.segment(lower_bound=lambda_min, upper_bound=lambda_max)
                match latch:
                    case 0:
                        metric = np.nanmean(current_segment.signal)
                        if verbose: print(f"{latch=}, {metric=:.3f}")
                        if metric < signal_threshold:
                            consecutive_timer = datetime.datetime.now()
                            continue
                        # if metric > signal_threshold
                        if (datetime.datetime.now() - consecutive_timer).total_seconds() > temporal_threshold:
                            latch = 1
                            consecutive_timer = datetime.datetime.now()
                    case 1:
                        metric = np.nanmean(current_segment.signal)
                        metric_2 = np.nanstd(current_segment.signal, ddof=1)
                        if verbose: print(f"{latch=}, {metric=:.3f}, {metric_2=:.3f}")
                        if (metric > signal_threshold) and (metric_2 < variance_threshold):
                            consecutive_timer = datetime.datetime.now()
                            continue
                        # if metric < signal_threshold
                        if (datetime.datetime.now() - consecutive_timer).total_seconds() > temporal_threshold:
                            semaphore.set()
                            return
            else:
                error = TimeoutError(f"Did not detect any droplet over {timeout} seconds")
                semaphore.is_bad = error
                semaphore.set()
                raise error


class OpticalSpecs(Mapping):
    """ Container for the parameters of a spectrometer measurement. """
    def __init__(self,
                 count: int = 1,
                 interval: float = 0.1,
                 integration_time: int = None,
                 count_units: str = "",
                 interval_units: str = " (Sec)",
                 integration_time_units: str = " (uSec)",
                 correct_nonlinearity=False,
                 correct_dark_counts=False,
                 wavelength_calibration: float = None,
                 slit: str = None
                 ):
        self.values = {'count': count, 'interval': interval, 'integration_time': integration_time}

        count_units = self._enforce_space(count_units)
        interval_units = self._enforce_space(interval_units)
        integration_time_units = self._enforce_space(integration_time_units)

        self.units = (count_units, interval_units, integration_time_units)
        self.correct_nonlinearity = correct_nonlinearity
        self.correct_dark_counts = correct_dark_counts
        self.wavelength_calibration = wavelength_calibration
        """ true wavelength = reported wavelength + wavelength_calibration """
        self.slit = slit

    @property
    def count(self):
        """ How many scans """
        return self.values['count']
    @property
    def interval(self):
        """ Time between scans """
        return self.values['interval']
    @property
    def integration_time(self):
        """ Integration time of each scan """
        return self.values['integration_time']
    @count.setter
    def count(self, value):
        self.values['count'] = value
    @interval.setter
    def interval(self, value):
        self.values['interval'] = value
    @integration_time.setter
    def integration_time(self, value):
        self.values['integration_time'] = value

    @staticmethod
    def _enforce_space(string: str):
        if string and not string.startswith(" "):
            return " " + string
        return string

    def generate_tag(self) -> str:
        """ Produces a comma-separated tag of the form 'var=value, ...' for count, interval, and integration_time """
        # TODO: Add Timestamp?
        return "\n".join(f"{k}, {v}{u}" for (k, v), u in zip(self.values.items(), self.units))

    def generate_corrections_tag(self) -> str:
        """ Produces a comma-separated tag of the form 'var=value, ...' for spectrometer properties (nonlin,
        dark_count, calibration, slit)"""
        return f"NLC={self.correct_nonlinearity}, DCC={self.correct_dark_counts}, WCAL={self.wavelength_calibration}, Slit={self.slit}"

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, item):
        return self.values[item]

    def __len__(self):
        return len(self.values)

    def __repr__(self):
        return (f"OpticalSpecs(count={self.count}, interval={self.interval}, integration_time={self.integration_time}, "
                f"count_units={self.units[0]}, interval_units={self.units[1]}, integration_time_units={self.units[2]}, "
                f"correct_nonlinearity={self.correct_nonlinearity}, correct_dark_counts={self.correct_dark_counts})")

    def __str__(self):
        annotated_values = ", ".join(f"{k}={v}{u}" for (k, v), u in zip(self.values.items(), self.units))
        return (f"OpticalSpecs({annotated_values}, "
                f"correct_nonlinearity={self.correct_nonlinearity}, correct_dark_counts={self.correct_dark_counts})")


if __name__ == '__main__':
    import os
    # from seabreeze.spectrometers import list_devices
    # print(list_devices())

    test = LightSource("Dev1/port0/line1", "Dev1/port0/line0")
    my_spec = SpectrometerSystem(test)

    my_spec.abs.backend.correct_dark_counts = False  # True  # their version has this on True
    my_spec.abs.backend.correct_nonlinearity = False  # theirs does not support this at all

    optical_abs_specs = {'count': 30, 'interval': 0.1, 'integration_time': 20_000}
    optical_pl_specs = {'count': 3, 'interval': 0.1, 'integration_time': 2_000_000}

    def run_pl_exp(manual=True):
        manual and input("Light ")
        my_spec.measure_average_reference(**optical_pl_specs, light="light", mode="pl")
        manual and input("Dark ")
        my_spec.measure_average_reference(**optical_pl_specs, light="dark", mode="pl")
        manual and input("PL ")
        spectrum = my_spec.measure_pl_spectra(**optical_pl_specs)
        print(f"The 340-370 integral is: {spectrum.integrate(340, 370)}")
        ZipSpectra(spectrum, my_spec.pl).print()

    def run_pl_cuvette():
        spectrum = my_spec.measure_pl_spectra(**optical_pl_specs)
        ZipSpectra(spectrum, my_spec.pl).print()

    def run_abs_exp(manual=True):
        manual and input("Dark ")
        my_spec.measure_average_reference(**optical_abs_specs, light="dark", mode="abs")
        manual and input("Light ")
        my_spec.measure_average_reference(**optical_abs_specs, light="light", mode="abs")
        manual and input("ABS ")
        spectrum = my_spec.measure_abs_spectra(**optical_abs_specs)
        ZipSpectra(spectrum, my_spec.abs).print()

    def run_abs_cuvette():
        my_dir = r"C:\Users\User\Documents\Gilson Spectroscopy Project"
        my_spec.load_reference(os.path.join(my_dir, r"1mm_cuvette_light_reference_MeCN_v2.csv"), mode="abs", light="light")
        # You can create a new light reference by running run_abs_exp() on the blank cuvette and then saving the
        #   Wavelength and Light signal to a csv file.
        print("Dark ") or time.sleep(1)
        my_spec.measure_average_reference(**optical_abs_specs, light="dark", mode="abs")
        print("ABS ") or time.sleep(1)
        spectrum = my_spec.measure_abs_spectra(**optical_abs_specs)
        ZipSpectra(spectrum, my_spec.abs).print()

    # run_pl_cuvette()
    run_abs_cuvette()
    # run_abs_exp(manual=True)
