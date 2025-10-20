import json
import os
import re
from typing import Self, Callable, Literal

from deck_layout.coordinates import Point2D
from deck_layout.pprint_rack import VialTuple, agglomerate, Cluster
from deck_layout.vial import Vial


PI = 3.1415926535897932384626433

DEFAULT_SAFE_Z_TRAVEL_OFFSET = 5
DEFAULT_SAFE_Z_PIPETTE_OFFSET = 1
CANNULA_DIAMETER_MM = 1.44

WELL_ID = re.compile(r"(?P<row>[a-z]+)(?P<column>[0-9]+)", re.IGNORECASE)
# REGEX for parting well names


def row2num(a):
    """ converts a row letter to a number (1-index) """
    return 0 if a == '' else 1 + ord(a[-1]) - ord('A') + 26 * row2num(a[:-1])


def parse_well_id(well_id: str):
    """ Converts a well ID (e.g., D3) into a tuple of indices (1-indexed)

    ID -> (row, col) """
    row_id, column_id = WELL_ID.match(well_id).groups()
    row_num = row2num(row_id)
    column_num = int(column_id)
    return row_num, column_num


class Rack:
    """ A rack is an object that holds Vials in a grid (even if that grid is 1x1)

    NOTE: Dimensional quantities are in mm
    """
    def __init__(self,
                 origin_x: int| float,
                 origin_y: int| float,
                 rack_pos_x_spacing: int | float,
                 rack_pos_y_spacing: int | float,
                 num_rows: int,
                 num_cols: int,
                 base_z_height: int| float,
                 travel_z_height: int| float,
                 meta_data: dict = None
                 ):
        """
        Constructs a Rack object.

        :param origin_x: The X coordinates of the top left well's center
        :param origin_y: The X coordinates of the top left well's center
        :param rack_pos_x_spacing: The X center-to-center distance between wells in the rack, in mm
        :param rack_pos_x_spacing: The Y center-to-center distance between wells in the rack, in mm
        :param num_rows: The number of rows in the rack (a row is a single Y, spanning X)
        :param num_cols: The number of columns in the rack (a column is a single X, spanning Y)
        :param base_z_height: The height of the rack's base (the part that touches the bottom of the vials), in mm
        :param travel_z_height: The safe travel Z-height for this rack, in mm
        :param meta_data: Any supplemental data
        """
        self.origin_xy: Point2D = Point2D(x=origin_x, y=origin_y)
        """ Represents the X and Y positions of the center of the rack vial hole closest to the GX-241's 
          own origin point. """
        self.rack_pos_x_spacing = rack_pos_x_spacing
        """ Center-to-center spacing between rack positions in X direction (column to column). In mm """
        self.rack_pos_y_spacing = rack_pos_y_spacing
        """ Center-to-center spacing between rack positions in Y direction (row to row). In mm """
        self.num_rows = num_rows
        """ Number of rows in the rack """
        self.num_cols = num_cols
        """ Number of columns in the rack """
        self.base_z_height = base_z_height
        """ The Z-height of where vials rest. In mm """
        self._travel_z_height = travel_z_height
        """ The highest Z-height of the rack (when empty). In mm """
        self.vials: dict[str, Vial] = {}
        """ A map of vial name (eg "A1", "H12") to a vial object"""
        self.meta_data = meta_data
        """ The user can put any data here so long as it is json-serializable """

    @property
    def travel_z_height(self) -> int:
        """ The current safe travel Z-height (in mm) """
        vial_offset = max([v.access_height for v in self.vials.values()], default=0)
        return max(self.base_z_height + vial_offset, self._travel_z_height) + DEFAULT_SAFE_Z_TRAVEL_OFFSET

    # ## Serialization ## # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def save_to_path(self, directory: str, as_file: str = None) -> None:
        """ Saves the Rack (and it's vial) to file form """
        x, y = self.origin_xy
        file_name = f"rack_at_{x}_{y}" if as_file is None else as_file
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, file_name + ".rak" * bool(".rak" not in file_name)), 'w') as file:
            json.dump(self.to_dict(), file, indent=2)
        vial_folder = os.path.join(directory, f"{file_name}_vials")
        os.makedirs(vial_folder, exist_ok=True)
        for vial_name, vial_object in self.vials.items():
            with open(os.path.join(vial_folder, f"vial_{vial_name}.vil"), 'w') as file:
                json.dump(vial_object.to_dict(), file, indent=2)

    @classmethod
    def load_from_path(cls, directory: str, rack_file: str) -> Self:
        """ Loads the Rack object from file and populates its Vials """
        rack_name: str = rack_file.split(".")[0]
        rack: Rack = cls.partial_from_json_file(os.path.join(directory, rack_file))
        vial_folder = os.path.join(directory, f"{rack_name}_vials")
        rack.load_vials_from_folder(vial_folder, key=lambda f: ".vil" in f)
        return rack

    def to_dict(self) -> dict[str, int]:
        """ Returns a dictionary which can be passed to the constructor """
        temp = {k: v for k, v in self.__dict__.items()}
        temp.pop('origin_xy')
        origin_x, origin_y = self.origin_xy
        temp['origin_x'] = origin_x
        temp['origin_y'] = origin_y
        temp['travel_z_height'] = temp.pop('_travel_z_height')
        temp.pop('vials')
        return temp

    @classmethod
    def partial_from_json_file(cls, filepath) -> Self:
        """ creates a Rack object from a json-serializable file. "self.vials" is uninitialized. """
        with open(filepath, 'r') as file:
            try:
                kwargs = json.load(file)
            except json.JSONDecodeError as jde:
                print(f"JSON Error in '{filepath}'")
                print("\n\t".join([line for line in file]))
                raise jde
        return cls(**kwargs)

    def load_vial_from_file(self, root: str, vial_file_name: str) -> None:
        """ Creates and saves a Vial object from a json-serializable file """
        vial: Vial = Vial.from_json_file(os.path.join(root, vial_file_name))

        pattern = re.compile(r"vial_([A-Za-z0-9]+)\.vil", re.IGNORECASE)
        try:
            name, *_ = pattern.match(vial_file_name).groups()
        except AttributeError:
            print(f"Vial file '{vial_file_name}' not in the valid format 'vial_&##.vil'.  Ignoring.")
            return
        # name: str = vial_file_name.split(".")[0].split("_")[-1]

        try:
            self.check_row_and_column(*parse_well_id(name))  # id_to_row_and_colum
        except ValueError as e:
            print(f"\033[93m WARNING: Vial {name} may not be compatible with the Rack \033[0m \n"
                  f"See: {e.args[0]}")

        self.vials[name] = vial

    def load_vials_from_folder(self, directory: str, key: Callable[[str], bool] = lambda f: ".vil" in f) -> None:
        """ Bulk import for vial files given a directory.  'key' is called on the file name. """
        for root, _, files in os.walk(directory):
            for vial_file_name in files:
                if not key(vial_file_name):
                    continue
                self.load_vial_from_file(root, vial_file_name)

    # ## Vial management methods ## # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    def get_vial_xy_location(self, vial_id: str) -> tuple[int, int]:
        """ Given a vial ID (eg "A1", "H12"), provides the true X and Y coordinates (in mm)"""
        self.check_vial_id(vial_id)
        row, col = self.id_to_row_and_colum(vial_id)
        self.check_row_and_column(row, col)
        offset: Point2D = Point2D(
            (col - 1) * self.rack_pos_x_spacing,
            (row - 1) * self.rack_pos_y_spacing,
            )
        x, y = self.origin_xy + offset
        return x, y

    def get_vial_access_z(self, vial_id, additional_offset: int = DEFAULT_SAFE_Z_PIPETTE_OFFSET) -> int:
        """ Provides the Z position above the top of the vial (in mm) """
        self.check_vial_id(vial_id)
        return self.vials[vial_id].access_height + self.base_z_height + additional_offset

    def get_vial_transfer_z(self, vial_id, additional_offset: int = DEFAULT_SAFE_Z_PIPETTE_OFFSET) -> int:
        """ Provides the Z position above the base of the vial (in mm) """
        self.check_vial_id(vial_id)
        return self.vials[vial_id].base_offset + self.base_z_height + additional_offset

    def get_y_edge(self, vial_id: str) -> tuple[int, int]:
        """ Given a vial ID (eg "A1", "H12"), provides the true X and Y coordinates (in mm) of the y-inward edge """
        self.check_vial_id(vial_id)
        center = Point2D(*self.get_vial_xy_location(vial_id))
        offset = Point2D(y=int(self.vials[vial_id].access_diameter/2 - CANNULA_DIAMETER_MM/2 + 0.5), x=0)
        rack_center = Point2D(
            self.num_cols * self.rack_pos_x_spacing,
            self.num_rows * self.rack_pos_y_spacing
        ) / 2 + self.origin_xy
        if center.y > rack_center.y:
            touch = center - offset
        else:
            touch = center + offset
        x, y = touch
        return x, y

    # ## Helper methods ## # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    @staticmethod
    def id_to_row_and_colum(vial_id: str) -> tuple[int, int]:
        """ Casts an id (eg "A1", "H12") to a (row, column) pair, 1-indexed"""
        try:
            row, col = parse_well_id(vial_id)
        except AttributeError:
            raise ValueError(f"Vial {vial_id} is an invalid vial ID")
        return row, col

    def check_vial_id(self, vial_id: str):
        """ If bad vial_id, throws an ValueError """
        if vial_id not in self.vials:
            raise ValueError(f"Invalid vial ID: {vial_id}")

    def check_row_and_column(self, row, column):
        """ If bad (row, column), throws an ValueError """
        errors = []
        if not (0 < row <= self.num_rows):
            errors.append(f"Invalid row, must be (0, {self.num_rows}]")
        if not (0 < column <= self.num_cols):
            errors.append(f"Invalid column, must be (0, {self.num_cols}]")
        if errors:
            raise ValueError("\n".join(errors))

    def init_message(self):
        vials_to_print = []
        for vial_name in self.vials.keys():
            row_id, column_id = WELL_ID.match(vial_name).groups()
            column = int(column_id)
            row = row2num(row_id)
            vials_to_print.append(VialTuple(row, row_id, column))
        yield from agglomerate([Cluster([v, ]) for v in vials_to_print])


