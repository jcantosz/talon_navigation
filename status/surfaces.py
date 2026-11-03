"""Accessible status targets, geometry, and open-panel discovery."""

import logging
from dataclasses import dataclass
from math import isfinite

from talon import ui

from ..lib.roles import CONTROL_ROLES
from . import discovery

PANEL_ROLES = CONTROL_ROLES - {"AXMenuItem", "AXTab", "AXTextArea"}


def children(element):
    # Some accessibility leaves raise AttributeError when using .children.
    return element.get("AXChildren") or ()


def rect_key(rect):
    return rect.x, rect.y, rect.width, rect.height


def contains_rect(outer, inner):
    # Native labels inset slider hit rectangles; AX animation also adds subpixel noise.
    return (
        outer.x - 1 <= inner.x
        and outer.y - 1 <= inner.y
        and outer.x + outer.width + 1 >= inner.x + inner.width
        and outer.y + outer.height + 1 >= inner.y + inner.height
    )


def same_layout(previous, current):
    if len(previous) != len(current):
        return False
    return all(
        before[0] == after[0]
        and before[2:] == after[2:]
        and all(abs(a - b) <= 1 for a, b in zip(before[1], after[1]))
        for before, after in zip(previous, current)
    )


def visible_frame(element, screen_bounds=None):
    frame = element.get("AXFrame")
    if (
        element.get("AXHidden")
        or frame is None
        or not all(isfinite(value) for value in rect_key(frame))
        or frame.width <= 0
        or frame.height <= 0
    ):
        return None
    if screen_bounds is None:
        screen_bounds = [screen.rect for screen in ui.screens()]
    for bounds in screen_bounds:
        if (
            frame.x < bounds.x + bounds.width
            and frame.x + frame.width > bounds.x
            and frame.y < bounds.y + bounds.height
            and frame.y + frame.height > bounds.y
        ):
            return frame
    return None


@dataclass
class Target:
    element: ui.Element
    owner: ui.App
    frame: ui.Rect

    def signature(self):
        return (
            self.element,
            rect_key(self.frame),
            self.element.get("AXRole"),
            self.element.get("AXTitle"),
            self.element.get("AXDescription"),
        )


@dataclass
class Surface:
    root: ui.Element
    owner: ui.App
    targets: list[Target]


@dataclass
class OpenStatus:
    surface: Surface
    owner: ui.App
    opener: ui.Element | None


def is_unobstructed(element, frame):
    try:
        hit = ui.element_at(frame.x + frame.width / 2, frame.y + frame.height / 2)
    except RuntimeError as error:
        if str(error) != "No element found.":
            raise
        logging.debug(
            "Status labels: no accessibility element at target center %s", frame
        )
        return False
    for _ in range(12):
        if hit is None:
            break
        if hit == element:
            return True
        hit = hit.get("AXParent")
    logging.debug("Status labels: ignoring covered target at %s", frame)
    return False


def panel_targets(root, owner):
    targets = []
    pending = [(root, 0)]
    visited = 0
    menu = root.get("AXRole") == "AXMenu"
    screen_bounds = [screen.rect for screen in ui.screens()]
    while pending:
        element, depth = pending.pop()
        visited += 1
        if visited > 600 or depth > 12:
            raise RuntimeError("The status panel accessibility tree is too large.")
        role = element.get("AXRole")
        frame = visible_frame(element, screen_bounds)
        if element.get("AXHidden"):
            continue
        if (
            frame is not None
            and element.get("AXEnabled") is not False
            and (
                (menu and role == "AXMenuItem" and element.get("AXTitle"))
                or (
                    not menu
                    and role in PANEL_ROLES
                    and (
                        "AXPress" in element.actions
                        or role
                        in ("AXSlider", "AXTextField", "AXSearchField", "AXComboBox")
                    )
                )
            )
        ):
            targets.append(Target(element, owner, frame))
        if not menu or element == root:
            pending.extend((child, depth + 1) for child in reversed(children(element)))
    return targets


def windows(owner):
    screen_bounds = [screen.rect for screen in ui.screens()]
    return [
        root
        for root in owner.element.get("AXWindows") or ()
        if root.get("AXRole") == "AXWindow"
        and visible_frame(root, screen_bounds) is not None
    ]


def owns_menu(menu, owner):
    element = menu
    for _ in range(12):
        if element is None:
            return False
        if element == owner.element:
            return True
        element = element.get("AXParent")
    return False


def _name_key(text):
    return "".join(
        character for character in (text or "").casefold() if character.isalnum()
    )


def open_status(parents):
    applications = list(ui.apps())
    owners = list({owner.pid: owner for parent, owner in parents}.values())
    items = []
    for parent, owner in parents:
        try:
            items.extend(
                (element, owner) for element in discovery.status_children(parent)
            )
        except ui.UIErr:
            logging.warning(
                "Status labels: unable to inspect %s", owner.name, exc_info=True
            )
    menu = ui.active_menu()
    ancestor = menu
    for _ in range(12):
        if ancestor is None:
            break
        for element, owner in items:
            if ancestor == element:
                targets = panel_targets(menu, owner)
                if targets:
                    return OpenStatus(Surface(menu, owner, targets), owner, element)
        ancestor = ancestor.get("AXParent")
    for element, owner in items:
        try:
            for root in children(element):
                if root.get("AXRole") == "AXMenu" and visible_frame(root) is not None:
                    targets = panel_targets(root, owner)
                    if targets and is_unobstructed(
                        targets[0].element, targets[0].frame
                    ):
                        return OpenStatus(Surface(root, owner, targets), owner, element)
        except ui.UIErr:
            logging.warning(
                "Status labels: unable to inspect %s", owner.name, exc_info=True
            )
    clock = next(
        (
            (element, owner)
            for element, owner in items
            if element.get("AXIdentifier") == "com.apple.menuextra.clock"
        ),
        None,
    )
    if clock is not None:
        owners.extend(
            owner
            for owner in applications
            if owner.bundle == "com.apple.notificationcenterui"
        )
    for owner in owners:
        try:
            for root in windows(owner):
                if root.get("AXSubrole") not in ("AXSystemDialog", "AXPopover"):
                    continue
                targets = panel_targets(root, owner)
                if not targets or not any(
                    is_unobstructed(target.element, target.frame) for target in targets
                ):
                    continue
                if (
                    owner.bundle == "com.apple.notificationcenterui"
                    and clock is not None
                ):
                    return OpenStatus(Surface(root, owner, targets), clock[1], clock[0])
                title = _name_key(root.get("AXTitle"))
                matches = [
                    element
                    for element, provider in items
                    if provider.pid == owner.pid
                    and title
                    and title
                    in (
                        _name_key(element.get("AXTitle")),
                        _name_key((element.get("AXDescription") or "").split(",")[0]),
                        _name_key(
                            (element.get("AXIdentifier") or "").rsplit(".", 1)[-1]
                        ),
                    )
                ]
                if (
                    not matches
                    and root.get("AXSubrole") != "AXPopover"
                    and owner.bundle
                    not in ("com.apple.controlcenter", "com.apple.Spotlight")
                ):
                    continue
                return OpenStatus(
                    Surface(root, owner, targets),
                    owner,
                    matches[0] if len(matches) == 1 else None,
                )
        except ui.UIErr:
            logging.warning(
                "Status labels: unable to inspect %s", owner.name, exc_info=True
            )
    return None
