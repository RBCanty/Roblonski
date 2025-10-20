import abc
from abc import abstractmethod
from typing import Iterator
from misc_func import format_as_table


class Dilution(abc.ABC):
    """ Base abstract class for specifying a serial dilution. """
    def __init__(self, value: int | float):
        """ As this leve, the meaning of value is hidden, but the intent is that any dilution will be based on some
         value, such as a volume or fraction. """
        self.value = value

    @abstractmethod
    def get_volume(self, total_volume: int | float) -> int | float: ...

    def __repr__(self):
        scheme_name = type(self).__name__.split(".")[-1]
        return f"{scheme_name}(value={self.value})"


class Volumetric(Dilution):
    """ Dilute based on a constant volume being replaced. """
    def get_volume(self, total_volume: int | float) -> int | float:
        """ Based on self.value as an absolute replaced volume, `get_volume()` returns self.value.

        If the dilution volume is negative or greater than `total_volume`, a ValueError is thrown as this
        volumetric replacement is impossible. """
        if not (0 < self.value < total_volume):
            raise ValueError(f"Volume ({self.value}) must be physical (0-{total_volume}).")
        return self.value

    def __repr__(self):
        return f"Volumetric(value={self.value})"


class Fractional(Dilution):
    """ Dilute based on a constant volume fraction being replaced. """
    def get_volume(self, total_volume: int | float) -> int | float:
        """ Based on self.value as a fraction of the total volume to be replaced, `get_volume()` returns
        self.value * total_volume.

        If the replaced fraction is not bounded between 0 and 1 (exclusive), a ValueError is thrown as this relative
        volumetric replacement is impossible/not meaningful.
        """
        if not (0 < self.value < 1):
            raise ValueError(f"Fraction ({self.value:.2%}) must be physical (0-100%)")
        return self.value * total_volume

    def __repr__(self):
        return f"Fractional(value={self.value})"


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

class DilutionTracker:
    """ Tracks changes in volume (nominal and actual) to compute concentration and net dilution. """
    def __init__(self, calibration: 'Calibration', init_conc: float, init_volume: float):
        """
        :param calibration: f(nominal) = actual
        :param init_conc: Concentration (assumed to be precise)
        :param init_volume: Nominal value
        """
        self.cal = calibration
        self.nominal: list[tuple[float, float]] = [(init_conc * init_volume, init_volume), ]
        self.actual: list[tuple[float, float]] = [(init_conc * self.cal(init_volume), self.cal(init_volume)), ]
        self.init_conc = init_conc

    def add_direct(self, moles: float, volume: float):
        """ Add a number of moles (fixed) in a given volume (nominal) """
        self.nominal.append((moles, volume))
        self.actual.append((moles, self.cal(volume)))
        # print("DEBUG: add_direct()")
        # self.print_history()

    def add_relative(self, concentration: float, volume: float):
        """ Add a volume (nominal) at a given concentration (fixed) """
        self.nominal.append((concentration * volume, volume))
        self.actual.append((concentration * self.cal(volume), self.cal(volume)))
        # print("DEBUG: add_relative()")
        # self.print_history()

    def remove(self, volume: float):
        """ Removes a volume (nominal) [use a positive number]"""
        self.nominal.append((0, -volume))
        self.actual.append((0, -self.cal(volume)))
        # print("DEBUG: remove()")
        # self.print_history()

    def replace(self, volume: float):
        """ Replaces volume (nominal) with solvent (concentration = 0) """
        self.remove(volume)
        self.add_direct(0, volume)

    def transfer(self, carry_over_volume: float, make_up_volume: float):
        """ Follows 'carry_over_volume' into a new solution """
        nom, act = self.concentration
        total_new_nom = carry_over_volume + make_up_volume
        total_new_act = self.cal(carry_over_volume) + self.cal(make_up_volume)
        self.nominal.append((-nom * carry_over_volume, total_new_nom))
        self.actual.append((-act * self.cal(carry_over_volume), total_new_act))
        # print("DEBUG: transfer()")
        # self.print_history()

    @staticmethod
    def unwind(iterable: Iterator[tuple[float, float]]):
        """ (net_moles, net_volume) """
        net_moles, net_volume = next(iterable)  # type: float, float
        for dm, dv in iterable:
            if dm < 0:
                net_moles = -dm
                net_volume = dv
                continue
            if dv >= 0:
                net_moles += dm
                net_volume += dv
            else:
                net_moles += dv * (net_moles / net_volume)
                net_volume += dv
        return net_moles, net_volume

    @property
    def current_nominal(self):
        """ Current-state nominal moles and volume """
        return self.unwind(iter(self.nominal))

    @property
    def current_actual(self):
        """ Current-state actual moles and volume """
        return self.unwind(iter(self.actual))

    @property
    def concentration(self):
        """ Current-state concentrations (nominal, actual)"""
        nm, nv = self.current_nominal
        am, av = self.current_actual
        return nm/nv, am/av

    @property
    def dilution_factor(self):
        """ (Nominal, Actual) """
        nom, act = self.concentration
        # print("DEBUG: *.dilution_factor")
        # self.print_history()
        return nom/self.init_conc, act/self.init_conc

    def history(self, *, nominal: bool = True, sig_figs: int = 3):
        """ Produces a table (with headers) revealing the history of actions and changes. """
        table: list[list[str]] = [["Action", "dVol", "dMol", "Volume", "Moles", "Concentration"], ]
        # Action dVolume dMoles Volume Moles Concentration
        if nominal:
            iterable = iter(self.nominal)
        else:
            iterable = iter(self.actual)
        net_func = lambda m, v: [f"{v:.{sig_figs}g}", f"{m:.{sig_figs}g}", f"{m/v:.{sig_figs}g}"]
        delta_func = lambda m, v: [f"{v:.{sig_figs}g}", f"{m:.{sig_figs}g}"]

        net_moles, net_volume = next(iterable)  # type: float, float
        table.append(["Init", "", "", *net_func(net_moles, net_volume)])
        for dm, dv in iterable:
            if dm < 0:
                net_moles = -dm
                net_volume = dv
                table.append(["Transfer", "", "", *net_func(net_moles, net_volume)])
                continue
            if dv >= 0:
                net_moles += dm
                net_volume += dv
                table.append(["Addition", *delta_func(dm, dv), *net_func(net_moles, net_volume)])
            else:
                net_moles += dv * (net_moles / net_volume)
                net_volume += dv
                table.append(["Removal", *delta_func(dv * (net_moles / net_volume), dv), *net_func(net_moles, net_volume)])
        return table

    def print_history(self, *, nominal: bool = True, sig_figs: int = 3):
        """ A 'pretty print' of the self.history() """
        print(format_as_table(self.history(nominal=nominal, sig_figs=sig_figs), 3, justification="R"))


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

