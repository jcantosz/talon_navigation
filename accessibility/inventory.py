import logging

from talon import Context, Module, actions, app, axquery, cron, settings, ui

from ..lib.labels import LabelSession

mod = Module()
mod.tag(
    "application_labels_active",
    desc="Navigating focused application controls with accessibility labels",
)
mod.setting(
    "accessibility_activation_disallowed_bundles",
    type=str,
    default="",
    desc="Comma-separated app bundle IDs that must not have AX interfaces enabled.",
)
mod.setting(
    "accessibility_query_max_depth",
    type=int,
    default=0,
    desc="Maximum AX query depth for application labels; 0 means unlimited.",
)
ctx = Context()
ctx.matches = "os: mac"
labels_ctx = Context()
labels_ctx.matches = """
os: mac
tag: user.application_labels_active
"""

CONTROL_ROLES = {
    "AXButton",
    "AXCheckBox",
    "AXComboBox",
    "AXDisclosureTriangle",
    "AXLink",
    "AXMenuButton",
    "AXMenuItem",
    "AXPopUpButton",
    "AXRadioButton",
    "AXSearchField",
    "AXSlider",
    "AXSwitch",
    "AXTab",
    "AXTextArea",
    "AXTextField",
}
EXPANDING_ROLES = {
    "AXComboBox",
    "AXDisclosureTriangle",
    "AXMenuButton",
    "AXPopUpButton",
}
QUERY = "[AXPosition]:action(AXPress)"
ACCESSIBILITY_ATTRIBUTES = (
    "AXEnhancedUserInterface",
    "AXManualAccessibility",
)
_session = None
_activation_overrides = {}

_previous_session = globals().get("_session")
if _previous_session is not None:
    _previous_session.stop()


def focused_surfaces(owner):
    focused_window = owner.element.get("AXFocusedWindow")
    if focused_window is None:
        raise RuntimeError(
            f"{owner.name} does not expose an AXFocusedWindow attribute."
        )
    surfaces = [("focused-window", focused_window)]
    menu = ui.active_menu()
    if menu is not None:
        surfaces.append(("active-menu", menu))
    return surfaces


def _controls(owner):
    controls = []
    configured_depth = settings.get("user.accessibility_query_max_depth")
    if configured_depth < 0:
        raise RuntimeError(
            "user.accessibility_query_max_depth must be zero or a positive integer."
        )
    max_depth = configured_depth or -1
    for _, root in focused_surfaces(owner):
        for element in axquery.query_all(
            QUERY,
            root=root,
            visible_only=True,
            max_depth=max_depth,
            timeout=1,
        ):
            if (
                element.get("AXRole") in CONTROL_ROLES
                and element.get("AXEnabled") is not False
                and not any(existing == element for existing in controls)
            ):
                controls.append(element)
    return controls


def _signature(elements):
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


def _may_expand(element):
    return element.get("AXRole") in EXPANDING_ROLES or "AXShowMenu" in element.actions


def _activation_disallowed(owner):
    configured = settings.get("user.accessibility_activation_disallowed_bundles")
    bundles = {bundle.strip() for bundle in configured.split(",") if bundle.strip()}
    return owner.bundle in bundles


def _set_accessibility_interfaces(owner, enabled, force=False):
    if enabled and not force and _activation_disallowed(owner):
        return "disallowed", ()

    if enabled:
        # Firefox and other lazy AX providers activate when their app role is read.
        owner.element.get("AXRole")

    changed = []
    for attribute in ACCESSIBILITY_ATTRIBUTES:
        try:
            owner.element[attribute] = enabled
        except ui.UIErr:
            continue
        changed.append(attribute)
    return "updated", tuple(changed)


def _activation_key(owner):
    return owner.pid, owner.created_at


def _prepare_accessibility_interfaces(owner):
    if _activation_overrides.get(_activation_key(owner)) is False:
        return False

    status, changed = _set_accessibility_interfaces(owner, True)
    if status == "disallowed":
        logging.debug(
            "Application labels: AX activation is disallowed for %s (%s)",
            owner.name,
            owner.bundle,
        )
        return False

    logging.debug(
        "Application labels: enabled AX interfaces for %s: %s",
        owner.name,
        changed,
    )
    return True


