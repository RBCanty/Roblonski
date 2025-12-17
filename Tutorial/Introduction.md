# Introduction #
The contents of this folder are presented as a tutorial for a user with minimal to 
no programming/Python experience. It will assume that an integrated development 
environment (IDE; such as PyCharm or Spyder) is being used.
If you are already familiar with basic coding principles (control flow, basic 
syntax, variables and function) and can read Python, you can skip to tutorial #5.
If you are well-versed in Python, tutorial_8 and the examples in the workflows folder
would be the place to start.

The tutorial will consist of a series of Python files which can be read and run to 
observe the behaviors of Python. The tutorial files are intended to be read in-order.

It is the goal of this tutorial to show that if you can break down an experiment into
a checklist, then it can be turned into a program. In addition, while not a 
comprehensive guide to Python programming, this tutorial should provide the reader
with enough context to understand that any higher-complexity constructions observed
in this project's code are still accomplishing the same fundamental tasks as the basic
check-list-of-operations of the tutorial.


### At a glance ###
The eight tutorial files cover the following topics:
1) The general structure of a Python file, how to define methods, and the \_\_main\_\_ block
2) Importing python files and type hints
3) IF statements, FOR loops, and method execution order
4) *args and **kwargs and Objects
5) Turning a checklist of operations into a program (uses the liquid handler)
6) Reorganizing checklists into methods and basic bookkeeping
7) Incorporation of the spectrometer
8) Annotated walkthrough of the Stern-Volmer code (naming.py, stern_volmer_3src.py, stern_volmer_core.py, and stern_volmer.py)
9) Annotated walkthrough of adapting the Stern-Volmer code to be more flexible (such as multiple, simultaneous wavelength analysis)

### Reading a *.py file ###

A Python file can be segmented into roughly three section:
 1) Set-up (i):  Telling Python what tools it will need from other files (importing).
 2) Set-up (ii): Defining any tools you wish to use/store in this file.
 3) Execution:   Defining what happens when you run this file (as opposed to when \
                 another file imports this file during its set-up (i) section).

In addition, Python will always read the code from left to right, top to bottom. It
will only jump around if it is told to do so (e.g., IF statements, Loops, and Methods).

### Key Terms ###

 - Variable: Similar to a variable in math, a variable allows something to be 
             referred to by a name.
 - Method:   Similar to a function in math, something which takes in inputs and
             performs some action and/or returns some result. Methods are also 
             called 'Functions'. Once a method returns/exits, Python
             will resume from where it left off when the method was called.
 - Object:   An organized collection of data (these data are called attributes)
             and associated methods
 - Int & float:  These are numbers. Computers cannot maintain an infinite number of
                 decimal places and so must bound the range of values and their 
                 precision. This gives rise to integers (int) and floating-point-
                 precision (float) numbers.
 - String:       A string is text. A string in Python is denoted by quotation marks. 
                 Either single or double quotes are acceptable. Within a string, 
                 special characters (such as a newline, a tab, or a quote) can be
                 specified by using a backslash (e.g., \n, \t, \\", \\\\)
 - List & Tuple: List and tuples are collections of values where the order matters.
                 Whereas a List can be modified (values can be added/removed/changed),
                 a Tuple is fixed. Values in a List or Tuple can be accessed using an
                 index (0-indexed).  (N.b., it may be helpful to think of the index
                 as an offset rather than an index).  For example, example_list[0]
                 is the first value in the list, and example_list[2] is the third value.
 - Dictionary:   A Dictionary is a collection of values where each value is accessed by
                 a key. Most often, the key is a name (a string), but a key can also
                 be a number or a tuple.  For example, example_dict['age'] is the
                 value of example_dict associated with the label: age.
 - Truthy/Falsey: While Python has a boolean (True/False) type for data, most logic
                  is controlled by a truthy/falsey dichotomy. True (boolean) is Truthy
                  and False (boolean) is Falsey. However, None (no value) is Falsey as
                  are empty strings, lists, tuples, and dictionaries. Conversely, a
                  string with text, or lists/tuples/dictionaries with items are Truthy.
