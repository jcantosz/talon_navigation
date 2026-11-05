"""Application label rendering, refreshes, selection, and menu transitions."""

import logging
import time

from talon import actions, app, cron, ctrl, settings, ui

from ..lib.labels import (
    MENU_BACK_FALLBACK_TICKS,
    MENU_HOVER_DELAY_TICKS,
    MENU_WAIT_TICKS,
    LabelSession,
    label_elements,
    menu_opener,
    menu_parent,
    usable_frame,
)
from . import controls

EXPANDING_ROLES = {
    "AXComboBox",
    "AXDisclosureTriangle",
    "AXMenuButton",
    "AXPopUpButton",
    "AXTab",
}
MENU_POLL_INTERVAL = "100ms"
SETTLE_INTERVAL = "250ms"
SETTLE_SCANS = 8
SETTLE_STABLE_SCANS = 2
START_RETRY_SECONDS = 2.0


def _may_expand(element):
    role = element.get("AXRole")
    if role in EXPANDING_ROLES or "AXShowMenu" in element.actions:
        return True
    if role == "AXRadioButton":
        parent = element.get("AXParent")
        return parent is not None and parent.get("AXRole") == "AXTabGroup"
    return False


class ApplicationLabelSession(LabelSession):
    def __init__(self, owner, context, session_context, stop_session):
        # Back suspends the visible-label grammar while retaining session ownership.
        super().__init__(context, "user.application_labels_active", False)
        self.session_context = session_context
        self._stop_session = stop_session
        self.owner = owner
        self.targets = []
        self.labelled = []
        self.window = None
        self.menu = None
        self.signature = ()
        self.refresh_job = None
        self.deferred_job = None
        self.refreshing = False
        self.selecting = False
        self.reported_menu = None
        self.resolved_menu = None
        self.menu_wait = None
        self.menu_wait_target = None
        self.menu_wait_remaining = 0
        self.menu_hover_target = None
        self.menu_hover_position = None
        self.menu_back_fallback = False
        self.empty_menu = None
        self.empty_menu_attempts = 0
        self.settle_job = None
        self.settle_remaining = 0
        self.settle_changed = False
        self.settle_stable = 0
        self.start_deadline = 0.0
        self.start_retry_job = None

    def start(self, settle=False):
        self.start_deadline = time.monotonic() + START_RETRY_SECONDS
        if settle:
            self.settle_remaining = SETTLE_SCANS
        self.refresh(force=True)
        if not self.stopped:
            self.start_updates(self._check_menu, MENU_POLL_INTERVAL)
        if settle and not self.stopped and self.start_retry_job is None:
            self.settle_job = cron.after(SETTLE_INTERVAL, self._settle)

    def _retry_start(self):
        """Repeat a failed first scan while the application finishes responding."""
        self.start_retry_job = None
        if self.stopped:
            return
        self.refresh(force=True)
        if (
            not self.stopped
            and self.start_retry_job is None
            and self.settle_remaining > 0
            and self.settle_job is None
        ):
            self.settle_job = cron.after(SETTLE_INTERVAL, self._settle)

    def _settle(self):
        """Re-scan while a just-enabled AX tree is still being built."""
        self.settle_job = None
        if self.stopped:
            return
        previous = self.signature
        self.refresh()
        if self.stopped:
            return
        self.settle_remaining -= 1
        if self.signature != previous:
            self.settle_changed = True
            self.settle_stable = 0
        else:
            self.settle_stable += 1
        settled = self.settle_changed and self.settle_stable >= SETTLE_STABLE_SCANS
        if self.settle_remaining > 0 and not settled:
            self.settle_job = cron.after(SETTLE_INTERVAL, self._settle)

    def request_refresh(self, delay="0ms"):
        if (
            self.stopped
            or self.selecting
            or self.refresh_job is not None
            or self.menu_wait is not None
        ):
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

    def _active_menu(self):
        menu = ui.active_menu()
        if menu is None or usable_frame(menu):
            self.reported_menu = None
            self.resolved_menu = None
            return menu
        if (
            menu == self.reported_menu
            and self.resolved_menu is not None
            and usable_frame(self.resolved_menu)
        ):
            return self.resolved_menu
        resolved = controls.visible_menu(self.owner.element.get("AXFocusedWindow"))
        self.reported_menu = menu
        self.resolved_menu = resolved
        return resolved if resolved is not None else menu

    def _check_menu(self):
        if self.stopped or self.refreshing or self.selecting:
            return
        try:
            active = ui.active_app()
            if self.stopped:
                return
            if active is None or active.pid != self.owner.pid:
                self._stop_session()
                actions.labels.hide()
                return
            menu = self._active_menu()
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
                    self._stop_session()
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
            self._stop_session()
            actions.labels.hide()
            return False
        window = self.owner.element.get("AXFocusedWindow")
        if self.stopped:
            return False
        if window != self.window:
            self._stop_session()
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
            self.hover_submenu_if_current(
                target,
                self.menu,
                position,
                self._transition_focus_valid,
                self._active_menu,
            )
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if self.stopped:
                return
            logging.exception("Application labels: unable to hover submenu")
            self._stop_session()
            actions.labels.hide()
            app.notify(
                "Application control labels", "Unable to open the selected submenu."
            )

    def _fallback_back(self):
        try:
            if (
                not self._transition_focus_valid()
                or self._active_menu() != self.menu
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
            self._stop_session()
            actions.labels.hide()
            app.notify(
                "Application control labels", "Unable to return to the parent menu."
            )

    def refresh(self, force=False):
        if (
            self.stopped
            or self.refreshing
            or self.selecting
            or self.menu_wait is not None
        ):
            return
        active = ui.active_app()
        if self.stopped:
            return
        if active is None or active.pid != self.owner.pid:
            self._stop_session()
            actions.labels.hide()
            return

        self.refreshing = True
        try:
            self._cancel_deferred()
            window = self.owner.element.get("AXFocusedWindow")
            menu = self._active_menu()
            targets, deferred = controls.collect(self.owner, menu, window)
            if self.stopped:
                return
            if self._active_menu() != menu:
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
            extra = controls.collect_deferred(deferred, targets)
            if self._active_menu() != menu:
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
                or self._active_menu() is not None
            ):
                self._schedule_menu_refresh()
                return
            extra = controls.collect_deferred(deferred, targets)
            if self._active_menu() is not None:
                self._schedule_menu_refresh()
                return
            if extra:
                self._update(window, None, targets + extra, force=False)
        except (AttributeError, RuntimeError, ui.UIErr):
            self._query_failed()

    def _update(self, window, menu, targets, force):
        if self.stopped:
            return
        signature = controls.signature(targets)
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
            self._stop_session()
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
        self.labelled = label_elements(targets, in_menu=menu is not None)
        self.window = window
        self.menu = menu
        self.signature = signature
        if self.render(self.labelled) and not self.stopped:
            self.session_context.tags = ["user.application_labels_session"]

    def _query_failed(self):
        if self.stopped:
            return
        if not self.targets and time.monotonic() < self.start_deadline:
            logging.debug(
                "Application labels: first scan failed; retrying", exc_info=True
            )
            if self.start_retry_job is None:
                self.start_retry_job = cron.after(SETTLE_INTERVAL, self._retry_start)
            return
        logging.exception("Application labels: unable to query focused controls")
        self._stop_session()
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
            self._stop_session()
            actions.labels.hide()
            app.notify("Application control labels", "The active application changed.")
            return
        if self.refreshing or self.selecting:
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
        expand = False
        try:
            if self._active_menu() != self.menu:
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
                and not controls.in_visible_web_area(target, [])
            ):
                actions.labels.hide()
                app.notify(
                    "Application control labels",
                    "The control's web area is covered. Show application numbers again.",
                )
                return
            menu_selection = self.menu is not None
            expand = not menu_selection and _may_expand(target)
            activation_target = controls.row_activation_target(target)
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
            self.selecting = True
            if native_selection:
                actions.next(label)
                if not self.stopped and not menu_selection and not expand:
                    actions.labels.hide()
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
                self.selecting = False
                self.signature = ()
                self.request_refresh("100ms")
        except ui.ActionFailed:
            if self.stopped:
                return
            if expand:
                # Some apps (e.g. Word combo-box arrows) open the popup but still
                # report failure. Never retry the press; refresh to show what is open.
                logging.warning(
                    "Application labels: expanding control reported failure; refreshing"
                )
                actions.labels.hide()
                self.selecting = False
                self.signature = ()
                self.request_refresh("100ms")
                return
            logging.exception("Application labels: unable to select target")
            self._stop_session()
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "Unable to activate the selected control.",
            )
        except (AttributeError, RuntimeError, ui.UIErr):
            if self.stopped:
                return
            logging.exception("Application labels: unable to select target")
            self._stop_session()
            actions.labels.hide()
            app.notify(
                "Application control labels",
                "Unable to activate the selected control.",
            )
        finally:
            self.selecting = False
            self.preserve_hide = False

    def back(self):
        try:
            active = ui.active_app()
            if self.stopped:
                return
            if active is None or active.pid != self.owner.pid:
                self._stop_session()
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
            menu = self._active_menu()
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
            self._stop_session()
            actions.labels.hide()
            app.notify(
                "Application control labels", "Unable to return to the parent menu."
            )

    def stop(self):
        if self.stopped:
            return
        super().stop()
        self.session_context.tags = []
        if self.refresh_job is not None:
            cron.cancel(self.refresh_job)
            self.refresh_job = None
        if self.settle_job is not None:
            cron.cancel(self.settle_job)
            self.settle_job = None
        if self.start_retry_job is not None:
            cron.cancel(self.start_retry_job)
            self.start_retry_job = None
        self._cancel_deferred()
        self.menu_hover_target = None
        self.menu_hover_position = None
