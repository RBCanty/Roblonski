import random
import tkinter as tk
from threading import Lock
from typing import Literal

from deck_layout.handler_bed import DEFAULT_Z_SPEED, DEFAULT_XY_SPEED, DEFAULT_SYRINGE_FLOWRATE, MAX_Z_HEIGHT
from deck_layout.handler_bed import Point2D, Coordinate
from liquid_handling.gilson_handler import Gilson241LiquidHandler
from workflows.common_macros import boot_with_user

PADDING = {'ipadx': 8, 'ipady': 8, 'padx': 1, 'pady': 1}
PRECISION = 5


class Seahorse:
    """ User interface for basic liquid handler control. """
    def __init__(self, root: tk.Tk | tk.Toplevel, ctrl: Gilson241LiquidHandler):
        self.root = root
        self.ctrl = ctrl
        self._position: tuple[float, float, float] = (-1, -1, -1)
        self._mutex = Lock()
        self.xyz: list[tk.Label] = []
        self.speeds: list[tk.Entry] = []
        self.jumps = []

        # Build the UI # ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ #
        frame = tk.Frame(self.root)
        frame.winfo_toplevel().title("Robotic Arm Control")
        self.root.attributes('-topmost', 1)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=10)

        tk.Label(frame, text="-x").grid(row=2, column=0, **PADDING)
        tk.Label(frame, text="+x").grid(row=2, column=4, **PADDING)
        tk.Label(frame, text="+y").grid(row=4, column=2, **PADDING)
        tk.Label(frame, text="-y").grid(row=0, column=2, **PADDING)
        tk.Button(frame, text="←", command=lambda: self.move_delta(dx=-self.step_size)).grid(row=2, column=1, **PADDING)
        tk.Button(frame, text="↑", command=lambda: self.move_delta(dy=-self.step_size)).grid(row=1, column=2, **PADDING)
        tk.Button(frame, text="→", command=lambda: self.move_delta(dx=self.step_size)).grid(row=2, column=3, **PADDING)
        tk.Button(frame, text="↓", command=lambda: self.move_delta(dy=self.step_size)).grid(row=3, column=2, **PADDING)
        tk.Button(frame, text="⌂", command=self.home).grid(row=2, column=2, **PADDING)

        tk.Button(frame, text="UP", command=lambda: self.move_delta(dz=self.step_size)).grid(row=0, rowspan=2, column=5, **PADDING, sticky="NSEW")
        tk.Button(frame, text="max", command=self.max_z).grid(row=2, column=5, **PADDING, sticky="EW")
        tk.Button(frame, text="DOWN", command=lambda: self.move_delta(dz=-self.step_size)).grid(row=3, rowspan=2, column=5, **PADDING, sticky="NSEW")

        tk.Label(frame, text="X").grid(row=0, column=6, **PADDING)
        tk.Label(frame, text="Y").grid(row=1, column=6, **PADDING)
        tk.Label(frame, text="Z").grid(row=2, column=6, **PADDING)
        self.xyz = [tk.Label(frame, text=str(p)) for p in self._position]

        [label.grid(row=row, column=7) for row, label in enumerate(self.xyz)]
        tk.Button(frame, text="Update", command=self.update_positions).grid(row=3, column=6, columnspan=2, **PADDING, sticky="NSEW")

        tk.Label(frame, text="Sxy").grid(row=0, column=8, **PADDING)
        tk.Label(frame, text="Sz").grid(row=1, column=8, **PADDING)
        tk.Label(frame, text="Step").grid(row=2, column=8, **PADDING)
        self.speeds = [
            tk.Entry(frame),
            tk.Entry(frame),
            tk.Entry(frame),
        ]
        [entry.grid(row=row, column=9) for row, entry in enumerate(self.speeds)]
        for entry, speed in zip(self.speeds, [DEFAULT_XY_SPEED, DEFAULT_Z_SPEED, 1]):
            entry.insert(0, str(speed))

        tk.Button(frame, text="Jx", command=lambda: self.jump('x')).grid(row=0, column=10, **PADDING, sticky="EW")
        tk.Button(frame, text="Jy", command=lambda: self.jump('y')).grid(row=0, column=11, **PADDING, sticky="EW")
        tk.Button(frame, text="Jz", command=lambda: self.jump('z')).grid(row=0, column=12, **PADDING, sticky="EW")
        self.jumps = [
            tk.Entry(frame),
            tk.Entry(frame),
            tk.Entry(frame)
        ]
        [entry.grid(row=1, column=column) for column, entry in enumerate(self.jumps, start=10)]
        [entry.insert(0, "0") for entry in self.jumps]

        tk.Label(frame, text="Volume (uL)").grid(row=2, column=10, **PADDING)
        self._vol = tk.Entry(frame)
        self._vol.grid(row=2, column=11, columnspan=2)
        tk.Button(frame, text="AR", command=lambda: self.aspirate(source="R")).grid(row=3, column=10, **PADDING)
        tk.Button(frame, text="AN", command=lambda: self.aspirate(source="N")).grid(row=3, column=11, **PADDING)
        tk.Button(frame, text="DN", command=self.dispense).grid(row=3, column=12, **PADDING)
        tk.Button(frame, text="⌂", command=self.home_pump).grid(row=4, column=10, columnspan=3, **PADDING, sticky="EW")

        tk.Label(frame, text="Use arrows to move arm\n"
                             "⌂ will home the arm\n"
                             "'max' will move the arm to max Z height.\n"
                             "X, Y, and Z will show the position, requires manual update\n"
                             "Sxy and Sz are for arm movement speeds\n"
                             "Step adjust the movement when using the arrows\n"
                             "Jx, Jy, and Jz will jump the arm (One axis at a time)\n"
                             "(Note: when moving in X/Y, Jumps will raise to max z first)\n"
                             "Volume (mL) is for the pump\n"
                             "AR/AN - Aspirate from Reservoir/Needle\n"
                             "DN - Dispense to Needle\n"
                             "⌂ will home the pump (Pay attention to where the needle is!)\n").grid(
            row=0, column=13, rowspan=5, **PADDING, sticky="NSEW"
        )

    @property
    def xy_motor_speed(self) -> float:
        return round(float(self.speeds[0].get()), PRECISION)

    @property
    def z_motor_speed(self) -> float:
        return round(float(self.speeds[1].get()), PRECISION)

    @property
    def step_size(self) -> float:
        return round(float(self.speeds[2].get()), PRECISION)

    @property
    def jump_positions(self) -> dict[Literal['x', 'y', 'z'], float | None]:
        jumps: dict[Literal['x', 'y', 'z'], float | None] = {'x': None, 'y': None, 'z': None}
        for i, k in enumerate(jumps.keys()):
            try:
                jumps[k] = round(float(self.jumps[i].get()), PRECISION)
            except ValueError:
                jumps[k] = None
        return jumps

    @property
    def position_xyz(self) -> tuple[float, float, float]:
        """ May use mutex! """
        if any(_p < 0 for _p in self._position):
            with self._mutex:
                self._position = self.ctrl.get_current_coordinates()
        return self._position

    def update_nominal_position(self, x, y, z):
        self._position = (x, y, z)
        self.xyz[0]['text'] = str(x)
        self.xyz[1]['text'] = str(y)
        self.xyz[2]['text'] = str(z)

    def update_positions(self):
        if self.ctrl is None:
            values = [round(v + random.random(), 4) for v in [1, 2, 3]]
            self.update_nominal_position(*values)
            return
        with self._mutex:
            self.update_nominal_position(*self.ctrl.get_current_coordinates())

    def move_delta(self, *, dx: int | float = 0, dy: int | float = 0, dz: int | float = 0):
        cx, cy, cz = self.position_xyz
        nx, ny, nz = cx + dx, cy + dy, cz + dz
        self.update_nominal_position(nx, ny, nz)
        if self.ctrl is None:
            print(f"Nudging: {dx=}, {dy=}, {dz=}")
            return
        with self._mutex:
            if nz > cz:
                self.ctrl.move_arm_z(nz, self.z_motor_speed)
            self.ctrl.move_arm_xy(Point2D(x=nx, y=ny), self.xy_motor_speed)
            if cz > nz:
                self.ctrl.move_arm_z(nz, self.z_motor_speed)

    def home(self):
        self.update_nominal_position(-1, -1, -1)
        if self.ctrl is None:
            print(f"Homing arm")
            return
        with self._mutex:
            self.ctrl.home_arm()

    def max_z(self):
        self.update_nominal_position(*self.position_xyz[:2], MAX_Z_HEIGHT)
        if self.ctrl is None:
            print(f"Moving to max Z height ({MAX_Z_HEIGHT})")
            return
        with self._mutex:
            self.ctrl.move_arm_z(MAX_Z_HEIGHT, self.z_motor_speed)

    def jump(self, dim: Literal['x', 'y', 'z']):
        if self.ctrl is None:
            print(f"Jumping in {dim} to {self.jump_positions[dim]}")
            return
        jump_to = self.jump_positions[dim]
        if jump_to is None:
            print(f"Error, invalid value for Jump({dim})")
            return
        if dim == 'z':
            with self._mutex:
                self.ctrl.move_arm_z(jump_to, self.z_motor_speed)
                self.update_nominal_position(*self.position_xyz[:2], jump_to)
                return
        cx, cy, cz = self.position_xyz
        new_point = {'x': cx, 'y': cy, dim: jump_to}
        new_point = Coordinate(
            xy=Point2D(**new_point),
            z=cz
        )
        with self._mutex:
            self.ctrl.move_arm_to(new_point, xy_speed=self.xy_motor_speed, z_speed=self.z_motor_speed)
        self.update_nominal_position(*new_point.xy, new_point.z)

    def aspirate(self, source: Literal["R", "N"]):
        if self.ctrl is None:
            print(f"Aspirating {self._vol.get()}")
            return
        volume = float(self._vol.get())
        if source == "R":
            self.ctrl.aspirate_from_reservoir(volume, DEFAULT_SYRINGE_FLOWRATE)
        else:
            self.ctrl.aspirate_from_curr_pos(volume, DEFAULT_SYRINGE_FLOWRATE)

    def dispense(self):
        if self.ctrl is None:
            print(f"Dispensing {self._vol.get()}")
            return
        volume = float(self._vol.get())
        self.ctrl.dispense_to_curr_pos(volume, DEFAULT_SYRINGE_FLOWRATE)

    def home_pump(self):
        if self.ctrl is None:
            print(f"Homing pump")
            return
        self.ctrl.home_pump()

    def run(self):
        self.update_positions()
        print("Hello!")
        self.root.mainloop()


