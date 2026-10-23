import logging
from dataclasses import dataclass
from math import isfinite

from talon import Context, Module, actions, app, ui

from ..lib.labels import LabelSession
from .discovery import discover

mod = Module()
mod.tag("status_labels_active", desc="Navigating macOS status icons and their panels")
ctx = Context()
ctx.matches = "os: mac"
controls_ctx = Context()
controls_ctx.matches = """
os: mac
tag: user.status_labels_active
"""

PANEL_ROLES = {
    "AXButton",
    "AXCheckBox",
    "AXComboBox",
    "AXDisclosureTriangle",
    "AXLink",
    "AXMenuButton",
    "AXPopUpButton",
    "AXRadioButton",
    "AXSearchField",
    "AXSlider",
    "AXSwitch",
    "AXTextField",
}
_session = None
_parents = []


def _children(element):
    # Some accessibility leaves raise AttributeError when using .children.
    return element.get("AXChildren") or ()


def _rect_key(rect):
    return rect.x, rect.y, rect.width, rect.height


def _contains_rect(outer, inner):
    # Native labels inset slider hit rectangles; AX animation also adds subpixel noise.
    return (
        outer.x - 1 <= inner.x
        and outer.y - 1 <= inner.y
        and outer.x + outer.width + 1 >= inner.x + inner.width
        and outer.y + outer.height + 1 >= inner.y + inner.height
    )


def _same_layout(previous, current):
    if len(previous) != len(current):
        return False
    return all(
        before[0] == after[0]
        and before[2:] == after[2:]
        and all(abs(a - b) <= 1 for a, b in zip(before[1], after[1]))
        for before, after in zip(previous, current)
    )


