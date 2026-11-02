"""Status label sessions, panel transitions, and safe control selection."""

from talon import actions, app, ui

from ..lib.labels import LabelSession, menu_opener, menu_parent
from . import surfaces


class StatusSession(LabelSession):
    def __init__(self, names, context, *, icons, get_parents, failed):
        super().__init__(context, "user.status_labels_active", names)
        self._icons = icons
        self._get_parents = get_parents
        self._failed = failed
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
        self.icon_parents = list(self._get_parents())
        self.baseline = [
            root
            for provider in self.providers
            for root in surfaces.windows(provider)
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
                self.icon_parents = list(self._get_parents())
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
            frame = surfaces.visible_frame(target.element)
            if frame is not None and surfaces.contains_rect(frame, rect):
                return target
            raise RuntimeError(
                "The selected status number no longer matches a control."
            )
        candidates = []
        for target in self.targets:
            frame = surfaces.visible_frame(target.element)
            if frame is not None and surfaces.contains_rect(frame, rect):
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
                root
                for provider in self.providers
                for root in surfaces.windows(provider)
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
        if (
            menu is not None
            and self.owner is not None
            and surfaces.owns_menu(menu, self.owner)
        ):
            if menu != self.before_menu or (
                self.surface is not None and self.surface.root.get("AXRole") == "AXMenu"
            ):
                targets = surfaces.panel_targets(menu, self.owner)
                if targets:
                    return surfaces.Surface(menu, self.owner, targets)
        for anchor in (self.anchor, self.opener):
            if anchor is None:
                continue
            for root in surfaces.children(anchor):
                if root.get("AXRole") == "AXMenu":
                    targets = surfaces.panel_targets(root, self.owner)
                    if targets:
                        return surfaces.Surface(root, self.owner, targets)
        candidates = []
        for provider in self.providers:
            for root in surfaces.windows(provider):
                if root not in self.baseline:
                    targets = surfaces.panel_targets(root, provider)
                    if targets:
                        candidates.append(surfaces.Surface(root, provider, targets))
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
                    targets = self._icons(self.icon_parents)
                    if not targets:
                        raise RuntimeError("No visible status icons are accessible.")
                    self.show(targets)
                    return
            elif surface is not None:
                signature = [target.signature() for target in surface.targets]
                changed = (
                    self.surface is None
                    or surface.root != self.surface.root
                    or not surfaces.same_layout(self.signature, signature)
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
            self._failed("Unable to read the status panel.")

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
        parent = menu_parent(root)
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
                opener = menu_opener(parent)
                if opener is not None and opener != self.opener:
                    opener.perform("AXPress")
                else:
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