if __name__ == '__main__':
    # Create (but not yet run) the GUI
    my_prompt = Seahorse(
        tk.Tk(),
        Gilson241LiquidHandler(home_arm_on_startup=True, home_pump_on_startup=False)
    )

    # Start up the Gilson by homing the arm and loading the bed
    # my_prompt.ctrl.load_bed(
    #     "C:/Users/User/Documents/Gilson_Deck_Layouts/SternVolmer_Deck",
    #     "Gilson_Bed.bed"
    # )

    # (Requires a Bed to be loaded)
    # Have the system boot up with a purge specified by the User
    # WASTE = my_prompt.ctrl.locate_position_name('waste', "A1")
    # my_prompt.ctrl.home_arm()  # needed if home_arm_on_startup=False
    # boot_with_user(my_prompt.ctrl, WASTE)

    # (Requires a Bed to be loaded)
    # Have the device move to a position before starting the GUI
    # my_prompt.ctrl.home_arm()  # needed if home_arm_on_startup=False and not already called
    # test_jump=my_prompt.ctrl.locate_position_name('pos_1_rack', "A4")
    # my_prompt.ctrl.move_arm_to(test_jump)

    # Run the GUI
    my_prompt.run()

    # Notes:

    #  1 <-- X --> 162
    #  ^
    #  |    Z fully retracted is 125,
    #  Y      and all the way down is 5
    #  |
    #  v
    #  249

    # Pump to Needle-tip: ~1400 uL
    # Reservoir to Pump: ??? uL
