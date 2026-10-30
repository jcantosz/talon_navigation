import logging
from math import isfinite

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
mod.setting(
    "accessibility_query_timeout",
    type=float,
    default=1.0,
    desc="Positive timeout in seconds for each application label AX query.",
)
mod.setting(
    "accessibility_defer_web_areas",
    type=bool,
    default=False,
    desc=(
        "Number the web area titled like the focused window first, then append "
        "controls from other web areas whose centers are visible."
    ),
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
MAX_NATIVE_NODES = 10000
ACCESSIBILITY_ATTRIBUTES = (
    "AXEnhancedUserInterface",
    "AXManualAccessibility",
)
_previous_session = globals().get("_session")
_session = None
_activation_overrides = {}
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


def _add_control(element, controls):
    if (
        element.get("AXRole") in CONTROL_ROLES
        and element.get("AXEnabled") is not False
        and element.get("AXHidden") is not True
        and _has_usable_frame(element)
        and not any(existing == element for existing in controls)
    ):
        controls.append(element)


def _query_controls(root, controls, budget):
    max_depth, timeout = budget
    for element in axquery.query_all(
        QUERY,
        root=root,
        visible_only=True,
        max_depth=max_depth,
        timeout=timeout,
    ):
        _add_control(element, controls)


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


def _controls(owner):
    """Return numbered controls and web areas whose controls may be appended later."""
    budget = _query_budget()
    defer = settings.get("user.accessibility_defer_web_areas")
    controls = []
    deferred = []
    for kind, root in focused_surfaces(owner):
        split = _split_web_areas(root) if defer and kind == "focused-window" else None
        if split is None:
            _query_controls(root, controls, budget)
            continue
        native, primary, others = split
        for element in native:
            _add_control(element, controls)
        _query_controls(primary, controls, budget)
        deferred.extend(others)
    return controls, deferred


def _deferred_controls(areas, controls):
    """Return controls from deferred web areas whose centers are not covered."""
    budget = _query_budget()
    combined = list(controls)
    cache = []
    for area in areas:
        if _has_usable_frame(area) and _in_visible_web_area(area, cache):
            _query_controls(area, combined, budget)
    return combined[len(controls) :]


def _has_usable_frame(element):
    frame = element.get("AXFrame")
    return (
        frame is not None
        and all(
            isfinite(value) for value in (frame.x, frame.y, frame.width, frame.height)
        )
        and frame.width > 0
        and frame.height > 0
    )


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


def _in_visible_web_area(element, cache):
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
        # Publish the tag from the unconditional context; labels_ctx requires it.
        super().__init__(ctx, "user.application_labels_active", False)
        self.owner = owner
        self.targets = []
        self.window = None
        self.signature = ()
        self.refresh_job = None
        self.deferred_job = None
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
            self._cancel_deferred()
            window = self.owner.element.get("AXFocusedWindow")
            targets, deferred = _controls(self.owner)
            if force and targets and deferred:
                # Show the primary surface before walking secondary web areas.
                self._update(window, targets, force)
                if not self.stopped:
                    self.deferred_job = cron.after(
                        "0ms", lambda: self._append_deferred(window, targets, deferred)
                    )
                return
            self._update(window, targets + _deferred_controls(deferred, targets), force)
        except (AttributeError, RuntimeError, ui.UIErr):
            self._query_failed()
        finally:
            self.refreshing = False

    def _append_deferred(self, window, targets, deferred):
        self.deferred_job = None
        if self.stopped or ui.active_app().pid != self.owner.pid:
            return
        try:
            if self.owner.element.get("AXFocusedWindow") != window:
                self.request_refresh()
                return
            extra = _deferred_controls(deferred, targets)
            if extra:
                self._update(window, targets + extra, force=False)
        except (AttributeError, RuntimeError, ui.UIErr):
            self._query_failed()

    def _update(self, window, targets, force):
        signature = _signature(targets)
        if not force and signature == self.signature and window == self.window:
            return
        if not targets:
            _stop()
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "The focused window exposes no visible pressable controls.",
            )
            return
        self.targets = targets
        self.window = window
        self.signature = signature
        self.render(targets)

    def _query_failed(self):
        logging.exception("Application labels: unable to query focused controls")
        _stop()
        actions.labels.hide()
        app.notify(
            "Application control labels",
            "Unable to query the focused accessibility window.",
        )

    def _cancel_deferred(self):
        if self.deferred_job is not None:
            cron.cancel(self.deferred_job)
            self.deferred_job = None

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
        try:
            if self.owner.element.get("AXFocusedWindow") != self.window:
                actions.labels.hide()
                app.notify(
                    "Application control labels",
                    "The focused window changed. Say 'show application numbers' again.",
                )
                return
            if settings.get(
                "user.accessibility_defer_web_areas"
            ) and not _in_visible_web_area(target, []):
                actions.labels.hide()
                app.notify(
                    "Application control labels",
                    "The control's web area is covered. Show application numbers again.",
                )
                return
            expand = _may_expand(target)
            self.preserve_hide = expand
            actions.next(label)
            if expand:
                self.request_refresh("100ms")
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
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
        self._cancel_deferred()
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

    try:
        _prepare_accessibility_interfaces(owner)
    except (RuntimeError, ui.UIErr):
        logging.exception("Application labels: unable to enable AX interfaces")
        app.notify(
            "Application control labels",
            f"Unable to enable accessibility interfaces for {owner.name}.",
        )
        return

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
        if owner is None:
            app.notify("Accessibility interfaces", "There is no active application.")
            return
        try:
            status, changed = _set_accessibility_interfaces(owner, enabled, force=force)
        except (RuntimeError, ui.UIErr):
            logging.exception("Accessibility interfaces: unable to update")
            app.notify(
                "Accessibility interfaces",
                f"Unable to update accessibility interfaces for {owner.name}.",
            )
            return
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
        actions.next()
        if _session is not None and not _session.preserve_hide:
            _stop()


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
