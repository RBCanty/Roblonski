from typing import Iterator, Self


class _Point:
    """ Base class for an N-dimensional point """
    def __init__(self, /, **kwargs):
        pass

    def _get_dim(self, other):
        my_keys = self.__dict__.keys()
        your_keys = other.__dict__.keys()
        if my_keys != your_keys:
            raise TypeError(f"Cannot add two points of different dimensions ({self} + {other})")
        return my_keys

    def _get(self, item):
        return self.__dict__[item]

    def __add__(self, other: Self):
        cls = type(self)
        return cls(**{k: self._get(k) + other._get(k) for k in self._get_dim(other)})

    def __sub__(self, other: Self):
        cls = type(self)
        return cls(**{k: self._get(k) - other._get(k) for k in self._get_dim(other)})

    def __abs__(self):
        return sum([v**2 for v in self])**0.5

    def __eq__(self, other: Self):
        return all([self._get(k) == other._get(k) for k in self._get_dim(other)])

    def __str__(self):
        return f"(" + ", ".join([f"{v}" for v in self]) + ")"

    def __repr__(self):
        name = type(self).__name__
        return f"{name}(" + ", ".join([f"{k}={v}" for k, v in self.__dict__.items()]) + ")"

    def __iter__(self) -> Iterator[int]:
        return iter(self.__dict__.values())

    def interpolate_min(self, other: Self) -> Self:
        """ creates a new point whose dimensions are the min of each dimension.
        Eg (1, 2, 3) & (3, 2, 1) -> (1, 2, 1) """
        cls = type(self)
        return cls(**{k: min(self._get(k), other._get(k)) for k in self._get_dim(other)})

    def interpolate_max(self, other: Self) -> Self:
        """ creates a new point whose dimensions are the max of each dimension.
        Eg (1, 2, 3) & (3, 2, 1) -> (3, 2, 3) """
        cls = type(self)
        return cls(**{k: max(self._get(k), other._get(k)) for k in self._get_dim(other)})

    def interpolate_mid(self, other: Self) -> Self:
        """ creates a new point whose dimensions are the average of each dimension.
        Eg (0, 2, 4) & (4, 2, 0) -> (2, 2, 2) """
        cls = type(self)
        return cls(**{k: self._get(k) + other._get(k) for k in self._get_dim(other)}) / 2

    def __mul__(self, scale: int | float):
        cls = type(self)
        return cls(**{k: scale*v for k, v in self.__dict__.items()})

    def __rmul__(self, other):
        return self * other

    def __truediv__(self, divisor: int | float):
        cls = type(self)
        return cls(**{k: v / divisor for k, v in self.__dict__.items()})

    def __gt__(self, other: Self):
        return abs(self) > abs(other)


class Point1D(_Point):
    def __init__(self, x):
        super().__init__()
        self.x = x


class Point2D(Point1D):
    def __init__(self, x, y):
        super().__init__(x)
        self.y = y


class Point3D(Point2D):
    def __init__(self, x, y, z):
        super().__init__(x, y)
        self.z = z


if __name__ == '__main__':
    p0 = _Point(b=4)
    print(p0)
    print(repr(p0))

    p1 = Point3D(1, 1, 1)
    p2 = Point3D(0, 0, 0)

    print(f"{p1=!s}")
    print(f"{p2=!s}")
    print(f"{p1 + p2=!s}")
    print(f"{p1 - p2=!s}")
    print(f"{abs(p1)=}")
    print(f"{abs(p2)=}")

    print(f"{p1 * 2=}")
    print(f"{-2 * p1=}")
    print(f"{p1 * (2 ** 0.5)=}")
    print(f"{p2 / 2=}")

    print(p1.interpolate_mid(p2))

    a, b, c = p1
    print(p1)
    print(a, b, c)
