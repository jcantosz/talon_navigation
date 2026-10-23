import logging

from talon import Context, Module, actions, app, cron, ui

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

_targets = []
_container = None
_names = True
_app_pid = None
_job = None
_waiting = False
_previous_menu = None
_attempts = 0
_selecting = False
_back_parent = None


def _targets_in(container):
    roles = (
        ("AXMenuItem",)
        if container.get("AXRole") == "AXMenu"
        else ("AXMenuBarItem", "AXMenuExtra")
    )
    return [
        child
        for child in container.children
        if child.get("AXRole") in roles
        and (child.get("AXTitle") or "").strip()
        and child.get("AXEnabled") is not False
    ]


def _stop():
    global _targets, _container, _app_pid, _job, _waiting, _previous_menu
    global _back_parent

    cron.cancel(_job)
    _job = None
    _targets = []
    _container = None
    _app_pid = None
    _waiting = False
    _previous_menu = None
    _back_parent = None
    ctx.tags = []


def _show_container(container, targets):
    global _targets, _container, _waiting, _back_parent

    _targets = targets
    _container = container
    _waiting = False
    _back_parent = None
    if _names:
        actions.labels.show_names(targets)
    else:
        actions.labels.show(targets)
    ctx.tags = ["user.menu_labels_active"]


def _failed(message):
    logging.exception(message)
    actions.labels.hide()
    _stop()
    app.notify("Menu labels", message)


def _update():
    global _attempts

    if _selecting:
        return
    try:
        if ui.active_app().pid != _app_pid:
            actions.labels.hide()
            return

        menu = ui.active_menu()
        if _waiting:
            if _back_parent is not None:
                parent_is_bar = _back_parent.get("AXRole") == "AXMenuBar"
                if menu == _back_parent or (parent_is_bar and menu is None):
                    targets = _targets_in(_back_parent)
                    if targets:
                        _show_container(_back_parent, targets)
                        return
                _attempts -= 1
                if _attempts <= 0:
                    actions.labels.hide()
                    app.notify("Menu labels", "Unable to return to the parent menu.")
                return
            # AXPress returns before macOS publishes the newly opened menu.
            if menu is not None and menu != _previous_menu:
                targets = _targets_in(menu)
                if targets:
                    _show_container(menu, targets)
                    return
            _attempts -= 1
            if _attempts <= 0:
                actions.labels.hide()
                if menu is not None:
                    app.notify("Menu labels", "No new selectable submenu appeared.")
        elif _container.get("AXRole") == "AXMenu" and menu != _container:
            actions.labels.hide()
    except ui.UIErr:
        _failed("Unable to read the active menu.")


def _select(label):
    global _waiting, _previous_menu, _attempts, _selecting

    try:
        if ui.active_app().pid != _app_pid:
            actions.labels.hide()
            app.notify(
                "Menu labels", "The active application changed. Show menu labels again."
            )
            return

        _previous_menu = ui.active_menu()
        _waiting = True
        _attempts = 15
        _selecting = True
        actions.next(label)
    except (ui.UIErr, ui.ActionFailed):
        _failed("Unable to select the menu item.")
    finally:
        _selecting = False


@mod.action_class
class MenuLabelsActions:
    def menu_labels_back():
        """Close one menu level and relabel its parent in the current style."""
        global _back_parent, _waiting, _attempts, _selecting

        try:
            if ui.active_app().pid != _app_pid:
                actions.labels.hide()
                app.notify("Menu labels", "The active application changed.")
                return
            if _waiting:
                app.notify("Menu labels", "Wait for the menu to finish opening.")
                return
            if _container is None or _container.get("AXRole") != "AXMenu":
                app.notify("Menu labels", "Already at the application menu bar.")
                return

            owner = _container.get("AXParent")
            parent = owner.get("AXParent") if owner is not None else None
            if parent is None or parent.get("AXRole") not in ("AXMenu", "AXMenuBar"):
                app.notify("Menu labels", "No accessible parent menu found.")
                return

            _back_parent = parent
            _waiting = True
            _attempts = 15
            _selecting = True
            actions.labels.hide()
            # Escape can dismiss the whole menu chain; Left closes only a submenu.
            actions.key("left" if parent.get("AXRole") == "AXMenu" else "esc")
        except (ui.UIErr, ui.ActionFailed):
            _failed("Unable to return to the parent menu.")
        finally:
            _selecting = False

    def menu_labels_show(names: bool = True):
        """Label the active application's menu by title, or by number if names is false."""
        global _names, _app_pid, _job

        actions.labels.hide()
        _stop()
        _names = names
        try:
            active_app = ui.active_app()
            menu = ui.active_menu()
            if menu is None:
                menu = active_app.children.find_one(AXRole="AXMenuBar", max_depth=0)
            targets = _targets_in(menu)
            if not targets:
                app.notify("Menu labels", "No selectable application menu items found.")
                return

            _app_pid = active_app.pid
            _show_container(menu, targets)
            _job = cron.interval("100ms", _update)
        except ui.UIErr:
            _failed("Unable to access the active application's menu.")

    def menu_labels_click(number: int):
        """Select a numbered menu label and follow its submenu."""
        if not 1 <= number <= len(_targets):
            app.notify("Menu labels", f"No menu label numbered {number}.")
            return
        if _names:
            app.notify("Menu labels", "Say 'show menu numbers' to select by number.")
            return
        actions.labels.select(number)

    def menu_labels_move(number: int):
        """Move to a numbered menu label without selecting it."""
        if not 1 <= number <= len(_targets):
            app.notify("Menu labels", f"No menu label numbered {number}.")
            return
        if _names:
            app.notify("Menu labels", "Say 'show menu numbers' to move by number.")
            return
        actions.labels.mouse_move(number)


@menu_ctx.action_class("labels")
class MenuLabelOverrides:
    def select(label: int | str):
        # Keep the native title/number grammar and selection behavior.
        _select(label)

    def hide():
        actions.next()
        if not _selecting:
            _stop()