class Calibration:
    """ Container for a polynomial relation between nominal and actual values, such that Calibration(nominal) = actual.
    Supports upper and lower bounds to clamp the response as well as a nice string representation for annotating data.
    """
    def __init__(self, *polynomial: float, floor: float = None, ceil: float = None, meta: str = ""):
        """ A polynomial in ascending order (constant, linear, quadratic, cubic, ...).
        If polynomial is Falsey, it is set to (0, 1), i.e., y = x"""
        if not polynomial:
            polynomial = (0, 1)
        self.floor = floor
        self.ceil = ceil
        self.poly = polynomial
        self.meta = meta

    def __call__(self, nominal_volume: float | str) -> float:
        # Allows Calibration to be called like a function such that Calibration(nominal) returns actual.
        x = float(nominal_volume)
        value = sum([alpha_p * (x ** p) for p, alpha_p in enumerate(self.poly)], start=0.0)
        if self.floor is not None:
            value = max(self.floor, value)
        if self.ceil is not None:
            value = min(self.ceil, value)
        return value

    def __repr__(self) -> str:
        header = "Calibration(y = f(x); f(x) = "

        if all(alpha == 0 for alpha in self.poly):
            polynomial = "0"
        elif len(self.poly) == 1:
            polynomial =  f"{self.poly[0]}"
        else:  # len(self.poly) > 1:
            poly_iter = iter(self.poly)
            const_term = str(next(poly_iter))
            linear_term = str(next(poly_iter))
            if const_term == "0" and linear_term == "1":
                part_1 = f"x"
            elif const_term == "0":
                part_1 = linear_term + "x"
            elif linear_term == "0":
                part_1 = const_term
            else:
                part_1 = f"{self.poly[0]} + {self.poly[1]}x"

            remaining_terms = list(poly_iter)
            if all(alpha == 0 for alpha in remaining_terms):
                part_2 = ""
            elif remaining_terms:
                part_1 += " + "
                part_2 = " + ".join([f"{term if term != 1 else ''}x^{p}" for p, term in enumerate(remaining_terms, start=2) if term != 0])
            else:
                part_2 = ""
            polynomial = part_1 + part_2

        if (self.ceil is not None) and (self.floor is not None):
            polynomial += f"; s.t. {self.floor} < y < {self.ceil}"
        elif self.ceil is not None:
            polynomial += f"; s.t. y < {self.ceil}"
        elif self.floor is not None:
            polynomial += f"; s.t. y > {self.floor}"

        if self.meta:
            tail = f"; {self.meta})"
        else:
            tail = ")"

        return header + polynomial + tail


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #



if __name__ == '__main__':
    def check_dil_tracker():
        test = DilutionTracker(Calibration(-0.03, 0.98, floor=0.0), 100.0, 2.0)
        print(test.dilution_factor)  # (1.0, 1.0)
        test.remove(1.0)
        test.add_direct(0, 1.0)
        print(test.dilution_factor)  # Should be cut in half
        test.transfer(2 / 3, 4 / 3)
        print(test.dilution_factor)  # Then cut by a third (1/6 original)
        test.add_relative(100*3/6, 2.0)
        print(test.dilution_factor)  # hit 2 mL of 1/6 M with 2 mL of 3/6 M to get 4 mL of 2/6 M
        test.add_relative(100*2/3, 4.0)
        print(test.dilution_factor)  # Back to 50%

        print(format_as_table(test.history(nominal=False, sig_figs=5), 3, justification="R"))

    def check_calibration():
        cal = Calibration()
        print(cal)
        cal = Calibration(42, floor=-5, ceil=+5)
        print(cal)
        cal = Calibration(-0.2440, 0.9765, floor=0.0)
        print(cal)
        cal = Calibration(-0.5, 0, 1.2, 1, ceil=0.0)
        print(cal)
        cal = Calibration(0)
        print(cal)
        cal = Calibration(0, 0)
        print(cal)
        cal = Calibration(0, 0, 0)
        print(cal)
        print(cal)
        cal = Calibration(1)
        print(cal)
        cal = Calibration(1, 0)
        print(cal)
        cal = Calibration(1, 0, 0, meta="recorded on July 12th 1907")
        print(cal)
        cal = Calibration(0, 1)
        print(cal)
        cal = Calibration(0, 1, 0)
        print(cal)

    check_calibration()
