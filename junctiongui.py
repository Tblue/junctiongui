# vim: set fileencoding=utf-8:
#
# JunctionGUI - a very simple GUI intended to make it easy to move a directory somewhere else and create an NTFS
# junction point in its original place, pointing to the new location.
#
# Requires Windows Vista or later. Internally uses the mklink built-in command of cmd.exe.
#
# Copyright (c) 2015, Tilman "Tblue" Blumenbach
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
# following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
#    disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
#    products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import queue
import shutil
import subprocess
import threading
import tkinter.filedialog
import tkinter.messagebox
from functools import partial
from tkinter import *
from tkinter.ttk import *


APP_NAME = "JunctionGUI"
COPYRIGHT = "© 2015 by Tblue"


def dir_is_empty(path):
    return len(os.listdir(path)) == 0


def escape_path_for_cmd(path):
    return re.sub(r"([^%!]+)", r'"\1"', path).replace("%", "^%").replace("!", "^!")


class Worker(threading.Thread):
    def __init__(self, task_queue, result_queue):
        super().__init__()

        self._task_queue = task_queue
        self._result_queue = result_queue
        self.stop_thread = threading.Event()

    def run(self):
        while not self.stop_thread.is_set():
            # Wait for a task
            try:
                link_name, dest_path = self._task_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                # If the dest path exists, remove it
                if os.path.exists(dest_path):
                    os.rmdir(dest_path)

                # Now move the directory contents
                shutil.move(link_name, dest_path)

                # Finally, create the junction
                subprocess.check_call(
                    "mklink /j %s %s" % (
                        escape_path_for_cmd(link_name),
                        escape_path_for_cmd(dest_path)
                    ),
                    shell=True
                )
            except Exception as e:
                # Error
                self._result_queue.put((e, link_name, dest_path))
                continue

            # Success
            self._result_queue.put((True, link_name, dest_path))


class Application(Frame):
    def __init__(self, master=None):
        super().__init__(master)

        self.link_name = StringVar()
        self.dest_name = StringVar()

        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()

        self.worker = Worker(self.task_queue, self.result_queue)
        self.worker.start()

        self._root().protocol("WM_DELETE_WINDOW", self.on_quit)
        self._root().title("%s - %s" % (APP_NAME, COPYRIGHT))
        self._root().resizable(False, False)

        # These get set by create_widgets() below.
        # Initialized here for clarity and to make IntelliJ shut up about
        # "instance attribute defined outside __init__".
        self.button_link_name = None
        self.button_dest_name = None
        self.button_go = None
        self.progress_move = None

        self.pack()
        self.create_widgets()

    def create_widgets(self):
        # Link name label
        label_link_name = Label(self, text="Directory to move:")
        label_link_name.grid(sticky="W")

        # Destination directory label
        label_dest_name = Label(self, text="Move contents of this directory to:")
        label_dest_name.grid(sticky="W")

        # Link name input
        input_link_name = Entry(self, state="readonly", width=42, textvariable=self.link_name)
        input_link_name.grid(column=1, row=0)

        # Button: Choose link name (a directory)
        self.button_link_name = Button(
            self,
            text="Choose...",
            command=partial(self.choose_dir, self.link_name, "Please choose the directory to move:", True)
        )
        self.button_link_name.grid(column=2, row=0)
        self.button_link_name.focus_set()

        # Destination directory input
        input_dest_name = Entry(self, state="readonly", width=42, textvariable=self.dest_name)
        input_dest_name.grid(column=1, row=1)

        # Button: Choose destination directory
        self.button_dest_name = Button(
            self,
            text="Choose...",
            command=partial(self.choose_dir, self.dest_name, "Please choose the target directory:", False)
        )
        self.button_dest_name.grid(column=2, row=1)

        # Explanation label
        label_app_desc = Message(
            self,
            aspect=1000,
            text="Clicking the button below will move the contents of the first directory chosen above to the second "
                 "directory and create a \"junction point\" (think shortcut for directories) in place of the first "
                 "directory, pointing to the second directory."
        )
        label_app_desc.grid(columnspan=3)

        # This is the "Go!" area, containing the main action widgets
        frame_go = Frame(self)
        frame_go.grid(columnspan=3)

        # "Go!" button
        self.button_go = Button(
            frame_go,
            text="Move directory contents!",
            state=DISABLED,
            command=self.go_button_clicked
        )
        self.button_go.pack()

        # Progress bar
        self.progress_move = Progressbar(frame_go)
        self.progress_move.pack(fill=X)

    def choose_dir(self, textvariable, title, mustexist):
        chosen_dir = tkinter.filedialog.askdirectory(
            initialdir=textvariable.get(),
            parent=self,
            title=title,
            mustexist=mustexist
        )

        if chosen_dir:
            textvariable.set(chosen_dir)

        self.maybe_enable_go_button()

    def maybe_enable_go_button(self):
        if self.link_name.get() and self.dest_name.get():
            self.button_go["state"] = ACTIVE

    def set_buttons_state(self, state):
        for but in [self.button_link_name, self.button_dest_name, self.button_go]:
            but["state"] = state

    def start_progress(self):
        self.set_buttons_state(DISABLED)
        self.progress_move["mode"] = "indeterminate"
        self.progress_move.start(20)

    def stop_progress(self):
        self.set_buttons_state(ACTIVE)
        self.progress_move.stop()
        self.progress_move["mode"] = "determinate"

    def on_quit(self):
        # print("Quitting...")

        self.worker.stop_thread.set()
        self.worker.join()

        self._root().destroy()

    def schedule_completion_check(self):
        self._root().after(100, self.check_for_completion)

    def check_for_completion(self):
        try:
            exception, link_name, dest_path = self.result_queue.get_nowait()
        except queue.Empty:
            # Reschedule this completion check.
            self.schedule_completion_check()
            return

        # Either we got an error or everything went well -- in both cases, the operation has ended.
        self.stop_progress()

        if exception is True:
            # Success
            tkinter.messagebox.showinfo(
                "Operation completed successfully",
                "Successfully moved directory contents and created junction point!"
            )
        else:
            # Oops, error
            tkinter.messagebox.showerror(
                "Operation failed",
                "Sorry, the following error occurred:\n\n" + str(exception) + "\n\nPlease try again."
            )

    def go_button_clicked(self):
        self.start_progress()
        if not self.check_and_queue_task():
            self.stop_progress()

    def check_and_queue_task(self):
        link_name = self.link_name.get()
        dest_path = self.dest_name.get()

        # Sanity checks
        try:
            if not os.path.isdir(link_name):
                tkinter.messagebox.showerror("Error", "The directory to move does not exist (or is not a directory).")
                return False
            elif os.path.exists(dest_path):
                if not os.path.isdir(dest_path):
                    tkinter.messagebox.showerror("Error",
                                                 "The destination directory does not exist (or is not a directory).")
                    return False
                elif os.path.samefile(link_name, dest_path):
                    tkinter.messagebox.showerror("Error", "Please select two different directories.")
                    return False
                elif not dir_is_empty(dest_path):
                    tkinter.messagebox.showerror("Error", "The destination directory is not empty!")
                    return False
        except OSError as e:
            tkinter.messagebox.showerror(
                "Error",
                "Sorry, the following error occurred:\n\n" + str(e) + "\n\nPlease try again."
            )
            return False

        # Now, make our worker thread move the directory and create the junction.
        self.task_queue.put((link_name, dest_path))

        # Wait for completion.
        self.schedule_completion_check()
        return True


app = Application()
app.mainloop()
