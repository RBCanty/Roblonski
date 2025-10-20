# One more Python lesson before we go into how to build something useful in Neptune.
# In this tutorial, it will be rapid-fire set of examples of some other things you can do with functions
#   as well as how to create conceptually-organized information (classes).  Understanding these things isn't
#   actually the goal of this tutorial. Rather, it's to provide explained examples so when reading Python code
#   you have a basis for what's going on (or at least can go "oh, that's that things with like labeling the
#   inputs to a method or something").

# import the modules and things from modules that we need
from typing import Literal, Iterable


# #################################################################################################################### #
# Example 1: Variable-number arguments
def count_and_sum(*args) -> tuple[int, float]:
    """ :return: (number of arguments passed in, their gross sum) """
    tally = 0
    total = 0.0
    for value in args:
        tally += 1
        total += value
    return tally, total

# Line 1
# The asterisk before `args` means: "I do not know how many arguments will be provided to this method.
#   Python, please package them all up into a single container for me".  Python will put them into a tuple
#   (which is like a list, but won't let you change any values).
# The `tuple[int, float]` means "This function will return two values: an int then a float"

# Line 2
# Since the type annotation can't tell you what the int and float are, we can include a "doc-string" (documentation
#   text) that explains this in natural language.  In most code editors, now when you hover over count_and_sum()
#   a little text bubble will appear with that reminder.

# Lines 3 and 4
# Making two variables to keep track of things for us

# Line 5
# A FOR loop that iterates over each value in args (NO ASTERISK)

# Lines 6 and 7
# Each time through the loop, we add one to tally and we add whatever value is to the running total
# 'x += y' is shorthand for 'x = x + y'

# Line 8
# We return two values at once (their order will be preserved). Python actually packages them into a single tuple
#   and returns that instead. As shown below, this duality can be confusing at first


if __name__ == '__main__':
    print("count_and_sum() tests")
    # Capturing the entire result as a tuple
    result_tuple = count_and_sum(1, 2, 3, 4, 5, 6)
    print(f"{result_tuple=}")

    # Unpacking the two returned values
    result_count, result_sum = count_and_sum(2, 4, 6, 8)
    print(f"{result_count=}", "{result_sum=}")
    print()


# Yes, we are leaving the main block on purpose to show that it can be done


# #################################################################################################################### #
# Example 2: Keyword arguments and defaults
def do_math(x: float, y: float, mode: Literal['add', 'subtract'] = 'add') -> float:
    if mode == "add":
        return x + y
    elif mode == "subtract":
        return x - y
    else:
        raise ValueError(f"parameter 'mode' must be 'add' or 'subtract', not {mode}")

# Line 1
# x and y are floats
# mode is going to be text, and it should be, literally, either the text "add" or the text "subtract" (no other
#   text should be accepted)
# mode should also take a default value of "add" if none is provided.from
# raise means "Python, attempt to crash the program with the following error"
#   You can catch these errors and handle them in the code that calls do_math(),
#   otherwise Python will stop and print an error to the console.

if __name__ == '__main__':
    print("do_math() tests")
    a = 5
    b = 3
    print(f"{a=}, {b=}")
    print(f"{do_math(a, b) = }")  # This will use the default value for mode
    print(f"{do_math(y=b, mode='subtract', x=a) = }")  # When called by name, arguments can go in any order
    print(f"{do_math(a, b, 'add') = }")  # Pycharm may insert a little reminder tag that 'add' corresponds to mode
    print(f"{do_math(a, b, mode='subtract') = }")
    # print(f"{do_math(a, b, mode='multiply') = }")
    # ^ If I uncomment this, Python will just crash whenever you try to run this file
    # Feel free to uncomment it (remove the leading '# ') and try it out (it's fine, it won't actually
    # break anything). Re-comment it (add a leading '# ') once you're done to allow Python to continue
    try:
        print("Lets try to run: print(f\"{do_math(a, b, mode='divide') = }\")")
        print(f"{do_math(a, b, mode='divide') = }")  # Pycharm will complain because 'divide' isn't 'add'/'subtract'
    except ValueError as ve:
        print(f"Hey, the code you just tried to run would've caused the following error:\n"
              f"\t{repr(ve)}")  # repr(ve) will print out the error message (and some details)
        pass  # <-- this is not needed (because there's a print() statement in this code block)
              #     I just want to make it clear that we are effectively ignoring the error.
        # If you replace `pass` with `raise`, then Python will continue passing the error up the chain of method calls
        #   until it reaches __main__, at which point it will Stop execution and report an error message.
        #   Feel free to try this (again, it will not do any actual harm).  Just be sure to change it back if you
        #   want the rest of the program to run.
        # The `except error: do something then raise` syntax is nice for annotating errors and troubleshooting.
    print()


# #################################################################################################################### #
# Example 3: Forced keywords
def difference(*, minuend: float, subtrahend: float) -> float:
    return minuend - subtrahend

