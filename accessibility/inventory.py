import logging
from math import isfinite

from talon import Context, Module, actions, app, axquery, cron, ctrl, settings, ui

from ..lib.labels import (
    CONTROL_ROLES,
    MENU_BACK_FALLBACK_TICKS,
    MENU_HOVER_DELAY_TICKS,
    LabelSession,
    menu_opener,
    menu_parent,
)
from ..lib.labels import (
    label_element as _label_element,
)
from ..lib.labels import (
    submenu_hover_point as _submenu_hover_point,
)
from ..lib.labels import (
    usable_frame as _has_usable_frame,
)

mod = Module()
mod.tag(
    "application_labels_active",
    desc="Navigating focused application controls with accessibility labels",
)
mod.tag(
    "application_labels_session",
    desc="Preserve application label ownership during menu transitions",
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
mod.setting(
    "accessibility_clip_to_surface",
    type=bool,
    default=False,
    desc=(
        "Skip Talon's visibility pruning and keep controls whose frames overlap "
        "the queried window or menu; tolerates elements removed during the query."
    ),
)
ctx = Context()
ctx.matches = "os: mac"
session_ctx = Context()
session_ctx.matches = "os: mac"
labels_ctx = Context()
labels_ctx.matches = """
os: mac
tag: user.application_labels_session
"""

EXPANDING_ROLES = {
    "AXComboBox",
    "AXDisclosureTriangle",
    "AXMenuButton",
    "AXPopUpButton",
}
QUERY = "[AXPosition]:action(AXPress)"
ROW_ITEM_LEVELS = 3
ROW_ACTIVATION_COVERAGE = 0.8
MENU_POLL_INTERVAL = "100ms"
MENU_WAIT_TICKS = 15
MAX_NATIVE_NODES = 10000
_CURRENT_SURFACE = object()
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


def _row_activation_target(element):
    if element.get("AXRole") != "AXRow" or not _has_usable_frame(element):
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
        or not _has_usable_frame(child)
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
        and _has_usable_frame(element)
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
    if not _has_usable_frame(surface):
        raise RuntimeError("The accessibility surface has no usable frame.")
    return surface.get("AXFrame")


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


def _controls(owner, menu=_CURRENT_SURFACE, window=_CURRENT_SURFACE):
    """Return numbered controls and web areas whose controls may be appended later."""
    budget = _query_budget()
    controls = []
    if menu is _CURRENT_SURFACE:
        menu = ui.active_menu()
    if menu is not None:
        _query_controls(menu, controls, budget, _surface_clip(menu))
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


def _deferred_controls(areas, controls):
    """Return controls from deferred web areas whose centers are not covered."""
    budget = _query_budget()
    combined = list(controls)
    cache = []
    for area, clip in areas:
        if _has_usable_frame(area) and _in_visible_web_area(area, cache):
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
        # Back suspends the visible-label grammar while retaining session ownership.
        super().__init__(ctx, "user.application_labels_active", False)
        self.owner = owner
        self.targets = []
        self.labelled = []
        self.window = None
        self.menu = None
        self.signature = ()
        self.refresh_job = None
        self.deferred_job = None
        self.refreshing = False
        self.menu_wait = None
        self.menu_wait_target = None
        self.menu_wait_remaining = 0
        self.menu_hover_target = None
        self.menu_hover_position = None
        self.menu_back_fallback = False
        self.empty_menu = None
        self.empty_menu_attempts = 0

    def start(self):
        self.refresh(force=True)
        if not self.stopped:
            self.start_updates(self._check_menu, MENU_POLL_INTERVAL)

    def request_refresh(self, delay="0ms"):
        if self.stopped or self.refresh_job is not None or self.menu_wait is not None:
            return
        self.refresh_job = cron.after(delay, self._refresh_after_event)

    def _refresh_after_event(self):
        self.refresh_job = None
        self.refresh()

    def _schedule_menu_refresh(self, delay="0ms"):
        if self.stopped:
            return
        self.hide_for_transition()
        self.signature = ()
        self.request_refresh(delay)

    def _check_menu(self):
        if self.stopped or self.refreshing:
            return
        try:
            active = ui.active_app()
            if self.stopped:
                return
            if active is None or active.pid != self.owner.pid:
                _stop()
                actions.labels.hide()
                return
            menu = ui.active_menu()
            if self.stopped:
                return
            if self.menu_wait is not None:
                ready = (
                    menu == self.menu_wait_target
                    if self.menu_wait == "back"
                    else menu is not None and menu != self.menu
                )
                returned_to_window = (
                    self.menu_wait == "back"
                    and self.menu_back_fallback
                    and menu is None
                )
                if ready or returned_to_window:
                    self.menu_wait = None
                    self.menu_wait_target = None
                    self.menu_hover_target = None
                    self.menu_hover_position = None
                    self.menu_back_fallback = False
                    self.request_refresh()
                    if returned_to_window:
                        app.notify(
                            "Application control labels",
                            "The parent menu did not respond; showing application "
                            "controls instead.",
                        )
                    return
                self.menu_wait_remaining -= 1
                if (
                    self.menu_wait == "select"
                    and self.menu_hover_target is not None
                    and menu == self.menu
                    and self.menu_wait_remaining
                    <= MENU_WAIT_TICKS - MENU_HOVER_DELAY_TICKS
                ):
                    self._hover_submenu()
                    if self.stopped:
                        return
                if (
                    self.menu_wait == "back"
                    and self.menu_wait_target is not None
                    and not self.menu_back_fallback
                    and menu == self.menu
                    and self.menu_wait_remaining
                    <= MENU_WAIT_TICKS - MENU_BACK_FALLBACK_TICKS
                ):
                    self._fallback_back()
                    if self.stopped:
                        return
                if self.menu_wait_remaining <= 0:
                    waiting = self.menu_wait
                    _stop()
                    actions.labels.hide()
                    if waiting == "back":
                        app.notify(
                            "Application control labels",
                            "Unable to return to the parent menu.",
                        )
                    elif menu is not None:
                        app.notify(
                            "Application control labels",
                            "No new selectable submenu appeared.",
                        )
                return
            if menu != self.menu:
                self._schedule_menu_refresh()
        except (AttributeError, RuntimeError, ui.UIErr):
            self._query_failed()

    def _start_menu_wait(self, kind, expected=None):
        if self.refresh_job is not None:
            cron.cancel(self.refresh_job)
            self.refresh_job = None
        self._cancel_deferred()
        self.menu_wait = kind
        self.menu_wait_target = expected
        self.menu_wait_remaining = MENU_WAIT_TICKS
        self.menu_hover_target = None
        self.menu_hover_position = None
        self.menu_back_fallback = False
        self.signature = ()

    def _transition_focus_valid(self):
        active = ui.active_app()
        if self.stopped:
            return False
        if active is None or active.pid != self.owner.pid:
            _stop()
            actions.labels.hide()
            return False
        window = self.owner.element.get("AXFocusedWindow")
        if self.stopped:
            return False
        if window != self.window:
            _stop()
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "The focused window changed. Say 'show application numbers' again.",
            )
            return False
        return True

    def _hover_submenu(self):
        target = self.menu_hover_target
        position = self.menu_hover_position
        self.menu_hover_target = None
        self.menu_hover_position = None
        try:
            if ctrl.mouse_pos() != position or not self._transition_focus_valid():
                return
            point = _submenu_hover_point(target, self.menu)
            if (
                self.stopped
                or point is None
                or ctrl.mouse_pos() != position
                or not self._transition_focus_valid()
                or ui.active_menu() != self.menu
                or self.stopped
            ):
                return
            actions.mouse_move(*point)
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if self.stopped:
                return
            logging.exception("Application labels: unable to hover submenu")
            _stop()
            actions.labels.hide()
            app.notify(
                "Application control labels", "Unable to open the selected submenu."
            )

    def _fallback_back(self):
        try:
            if (
                not self._transition_focus_valid()
                or ui.active_menu() != self.menu
                or self.stopped
            ):
                return
            self.menu_back_fallback = True
            self.menu_wait_remaining = MENU_WAIT_TICKS
            actions.key("esc")
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if self.stopped:
                return
            logging.exception("Application labels: unable to leave submenu")
            _stop()
            actions.labels.hide()
            app.notify(
                "Application control labels", "Unable to return to the parent menu."
            )

    def refresh(self, force=False):
        if self.stopped or self.refreshing or self.menu_wait is not None:
            return
        active = ui.active_app()
        if self.stopped:
            return
        if active is None or active.pid != self.owner.pid:
            _stop()
            actions.labels.hide()
            return

        self.refreshing = True
        try:
            self._cancel_deferred()
            window = self.owner.element.get("AXFocusedWindow")
            menu = ui.active_menu()
            targets, deferred = _controls(self.owner, menu, window)
            if self.stopped:
                return
            if ui.active_menu() != menu:
                self._schedule_menu_refresh()
                return
            if force and targets and deferred:
                # Show the primary surface before walking secondary web areas.
                self._update(window, menu, targets, force)
                if not self.stopped:
                    self.deferred_job = cron.after(
                        "0ms", lambda: self._append_deferred(window, targets, deferred)
                    )
                return
            extra = _deferred_controls(deferred, targets)
            if ui.active_menu() != menu:
                self._schedule_menu_refresh()
                return
            self._update(window, menu, targets + extra, force)
        except (AttributeError, RuntimeError, ui.UIErr):
            self._query_failed()
        finally:
            self.refreshing = False

    def _append_deferred(self, window, targets, deferred):
        self.deferred_job = None
        active = ui.active_app()
        if self.stopped or active is None or active.pid != self.owner.pid:
            return
        try:
            if (
                self.owner.element.get("AXFocusedWindow") != window
                or ui.active_menu() is not None
            ):
                self._schedule_menu_refresh()
                return
            extra = _deferred_controls(deferred, targets)
            if ui.active_menu() is not None:
                self._schedule_menu_refresh()
                return
            if extra:
                self._update(window, None, targets + extra, force=False)
        except (AttributeError, RuntimeError, ui.UIErr):
            self._query_failed()

    def _update(self, window, menu, targets, force):
        if self.stopped:
            return
        signature = _signature(targets)
        if self.stopped:
            return
        if (
            not force
            and signature == self.signature
            and window == self.window
            and menu == self.menu
        ):
            return
        if not targets:
            if menu is not None:
                if menu != self.empty_menu:
                    self.empty_menu = menu
                    self.empty_menu_attempts = 0
                self.empty_menu_attempts += 1
                if self.empty_menu_attempts < MENU_WAIT_TICKS:
                    self._schedule_menu_refresh(MENU_POLL_INTERVAL)
                    return
            _stop()
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "The active menu exposes no visible pressable controls."
                if menu is not None
                else "The focused window exposes no visible pressable controls.",
            )
            return
        self.empty_menu = None
        self.empty_menu_attempts = 0
        self.targets = targets
        self.labelled = [
            _label_element(target, in_menu=menu is not None) for target in targets
        ]
        self.window = window
        self.menu = menu
        self.signature = signature
        if self.render(self.labelled) and not self.stopped:
            session_ctx.tags = ["user.application_labels_session"]

    def _query_failed(self):
        if self.stopped:
            return
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
        active = ui.active_app()
        if self.stopped:
            return
        if active is None or active.pid != self.owner.pid:
            _stop()
            actions.labels.hide()
            app.notify("Application control labels", "The active application changed.")
            return
        if self.refreshing:
            app.notify(
                "Application control labels",
                "Wait for the numbers to finish refreshing.",
            )
            return
        if self.menu_wait is not None:
            app.notify(
                "Application control labels", "Wait for the menu to finish opening."
            )
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
            if ui.active_menu() != self.menu:
                self._schedule_menu_refresh()
                app.notify(
                    "Application control labels",
                    "The active menu changed. Choose a refreshed number.",
                )
                return
            if self.owner.element.get("AXFocusedWindow") != self.window:
                actions.labels.hide()
                app.notify(
                    "Application control labels",
                    "The focused window changed. Say 'show application numbers' again.",
                )
                return
            if (
                self.menu is None
                and settings.get("user.accessibility_defer_web_areas")
                and not _in_visible_web_area(target, [])
            ):
                actions.labels.hide()
                app.notify(
                    "Application control labels",
                    "The control's web area is covered. Show application numbers again.",
                )
                return
            menu_selection = self.menu is not None
            expand = not menu_selection and _may_expand(target)
            activation_target = _row_activation_target(target)
            if self.stopped:
                return
            if menu_selection:
                self._start_menu_wait("select")
            elif expand:
                self.signature = ()
            self.preserve_hide = menu_selection or expand
            native_selection = (
                self.labelled[label - 1] is target and activation_target is target
            )
            if native_selection:
                actions.next(label)
            else:
                activation_target.perform("AXPress")
                if self.stopped:
                    return
                actions.labels.hide()
            if menu_selection and not self.stopped:
                if native_selection:
                    actions.labels.hide()
                if (
                    not self.stopped
                    and target.get("AXRole") == "AXMenuItem"
                    and target.get("AXHasPopup") is True
                ):
                    self.menu_hover_position = ctrl.mouse_pos()
                    self.menu_hover_target = target
            elif expand and not self.stopped:
                self.request_refresh("100ms")
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if self.stopped:
                return
            logging.exception("Application labels: unable to select target")
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "Unable to activate the selected control.",
            )
        finally:
            self.preserve_hide = False

    def back(self):
        try:
            active = ui.active_app()
            if self.stopped:
                return
            if active is None or active.pid != self.owner.pid:
                _stop()
                actions.labels.hide()
                app.notify(
                    "Application control labels", "The active application changed."
                )
                return
            if self.refreshing:
                app.notify(
                    "Application control labels",
                    "Wait for the numbers to finish refreshing.",
                )
                return
            if self.menu_wait is not None:
                app.notify(
                    "Application control labels",
                    "Wait for the menu to finish opening.",
                )
                return
            menu = ui.active_menu()
            if menu != self.menu:
                self._schedule_menu_refresh()
                app.notify(
                    "Application control labels",
                    "The active menu changed. Wait for the numbers to refresh.",
                )
                return
            if menu is None:
                app.notify(
                    "Application control labels",
                    "Already showing application controls.",
                )
                return

            parent = menu_parent(menu)
            parent = (
                parent
                if parent is not None and parent.get("AXRole") == "AXMenu"
                else None
            )
            opener = menu_opener(parent) if parent is not None else None
            if self.stopped:
                return
            self._start_menu_wait("back", parent)
            self.preserve_hide = True
            try:
                actions.labels.hide()
                if self.stopped:
                    return
                # The visible-label context would otherwise intercept Escape.
                self.context.tags = []
                if opener is not None:
                    opener.perform("AXPress")
                elif parent is not None:
                    actions.key("left")
                else:
                    actions.key("esc")
            finally:
                self.preserve_hide = False
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if self.stopped:
                return
            logging.exception("Application labels: unable to return from menu")
            _stop()
            actions.labels.hide()
            app.notify(
                "Application control labels", "Unable to return to the parent menu."
            )

    def stop(self):
        if self.stopped:
            return
        super().stop()
        session_ctx.tags = []
        if self.refresh_job is not None:
            cron.cancel(self.refresh_job)
            self.refresh_job = None
        self._cancel_deferred()
        self.menu_hover_target = None
        self.menu_hover_position = None


def _stop():
    global _session
    if _session is not None:
        _session.stop()
    _session = None


def _show_application_numbers():
    global _session
    actions.labels.hide()
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

    def accessibility_application_numbers_back():
        """Close one menu level and return to the parent menu or application."""
        if _session is None:
            app.notify("Application control labels", "Show application numbers first.")
            return
        _session.back()

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