RACK_BED_POSITION: dict[int, tuple[int, int]] = {
    1: (9, 41),
    2: (100, 248)
}


# ## The following methods are for generating objects for testing or starting up a new Deck ## # # # # # # # # # # # # #

def make_338_rack(position: Literal[1, 2]):
    origin_x, origin_y = RACK_BED_POSITION[position]
    return Rack(origin_x=origin_x, origin_y=origin_y,
                rack_pos_x_spacing=18, rack_pos_y_spacing=13.73333333,
                num_rows=16, num_cols=4,
                base_z_height=83, travel_z_height=113,
                meta_data={'Type': "Gilson 338"})


def make_335_rack(position: Literal[1, 2]):
    origin_x, origin_y = RACK_BED_POSITION[position]
    return Rack(origin_x=origin_x, origin_y=origin_y,
                rack_pos_x_spacing=18, rack_pos_y_spacing=18.63636364,
                num_rows=12, num_cols=4,
                base_z_height=68, travel_z_height=113,
                meta_data={'Type': "Gilson 335"})


def make_wash_station():
    print("TODO: base_z_height")
    return Rack(origin_x=1, origin_y=1,
                rack_pos_x_spacing=14, rack_pos_y_spacing=0,
                num_rows=1, num_cols=3,
                base_z_height=125, travel_z_height=125,
                meta_data={'Type': "Fixed on bed"})


