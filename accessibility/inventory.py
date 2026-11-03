"""Talon registrations, settings, and ownership of application-number sessions."""

import logging

from talon import Context, Module, actions, app, ui

from . import activation, application_session

mod = Module()
mod.tag(
    "application_numbers_enabled",
    desc="Use application numbers for the default 'show numbers' command",
)
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
enabled_ctx = Context()
enabled_ctx.matches = "os: mac"
enabled_ctx.tags = ["user.application_numbers_enabled"]
ctx = Context()
ctx.matches = "os: mac"
session_ctx = Context()
session_ctx.matches = "os: mac"
labels_ctx = Context()
labels_ctx.matches = """
os: mac
tag: user.application_labels_session
"""

_session = globals().get("_session")
if _session is not None:
    _session.stop()
_session = None
_activation_overrides = {}


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
        before = activation.enabled_interfaces(owner)
        activation.prepare(owner, _activation_overrides)
        # Apps build their AX tree after the switch is set, so the first scan
        # may see only the window frame. Talon's set result is unreliable.
        just_enabled = bool(activation.enabled_interfaces(owner) - before)
    except (RuntimeError, ui.UIErr):
        logging.exception("Application labels: unable to enable AX interfaces")
        app.notify(
            "Application control labels",
            f"Unable to enable accessibility interfaces for {owner.name}.",
        )
        return

    _session = application_session.ApplicationLabelSession(
        owner, ctx, session_ctx, _stop
    )
    _session.start(settle=just_enabled)


@mod.action_class
class Actions:
    def accessibility_prepare_active_app() -> bool:
        """Enable supported AX interfaces for a read-only accessibility action."""
        owner = ui.active_app()
        return owner is not None and activation.prepare(owner, _activation_overrides)

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
            status, changed = activation.set_interfaces(owner, enabled, force=force)
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
        _activation_overrides[activation.application_key(owner)] = enabled
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
