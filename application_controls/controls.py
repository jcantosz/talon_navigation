"""Collect application controls, with clipping and deferred web-area queries."""

import logging
from math import isfinite

from talon import axquery, settings, ui

from ..ax.surfaces import focused_surfaces as focused_surfaces
from ..lib.labels import usable_frame
from ..lib.roles import CONTROL_ROLES

QUERY = "[AXPosition]:action(AXPress)"
ROW_ITEM_LEVELS = 3
ROW_ACTIVATION_COVERAGE = 0.8
MAX_NATIVE_NODES = 10000
_CURRENT_SURFACE = object()


def _query_budget():
    configured_depth = settings.get("user.accessibility_query_max_depth")
    if configured_depth < 0:
        raise RuntimeError(
            "user.accessibility_query_max_depth must be zero or a positive integer."
        )
    timeout = settings.get("user.accessibility_query_timeout")
    if not isfinite(timeout) or timeout <= 0:
        raise RuntimeError(
            "user.accessibility_query_timeout must be finite and greater than zero."
        )
    return configured_depth or -1, timeout


def _is_row_item(element):
    """Return whether element is a row, or the pressable content of a row that is not."""
    role = element.get("AXRole")
    if role == "AXRow":
        return True
    if role != "AXGroup":
        return False
    for _ in range(ROW_ITEM_LEVELS):
        element = element.get("AXParent")
        if element is None:
            return False
        if element.get("AXRole") == "AXRow":
            return "AXPress" not in element.actions
    return False


def row_activation_target(element):
    if element.get("AXRole") != "AXRow" or not usable_frame(element):
        return element
    children = [
        child for child in element.get("AXChildren") or () if "AXPress" in child.actions
    ]
    if len(children) != 1:
        return element
    child = children[0]
    if (
        child.get("AXRole") != "AXGroup"
        or child.get("AXEnabled") is False
        or child.get("AXHidden") is True
        or not usable_frame(child)
    ):
        return element

    row = element.get("AXFrame")
    bounds = child.get("AXFrame")
    if (
        bounds.x >= row.x - 1
        and bounds.y >= row.y - 1
        and bounds.x + bounds.width <= row.x + row.width + 1
        and bounds.y + bounds.height <= row.y + row.height + 1
        and min(bounds.x + bounds.width, row.x + row.width) - max(bounds.x, row.x)
        >= row.width * ROW_ACTIVATION_COVERAGE
        and min(bounds.y + bounds.height, row.y + row.height) - max(bounds.y, row.y)
        >= row.height * ROW_ACTIVATION_COVERAGE
    ):
        return child
    return element


def _add_control(element, controls):
    if (
        (element.get("AXRole") in CONTROL_ROLES or _is_row_item(element))
        and element.get("AXEnabled") is not False
        and element.get("AXHidden") is not True
        and usable_frame(element)
        and not any(existing == element for existing in controls)
    ):
        controls.append(element)


def _query_controls(root, controls, budget, clip=None):
    """Add root's controls; with a clip frame, filter overlap instead of pruning."""
    max_depth, timeout = budget

    def query():
        return axquery.query_all(
            QUERY,
            root=root,
            visible_only=clip is None,
            max_depth=max_depth,
            timeout=timeout,
        )

    try:
        elements = query()
    except AttributeError:
        # Talon's matcher raises AttributeError when an element vanishes mid-query.
        logging.debug("Application labels: retrying AX query", exc_info=True)
        elements = query()
    for element in elements:
        if clip is None or _overlaps(element.get("AXFrame"), clip):
            _add_control(element, controls)


def _surface_clip(surface):
    if not settings.get("user.accessibility_clip_to_surface"):
        return None
    if not usable_frame(surface):
        raise RuntimeError("The accessibility surface has no usable frame.")
    return surface.get("AXFrame")


def foreign_element(element, owner):
    """Return whether element provably belongs to an application other than owner."""
    top = element.get("AXTopLevelUIElement") or element.get("AXWindow")
    application = None if top is None else top.get("AXParent")
    return (
        application is not None
        and application.get("AXRole") == "AXApplication"
        and application != owner.element
    )


def visible_menu(window):
    """Find an unambiguous visible menu without entering closed submenu trees."""
    if window is None:
        raise RuntimeError("The application has no focused accessibility window.")
    pending = [window]
    menus = []
    for _ in range(MAX_NATIVE_NODES):
        if not pending:
            return menus[0] if len(menus) == 1 else None
        element = pending.pop()
        if element.get("AXRole") == "AXMenu":
            if usable_frame(element):
                menus.append(element)
            continue
        pending.extend(reversed(element.get("AXChildren") or ()))
    raise RuntimeError("Too many accessibility nodes while locating a visible menu.")


