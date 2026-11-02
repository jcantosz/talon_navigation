"""Talon registrations and ownership of status-label sessions."""

import logging

from talon import Context, Module, actions, app, ui

from . import discovery, status_session, surfaces

mod = Module()
mod.tag("status_labels_active", desc="Navigating macOS status icons and their panels")
ctx = Context()
ctx.matches = "os: mac"
controls_ctx = Context()
controls_ctx.matches = """
os: mac
tag: user.status_labels_active
"""


_session = None
_parents = []


def _icons(parents=None):
    global _parents
    result = discovery.discover(
        ui,
        surfaces.visible_frame,
        surfaces.is_unobstructed,
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
        surfaces.Target(
            item.element,
            next(owner for parent, owner in parents if parent.element == item.bar),
            item.frame,
        )
        for item in result.items
    ]


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
            opened = surfaces.open_status(_parents)
            if not targets and opened is None:
                app.notify("Status labels", "No visible status icons are accessible.")
                return
            _session = status_session.StatusSession(
                names,
                ctx,
                icons=_icons,
                get_parents=lambda: _parents,
                failed=_failed,
            )
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
