# Set-up

# We would like to compare some of our methods to those in tutorial_1.py so we will need access to those methods
#   We accomplish this using an import statement as so:

import tutorial_1
# Note that even though we have imported tutorial_1.py, the code in its main block was not executed.


########################################################################################################################
# Making Methods

# Let's make a better version of the double method:

def double(number: int | float) -> int | float:
    return number * 2

# To break it down:
# - An 'int' is an integer number (-2, 0, 5, 1200)
# - A 'float' is a real number (-2.4, pi, 7/3)
#     - We say 'float' instead of 'real' because computers cannot store an infinite number of digits before/after
#       the decimal point.  We typically get about 16 digits after the decimal point--e.g., that 7/3 is
#       not 2.333... but rather it is 2.3333333333333335. Because these numbers have a non-infinite amount of
#       precision, they are called "floating-point precision numbers", hence 'float'.
#     - As experimentalists, the tiny error between the computer's value and the true value is normally not a
#       concern as this error is much less severe than the experimental error.
# When we say "number: int | float" we are saying "Python, the value of 'number' could be either an integer or
#   floating-point-precision number
# When we say "-> int | float" we sare saying "Python, the method should return a result that is either an integer
#   or float.
# These bits of information are called Type Annotations or Type Hints. Most programs you use to write Python will
#   read these and provide helpful tips/checks for you. Python, however, will actually ignore them when you press Run.
#   Nevertheless, they are still helpful for troubleshooting and helping others understand your code.
# For example, your code-writing program will probably highlight the following examples as a bad method:

def bad_method(number: int | float) -> int | float:
    return "This is not a number"  # PyCharm, for example, will complain here with a message:
    # "Expected type 'int | float', got 'str' instead" because mad_method() should return a number not a string

def another_example():
    return double("This is not a number")  # PyCharm, for example, will complain here with the same message because
                                           #   the method double() was given an input that is not an int or float

# in comparison, we can see that the old version of double does not exhibit these behaviors:
def comparison():
    the_bad_result = tutorial_1.double("This is not a number")  # No warnings in Pycharm
    # Since tutorial_1.py and this file both have a method called "double()", we must clarify which one Python should
    #   use.  Python will default to the version made in the current file; we specify that we want to use the other
    #   one by calling it out explicitly using dot notation.
    print(the_bad_result)
    some_variable_that_should_be_text: str = tutorial_1.double(7)  # no warnings in Pycharm
    print(some_variable_that_should_be_text)


########################################################################################################################
# So we can testing things:
if __name__ == '__main__':
    # The version of double in this file works:
    print("tutorial_2.py's version of double:")
    my_number = 3.5
    the_result = double(my_number)
    print("Given")
    print(my_number)
    print("double() returned")
    print(the_result)
    print()  # Adds some vertical spacing in the console to help with legibility

    print("And tutorial_1.py's version of double, given 3.5, returns:")
    print(tutorial_1.double(3.5))
    print()  # Adds some vertical spacing

    # ^ If this looks a bit cluttered and cumbersome, it is.
    # In practice, we would report out like this:
    my_number = 3.14
    print(f"Given {my_number} as input, double() returned: {double(my_number)}")  # note the 'f' before the string/text
    # or
    print("Given", my_number, "as input, double() returned:", double(my_number))
    # Both will print the same message to the console.  The version with the f"" gives you additional control
    #   over things like how many sig-figs to print (rounding) and left/right alignment of the text, so it is
    #   the version most used in the code within Neptune.
    #   One nice one (shown below) is that f"{thing=}" will prints as "thing=" followed by the value of the thing

    print()  # Adds some vertical spacing
    example = 42
    print(f"{example=}")  # Should print: "example=42"
    print(f"{example:e}")  # Prints 42 in scientific notation
    print(f"{example:.3e}")  # Prints 42 in scientific notation, up to 3 decimal places
    # These strings/text can also contain special characters like '\n' (newline, vertical space)
    # and '\t' (tab, horizontal space) and '\"' for when you want a quotation mark in the text.

    print()

    # And to show that Python will still run, even when the type hints are generating warnings:
    print(f"{bad_method(None)=}")
    print(f"{another_example()=}")
    print("Calling comparison()...")
    comparison()

    # Bonus: If when you saw the type annotations and thought "What if when I give a method a string, I want it to
    #   return a string, but when I give it a number, I want it to return a number?", then you will be pleased to know
    #   there is a way to do that:
    def parameterized_method[T](value: T) -> T:
        return value

    test_value: int = 100
    not_an_int: str = parameterized_method(test_value)  # Pycharm warning: "Expected type 'str', got 'int' instead"

    # Bonus:
    # You may encounter import statements like:
    # import numpy as np
    # import tkinter as tk
    # Since imported methods have to be addressed with dot notation, by giving the modules nicknames when you import
    #   them (the "as ___" syntax), you can save some trouble typing out long names
    # "import numpy" means you have to say "numpy.nansum(...)" whereas
    # "import numpy as np" means you can say "np.nansum(...)"
    # In addition, you may also see:
    # from module_name import *
    # This mean "Import everything!"
    #   The file module_name.py can actually clarify what it means by "import everything" (__all__ = [the names
    #   of the methods and variable that actually get imported when sometime tries to import everything from
    #   the module])
    #   In addition, Python will default to Not importing anything whose name starts with an underscore.
    # When a module is imported in this manner, you do not have to use any dot notation--you can just call the method
    #   by name.  However, any conflict in names can result in confusing code (Python will default to the current file)
    #   but if file_a.py imports everything from file_b.py and everything from file_c.py and both file_b.py and
    #   file_c.py have a method called do_something(), then which version will get used is not obvious.