class ApplicationLabelSession(LabelSession):
    def __init__(self, owner):
        super().__init__(labels_ctx, "user.application_labels_active", False)
        self.owner = owner
        self.targets = []
        self.signature = ()
        self.refresh_job = None
        self.refreshing = False

    def start(self):
        self.refresh(force=True)

    def request_refresh(self, delay="0ms"):
        if self.stopped or self.refresh_job is not None:
            return
        self.refresh_job = cron.after(delay, self._refresh_after_event)

    def _refresh_after_event(self):
        self.refresh_job = None
        self.refresh()

    def refresh(self, force=False):
        if self.stopped or self.refreshing:
            return
        if ui.active_app().pid != self.owner.pid:
            actions.labels.hide()
            return

        self.refreshing = True
        try:
            targets = _controls(self.owner)
            signature = _signature(targets)
            if not force and signature == self.signature:
                return
            if not targets:
                actions.labels.hide()
                app.notify(
                    "Application control labels",
                    "The focused window exposes no visible pressable controls.",
                )
                return
            self.targets = targets
            self.signature = signature
            self.render(targets)
        except (RuntimeError, ui.UIErr):
            logging.exception("Application labels: unable to query focused controls")
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "Unable to query the focused accessibility window.",
            )
        finally:
            self.refreshing = False

    def select(self, label):
        if ui.active_app().pid != self.owner.pid:
            actions.labels.hide()
            app.notify("Application control labels", "The active application changed.")
            return
        if not isinstance(label, int) or not 1 <= label <= len(self.targets):
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "That number no longer matches a control.",
            )
            return

        target = self.targets[label - 1]
        expand = _may_expand(target)
        self.preserve_hide = expand
        try:
            actions.next(label)
            if expand:
                self.request_refresh("100ms")
        except (ui.UIErr, ui.ActionFailed):
            logging.exception("Application labels: unable to select target")
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "Unable to activate the selected control.",
            )
        finally:
            self.preserve_hide = False

    def stop(self):
        if self.refresh_job is not None:
            cron.cancel(self.refresh_job)
            self.refresh_job = None
        super().stop()


def _stop():
    global _session
    if _session is not None:
        _session.stop()
    _session = None


def _show_application_numbers():
    global _session
    _stop()
    owner = ui.active_app()
    if owner is None:
        app.notify("Application control labels", "There is no active application.")
        return

    _prepare_accessibility_interfaces(owner)

    _session = ApplicationLabelSession(owner)
    _session.start()


@mod.action_class
class Actions:
    def accessibility_prepare_active_app() -> bool:
        """Enable supported AX interfaces for a read-only accessibility action."""
        owner = ui.active_app()
        return owner is not None and _prepare_accessibility_interfaces(owner)

    def accessibility_show_application_numbers():
        """Label controls in the focused accessibility window."""
        _show_application_numbers()

    def accessibility_refresh_application_numbers():
        """Refresh active application control labels after a UI change."""
        if _session is not None:
            _session.request_refresh()

    def accessibility_set_interfaces(enabled: bool, force: bool = False):
        """Enable or disable supported AX interfaces for the active app."""
        owner = ui.active_app()
        status, changed = _set_accessibility_interfaces(owner, enabled, force=force)
        if status == "disallowed":
            app.notify(
                "Accessibility interfaces",
                f"Activation is disallowed for {owner.bundle}.",
            )
            return
        _activation_overrides[_activation_key(owner)] = enabled
        operation = "Enabled" if enabled else "Disabled"
        detail = ", ".join(changed) if changed else "No supported writable interfaces"
        app.notify("Accessibility interfaces", f"{operation}: {detail}")
        if _session is not None and owner.pid == _session.owner.pid:
            _session.request_refresh()


@labels_ctx.action_class("labels")
class LabelOverrides:
    def select(label: int | str):
        if _session is not None:
            _session.select(label)

    def hide():
        if _session is not None and _session.preserve_hide:
            actions.next()
            return
        _stop()
        actions.next()


def _event_pid(event):
    if hasattr(event, "pid"):
        return event.pid
    owner = getattr(event, "app", None)
    return owner.pid if owner is not None else None


def _focus_changed(event):
    if _session is None:
        return
    if _event_pid(event) != _session.owner.pid:
        _stop()
        actions.labels.hide()
    else:
        _session.request_refresh()


def _window_changed(window):
    if _session is not None and ui.active_app().pid == _session.owner.pid:
        _session.request_refresh()


def _element_changed(*event):
    if _session is not None and ui.active_app().pid == _session.owner.pid:
        _session.request_refresh()


ui.register("win_focus", _focus_changed)
ui.register("app_activate", _focus_changed)
ui.register("win_open", _window_changed)
ui.register("win_close", _window_changed)
ui.register("element", _element_changed)
