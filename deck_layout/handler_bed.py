import json
import os
import abc
from abc import abstractmethod
from typing import Self, Callable, Iterable

from deck_layout.coordinates import Point2D
from deck_layout.rack import Rack

MAX_Z_HEIGHT = 125
MAX_SYRINGE_VOL = 1000
SYSTEM_AIR_GAP = 20

DEFAULT_SYRINGE_FLOWRATE = 1.0
""" Specified in mL/min """

PRIMING_FLOWRATE = 5
""" Specified in mL/min """

DEFAULT_XY_SPEED = 50
""" Specified in mm/s """

DEFAULT_Z_SPEED = 25
""" Specified in mm/s """

DEFAULT_INJECTOR_LOC = ("injector", "A1")  # NOT DEPLOYED, ignore this



class NotSet(object): pass


class HandlerBed:
    """ Representation of the liquid handler bed. Contains the boundaries, any racks, and the resource file. """
    def __init__(self, x_bounds: tuple[int, int], y_bounds: tuple[int, int], z_bounds: tuple[int, int], _meta: dict = None):
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds
        self.z_bounds = z_bounds
        self.racks: dict[str, Rack] = {}
        self._directory: str | None = None
        self.resource_cfg_path: str | None = "~/resources_cfg.json"

    def get_min_xy(self) -> Point2D:
        """ Provides the point at the minimum XY coordinate of the liquid handler's bounds. """
        return Point2D(self.x_bounds[0], self.y_bounds[0])

    def get_max_xy(self) -> Point2D:
        """ Provides the point at the maximum XY coordinate of the liquid handler's bounds. """
        return Point2D(self.x_bounds[1], self.y_bounds[1])

    def get_min_z(self) -> int:
        """ Provides the point at the minimum Z coordinate of the liquid handler's bounds. """
        return self.z_bounds[0]

    def get_max_z(self) -> int:
        """ Provides the point at the maximum Z coordinate of the liquid handler's bounds. """
        return self.z_bounds[1]

    def save_to_path(self, directory: str, as_file: str = None) -> None:
        """ Saves the Bed (and it's Racks (and their Vials)) """
        os.makedirs(directory, exist_ok=True)
        file_name = "gilson_bed" if as_file is None else as_file
        with open(os.path.join(directory, file_name + ".bed" * bool(".bed" not in file_name)), 'w') as file:
            json.dump({'x_bounds': self.x_bounds, 'y_bounds': self.y_bounds, 'z_bounds': self.z_bounds}, file, indent=2)
        for rack_name, rack_obj in self.racks.items():
            rack_obj.save_to_path(directory, rack_name)

    @classmethod
    def load_from_file(cls, directory: str, bed_file: str) -> Self:
        """ Loads a Bed object from files and loads its Racks (which load their Vials) """
        bed = cls.partial_from_json_file(os.path.join(directory, bed_file))
        bed.load_racks_from_folder(directory, key=lambda f: ".rak" in f)
        bed._directory = directory
        return bed

    @classmethod
    def partial_from_json_file(cls, filepath: str) -> Self:
        """ Saves the Bed itself to a file (nothing else) """
        with open(filepath, 'r') as file:
            try:
                kwargs: dict = json.load(file)
            except json.JSONDecodeError as jde:
                print(f"JSON Error in '{filepath}'")
                print("\n\t".join([line for line in file]))
                raise jde
        try:
            xb = kwargs.pop('x_bounds')
            yb = kwargs.pop('y_bounds')
            zb = kwargs.pop('z_bounds')
        except KeyError as e:
            raise ValueError(f"Bed file missing 'x/y/z_bound':\n{kwargs}\n{repr(e)}")

        return cls(xb, yb, zb, _meta=kwargs)

    def load_rack_from_file(self, root: str, rack_file_name: str) -> None:
        """ Creates and saves a Rack object from a json-serializable file """
        rack: Rack = Rack.load_from_path(root, rack_file_name)
        rack_name = rack_file_name.split(".")[0]

        rack_x, rack_y = rack.origin_xy
        real_coordinate = [rack_x, rack_y, rack.travel_z_height]
        coordinate_bounds = [self.x_bounds, self.y_bounds, self.z_bounds]

        if any([(not lb <= r <= ub) for r, (lb, ub) in zip(real_coordinate, coordinate_bounds)]):
            print(f"\033[93m WARNING: Rack {rack_name} may not be compatible with the Bed \033[0m \n"
                  f"Check ({rack_x}, {rack_y}, {rack.travel_z_height}) "
                  f"within ({self.x_bounds}, {self.y_bounds}, {self.z_bounds})")
            # return

        self.racks[rack_name] = rack

    def load_racks_from_folder(self, directory: str, key: Callable[[str], bool] = lambda f: ".rak" in f) -> None:
        """ Bulk import for racks files given a directory.  'key' is called on the file name. """
        for root, _, files in os.walk(directory):
            for rack_file_name in files:
                if not key(rack_file_name):
                    continue
                self.load_rack_from_file(root, rack_file_name)

    def __getitem__(self, key: str) -> Rack:
        return self.racks[key]

    def get(self, key: str, default: Rack | None) -> Rack | None:
        return self.racks.get(key, default)

    def __setitem__(self, key: str, value: Rack) -> None:
        self.racks[key] = value

    def setdefault(self, key: str, default: Rack) -> Rack:
        return self.racks.setdefault(key, default)

    def _sanitize_cfg_path(self, cfg_path: str | None):
        if cfg_path is None:
            cfg_path = self.resource_cfg_path
        if cfg_path is None:
            return None
        if cfg_path.startswith("~/") or cfg_path.startswith("~\\"):
            if self._directory:
                return os.path.join(self._directory, cfg_path[2:])
            return None
        return cfg_path

    def read_resource_cfg(self, cfg_path: str = None) -> dict:
        """ Can be a full path.  If the path starts with '~/' or '~\' then it will replace '~' with
        the path the bed was loaded from (if initialized from a file). None will default to "~/resources_cfg.json".
        """
        cfg_path = self._sanitize_cfg_path(cfg_path)
        if cfg_path is None:
            return {}
        try:
            with open(cfg_path, 'r') as _file:
                return json.load(_file)
        except FileNotFoundError:
            return {}

    def write_resource_cfg(self, cfg_object: dict | None, cfg_path: str = None) -> bool:
        """ Can be a full path.  If the path starts with '~/' or '~\' then it will replace '~' with
        the path the bed was loaded from (if initialized from a file). None will default to "~/resources_cfg.json".

        If the object is None, then this method just quits, returning True.
        """
        if cfg_object is None:
            return True
        cfg_path = self._sanitize_cfg_path(cfg_path)
        if cfg_path is None:
            return False
        try:
            with open(cfg_path, 'w') as _file:
                json.dump(cfg_object, _file, indent=2)
        except:  # noqa: A False return is sufficient
            return False
        return True

    def update_resource_cfg_value[T](self, _key: str, value: T | Callable[[T], T], cfg_path: str = None, *, default: T = NotSet(), overwrite: bool = True):
        """ Used to modify a specific value.

        :param _key: The dictionary key (top level only). If None, the method will quit, returning True.
        :param value: A value to write to the key OR a callable which will take the previous (current) value in the cfg
          file and return the new value to write.
        :param cfg_path: Can be a full path.  If the path starts with '~/' or '~\' then it will replace '~' with
          the path the bed was loaded from (if initialized from a file). None will default to "~/resources_cfg.json".
        :param default: If reading from the file (value is a Callable) and the key is not present, what value should
          be used?
        :param overwrite: Should the new value overwrite the previous value (Default: True)

        :return: True - no errors, False - error
        """
        if _key is None:
            return True
        cfg_object = self.read_resource_cfg(cfg_path)

        if callable(value):
            if isinstance(default, NotSet):
                try:
                    prev_value: T = cfg_object[_key]
                except KeyError:
                    return False
            else:
                prev_value: T = cfg_object.get(_key, default)
            value = value(prev_value)

        if overwrite:
            cfg_object[_key] = value
        else:
            cfg_object.setdefault(_key, value)

        return self.write_resource_cfg(cfg_object, cfg_path)

    def init_message(self):
        yield f"X:{self.x_bounds}, Y:{self.y_bounds}, Z:{self.z_bounds}"
        for rack_name, rack_obj in self.racks.items():
            yield rack_name
            yield from rack_obj.init_message()


