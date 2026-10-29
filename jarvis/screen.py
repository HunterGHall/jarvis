"""A console that can redraw itself when the terminal window is resized.

Boxes and panels are drawn at the window's width when they are printed. If the window is resized afterwards, the
terminal reflows the old lines and the boxes fall apart. So everything printed is remembered, and when the width
changes the screen is cleared and the whole conversation is printed again at the new width.

A redraw only happens at a safe moment: while Jarvis is waiting for you at the prompt with nothing typed yet, or
just before the next prompt. It never happens while a reply is being written or while you are typing.
"""
import ctypes
import shutil
import threading
import time
from contextlib import contextmanager

from rich.console import Console

MAX_LOGGED = 400  # how many printed items are kept for redrawing; older ones fall off the top
SETTLE_SECONDS = 0.4  # wait this long after the window stops changing before redrawing
POLL_SECONDS = 0.25

_screen_lock = threading.RLock()


def terminal_columns():
    return shutil.get_terminal_size().columns


def cursor_column():
    """The text cursor's column in the Windows console, or None if it can't be read (output is redirected, say)."""
    try:
        class Coord(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class Rect(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short), ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

        class BufferInfo(ctypes.Structure):
            _fields_ = [("size", Coord), ("cursor", Coord), ("attributes", ctypes.c_ushort), ("window", Rect), ("maximum", Coord)]

        kernel32 = ctypes.windll.kernel32
        info = BufferInfo()
        if not kernel32.GetConsoleScreenBufferInfo(kernel32.GetStdHandle(-11), ctypes.byref(info)):
            return None
        return info.cursor.X
    except (AttributeError, OSError):
        return None


class LoggedConsole(Console):
    """A Console that remembers what it prints, so the screen can be drawn again at a different width."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = []
        self.recording = True

    def print(self, *objects, **kwargs):
        with _screen_lock:
            # Lines ending in "\r" are status lines that get overwritten (like "listening..."), not part of the transcript
            if self.recording and kwargs.get("end", "\n") != "\r":
                self.log.append((objects, dict(kwargs)))
                del self.log[:-MAX_LOGGED]
            super().print(*objects, **kwargs)

    def print_unlogged(self, *objects, **kwargs):
        with _screen_lock:
            super().print(*objects, **kwargs)

    def input(self, prompt="", *, markup=True, emoji=True, password=False, stream=None):
        # Same as Console.input, except the prompt isn't remembered: the redraw prints it itself, at the very end.
        # The lock is not held while waiting for you to type, or a redraw could never happen.
        if prompt:
            self.print_unlogged(prompt, end="", markup=markup, emoji=emoji)
        if password:
            from getpass import getpass

            return getpass("", stream=stream)
        return stream.readline() if stream else input()

    def redraw(self):
        """Clears the screen and prints everything again, at the window's current width."""
        with _screen_lock:
            log = list(self.log)
            self.clear()  # screen cleared, cursor to the top
            if not self.legacy_windows:
                self.file.write("\x1b[3J")  # and the scrollback, whose old copies are the broken ones
                self.file.flush()
            for objects, kwargs in log:
                super().print(*objects, **kwargs)


class Screen:
    """Decides when the screen should be redrawn, and does it."""

    def __init__(self, console, columns=terminal_columns, cursor=cursor_column, clock=time.monotonic, enabled=True):
        self.console = console
        self.columns = columns
        self.cursor = cursor
        self.clock = clock
        self.enabled = enabled
        self.painted_width = columns()
        self.at_prompt = False
        self.prompt_markup = ""
        self.prompt_width = 0
        self._seen = self.painted_width
        self._changed_at = -SETTLE_SECONDS
        self._thread = None

    def resized(self):
        return self.columns() != self.painted_width

    def repaint_if_resized(self):
        """Called just before a prompt, when nothing is on screen being written or typed."""
        if self.enabled and self.resized():
            self.console.redraw()
            self.painted_width = self.columns()
            return True
        return False

    @contextmanager
    def prompt(self, markup, width):
        """Marks the time Jarvis is waiting for a typed message, the one moment a redraw can also happen on its own."""
        self.prompt_markup, self.prompt_width = markup, width
        self.at_prompt = True
        try:
            yield
        finally:
            self.at_prompt = False

    def step(self):
        """One look at the window. Redraws if it was resized and has stopped moving, and it's safe to. Returns True if it did."""
        if not self.enabled:
            return False
        now, width = self.clock(), self.columns()
        if width != self._seen:
            self._seen, self._changed_at = width, now  # still being dragged; wait for it to settle
            return False
        if width == self.painted_width or now - self._changed_at < SETTLE_SECONDS:
            return False
        with _screen_lock:
            if not self.at_prompt:
                return False  # the redraw happens before the next prompt instead
            if self.cursor() != self.prompt_width:
                return False  # something has been typed (or the cursor can't be read), so leave the line alone
            self.console.redraw()
            self.console.print_unlogged(self.prompt_markup, end="")
            self.painted_width = width
            return True

    def start(self):
        if self._thread or not self.enabled:
            return

        def watch():
            while True:
                time.sleep(POLL_SECONDS)
                try:
                    self.step()
                except Exception:
                    pass  # a failed redraw must never take Jarvis down; the next prompt will try again

        self._thread = threading.Thread(target=watch, daemon=True)
        self._thread.start()


console = LoggedConsole()
screen = Screen(console)
