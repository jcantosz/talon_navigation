"""Positioned wheel actions for retained current-window sections."""

import logging
import math
import subprocess
from functools import lru_cache

from talon import actions, app, ctrl, settings, ui

from . import core

TITLE = "Window sections"
DIRECTIONS = {"up", "down", "left", "right"}
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


@lru_cache(maxsize=1)
def _natural_scrolling():
    try:
        result = subprocess.run(
            ["/usr/bin/defaults", "read", "-g", "com.apple.swipescrolldirection"],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            "Unable to read the macOS natural-scroll preference."
        ) from error
    natural = result.stdout.strip()
    if natural not in ("0", "1"):
        raise RuntimeError("The macOS natural-scroll preference was not a boolean.")
    return natural == "1"


def _wheel_direction(direction):
    return direction if _natural_scrolling() else OPPOSITE[direction]


def refresh_scroll_direction():
    _natural_scrolling.cache_clear()


def scroll(resolve_section, direction, amount):
    if direction not in DIRECTIONS or not 1 <= amount <= 20:
        raise ValueError("Scroll direction must be up/down/left/right; amount 1–20.")
    wheel_direction = _wheel_direction(direction)
    root = resolve_section()
    owner = ui.active_app()
    window = None if owner is None else owner.element.get("AXFocusedWindow")
    if ui.active_menu() is not None:
        raise RuntimeError("Close the active menu before scrolling a section.")
    frame = core.as_rect(root.get("AXFrame"))
    if frame is None:
        raise RuntimeError("The section has no usable frame.")
    x, y = frame.center
    vertical = wheel_direction in ("up", "down")
    distance = settings.get(
        "user.mouse_wheel_down_amount"
        if vertical
        else "user.mouse_wheel_horizontal_amount"
    )
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError("The configured wheel distance must be finite and positive.")
    if (
        owner is None
        or root.get("AXWindow") != window
        or ui.active_app() != owner
        or owner.element.get("AXFocusedWindow") != window
    ):
        raise RuntimeError("The focused window changed; no scroll was sent.")
    actions.user.accessibility_invalidate_numbers_for_scroll()
    position = ctrl.mouse_pos()
    if max(abs(position[0] - x), abs(position[1] - y)) > 1:
        ctrl.mouse_move(x, y)
    delta = distance * amount * (-1 if wheel_direction in ("up", "left") else 1)
    # Explicit native event position avoids waiting for asynchronous pointer motion.
    ctrl.mouse_scroll(
        y=delta if vertical else 0, x=0 if vertical else delta, pos=(x, y)
    )


def run(operation):
    try:
        operation()
    except (
        AttributeError,
        TypeError,
        ValueError,
        RuntimeError,
        ui.UIErr,
        ui.ActionFailed,
    ) as error:
        logging.exception("Window sections: action failed")
        app.notify(TITLE, str(error))