class Placeable(abc.ABC):
    """ Abstract class for positions on the liquid handler which can be accessed. """
    @abstractmethod
    def get_xy_position(self) -> Point2D: ...
    """ The center of the vial/location """
    @abstractmethod
    def get_access_z(self) -> int: ...
    """ A safe Z coordinate above the vial/location """

    @abstractmethod
    def get_transfer_z(self) -> int: ...
    """ The Z coordinate within the vial/location for fluid transfer """
    @abstractmethod
    def get_edge(self) -> Point2D: ...
    """ The XY coordinate used for tip-touch, dispenses at a vial/position edge, etc. """

    @abstractmethod
    def __repr__(self) -> str: ...

    def lazy_name(self) -> str:
        return "Placeable(...)"

    def __eq__(self, other):
        if not isinstance(other, Placeable):
            return False
        if self.get_xy_position() != other.get_xy_position():
            return False
        if self.get_access_z() != other.get_access_z():
            return False
        if self.get_transfer_z() != other.get_transfer_z():
            return False
        if self.get_edge() != other.get_edge():
            return False
        return True


class Coordinate(Placeable):
    """ A location identified by exact XYZ coordinates. """
    def __init__(self, xy: Point2D, z: int | float, edge_offset: int = 0):
        self.xy = xy
        self.z = z
        self.edge_offset = edge_offset

    def get_xy_position(self) -> Point2D:
        return self.xy

    def get_access_z(self) -> int:
        return self.z

    def get_transfer_z(self) -> int:
        return self.z

    def get_edge(self) -> Point2D:
        return self.xy + Point2D(x=self.edge_offset, y=0)

    def __repr__(self):
        return f"Coordinate({self.xy!r}, {self.z})"

    def lazy_name(self):
        return f"({self.xy.x}, {self.xy.y}, {self.z})"


