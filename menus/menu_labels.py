"""Talon registrations and ownership of menu-label sessions."""

import logging

from talon import Context, Module, actions, app, ui

from .menu_session import MenuSession, _targets_in

mod = Module()
mod.tag(
    "menu_labels_enabled",
    desc="Use application menu navigation instead of generic menu labels",
)
mod.tag("menu_labels_active", desc="Navigating application menus with labels")

enabled_ctx = Context()
enabled_ctx.matches = "os: mac"
enabled_ctx.tags = ["user.menu_labels_enabled"]

ctx = Context()
ctx.matches = "os: mac"

menu_ctx = Context()
menu_ctx.matches = """
os: mac
tag: user.menu_labels_active
"""

_session = None


def _stop():
    global _session
    if _session is not None:
        _session.stop()
    _session = None


def _failed(message):
    logging.exception(message)
    actions.labels.hide()
    _stop()
    app.notify("Menu labels", message)


@mod.action_class
class MenuLabelsActions:
    def menu_labels_back():
        """Close one menu level and relabel its parent in the current style."""
        if _session is None:
            app.notify("Menu labels", "Show menu labels or numbers first.")
            return
        _session.back()

    def menu_labels_show(names: bool = True):
        """Label the active application's menu by title, or by number if names is false."""
        global _session

        actions.labels.hide()
        _stop()
        try:
            active_app = ui.active_app()
            menu = ui.active_menu()
            if menu is None:
                menu = active_app.children.find_one(AXRole="AXMenuBar", max_depth=0)
            targets = _targets_in(menu)
            if not targets:
                app.notify("Menu labels", "No selectable application menu items found.")
                return

            _session = MenuSession(names, active_app.pid, ctx, _failed)
            _session.show_container(menu, targets)
            _session.start_updates(_session.update)
        except ui.UIErr:
            _failed("Unable to access the active application's menu.")

    def menu_labels_click(number: int):
        """Select a numbered menu label and follow its submenu."""
        if _session is None or not 1 <= number <= len(_session.targets):
            app.notify("Menu labels", f"No menu label numbered {number}.")
            return
        if _session.names:
            app.notify("Menu labels", "Say 'show menu numbers' to select by number.")
            return
        actions.labels.select(number)

    def menu_labels_move(number: int):
        """Move to a numbered menu label without selecting it."""
        if _session is None or not 1 <= number <= len(_session.targets):
            app.notify("Menu labels", f"No menu label numbered {number}.")
            return
        if _session.names:
            app.notify("Menu labels", "Say 'show menu numbers' to move by number.")
            return
        actions.labels.mouse_move(number)


@menu_ctx.action_class("labels")
class MenuLabelOverrides:
    def select(label: int | str):
        # Keep the native title/number grammar and selection behavior.
        if _session is not None:
            _session.select(label)

    def hide():
        actions.next()
        if _session is not None and not _session.selecting:
            _stop()
