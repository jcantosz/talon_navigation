"""Window hints: label panes of the focused window.

With `user.window_hints_profile` set (by a Talon
context), panes come from the declarative profile of that name; otherwise from
generic AX pane roles. Labels are not refreshed; say "hide labels" to clear
them. See window_hints/README.md for supported behavior and compatibility limits.
"""

import logging
import time

from talon import Module, actions, app, settings, ui
from talon.types import Rect as TalonRect

from ..accessibility.controls import focused_surfaces
from ..accessibility.inventory_core import collect
from . import core, profiles
from . import labels as pane_labels

mod = Module()
mod.setting(
    "window_hints_profile",
    type=str,
    default="",
    desc="Pane profile name for window hints; empty uses generic AX role rules.",
)
TITLE = "Window hints"


def _read(element, attribute, default):
    try:
        return element.get(attribute) or default
    except ui.UIErr:
        return default


def _walk():
    owner = ui.active_app()
    if owner is None:
        raise RuntimeError("There is no active application.")
    root = focused_surfaces(owner)[0][1]
    started = time.perf_counter()
    inventory = collect(root, ui.UIErr)
    return inventory, time.perf_counter() - started


def _window_rect(inventory):
    for node in inventory.nodes:
        if node.role == "AXWindow":
            return core.as_rect(node.frame)
    return None


def _profile_nodes(inventory):
    return [
        profiles.Node(
            node.path,
            core.as_rect(node.frame),
            node.role or "",
            _read(node.element, "AXSubrole", ""),
            _read(node.element, "AXDOMIdentifier", ""),
            frozenset(_read(node.element, "AXDOMClassList", ())),
            node.title or "",
            node.description or "",
            node.element,
        )
        for node in inventory.nodes
    ]


def _warn_if_partial(inventory):
    if inventory.truncated or inventory.errors:
        app.notify(TITLE, "Partial walk; see the Talon log. Showing what was found.")


def _show_profile(name):
    profile = profiles.load_profile(name)
    inventory, walk_time = _walk()
    _warn_if_partial(inventory)
    started = time.perf_counter()
    panes = profiles.find_panes(_profile_nodes(inventory), profile)
    window = _window_rect(inventory)
    result = profiles.report(panes, window, profile.get("tiles", False))
    print(
        f"Window hints (profile {name}): panes={len(panes)} "
        f"coverage={result['coverage']:.3f} overlaps={result['overlaps']} "
        f"walk={walk_time:.2f}s match={time.perf_counter() - started:.2f}s"
    )
    for index, pane in enumerate(panes, 1):
        frame = pane.frame
        print(
            f"  {index}: {pane.name} "
            f"({frame.x:.0f},{frame.y:.0f},{frame.width:.0f},{frame.height:.0f})"
        )
    if not panes:
        app.notify(TITLE, f"Profile {name!r} matched no panes.")
        return
    if not result["ok"]:
        app.notify(TITLE, f"Profile {name!r} panes do not tile the window.")
    app.notify(TITLE, ", ".join(f"{i}: {p.name}" for i, p in enumerate(panes, 1)))
    if profile.get("labels") == "names":
        pane_labels.show(panes)
        return
    actions.labels.show(
        [TalonRect(p.frame.x, p.frame.y, p.frame.width, p.frame.height) for p in panes]
    )


def _show_generic(rule, names):
    inventory, walk_time = _walk()
    _warn_if_partial(inventory)
    candidates = []
    for node in inventory.nodes:
        rect = core.as_rect(node.frame)
        if rect is None:
            continue
        candidates.append(
            core.Candidate(
                node.role or "",
                rect,
                len(node.path),
                None,
                bool(node.title or node.description or node.identifier),
                node.element,
            )
        )
    window = _window_rect(inventory)
    if window is None:
        raise RuntimeError("The focused window has no usable AXWindow frame.")
    panes = core.select_candidates(candidates, window, rule)
    print(
        f"Window hints: rule={rule} nodes={len(inventory.nodes)} "
        f"errors={len(inventory.errors)} truncated={inventory.truncated} "
        f"panes={len(panes)} {core.pane_count_summary(panes)} walk={walk_time:.2f}s"
    )
    for index, pane in enumerate(panes, 1):
        print(f"  {index}: {pane.role} named={pane.named} frame={pane.frame}")
    if not panes:
        app.notify(TITLE, f"No panes found with rule {rule!r}.")
        return
    elements = [pane.ref for pane in panes]
    if names:
        actions.labels.show_names(elements)
    else:
        actions.labels.show(elements)


@mod.action_class
class Actions:
    def window_hints_show(rule: str = "named", names: bool = True):
        """Label the focused window's panes (profile if configured, else AX roles)."""
        actions.labels.hide()
        try:
            profile = settings.get("user.window_hints_profile")
            if profile:
                _show_profile(profile)
            else:
                _show_generic(rule, names)
        except (AttributeError, TypeError, ValueError, RuntimeError, ui.UIErr):
            logging.exception("Window hints failed")
            app.notify(TITLE, "Unable to label panes; see the Talon log.")