class NamePlace(Placeable):
    """ A location identified by a Rack name and Vial ID--e.g. (StorageRack, A4) """
    def __init__(self, bed: HandlerBed | None, rack_name: str, vial_id: str):
        self.bed = bed
        self.rack_name = rack_name
        self.vial_id = vial_id

    def get_xy_position(self) -> Point2D:
        return Point2D(*self.bed[self.rack_name].get_vial_xy_location(self.vial_id))

    def get_access_z(self) -> int:
        if self.bed is None:
            return MAX_Z_HEIGHT
        return self.bed[self.rack_name].get_vial_access_z(self.vial_id)

    def get_transfer_z(self) -> int:
        if self.bed is None:
            return MAX_Z_HEIGHT
        return self.bed[self.rack_name].get_vial_transfer_z(self.vial_id)

    def get_edge(self) -> Point2D:
        return Point2D(*self.bed[self.rack_name].get_y_edge(self.vial_id))

    def __repr__(self):
        return f"NamePlace(__bed__, '{self.rack_name}', '{self.vial_id}')"

    def lazy_name(self):
        return f"{self.rack_name}/{self.vial_id}"


class ShiftingPlaceable[T](Placeable):
    """ A collection of Placeable objects which will be cycled through.

    Since vials have finite volumes, it is sometimes convenient to represent repeated reservoirs with a
    ShiftingPlaceable so that the system can move onto the next reservoir as needed while still treating the
    reservoir, collectively, as a single placeable. """
    def __init__(self, places: list[T]):
        self._places = places
        self._index = 0

    @property
    def place(self) -> T:
        return self._places[self._index]

    def __repr__(self):
        return f"ShiftingPlaceable(" + ", ".join([repr(p) for p in self._places]) + f"; index={self._index})"

    @property
    def index_is_valid(self) -> bool:
        return 0 <= self._index < len(self._places)

    def next(self) -> bool:
        """ Moves to the next Place.  True if valid, False otherwise (Should be reset). """
        self._index += 1
        return self.index_is_valid

    def previous(self) -> bool:
        """ Moves to the previous Place.  True if valid, False otherwise (Should be reset). """
        self._index -= 1
        return self.index_is_valid

    def reset(self) -> bool:
        """ Resets to the first Place.  True if valid, False otherwise (If false then there are no Places loaded) """
        self._index = 0
        return self.index_is_valid

    def last(self) -> bool:
        """ Jumps to the last Place.  True if valid, False otherwise (If false then there are no Places loaded) """
        self._index = len(self._places) - 1
        return self.index_is_valid

    def pop(self, index: int) -> bool:
        """ Removes the Place at the given index.  Raises from list.pop()'s Exceptions.
        The internal index will track the previous Value, unless the provided index is the current internal index, in
        which case the internal index will proceed to the next in the order.

        Returns True if valid, False otherwise (Should be reset). """
        self._places.pop(index)
        if self._index <= index:
            return self.index_is_valid
        else:
            return self.previous()

    def insert(self, place: T, index: int = None) -> bool:
        """ Inserts the Place at the given index (ergo, it 'inserts' it before the specified element), and index=None
        will append to the end.
        Raises from list.insert()'s Exceptions.
        The internal index will track the previous Value.

        Returns True if valid, False otherwise (Should be reset).
        """
        if index is None:
            index = len(self._places)
        self._places.insert(index, place)
        if self._index <= index:
            return self.next()
        else:
            return self.index_is_valid

    def extend(self, places: Iterable[T]) -> bool:
        """ Calls list.extend(places).

        Returns True if valid, False otherwise (Should be reset).
        """
        self._places.extend(places)
        return self.index_is_valid

    def get_xy_position(self) -> Point2D:
        return self.place.get_xy_position()

    def get_access_z(self) -> int:
        return self.place.get_access_z()

    def get_transfer_z(self) -> int:
        return self.place.get_transfer_z()

    def get_edge(self) -> Point2D:
        return self.place.get_edge()


DEFAULT_WASTE_LOC = Coordinate(Point2D(100, 100), 90)


if __name__ == '__main__':
    pass
