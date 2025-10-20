# We've now seen the general structure of a Python file, how to make basic methods, and some ways to
#   take note of what kinds (types) of values we expect our variable and methods to handle.

# Rather than importing an Entire Module, we can ask Python to just import one bit.
# Here we'll just import the Any type annotation
from typing import Any


# We will not take a look at a few basic control structures:

if __name__ == '__main__':

    # First we'll look at how to have code execution branch along different paths

    def the_conditional(parameter: bool) -> str:  # A 'bool' or Boolean, is something that is either True or False*
        if parameter:
            return "The parameter was true :)"
            # Note, execution of a method STOPS when it reaches a 'return' statement.  If a return is encountered,
            #   everything else in the method will be ignored.
        elif parameter is None:
            return "The parameter was neither true nor false ???"
        else:
            return "The parameter was false :("

    # The IF statement says, only run the code in my block (the code that is below AND indented) if what follows the
    #  'if' is true
    # The ELIF statement says, only run the code in my block if what follows the 'elif' is true AND none of the previous
    #   conditions were satisfied.
    # The ELSE statement is executed if none of the preceding conditionals (IF and ELIF statements) were satisfied.

    print("Testing the_conditional(...)")
    print(f"{the_conditional(1 == 1) = }\n"  # 'X == Y' is read: "Does X equal Y"
          f"{the_conditional(1 == 3) = }\n"
          f"{the_conditional(None) = }")  # Pycharm will complain here because 'None' is not boolean


    # We can compare this to a conditional using only IF statements:
    def bad_conditional(parameter: bool) -> None:  # A 'bool' or Boolean, is something that is either True or False*
        if parameter:
            print("\tThe parameter was true :)")
        if parameter is None:
            print("\tThe parameter was neither true nor false ???")
        if not parameter:  # Not takes True and makes it False, and takes False and makes it True (it flips the value)
            print("\tThe parameter was false :(")

    print("\nTesting bad_conditional(...)")
    print(f"For '1 == 1', {bad_conditional(1 == 1)}")
    print(f"For '1 == 3', {bad_conditional(1 == 3)}")
    print(f"For 'None', {bad_conditional(None)}")  # Pycharm will complain here because 'None' is not boolean
    print()

    # There are probably two things that may be bothering you based on what was printed to the console by now:
    # 1) It printed the "the parameter was ..." text BEFORE printing the whole message of "For input, ..."
    # 2) Why were multiple conditions triggered for bad_conditional(None)

    # Re: 1, Python sees `print(f"For '1 == 1', {bad_conditional(1 == 1)}")` and in order to run that, it needs
    #   to run `bad_conditional(1 == 1)` to know what value to put there, so it "pauses" running print() and runs
    #   bad_conditional() first. We can explicitly show this order of operations with the silly example:
    print(print(1), print(2), print(3), print(4))
    # Which will print "1", "2", "3", "4", then "None None None None".

    # Re: 2, This is where the asterisk from above returns. Python will interpret many things as "Truthy" and "Falsey"
    #   rather than relying on exactly "TRUE" or "FALSE" values. The rules are generally:
    # 0 is Falsey, any other number is Truthy
    # Empty things are Falsey, things with at least one member are Truthy
    # None is Falsey
    # This behavior is why the conditionals in the_conditional() were ordered as they were. Had the method been written
    # as:
    #     def the_conditional(parameter: bool) -> str:
    #         if parameter:
    #             return "The parameter was true :)"
    #         if not parameter:
    #             return "The parameter was false :("
    #         else:
    #             return "The parameter was neither true nor false ???"
    # Then the code in the else block would never run. None or anything Falsey would be caught by the 'not parameter'
    #   condition.
    # Python permits some level of control by using 'is' rather than '=='

    def complete_conditional(expression: Any) -> str:
        report: str = f"{expression} is Unknown"
        # ^ Pycharm may complain here because it realizes there's no way
        #   for `report` to leave the method with this value.
        if expression is True:
            report = f"{expression} literally is True"
        elif expression is False:
            report = f"{expression} literally is False"
        elif expression is None:
            report = f"{expression} literally is None"
        elif expression:
            report = f"{expression} is Truthy"
        elif not expression:
            report = f"{expression} is Falsey"
        else:
            report = f"{expression} was neither True, False, Truthy, Falsey, nor None?"
        return report


    print()
    print("Testing complete_conditional(...)")
    print(f"\t{complete_conditional(True) = }\n"
          f"\t{complete_conditional(False) = }\n"
          f"\t{complete_conditional(None) = }\n"
          f"\t{complete_conditional(1 == 1) = }\n"  # Expressions will be evaluated before being passed in, '1 == 1' becomes 'True'
          f"\t{complete_conditional(1 == 3) = }\n"
          f"\t{complete_conditional(123) = }\n"
          f"\t{complete_conditional(0) = }\n"
          f"\t{complete_conditional([]) = }\n"  # [] denotes a list of values
          f"\t{complete_conditional([1,2,3]) = }\n"
          f"\t{complete_conditional('') = }\n"  # Quotes (single or double) indicate a string/text
          f"\t{complete_conditional('Text') = }\n")
    print()


    # As a mock example, we can see how this can be used to check a value then perform some response:
    def sound_alarm(temperature: float):
        if temperature > 300:
            print(f"{temperature:.0f}! Too hot! Sound the alarm!")
        elif temperature > 200:
            print(f"The current temperature ({temperature:.0f}) is a little hot, but within bounds")
        else:
            print(f"The current temperature ({temperature:.0f}) is fine.")

    sound_alarm(23.65)
    sound_alarm(197.32)
    sound_alarm(287.77)
    sound_alarm(310.10)
    print()

    # Does that mean than 'if __name__ == "__main__":' is just a conditional checking if the file's __name__ designation
    # matches the special value of "__main__" given to the *.py file that Python starts in?
    # Yes!


    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    # Next, we look at loops
    # Python supports While loops and For loops
    #  - A While loop will continue to run the contents of its code block until the condition after 'while' is false(y).
    #  - A For loop will run once for each item in a container.
    # Loops support two special commands: break, continue, and else
    #  - break will exit the loop regardless of whether the While-condition is Truthy/Falsey or whether the For loop
    #      has seen every item in the container
    #  - continue will jump back to the start of the loop (While will check its condition, For will move onto the next
    #      item)
    #  - else follows the loop and its contents are only executed if the loop did NOT exit via a break. This use is
    #      niche, and I'm not sure if it even gets used in Neptune.

    # In this tutorial, we will just look at a For loop (as While loops are hard to demonstrate in practice*).
    #   * Most often they are tied to some process parameter or observable, which are accessible when running
    #       an experiment, but not really when doing demo code. As a result, the While loops in examples wind
    #       up being infinite loops, never running, or are contrived into examples where a FOR loop would make
    #       much more sense.

    my_list: list[int] = [1, 2, 3, 4, 5, 6]
    # Basic for loop, each iteration, the value of item is updated to be the next value in my_list
    for value in my_list:
        print(f"{value}", end=", ")
        # ^ print() has some parameters you can use to customize its behavior (don't worry about it)
    print()
    # We can keep track of which (ordinal) value we are using via
    for index, value in enumerate(my_list):
        print(f"my_list_{index} = {value}")
    # A For loop over ordered data like lists will always be in the order the list specifies
    print()

    my_experimental_report: dict[str, Any] = {
        'title': "Project 1",
        'date': "01/02/03",
        'value': 100,
        'uncertainty': 2
    }
    # More complicated containers will require more specificity:
    for key in my_experimental_report.keys():
        print(key, end=", ")
    print()
    for value in my_experimental_report.values():
        print(value, end=", ")
    print()
    for key, value in my_experimental_report.items():
        print(f"{key} = {value}")
    # A For loop over unordered data like dictionaries and sets are not guaranteed to be in the same order
    print()

    # Given how often FOR loops are used, Python provides an abbreviated version (though, specifically for the context
    #   of making new containers based on other containers).  This is called a 'comprehension'

    my_list: list[int] = [1, 2, 3, 4, 5, 6]
    my_negative_list = [-value for value in my_list]
    print("Negate", my_negative_list)
    # ^ create a new list where every value if the negative of what it was in the original
    print("Zero", [0 for value in my_list])
    # ^ create a list of zeros that's the same size as my_list
    print("Expression", [idx - value for idx, value in enumerate(my_list)])
    # ^ create a list with a more complicate logic for the creation of each item
    print("Conditional", [value for value in my_list if value > 3])
    # ^ create a copy of my_list but removing any items less than or equal to 3
    print("Zip", [x * y for x, y in zip(my_list, my_list)])
    # ^ zip() lets you run through two lists at the same time, allowing you to do things like calculate
    #   the element-wise product of two lists


    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    # We've actually been using another control flow structure already.  Method calls!
    # When a method is called, Python will jump to that method and try to run it before jumping back and
    # finishing off whatever it was doing before. (Depth-first)
    # In addition, expressions like "3 > 1" or "2 == 4" are actually methods calls as well.
    #   They are calling hidden methods and being evaluated before returning their value back and allowing the
    #   program to continue execution.  For example, since 3 is an integer, "3 > 1" is akin to calling something like
    #   int.greater_than(3, 2) and "2 == 4" is akin to calling something like int.equals(2, 4).
    #   The actual syntax is 3.__gt__(1) and 2.__eq__(4).


