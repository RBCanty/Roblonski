import itertools
import json
import os.path
from typing import Self


class Vial:
    """ This class is intended to represent a vial, bottle, or other form of liquid vessel that can be access via probe.

    NOTE: all parameters corresponding to dimensional quantities are in mm,
    unless otherwise specified.
    """

    def __init__(self,
                 access_height: int | float,
                 base_offset: int| float,
                 volumetric_height: int| float,
                 volumetric_diameter: int| float,
                 access_diameter: int| float,
                 meta_data: dict = None):
        """
        :param access_height: The Z height in mm at which the probe is just above the rim of
          the vial
        :param base_offset: The Z thickness of the vial's base in mm
        :param volumetric_height: The height of the vial that determines its internal volume in mm
        :param volumetric_diameter: One of the inner diameters of the vial that determines its internal volume in mm
        :param access_diameter: The smallest inner diameter of the vial that determines where the probe can be
          lowered in XY space. In mm.
        :param meta_data: Additional data for human readability in JSON form or auditing.
        """
        super().__init__()
        self.access_height = access_height
        """ The height of the vial in mm """
        self.base_offset = base_offset
        """ The Z thickness of the vial's base in mm """
        self.volumetric_height = volumetric_height
        """ The height of the vial in mm that determines its internal volume """
        self.volumetric_diameter = volumetric_diameter
        """ The inner diameter of the vial in mm that determines its internal volume """
        self.access_diameter = access_diameter
        """ The inner diameter of the vial in mm that determines where the probe can be lowered in XY space """
        self.meta_data = meta_data if meta_data else dict()

    @classmethod
    def from_json_file(cls, filepath: str) -> Self:
        """ Reconstructs a Vial object from a JSON-serializable file """
        with open(filepath, 'r') as file:
            try:
                kwargs = json.load(file)
            except json.JSONDecodeError as jde:
                print(f"JSON Error in '{filepath}'")
                print("\n\t".join([line for line in file]))
                raise jde
        return cls(**kwargs)

    def to_dict(self) -> dict[str, int | dict]:
        """ Casts the object as a dictionary which would satisfy the constructor """
        return self.__dict__


# ## The following methods are for generating objects for testing or starting up a new Deck ## # # # # # # # # # # # # #

def make_gc_vial_no_cap():
    print("TODO: volumetric_height, volumetric_diameter, access_diameter")
    return Vial(access_height=30,
                base_offset=1,
                volumetric_height=25,
                volumetric_diameter=0,
                access_diameter=1,
                meta_data={'Type': "GC Vial (Part No. ###)", 'cap': False})


def make_fake_vial():
    return Vial(access_height=125,
                base_offset=0,
                volumetric_height=125,
                volumetric_diameter=0,
                access_diameter=1)


def sandbox():
    # SET THESE PARAMETERS (Below) # # # #
    all_row_ids = "ABCDEFGH"
    first_col_number = 1
    last_col_number = 12
    rack_path: str = "provide the full path to the rackname_vials directory here"
    default_vial_parameters = Vial(
        access_height=9999,  # Fill in these values based on the vial you are using for testing.
        base_offset=9999,
        volumetric_height=9999,
        volumetric_diameter=9999,
        access_diameter=9999,
    )
    # SET THESE PARAMETERS (Above) # # # #

    for row, col in itertools.product(all_row_ids.capitalize(), range(first_col_number, last_col_number+1)):
        vil_file_name = f"vial_{row}{col}.vil"
        with open(os.path.join(rack_path, vil_file_name), 'w') as vil_file:
            json.dump(default_vial_parameters.to_dict(), vil_file, indent=2)




if __name__ == '__main__':
    print("If trying to activate sandbox mode, please fill out the parameters in the sandbox() method, then"
          "comment this line and uncomment the following line which calls the sandbox() method, then re-run this"
          "file.")
    # sandbox()