# Some methods can be inherently confusing. Is the difference between 5 and 3 supposed to be 2 or -2?
# Similarly, I might have a method that takes a flow rate and a duration (but in what order)
# In the code just saying `pump(4.2, 10.6)` when I call the method can be unclear or at least, very easy
# for a mistake to be made.
# We can force the user to use the keyword names so that they cannot write/use the method ambiguously
# The syntax of putting a lone asterisk follows from Example 1. It is telling Python "whatever the method is provided,
#   unless it's labeled as minuend or subtrahend, bundle it into a tuple". Except, instead of saving this tuple
#   to a variable (e.g. a variable called args), it just throws it away.  You may also see this done via:
#     def difference(*_, minuend: float, subtrahend: float)
#   because the underscore is often used as a variable name when you don't care about keeping the value.
#

if __name__ == '__main__':
    print("difference() tests")
    a = 5
    b = 3
    # print(difference(a, b))
    # ^ This will not run (you can try it out if you want)
    # Python will complain that:
    #   Unexpected argument
    #   Parameter 'minuend' unfilled
    #   Parameter 'subtrahend' unfilled
    # we NEED to use the names
    print(f"{a=}, {b=}; {difference(minuend=a, subtrahend=b) = }")
    print(f"{a=}, {b=}; {difference(subtrahend=a, minuend=b) = }")  # named arguments can go in any order
    print()


# #################################################################################################################### #
# Example 4: Variable-keyword arguments
def format_dictionary(**kwargs):
    def _get_length(collection):  # a leading underscore in a name is a convention that means "For internal use only"
        max_len = 1
        for _item in collection:
            item_as_text = str(_item)
            max_len = max(max_len, len(item_as_text))
        return max_len

    # since we need to do this "get maximum length" logic twice we can package it as a method *inside* this method
    max_key_len = _get_length(kwargs.keys()) + 1
    max_value_len = _get_length(kwargs.values()) + 1
    for key, value in kwargs.items():
        print(f"{key:^{max_key_len}}: {value:^{max_value_len}}")

# When we want to tell python that a method can take any number of keyword argument, we use two asteriks.
# Python will then take all the keyword arguments provided to the method when it is called and packed them all
# into a dictionary (a mapping of names, called keys which are strings, to values, called values and can be any type)

if __name__ == '__main__':
    print("format_dictionary() tests")
    print("Example 4a")
    format_dictionary(x=1, y=2, z=4, coordinates="Cartesian")  # I can pass whatever keywords I want into this function
    print("Example 4b")
    format_dictionary(r=2.3, theta=45, phi=90, coordinates="Spherical")
    print()


# #################################################################################################################### #
# Example 5: Objects

# First a simple example. I want a data structure representing a point. I want it to contain a pair of values
# (x, y) and to be able to calculate the 2-norm of that pair of values.
class ExamplePoint:
    # ^ I want to define a new data structure and call it an 'ExamplePoint'

    # Each ExamplePoint will be a different packet in memory, but they all follow the same logic for getting
    #   created.
    def __init__(self, x: float, y: float):
        # ^ It will be created using a pair of values, x and y (both floats)
        #   (Ignore the 'self' in the first argument position)
        self.x = x  # Here it saves a local copy of these values
        self.y = y  # These variables (x and y) are called "attributes"

    # v I want this data structure to be able to calculate its own norm
    def norm(self) -> float:
        # The 'self' is to clarify "use your own values"  (as there may be many
        #   ExamplePoint objects in existence at once)
        return (self.x ** 2 + self.y ** 2) ** 0.5  # <-- Each point shall use its own value of x and y
        # Note: Python uses a**b to express "a to the b-th power" because '^' was already assigned to another
        #       mathematical operation.

# There's a whole host of functionality that we can give these data structures.
# The following class, Point, has been kitted out to show a bunch of cool things objects can do.
# You do not need to know how to use these features.
# Again, this is so when you see '@classmethod' in Neptune, even if you have no idea what the method is doing per se,
#   you can know "Oh, that's probably just another way to make a Point object".

