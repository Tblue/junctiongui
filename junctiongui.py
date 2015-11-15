# vim: set fileencoding=utf-8 :

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


def dirIsEmpty(path):
    return len(os.listdir(path)) == 0


def escapePathForCmd(path):
    return re.sub(r"([^%!]+)", r'"\1"', path).replace("%", "^%").replace("!", "^!")


class Worker(threading.Thread):
    def __init__(self, taskQueue, resultQueue):
        super().__init__()

        self._taskQueue = taskQueue
        self._resultQueue = resultQueue
        self.stopThread = threading.Event()

    def run(self):
        while not self.stopThread.is_set():
            # Wait for a task
            try:
                linkName, destPath = self._taskQueue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                # If the dest path exists, remove it
                if os.path.exists(destPath):
                    os.rmdir(destPath)

                # Now move the directory contents
                shutil.move(linkName, destPath)

                # Finally, create the junction
                subprocess.check_call(
                    "mklink /j %s %s" % (
                        escapePathForCmd(linkName),
                        escapePathForCmd(destPath)
                    ),
                    shell=True
                )
            except Exception as e:
                # Error
                self._resultQueue.put((e, linkName, destPath))
                continue

            # Success
            self._resultQueue.put((True, linkName, destPath))


class Application(Frame):
    def __init__(self, master=None):
        Frame.__init__(self, master)

        self.linkName = StringVar()
        self.destName = StringVar()

        self.taskQueue = queue.Queue()
        self.resultQueue = queue.Queue()

        self.worker = Worker(self.taskQueue, self.resultQueue)
        self.worker.start()

        self._root().protocol("WM_DELETE_WINDOW", self.onQuit)
        self._root().title("%s - %s" % (APP_NAME, COPYRIGHT))
        self._root().resizable(False, False)

        self.pack()
        self.createWidgets()

    def createWidgets(self):
        # Link name label
        self.labelLinkName = Label(self, text="Directory to move:")
        self.labelLinkName.grid(sticky="W")

        # Destination directory label
        self.labelDestName = Label(self, text="Move contents of this directory to:")
        self.labelDestName.grid(sticky="W")

        # Link name input
        self.inputLinkName = Entry(self, state="readonly", width=42, textvariable=self.linkName)
        self.inputLinkName.grid(column=1, row=0)

        # Button: Choose link name (a directory)
        self.buttonLinkName = Button(
            self,
            text="Choose...",
            command=partial(self.chooseDir, self.linkName, "Please choose the directory to move:", True)
        )
        self.buttonLinkName.grid(column=2, row=0)
        self.buttonLinkName.focus_set()

        # Destination directory input
        self.inputDestName = Entry(self, state="readonly", width=42, textvariable=self.destName)
        self.inputDestName.grid(column=1, row=1)

        # Button: Choose destination directory
        self.buttonDestName = Button(
            self,
            text="Choose...",
            command=partial(self.chooseDir, self.destName, "Please choose the target directory:", False)
        )
        self.buttonDestName.grid(column=2, row=1)

        # Explanation label
        self.labelAppDesc = Message(self, aspect=1000, text="Clicking the button below will move the contents of the "
                                                            "first directory chosen above to the second directory and "
                                                            "create a \"junction point\" (think shortcut for "
                                                            "directories) in place of the first directory, "
                                                            "pointing to the second directory."
                                    )
        self.labelAppDesc.grid(columnspan=3)

        # This is the "Go!" area, containing the main action widgets
        frameGo = Frame(self)
        frameGo.grid(columnspan=3)

        # "Go!" button
        self.buttonGo = Button(frameGo, text="Move directory contents!", state=DISABLED, command=self.goButtonClicked)
        self.buttonGo.pack()

        # Progress bar
        self.progressMove = Progressbar(frameGo)
        self.progressMove.pack(fill=X)

    def chooseDir(self, textvariable, title, mustexist):
        chosenDir = tkinter.filedialog.askdirectory(
            initialdir=textvariable.get(),
            parent=self,
            title=title,
            mustexist=mustexist
        )

        if chosenDir:
            textvariable.set(chosenDir)

        self.maybeEnableGoButton()

    def maybeEnableGoButton(self):
        if self.linkName.get() and self.destName.get():
            self.buttonGo["state"] = ACTIVE

    def setButtonsState(self, state):
        for but in [self.buttonLinkName, self.buttonDestName, self.buttonGo]:
            but["state"] = state

    def startProgress(self):
        self.setButtonsState(DISABLED)
        self.progressMove["mode"] = "indeterminate"
        self.progressMove.start(20)

    def stopProgress(self):
        self.setButtonsState(ACTIVE)
        self.progressMove.stop()
        self.progressMove["mode"] = "determinate"

    def onQuit(self):
        # print("Quitting...")

        self.worker.stopThread.set()
        self.worker.join()

        self._root().destroy()

    def scheduleCompletionCheck(self):
        self._root().after(100, self.checkForCompletion)

    def checkForCompletion(self):
        try:
            exception, linkName, destPath = self.resultQueue.get_nowait()
        except queue.Empty:
            # Reschedule this completion check.
            self.scheduleCompletionCheck()
            return

        # Either we got an error or everything went well -- in both cases, the operation has ended.
        self.stopProgress()

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

    def goButtonClicked(self):
        self.startProgress()
        if not self.checkAndQueueTask():
            self.stopProgress()

    def checkAndQueueTask(self):
        linkName = self.linkName.get()
        destPath = self.destName.get()

        # Sanity checks
        try:
            if not os.path.isdir(linkName):
                tkinter.messagebox.showerror("Error", "The directory to move does not exist (or is not a directory).")
                return False
            elif os.path.exists(destPath):
                if not os.path.isdir(destPath):
                    tkinter.messagebox.showerror("Error",
                                                 "The destination directory does not exist (or is not a directory).")
                    return False
                elif os.path.samefile(linkName, destPath):
                    tkinter.messagebox.showerror("Error", "Please select two different directories.")
                    return False
                elif not dirIsEmpty(destPath):
                    tkinter.messagebox.showerror("Error", "The destination directory is not empty!")
                    return False
        except OSError as e:
            tkinter.messagebox.showerror(
                "Error",
                "Sorry, the following error occurred:\n\n" + str(e) + "\n\nPlease try again."
            )
            return False

        # Now, make our worker thread move the directory and create the junction.
        self.taskQueue.put((linkName, destPath))

        # Wait for completion.
        self.scheduleCompletionCheck()
        return True


app = Application()
app.mainloop()
