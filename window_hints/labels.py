"""Named AX proxies for centre labels; no native attributes are written."""

import logging
import math

from talon import actions, app, ui
from talon.types import Rect, Size2d

TITLE = "Window hints"


def _number_words(number):
    small = (
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
    ).split()
    if number < 20:
        return small[number]
    if number < 100:
        tens = "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()
        quotient, remainder = divmod(number, 10)
        return tens[quotient] + (f" {small[remainder]}" if remainder else "")
    for scale, word in (
        (10**12, "trillion"),
        (10**9, "billion"),
        (10**6, "million"),
        (1000, "thousand"),
        (100, "hundred"),
    ):
        if number >= scale:
            quotient, remainder = divmod(number, scale)
            return f"{_number_words(quotient)} {word}" + (
                f" {_number_words(remainder)}" if remainder else ""
            )


def spoken_name(name):
    """Talon's names list matches words, not embedded numeric suffixes."""
    base, separator, suffix = name.rpartition(" ")
    if separator and suffix.isascii() and suffix.isdecimal():
        return f"{base} {_number_words(int(suffix))}"
    return name


class PaneLabel(ui.Element):
    def __init__(self, element, name):
        self._original = element.copy()
        super().__init__(self._original._ref)
        self._label_name = spoken_name(name)
        self._geometry_failed = False

    def _frame(self):
        frame = self._original.get("AXFrame")
        if self._geometry_failed:
            return frame
        try:
            if (
                frame is None
                or not all(
                    math.isfinite(value)
                    for value in (frame.x, frame.y, frame.width, frame.height)
                )
                or frame.width <= 0
                or frame.height <= 0
            ):
                raise ValueError("Pane has no usable AXFrame")
            return Rect(
                frame.x + frame.width / 2 - 6,
                frame.y + frame.height / 2 - 6,
                12,
                12,
            )
        except (AttributeError, TypeError, ValueError):
            self._geometry_failed = True
            logging.exception(
                "Window hints: using original geometry for %s", self._label_name
            )
            app.notify(TITLE, f"Using original group geometry for {self._label_name}.")
            return frame

    def _attribute(self, key, default=None):
        if key in ("AXTitle", "AXDescription"):
            return self._label_name
        if key in ("AXFrame", "AXPosition", "AXSize"):
            frame = self._frame()
            if frame is None:
                return self._original.get(key, default)
            if key == "AXPosition":
                return frame.pos
            if key == "AXSize":
                return Size2d(width=frame.width, height=frame.height)
            return frame
        return self._original.get(key, default)

    def get(self, key, default=None):
        return self._attribute(key, default)

    def __getitem__(self, key):
        return self._attribute(key)

    def __getattr__(self, key):
        if key.startswith("AX"):
            return self._attribute(key)
        return super().__getattr__(key)

    def perform(self, action):
        return self._original.perform(action)


def show(panes):
    """Try centred names; explicitly fall back to the real AX groups."""
    try:
        targets = [PaneLabel(pane.ref, pane.name) for pane in panes]
        actions.labels.show_names(targets)
    except (AttributeError, TypeError, ValueError, RuntimeError, ui.UIErr):
        logging.exception("Window hints: centred labels failed; using original groups")
        app.notify(TITLE, "Centred labels failed; using original group labels.")
        actions.labels.hide()
        actions.labels.show_names([pane.ref for pane in panes])
