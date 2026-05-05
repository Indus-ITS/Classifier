"""ANSI color helper. Degrades to plain ASCII when not a TTY or NO_COLOR is set."""
from __future__ import annotations

import os
import sys


class _Color:
    """Minimal ANSI color helper. When .enabled is False the wrap functions
    return the raw text unchanged. Also exposes .block which is the bar
    character to use for plan/progress visuals - block when color is on,
    '#' when off (so we don't hit UnicodeEncodeError on cp1252 stdout).
    """
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.block = "█" if enabled else "#"
        self.empty = "░" if enabled else "."
        self.branch = "├──" if enabled else "+--"
        if enabled and os.name == "nt":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                mode = ctypes.c_uint32()
                kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VT
            except Exception:
                pass

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, t: str) -> str: return self._wrap("1", t)
    def dim(self, t: str) -> str: return self._wrap("2", t)
    def red(self, t: str) -> str: return self._wrap("31", t)
    def green(self, t: str) -> str: return self._wrap("32", t)
    def yellow(self, t: str) -> str: return self._wrap("33", t)
    def blue(self, t: str) -> str: return self._wrap("34", t)
    def cyan(self, t: str) -> str: return self._wrap("36", t)


def _color_enabled(no_color_flag: bool) -> bool:
    if no_color_flag:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return True
