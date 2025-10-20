# Part 1: The general structure of a Python file

# At the beginning of each file there is typically some amount of set-up. Most often, this is telling Python
#   what tools (code present in other files) that this file will need access to in order to operate.
# For example, we can import the 'time' module to allow code in this file to perform actions such as waiting
#   a specified amount of time.  Further examples of this will be shown in tutorial_2.py

import time


########################################################################################################################

# Next, we can write the actual code that will be associated with this file.

# To start, we can create methods (analogy: mathematical functions) that take some inputs, perform some actions,
# and may return some result.
# To do this, we use the following syntax:
# def method(argument):
#     ...
#     return

# For a more concrete example, consider a method that doubles a number (e.g. f(x) = 2x):
def double(number):
    new_number = number * 2
    # Unlike math where "x = y" implies "y = x", in programming the equals sign is better read as "assign".
    # E.g., "Assign the value of (number * 2) to the variable, new_number"
    # If we number is changed, new_number does not get updated.

    return new_number
    # Once a `return` is encountered, the method will stop and Python will return to wherever it was when the method
    #   was called. Code after a return is not executed.
    # A `return` is not required. By default, if Python reaches the end of a method and never encounters an explicit
    #   return statement, it will assume `return None`.


########################################################################################################################

# Finally, many files will contain a "Main Block". This code is only executed when we Run this file.
#   This distinction is important when we consider how import-ing works and will be discussed in tutorial_2.py
# For now, the Main block is very useful for 2 things:
#   1) Testing code
#   2) Allowing a user to run a single step in a larger process.  If our ultimate program will span multiple
#      Python files, and each step corresponds to a file, then we can run each file one-at-a-time to make
#      sure everything is functioning properly (or maybe you just need to redo the last step).
# To tell Python "Only run this code when I run this file, not when I import this file", we use the
#   following syntax:
if __name__ == '__main__':
    ...
#   ^ Any code that is put here (indented) will only run when this file is ran directly.
# The file in which Python starts running is given the special property (__name__) with the value "__main__".
# The rest of the construction `if ____:` is telling Python to only run the following indented code if what follows
#   the `if` is truthy.  A double equals means "is equal to?"

# Note that any code that is left outside a Main block (that isn't a definition for something, like a method definition)
# Will get executed whether this file is run directly or imported.
print("\ntutorial.py is being executed or imported!\n")


# For a concrete example:
if __name__ == '__main__':
    # In here we can call the methods we created earlier to test that they work.

    print("Testing double() with 3 as input.")
    # We can check our double method:
    my_number = 3  # Create a variable and assign it the value of 3
    the_result = double(my_number)  # In analogy to y = f(x), we capture the result of a method using a similar syntax
    # then we can display the result (should be 6)
    print(the_result)

    time.sleep(3)  # Waiting for 3 seconds between operations so you have time to see each behavior happening
    # ^ since we imported the 'time' module, we have access to its methods as well.  We format it as module.method
    #   to let Python know that we're talking about the method in the time module.

    print("\nTesting double() with 4 as input.")
    # We can update variables as well:
    my_number = 4
    # and now the result of double(my_number) should be 8
    print(double(my_number))  # In analogy to g(f(x)), we can skip the making of variables for every value
    time.sleep(3)

    print("\nDemonstrating that equals behavior.")
    # As a quick aside, while in math "x = y" is the same as "y = x", in Python, this is not the case.
    # It would be better to read "x = y" as "assign the value of y to x" (it is unidirectional).
    # Consider:
    my_number = 1
    print(f"\t{my_number = }")  # my_number = 1  # this syntax will be explained later
    the_result = my_number
    print(f"\tthe_result = my_number --> {the_result = }, {my_number = }") # the_result is 1, my_number is 1
    my_number = my_number + 1
    print(f"\tmy_number = my_number + 1 --> {the_result = }, {my_number = }") # the_result is 1, my_number is 2
    the_result = double(the_result)
    print(f"\tthe_result = double(the_result) --> {the_result = }, {my_number = }")  # the_result is 2, my_number is 2
    time.sleep(15)

    print("\nMotivation for next tutorial (unexpected behaviors).")
    print("Testing double() with 'Two' as input.")
    # As motivation for the next part of this tutorial, consider the following:
    my_number = "Two"
    # Note how we've made a variable called "my_number" but assigned it the value of "Two" (text, not a number).
    the_result = double(my_number)
    # What does: "Two" * 2 equal? According to Python, it is...
    print(the_result)
    # ...the text: "TwoTwo"
    # While this has a logic to it, it is not what we would necessarily expect. So we will add protections
    #   against this in the next tutorial.
    time.sleep(3)


    # Bonus: You can create methods in the Main Block, but you cannot use them outside the current file.
    def say_hello():
        print("\nHello from within the main block")

    say_hello()