def make_sample_loop():
    print("TODO: base_z_height")
    return Rack(origin_x=147, origin_y=1,
                rack_pos_x_spacing=0, rack_pos_y_spacing=0,
                num_rows=1, num_cols=1,
                base_z_height=115, travel_z_height=115,
                meta_data={'Type': "Fixed on bed"})


if __name__ == '__main__':
    from deck_layout.vial import make_gc_vial_no_cap, make_fake_vial

    main_rack = make_338_rack(1)
    main_rack.vials["A1"] = make_gc_vial_no_cap()
    main_rack.vials["A2"] = make_gc_vial_no_cap()
    main_rack.vials["A3"] = make_gc_vial_no_cap()
    main_rack.vials["B4"] = make_gc_vial_no_cap()
    main_rack.save_to_path("./ExampleGilsonDatabase", "pos_1_rack")

    wash_station = make_wash_station()
    wash_station.vials["A1"] = make_fake_vial()
    wash_station.vials["A2"] = make_fake_vial()
    wash_station.vials["A3"] = make_fake_vial()
    wash_station.save_to_path("./ExampleGilsonDatabase", "wash")

    injector = make_sample_loop()
    injector.vials["A1"] = make_fake_vial()
    injector.save_to_path("./ExampleGilsonDatabase", "injector")

    print("Saved")

    new_rack = Rack.load_from_path("./Test", "pos_1_rack.rak")

    print(f"old {main_rack.travel_z_height} = new {new_rack.travel_z_height} ?")

    print("A1.get_vial_xy_location", new_rack.get_vial_xy_location("A1"))

    print("H12.get_vial_xy_location", new_rack.get_vial_xy_location("H12"))

    print("G7.get_vial_access_z", main_rack.get_vial_access_z("G7"))

    print("B4.get_vial_transfer_z", new_rack.get_vial_transfer_z("B4"))

    try:
        print(main_rack.get_vial_xy_location("K42"))
    except ValueError as my_value_error:
        print(repr(my_value_error))