# Quick Note: "Scope"
# Python uses indentation to help with defining the scope (or domain of applicability) of something.
# (Python also allows for indentation to be used to help legibility with long lines as well, which can make this a
#  little confusing)
# Each method has its own scope, each branch of a conditional has its own scope.
# (this is how the example methods in this file can all have a variable called 'parameter' without that causing
# problems)

# Ignoring how exactly Python handles doing into or out from scopes:
# variable_a = 1
# def method_one():
#   variable_b = variable_a + 1  # In this case method_one() would "know about variable_a" (variable_b has a value of 2)
# but
# def method_two():
#   variable_a = variable_a + 1  # In this case method_two() would "NOT know about variable_a" (Python would crash)
# ^Ignoring all of this because it is confusing*

# We can at least say:
# def method_three():
#   variable_x = 10
#   print(variable_x)  # This will print 10
# def method_four():
#   variable_x = 20
#   print(variable_x)  # This will print 20
# print(variable_x)  # This print() would "NOT know about variable_x" because variable_x was defined in a more
#   restricted scope (the methods method_three() and method_four()).
# In these cases, since each 'variable_x' is in its own scope (its own method), these two variable_x variables
#   are actually completely different things to Python, and they will not affect each other.
# This is a good thing, as it gives you the freedom to use names for your variables without having to scour through
#   the entire code base to make sure you're using a completely unique variable name.

# *For the curious. Python will allow READ operations to cross scopes but not WRITE operations.  In method_one()
# variable_a is read but never assigned a new value (written to), so Python permits this. In contrast, method_two()
# attempts to assign a value to variable_a, and so Python will not cross scopes and will assume that variable_a is
# restricted to the scope of method_two(). As a result the use of variable_a on the right side of the equals sign
# does not make sense to Python (no variable_a has been defined within the scope of method_two() yet).
# Regrettably, some of the files in the workflows directory do make use of this. In particular,
# some values like concentration or spectrometer specifications are defined in the Main block but then used
# in methods (methods that do not change the value).