"""Discover status providers from visible menu-bar hit tests."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import isfinite
from time import perf_counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from talon import ui as talon_ui


@dataclass
class Item:
    """A status item and its menu bar or direct parent container."""

    element: talon_ui.Element
    bar: talon_ui.Element
    application: talon_ui.Element
    frame: talon_ui.Rect


@dataclass
class Parent:
    """A discovered container; non-menu bars retain only hit-tested candidates."""

    element: talon_ui.Element
    application: talon_ui.Element
    candidates: list[talon_ui.Element] | None = None


@dataclass
class Result:
    """Discovery results; bars also includes direct fallback containers."""

    items: list[Item]
    bars: list[Parent]
    rows: list[float]
    probes: int
    empty_hits: int
    seconds: float


def _ancestor(element, role):
    for _ in range(12):
        if element is None:
            return None
        if element.get("AXRole") == role:
            return element
        element = element.get("AXParent")
    return None


def _scan_parents(ui, step):
    probes = 0
    empty_hits = 0
    parents = []
    rows = []

    def add_parent(element, candidate=None):
        parent = next((parent for parent in parents if parent.element == element), None)
        if parent is None:
            application = _ancestor(element, "AXApplication")
            if application is None:
                raise RuntimeError(
                    "A status-item parent has no accessible application owner."
                )
            parent = Parent(element, application, None if candidate is None else [])
            parents.append(parent)
        if (
            candidate is not None
            and parent.candidates is not None
            and candidate not in parent.candidates
        ):
            if not any(child == candidate for child in element.get("AXChildren") or ()):
                raise RuntimeError(
                    "A status item is missing from its accessible parent."
                )
            parent.candidates.append(candidate)

    def hit(x, y):
        nonlocal probes, empty_hits
        probes += 1
        try:
            return ui.element_at(x, y)
        except RuntimeError as error:
            if str(error) != "No element found.":
                raise
            empty_hits += 1
            return None

    for screen in ui.screens():
        bounds = screen.rect
        height = None
        inset = min(20, bounds.width / 2)
        for x in (bounds.x + inset, bounds.x + bounds.width - inset):
            bar = _ancestor(hit(x, bounds.y + 1), "AXMenuBar")
            frame = bar.get("AXFrame") if bar is not None else None
            if frame is not None and isfinite(frame.height) and frame.height > 0:
                height = frame.height
                break
        if height is None:
            bar = ui.active_app().element.get("AXMenuBar")
            frame = bar.get("AXFrame") if bar is not None else None
            if frame is None or not isfinite(frame.height) or frame.height <= 0:
                raise RuntimeError("Cannot determine the menu-bar probe height.")
            height = frame.height
        y = bounds.y + height / 2
        rows.append(y)
        x = bounds.x + bounds.width - min(step, 1) / 2
        while x >= bounds.x:
            element = hit(x, y)
            for _ in range(12):
                if element is None:
                    break
                role = element.get("AXRole")
                if role in ("AXMenuBar", "AXApplication", "AXWindow"):
                    break
                if role in ("AXMenuBarItem", "AXMenuExtra"):
                    if (
                        role == "AXMenuExtra"
                        or element.get("AXSubrole") == "AXMenuExtra"
                    ):
                        direct_parent = element.get("AXParent")
                        bar = _ancestor(direct_parent, "AXMenuBar")
                        if bar is not None:
                            add_parent(bar)
                        if bar is None or direct_parent != bar:
                            if direct_parent is None:
                                raise RuntimeError(
                                    "A status item has no accessible parent."
                                )
                            add_parent(direct_parent, element)
                    break
                element = element.get("AXParent")
            x -= step

    return parents, rows, probes, empty_hits


def status_children(parent):
    for element in parent.element.get("AXChildren") or ():
        if parent.candidates is not None and (
            element not in parent.candidates
            or element.get("AXParent") != parent.element
        ):
            continue
        if (
            element.get("AXRole") == "AXMenuExtra"
            or element.get("AXSubrole") == "AXMenuExtra"
        ):
            yield element


def discover(ui, visible_frame, is_unobstructed, *, step=8, parents=None):
    if not isfinite(step) or step <= 0:
        raise ValueError("The probe stride must be finite and positive.")
    started = perf_counter()
    rows = []
    probes = empty_hits = 0
    if parents is None:
        parents, rows, probes, empty_hits = _scan_parents(ui, step)
    else:
        parents = list(parents)
    items = []
    for parent in parents:
        for element in status_children(parent):
            frame = visible_frame(element)
            if (
                frame is not None
                and element.get("AXEnabled") is not False
                and is_unobstructed(element, frame)
                and not any(item.element == element for item in items)
            ):
                items.append(Item(element, parent.element, parent.application, frame))
    items.sort(key=lambda item: (item.frame.x, item.frame.y))
    if empty_hits:
        logging.debug(
            "Status discovery: %s empty regions in %s probes", empty_hits, probes
        )
    return Result(items, parents, rows, probes, empty_hits, perf_counter() - started)