class Point:
# ^ I want to define a new data structure and call it a 'Point'

    def __init__(self, x: float, y: float):
    # ^ It will be created using a pair of values, x and y (both floats)
        self.x = x
        self.y = y

        # In addition, we'll keep private (name starts with an underscore) attribute to record that we're talking
        #   about cartesian points. The convention is that names which start with an underscore are for internal use
        #   only. That is, Point can use _coordinate in its methods, but someone/something outside of Point should
        #   not be messing with this attribute.
        self._coordinate = "Cartesian"


    def norm(self) -> float:
        """ 2-norm: sqrt(quadratic sum) """
        # ^ remind anyone using it that we've chosen the 2-norm (not any of the other norms)
        # v This is to demonstrate static method (see below). Note how Python does not care about the
        #   order in which methods are defined within a Class, as long as they're all there.
        return Point.calculate_norm(self.x, self.y, n=2)

    # A `@staticmethod` is a method that does not have that 'self' things as the first argument.  It cannot access
    #   any internal attributes (x and y) but the method can be called without actually to actually create a Point.
    @staticmethod
    def calculate_norm(*args, n=2):
        return sum(value**n for value in args)**(1/n)
        # ^ that's a comprehension (a secret For loop that creates a collection) in there that sum() can iterate over.
    # With this new static method, now anyone can calculate a norm:
    #   something_else = Point.calculate_norm(1,2,3,4,5, n=2)
    # without having to make a point
    #   something_else = Point(1, 2, uh... where do I put the 3, 4 and 5?).norm()
    #   something_else = Point(0, 0).calculate_norm(1,2,3,4,5, n=2)


    # The methods that start with two underscores ("dunder" or "magic" methods) typically define behaviors
    #   that controlled by the symbols (like '+', '*', '-', '/') or structures (like 'for x in y' or 'name[key]'),
    #   or special operations (like import) in Python.

    # v I want to be able to add two of these data structures together using simple 'A + B' notation
    def __add__(self, other):
        if not isinstance(other, Point):  # Check to make sure the B in 'A + B' is a Point
            # Throw an error if it's not
            raise ValueError("Cannot add a Point to something that is not a Point")
        return Point(self.x + other.x, self.y + other.y)


    # Defining a "__str__(self): ..." method will control how our object looks when
    # someone/something calls `str(point)`, `print(point)`, or ` f"{point}" `. That is, when
    # we want to represent this Point as plain-text.
    def __str__(self):
        return f"Point(x={self.x}, y={self.y})"


    # We can also have class-methods which are (among other things) used to provide alternate ways to make a Point.
    @classmethod
    def make_from_iterable(cls, input_param: Iterable[float]):
        # `input_param` is an iterable, and can contain any number of values (including no values).
        # Point's initializer expects two arguments (named x and y). Using the leading asterisk, we can tell Python:
        #   "Break this iterable out into however many arguments as it has elements and pass them in to this method
        #   in the same order".
        # If the iterable has too few values in it, it will crash (complaining that not enough parameters were passed
        #   into Point.__init__)
        # If the iterable has too many values in it, it will crash (complaining that too many parameters were passed into
        #   Point__init__)
        # Otherwise, the first value will be matched to x and the second matched to y and new point created
        return cls(*input_param)


    # A `@property` is a way to allow control over how attributes are set and can allow some attributes to only
    #   be calculated if they are needed.
    @property
    def coordinate(self) -> str:
        return self._coordinate
    @coordinate.setter
    def coordinate(self, new_value: str):
        # We could just let anyone assign a value to self._coordinate
        # This code would be:
        # self._coordinate = new_value
        # But instead, we won't
        print(f"No, I won't let you change coordinate systems to anything else (like {new_value}).")
        # As such, we can protect values from changes or protect them from having bad values
        # (e.g., don't let anyone set a certain attribute to a negative value)


if __name__ == '__main__':
    # Make some points using the __init__() method
    # So "point_a = Point.__init__(1, 1)" ?
    # The creation of objects is actually a little intricate, so Python's syntax provides a default implementation
    #   that you can use by just saying:
    point_a = Point(1, 0)
    point_b = Point(0, 1)
    # As non-computer scientists, there is almost no reason we would every use an alternate way of declaring
    # and initializing objects.
    # Declaring: "I am making a new object, and calling it 'point_a'."
    # Initializing: "This object, 'point_a', is built using 1 for x and 0 for y."

    # The '+' sign operator is encoded by the __add__() method
    point_c = point_a + point_b

    # Print the norms of points A and C
    print("Point A", point_a.norm())  # Should be 1
    print("Point C", point_c.norm())  # Should be sqrt(2)
    print()

    # Quick demos of the other methods:
    print(Point.make_from_iterable([3, 4]).norm(), "(Should be 5)")
    print(f"{Point.calculate_norm(2, 5, 7, -2, n=3) = }")
    print(f"Initially, Point B's coordinate system attribute = {point_b.coordinate}")
    point_b.coordinate = "Polar"  # Try to change it to "Polar"
    print(f"After trying to assign 'Polar' to Point B's coordinate system attribute,\n"
          f"\tPoint B's coordinate system attribute = {point_b.coordinate}")
    # It should have rejected the change (should still be "Cartesian")


    # Bonus: If I wanted to have a 3D point, would I need to make an entirely new Point3D class?
    # Not entirely, you can tell Python "Hey, this new data structure, called Point3D, should default
    # being a Point, and I'll let you know where it differs".
    class Point3D(Point):
        def __init__(self,x: float, y: float, z: float):
            super().__init__(x, y)  # initialize like a Point with x and y; I'll take care of z next
            self.z = z
        def norm(self) -> float:
            return Point.calculate_norm(self.x, self.y, self.z, n=2)
        def __add__(self, other):
            if not isinstance(other, Point3D):
                raise ValueError  # You don't have to add error details if you don't want to.
            return Point3D(self.x + other.x, self.y + other.y, self.z + other.z)
        def __str__(self):
            return f"Point3D(x={self.x}, y={self.y}, z={self.z})"
        # I do not have to re-write any of the other methods

# Okay, that's been a lot, but next is how to turn an experiment into Python