def _visible_frame(element, screen_bounds=None):
    frame = element.get("AXFrame")
    if (
        element.get("AXHidden")
        or frame is None
        or not all(isfinite(value) for value in _rect_key(frame))
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
            _rect_key(self.frame),
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


def _is_unobstructed(element, frame):
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


def _icons(parents=None):
    global _parents
    result = discover(
        ui,
        _visible_frame,
        _is_unobstructed,
        step=8,
        parents=None if parents is None else [parent for parent, owner in parents],
    )
    if parents is None:
        applications = (
            [(owner.element, owner) for owner in ui.apps()] if result.bars else []
        )
        parents = []
        for parent in result.bars:
            owner = next(
                (
                    owner
                    for element, owner in applications
                    if element == parent.application
                ),
                None,
            )
            if owner is None:
                raise RuntimeError("A discovered status provider is no longer running.")
            parents.append((parent, owner))
        _parents = parents
    return [
        Target(
            item.element,
            next(owner for parent, owner in parents if parent.element == item.bar),
            item.frame,
        )
        for item in result.items
    ]


def _panel_targets(root, owner):
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
        frame = _visible_frame(element, screen_bounds)
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
            pending.extend((child, depth + 1) for child in reversed(_children(element)))
    return targets


def _windows(owner):
    screen_bounds = [screen.rect for screen in ui.screens()]
    return [
        root
        for root in owner.element.get("AXWindows") or ()
        if root.get("AXRole") == "AXWindow"
        and _visible_frame(root, screen_bounds) is not None
    ]


def _owns_menu(menu, owner):
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


def _open_status():
    applications = list(ui.apps())
    owners = list({owner.pid: owner for parent, owner in _parents}.values())
    items = []
    for parent, owner in _parents:
        try:
            items.extend(
                (element, owner)
                for element in _children(parent.element)
                if element.get("AXSubrole") == "AXMenuExtra"
                or element.get("AXRole") == "AXMenuExtra"
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
                targets = _panel_targets(menu, owner)
                if targets:
                    return OpenStatus(Surface(menu, owner, targets), owner, element)
        ancestor = ancestor.get("AXParent")
    for element, owner in items:
        try:
            for root in _children(element):
                if root.get("AXRole") == "AXMenu" and _visible_frame(root) is not None:
                    targets = _panel_targets(root, owner)
                    if targets and _is_unobstructed(
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
            for root in _windows(owner):
                if root.get("AXSubrole") not in ("AXSystemDialog", "AXPopover"):
                    continue
                targets = _panel_targets(root, owner)
                if not targets or not any(
                    _is_unobstructed(target.element, target.frame) for target in targets
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


class StatusSession(LabelSession):
    def __init__(self, names):
        super().__init__(ctx, "user.status_labels_active", names)
        self.initial_pid = ui.active_app().pid
        self.targets = []
        self.surface = None
        self.owner = None
        self.opener = None
        self.anchor = None
        self.providers = []
        self.icon_parents = []
        self.baseline = []
        self.before_menu = None
        self.internal = False
        self.waiting = False
        self.returning = False
        self.requires_change = False
        self.remaining = 0
        self.settle = 0
        self.signature = []

    def adopt(self, opened):
        self.owner = opened.owner
        self.opener = opened.opener
        self.anchor = opened.opener
        self.providers = list(
            {
                owner.pid: owner for owner in (opened.owner, opened.surface.owner)
            }.values()
        )
        self.icon_parents = list(_parents)
        self.baseline = [
            root
            for provider in self.providers
            for root in _windows(provider)
            if root != opened.surface.root
        ]
        self.show(opened.surface.targets, opened.surface)

    def show(self, targets, surface=None):
        if self.stopped:
            return
        self.internal = True
        try:
            self.targets = targets
            self.surface = surface
            if surface is None:
                self.icon_parents = list(_parents)
            self.signature = (
                [target.signature() for target in targets]
                if surface is not None
                else []
            )
            if not self.render(target.element for target in targets):
                return
            self.waiting = False
            self.returning = False
            self.requires_change = False
        finally:
            self.internal = False

    def target(self, label):
        numbered = not self.names and isinstance(label, int)
        if numbered and not 1 <= label <= len(self.targets):
            raise RuntimeError(
                "The selected status number no longer matches a control."
            )
        rect = actions.labels.rect(label)
        if numbered:
            target = self.targets[label - 1]
            frame = _visible_frame(target.element)
            if frame is not None and _contains_rect(frame, rect):
                return target
            raise RuntimeError(
                "The selected status number no longer matches a control."
            )
        candidates = []
        for target in self.targets:
            frame = _visible_frame(target.element)
            if frame is not None and _contains_rect(frame, rect):
                candidates.append((frame.width * frame.height, target))
        if candidates:
            smallest = min(area for area, target in candidates)
            matches = [target for area, target in candidates if area == smallest]
            if len(matches) == 1:
                return matches[0]
        raise RuntimeError("The selected status label no longer matches a control.")

    def check_focus(self):
        allowed = {self.initial_pid, *(provider.pid for provider in self.providers)}
        if ui.active_app().pid not in allowed:
            actions.labels.hide()
            return False
        return True

    def prepare(self, target):
        self.anchor = target.element
        if self.surface is None:
            self.owner = target.owner
            self.opener = target.element
            self.providers = [target.owner]
            # Clock opens Notification Center, which belongs to a different process.
            if target.element.get("AXIdentifier") == "com.apple.menuextra.clock":
                self.providers.extend(
                    owner
                    for owner in ui.apps()
                    if owner.bundle == "com.apple.notificationcenterui"
                )
            self.baseline = [
                root for provider in self.providers for root in _windows(provider)
            ]
        self.before_menu = ui.active_menu()
        self.waiting = True
        self.remaining = 15
        self.settle = 2

    def select(self, label, operation="select"):
        if not self.check_focus():
            app.notify("Status labels", "The active application changed.")
            return
        target = self.target(label)
        role = target.element.get("AXRole")
        if operation == "select" and role == "AXSlider":
            app.notify(
                "Status labels",
                f"Use 'status increase {label}' or 'status decrease {label}' "
                "to adjust this slider.",
            )
            return
        action = None
        if operation == "details":
            action = next(
                (
                    name
                    for name, description in target.element.actions.items()
                    if description.casefold() == "show details"
                ),
                None,
            )
        elif operation in ("increase", "decrease"):
            action = "AXIncrement" if operation == "increase" else "AXDecrement"
            if action not in target.element.actions:
                action = None
        if operation != "select" and action is None:
            message = f"This control does not support {operation}."
            if operation in ("increase", "decrease"):
                message += " Use the label on a slider or another adjustable control."
            app.notify("Status labels", message)
            return
        if operation in ("increase", "decrease"):
            self.internal = True
            try:
                target.element.perform(action)
            finally:
                self.internal = False
            return
        self.prepare(target)
        from_icons = self.surface is None
        self.requires_change = operation == "details"
        self.internal = True
        try:
            if action is None:
                if from_icons:
                    # Some NSStatusItems advertise AXPress but do not respond to it.
                    actions.labels.mouse_move(label)
                    self.hide_for_transition()
                    actions.mouse_click()
                else:
                    self.preserve_hide = True
                    try:
                        actions.next(label)
                    finally:
                        self.preserve_hide = False
            else:
                self.hide_for_transition()
                target.element.perform(action)
        finally:
            self.internal = False

    def find_surface(self):
        menu = ui.active_menu()
        if menu is not None and self.owner is not None and _owns_menu(menu, self.owner):
            if menu != self.before_menu or (
                self.surface is not None and self.surface.root.get("AXRole") == "AXMenu"
            ):
                targets = _panel_targets(menu, self.owner)
                if targets:
                    return Surface(menu, self.owner, targets)
        for anchor in (self.anchor, self.opener):
            if anchor is None:
                continue
            for root in _children(anchor):
                if root.get("AXRole") == "AXMenu":
                    targets = _panel_targets(root, self.owner)
                    if targets:
                        return Surface(root, self.owner, targets)
        candidates = []
        for provider in self.providers:
            for root in _windows(provider):
                if root not in self.baseline:
                    targets = _panel_targets(root, provider)
                    if targets:
                        candidates.append(Surface(root, provider, targets))
        return candidates[-1] if candidates else None

    def update(self):
        if self.internal or self.stopped:
            return
        try:
            if not self.check_focus():
                return
            if self.waiting and self.settle:
                self.settle -= 1
                return
            if not self.waiting and self.surface is None:
                return
            surface = self.find_surface()
            if self.returning:
                if surface is None:
                    targets = _icons(self.icon_parents)
                    if not targets:
                        raise RuntimeError("No visible status icons are accessible.")
                    self.show(targets)
                    return
            elif surface is not None:
                signature = [target.signature() for target in surface.targets]
                changed = (
                    self.surface is None
                    or surface.root != self.surface.root
                    or not _same_layout(self.signature, signature)
                )
                if not self.waiting or not self.requires_change or changed:
                    if self.waiting or changed:
                        self.show(surface.targets, surface)
                    return
            elif not self.waiting:
                actions.labels.hide()
                return
            self.remaining -= 1
            if self.remaining <= 0:
                from_icons = self.surface is None
                returning = self.returning
                requires_change = self.requires_change
                actions.labels.hide()
                if from_icons or returning or requires_change:
                    app.notify(
                        "Status labels",
                        "No accessible status panel transition appeared.",
                    )
        except (ui.UIErr, ui.ActionFailed, RuntimeError):
            _failed("Unable to read the status panel.")

    def back(self):
        if not self.check_focus():
            return
        if self.waiting:
            app.notify("Status labels", "Wait for the status panel to finish opening.")
            return
        if self.surface is None:
            app.notify("Status labels", "Already at the status icons.")
            return
        root = self.surface.root
        owner = root.get("AXParent")
        parent = owner.get("AXParent") if owner is not None else None
        nested_menu = (
            root.get("AXRole") == "AXMenu"
            and parent is not None
            and parent.get("AXRole") == "AXMenu"
        )
        back = next(
            (
                target
                for target in self.targets
                if target.element.get("AXRole") == "AXButton"
                and (
                    target.element.get("AXTitle")
                    or target.element.get("AXDescription")
                    or ""
                )
                .strip()
                .casefold()
                == "back"
            ),
            None,
        )
        close = root.get("AXCloseButton")
        if (
            back is None
            and not nested_menu
            and "AXCancel" not in root.actions
            and close is None
            and self.opener is None
        ):
            app.notify(
                "Status labels",
                "This panel has no identifiable status icon or accessible close action. "
                "Close it normally, then show status labels or numbers again.",
            )
            return
        self.before_menu = ui.active_menu()
        self.waiting = True
        self.remaining = 15
        self.settle = 2
        self.returning = not nested_menu and back is None
        self.requires_change = not self.returning
        self.internal = True
        try:
            self.hide_for_transition()
            if back is not None:
                back.element.perform("AXPress")
            elif nested_menu:
                actions.key("left")
            elif "AXCancel" in root.actions:
                root.perform("AXCancel")
            elif close is not None:
                close.perform("AXPress")
            else:
                # Escape also invokes Talon's generic "hide labels" binding.
                self.opener.perform("AXPress")
        finally:
            self.internal = False


def _stop():
    global _session
    if _session is not None:
        _session.stop()
    _session = None


def _failed(message):
    logging.exception(message)
    actions.labels.hide()
    _stop()
    app.notify("Status labels", message)


def _operate(label, operation):
    if _session is None:
        app.notify("Status labels", "Show status labels or numbers first.")
        return
    try:
        _session.select(label, operation)
    except (ui.UIErr, ui.ActionFailed, RuntimeError):
        _failed("Unable to select the status control.")


@mod.action_class
class StatusLabelsActions:
    def status_labels_refresh(names: bool = True):
        """Reshow the current panel or freshly discover visible status-bar parents."""
        actions.user.status_labels_show(names)

    def status_labels_show(names: bool = True):
        """Label visible macOS status icons and follow their opened menus or panels."""
        global _session
        try:
            if _session is not None and _session.check_focus():
                if _session.waiting:
                    _session.names = names
                    return
                if _session.surface is not None:
                    surface = _session.find_surface()
                    if surface is not None:
                        _session.names = names
                        _session.show(surface.targets, surface)
                        return
            actions.labels.hide()
            _stop()
            targets = _icons()
            opened = _open_status()
            if not targets and opened is None:
                app.notify("Status labels", "No visible status icons are accessible.")
                return
            _session = StatusSession(names)
            if opened is not None:
                _session.adopt(opened)
            else:
                _session.show(targets)
            _session.start_updates(_session.update)
        except (ui.UIErr, ui.ActionFailed, RuntimeError):
            _failed("Unable to access the status icons.")

    def status_labels_back():
        """Return to a parent menu/back control, or close the panel and relabel status icons."""
        if _session is None:
            app.notify("Status labels", "Show status labels or numbers first.")
            return
        try:
            _session.back()
        except (ui.UIErr, ui.ActionFailed, RuntimeError):
            _failed("Unable to return from the status panel.")

    def status_labels_adjust(label: int | str, operation: str):
        """Show details or increment/decrement a labeled status control."""
        if operation not in ("details", "increase", "decrease"):
            app.notify("Status labels", f"Unknown status operation: {operation}")
            return
        _operate(label, operation)


@controls_ctx.action_class("labels")
class StatusLabelOverrides:
    def select(label: int | str):
        _operate(label, "select")

    def hide():
        actions.next()
        if _session is not None and not _session.preserve_hide:
            _stop()