def _query_menu_controls(menu, controls, budget):
    children = list(menu.get("AXChildren") or ())
    if (
        usable_frame(menu)
        and children
        and all(child.get("AXRole") == "AXMenuItem" for child in children)
    ):
        clip = menu.get("AXFrame")
        for child in children:
            if (
                _overlaps(child.get("AXFrame"), clip)
                and child.get("AXPosition") is not None
                and "AXPress" in child.actions
            ):
                _add_control(child, controls)
        return
    _query_controls(menu, controls, budget, _surface_clip(menu))


def _overlaps(frame, clip):
    return (
        frame is not None
        and min(frame.x + frame.width, clip.x + clip.width) > max(frame.x, clip.x)
        and min(frame.y + frame.height, clip.y + clip.height) > max(frame.y, clip.y)
    )


def _split_web_areas(window):
    """Return native controls, the window's primary web area, and other web areas."""
    native = []
    areas = []
    stack = [window]
    for _ in range(MAX_NATIVE_NODES):
        if not stack:
            break
        element = stack.pop()
        if element.get("AXRole") == "AXWebArea":
            areas.append(element)
            continue
        if "AXPress" in element.actions and element.get("AXPosition") is not None:
            native.append(element)
        stack.extend(reversed(element.get("AXChildren") or ()))
    else:
        raise RuntimeError("Too many native accessibility nodes outside web areas.")

    title = window.get("AXTitle")
    primary = [area for area in areas if title and area.get("AXTitle") == title]
    if len(primary) != 1:
        logging.debug(
            "Application labels: %d web areas match the window title; "
            "querying the whole window",
            len(primary),
        )
        return None
    others = [area for area in areas if area != primary[0]]
    return native, primary[0], others


def collect(owner, menu=_CURRENT_SURFACE, window=_CURRENT_SURFACE):
    """Return numbered controls and web areas whose controls may be appended later."""
    budget = _query_budget()
    controls = []
    if menu is _CURRENT_SURFACE:
        menu = ui.active_menu()
    if menu is not None:
        _query_menu_controls(menu, controls, budget)
        return controls, []
    if window is _CURRENT_SURFACE:
        window = owner.element.get("AXFocusedWindow")
    if window is None:
        raise RuntimeError(
            f"{owner.name} does not expose an AXFocusedWindow attribute."
        )
    clip = _surface_clip(window)
    defer = settings.get("user.accessibility_defer_web_areas")
    split = _split_web_areas(window) if defer else None
    if split is None:
        _query_controls(window, controls, budget, clip)
        return controls, []
    native, primary, others = split
    for element in native:
        _add_control(element, controls)
    _query_controls(primary, controls, budget, clip)
    return controls, [(area, clip) for area in others]


def collect_deferred(areas, controls):
    """Return controls from deferred web areas whose centers are not covered."""
    budget = _query_budget()
    combined = list(controls)
    cache = []
    for area, clip in areas:
        if usable_frame(area) and in_visible_web_area(area, cache):
            _query_controls(area, combined, budget, clip)
    return combined[len(controls) :]


def _web_area(element, cache):
    # Talon elements are unhashable; cache ancestors by equality per collection.
    trail = []
    for _ in range(100):
        if element is None:
            area = None
            break
        for node, area in reversed(cache):
            if element == node:
                break
        else:
            trail.append(element)
            if element.get("AXRole") == "AXWebArea":
                area = element
                break
            element = element.get("AXParent")
            continue
        break
    else:
        raise RuntimeError("Unable to resolve accessibility web-area ancestry.")
    cache.extend((node, area) for node in trail)
    return area


def in_visible_web_area(element, cache):
    area = _web_area(element, cache)
    if area is None:
        return True
    frame = element.get("AXFrame")
    if frame is None:
        return False
    try:
        hit = ui.element_at(frame.x + frame.width / 2, frame.y + frame.height / 2)
    except RuntimeError as error:
        if str(error) != "No element found.":
            raise
        logging.debug("Application labels: no element at web control center %s", frame)
        return False
    return _web_area(hit, cache) == area


def signature(elements):
    return tuple(
        (
            element,
            element.get("AXRole"),
            element.get("AXTitle"),
            element.get("AXDescription"),
            element.get("AXIdentifier"),
            element.get("AXFrame"),
            tuple(element.actions),
        )
        for element in elements
    )
