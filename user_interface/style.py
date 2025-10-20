from typing import Literal
from colorama import init
from colorama import Fore, Style, Back


# Common TKINTER arguments when building GUIs
BOTH33 = {'fill': 'both', 'ipadx': 3, 'ipady': 3}
TB33 = {'side': 'top', 'fill': 'both', 'ipadx': 3, 'ipady': 3}
TB33E = {'side': 'top', 'fill': 'both', 'ipadx': 3, 'ipady': 3, 'expand': True}
LB33 = {'side': 'left', 'fill': 'both', 'ipadx': 3, 'ipady': 3}
LB33E = {'side': 'left', 'fill': 'both', 'ipadx': 3, 'ipady': 3, 'expand': True}
LBA3 = {'side': 'left', 'fill': 'both', 'ipadx': 3, 'ipady': 3, 'pady': 3, 'padx': 3}
TBA3 = {'side': 'top', 'fill': 'both', 'ipadx': 3, 'ipady': 3, 'pady': 3, 'padx': 3}
T33 = {'side': 'top', 'ipadx': 3, 'ipady': 3}
L33 = {'side': 'left', 'ipadx': 3, 'ipady': 3}
TX33 = {'side': 'top', 'fill': 'x', 'ipadx': 3, 'ipady': 3}
LX33 = {'side': 'left', 'fill': 'x', 'ipadx': 3, 'ipady': 3}
TY33 = {'side': 'top', 'fill': 'y', 'ipadx': 3, 'ipady': 3}
LY33 = {'side': 'left', 'fill': 'y', 'ipadx': 3, 'ipady': 3}
P33 = {'ipadx': 3, 'ipady': 3}
GRID_B33 = {'ipadx': 3, 'ipady': 3, 'sticky': 'nsew'}
PADDING_3 = {'ipadx': 3, 'ipady': 3, 'pady': 3, 'padx': 3}
PACK_SCROLL = {'side': 'right', 'fill': 'y'}

ST_CONTENTS = ["1.0", 'end']
INPUT_CONTENTS = [0, "end"]


init()

def label_text(text: str, level: Literal[0,1,2] = 0):
    """ Changes the background (highlight) color of text printed to the console and bolds the text. """
    if level == 1:
        bkg = Back.YELLOW
    elif level == 2:
        bkg = Back.RED
    else:
        bkg = Back.WHITE
    return bkg + bold_text(text)

def bold_text(text: str):
    """ Bolds text printed to the console. """
    return Style.BRIGHT + text + ("" if text.endswith(Style.RESET_ALL) else Style.RESET_ALL)

def warning_text(text: str):
    """ Renders Bold, Yellow text to the console. """
    return Fore.YELLOW + bold_text(text)

def critical_text(text: str):
    """ Renders Bold, Red text to the console. """
    return Fore.RED + bold_text(text)
