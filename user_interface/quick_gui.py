""" A quick and simple GUI prompt for asking basic questions
@author: Ben C
"""

import tkinter as tk
from typing import Any, Callable, Literal
from user_interface.style import TB33, LB33


class QuickButtonUI:
    """ A quick UI generator so you can create a dialog without needing to know tkinter """
    def __init__(self, root: tk.Tk | tk.Toplevel, *,
                 title: str, dialog: str, buttons: dict = None, kwargs: dict = None, ret_if_ok: Any = None):
        """
        Creates a simple UI, all buttons close the message box.

        An OK button is added by default (a user-specified button can override the default "OK" behavior if provided
        in the 'buttons' argument).

        Normal behaviour is to return a tuple (str, Any) where the first element is the name of the button pressed and
        the second element is the return from the button's function.

        If closed by the parent (e.g., pressing the OS's close button), run() will return (None, None)

        :param root: A Tkinter object (should be tk.Tk() from the calling function, tkinter won't let me spawn it here)
        :param title: The text shown on the header bar of the message box
        :param dialog: The text shown in the message box
        :param buttons: A dictionary of {"Button text": python function handle}
        :param kwargs: Arguments to be passed into the button functions
        :param ret_if_ok: Allows setting the return value for pressing OK without needing to make a custom OK function
        """
        if title is None:
            title = "User Dialog"
        if dialog is None:
            dialog = "Default Message"
        if buttons is None:
            buttons = {}
        buttons.setdefault("OK", self.ok)
        if kwargs is None:
            kwargs = {}

        self.root = root
        self._kwargs = kwargs
        self.ret_button = None
        self.ret_val = None
        self._ret_if_ok = ret_if_ok

        frame = tk.Frame(root)
        frame.winfo_toplevel().title(title)
        root.attributes('-topmost', 1)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=10)
        prompt = tk.Label(frame, text=dialog)
        prompt.pack(**TB33)

        button_frame = tk.Frame(frame)
        button_frame.pack(**TB33)

        for t, f in buttons.items():
            tk.Button(button_frame, text=t, command=lambda x=f: self.func_wrapper(t, x)).pack(**LB33)

    def ok(self, *_, **__):
        """ the default OK button behavior """
        return self._ret_if_ok

    def func_wrapper(self, name: str, f: Callable):
        """ Wraps functions calls for buttons such that they are given the default args, record the return of the
        function, save the name of the pressed button the contents of the Entry box (if present), and will exit the
        popup upon execution.
        """
        self.ret_val = f(**self._kwargs)
        self.ret_button = name
        self.root.destroy()
        self.root.quit()

    def run(self) -> tuple[str, Any]:
        """ Executes the popup

        :return: (The name of the button pressed--the key in the buttons constructor kwarg--, the value returned by the
          function the button maps to)
        """
        self.root.mainloop()
        return self.ret_button, self.ret_val


class QuickEntryUI:
    """ A quick UI generator so you can create a dialog without needing to know tkinter

    Good if all input is Button or single-entry based.  For selecting between multiple options,
    see :class:`QuickSelectUI`
    """
    def __init__(self,
                 root: tk.Tk | tk.Toplevel, *,
                 title: str,
                 dialog: str,
                 default_entry_value: str = "",
                 _override_submit: Callable[[str], Literal[True]] = None,
                 _override_cancel: Callable[[str], Literal[False]] = None):
        """
        Creates a simple UI with an entry field, all buttons close the message box.

        Upon exiting via button press, run() will return (bool, str) where the first element is True if submit is
        pressed and False otherwise and the second element is the text in the entry field; or None if closed by the
        parent (e.g., pressing the OS's close button).

        :param root: A Tkinter object (should be tk.Tk() from the calling function, tkinter won't let me spawn it here)
        :param title: The text shown on the header bar of the message box
        :param dialog: The text shown in the message box
        """
        if title is None:
            title = "User Dialog"
        if dialog is None:
            dialog = "Default Message"

        self.root = root
        self.ret_val: tuple[bool, str] | None = None

        frame = tk.Frame(root)
        frame.winfo_toplevel().title(title)
        root.attributes('-topmost', 1)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=10)
        prompt = tk.Label(frame, text=dialog)
        prompt.pack(**TB33)

        buttons = {
            'Submit': self.submit,
            'Cancel': self.cancel,
        }
        if _override_submit:
            buttons['Submit'] = _override_submit
        if _override_cancel:
            buttons['Cancel'] = _override_cancel

        self.entry_field = tk.Entry(frame)
        self.entry_field.pack(**TB33)
        if default_entry_value:
            self.entry_field.insert(0, default_entry_value)

        button_frame = tk.Frame(frame)
        button_frame.pack(**TB33)

        for t, f in buttons.items():
            tk.Button(button_frame, text=t, command=lambda x=f: self.func_wrapper(x)).pack(**LB33)

    @staticmethod
    def submit(*_):
        return True

    @staticmethod
    def cancel(*_):
        return False

    def func_wrapper(self, f: Callable[[str], bool]):
        """ Wraps functions calls for buttons such that they are given the contents of the Entry box and will exit the
        popup upon execution.  Also sets the return value to the contents of the Entry box """
        entry_field = self.entry_field.get()
        button = f(entry_field)
        self.ret_val = (button, entry_field)
        self.root.destroy()
        self.root.quit()

    def run(self) -> tuple[bool, str] | None:
        """ Executes the popup

        :return: (True if Submit was pressed or False if Cancel, text in the entry field) or None if closed by parent
        """
        self.root.mainloop()
        return self.ret_val


class QuickSelectUI:
    """ A simple Helper UI for making selections rather than giving inputs or pushing buttons
    (for that see :class:`QuickUI`) that doesn't require knowing how tkinter works
    """
    def __init__(self, root: tk.Tk | tk.Toplevel, *, title: str, dialog: str, options: list, default=None):
        """ Creates a selector popup box

        :param root: a tkinter root
        :param title: the title of the popup
        :param dialog: the prompt
        :param options: a list of options available
        :param default: the default selection (added to options, if not already present)
        """

        if title is None:
            title = "User Dialog"
        if dialog is None:
            dialog = "Default Message"
        if options is None:
            options = list()
        if default is None:
            default = "None"
        if default not in options:
            options = [default, ] + options
        self.root = root
        self.ret_val = default

        frame = tk.Frame(root)
        frame.winfo_toplevel().title(title)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=10)
        prompt = tk.Label(frame, text=dialog)
        prompt.pack(**TB33)

        self.selection = tk.StringVar(frame, value=default)

        menu = tk.OptionMenu(frame, self.selection, *options)
        menu.pack(**TB33)

        button = tk.Button(frame, text="Submit", command=self.submit)
        button.pack(**TB33)

    def submit(self):
        """ Sets the return value to the selection and exits

        :return: None
        """
        self.ret_val = self.selection.get()
        self.root.destroy()
        self.root.quit()

    def run(self):
        """ Executes the popup

        :return: the value of the selection
        """
        self.root.mainloop()
        return self.ret_val


if __name__ == "__main__":
    project_name = "C:/Users/User/Documents/Tests/testing_june_7_4"
    my_prompt = QuickEntryUI(
        tk.Tk(),
        title="Project ",
        dialog=f"The project name '{project_name}' already exists!\n"  # <-- making this up, the code never actually checks for this
               f"Please enter the project name you wish to use\n"
               f"(or press close to abort)",
        default_entry_value=project_name
    )
    print(f"return value of {my_prompt.run()[1].strip()=!r}")
