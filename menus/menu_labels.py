import logging

from talon import Context, Module, actions, app, ui

from ..lib.labels import LabelSession

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


class MenuSession(LabelSession):
    def __init__(self, names, app_pid):
        super().__init__(ctx, "user.menu_labels_active", names)
        self.app_pid = app_pid
        self.targets = []
        self.container = None
        self.waiting = False
        self.previous_menu = None
        self.attempts = 0
        self.selecting = False
        self.back_parent = None

    def show_container(self, container, targets):
        self.targets = targets
        self.container = container
        self.waiting = False
        self.back_parent = None
        self.render(targets)

    def stop(self):
        super().stop()
        self.targets = []
        self.container = None
        self.waiting = False
        self.previous_menu = None
        self.back_parent = None

    def update(self):
        if self.selecting or self.stopped:
            return
        try:
            if ui.active_app().pid != self.app_pid:
                actions.labels.hide()
                return

            menu = ui.active_menu()
            if self.waiting:
                if self.back_parent is not None:
                    parent_is_bar = self.back_parent.get("AXRole") == "AXMenuBar"
                    if menu == self.back_parent or (parent_is_bar and menu is None):
                        targets = _targets_in(self.back_parent)
                        if targets:
                            self.show_container(self.back_parent, targets)
                            return
                    self.attempts -= 1
                    if self.attempts <= 0:
                        actions.labels.hide()
                        app.notify(
                            "Menu labels", "Unable to return to the parent menu."
                        )
                    return
                # AXPress returns before macOS publishes the newly opened menu.
                if menu is not None and menu != self.previous_menu:
                    targets = _targets_in(menu)
                    if targets:
                        self.show_container(menu, targets)
                        return
                self.attempts -= 1
                if self.attempts <= 0:
                    actions.labels.hide()
                    if menu is not None:
                        app.notify("Menu labels", "No new selectable submenu appeared.")
            elif self.container.get("AXRole") == "AXMenu" and menu != self.container:
                actions.labels.hide()
        except ui.UIErr:
            _failed("Unable to read the active menu.")

    def select(self, label):
        try:
            if ui.active_app().pid != self.app_pid:
                actions.labels.hide()
                app.notify(
                    "Menu labels",
                    "The active application changed. Show menu labels again.",
                )
                return

            self.previous_menu = ui.active_menu()
            self.waiting = True
            self.attempts = 15
            self.selecting = True
            actions.next(label)
        except (ui.UIErr, ui.ActionFailed):
            _failed("Unable to select the menu item.")
        finally:
            self.selecting = False

    def back(self):
        try:
            if ui.active_app().pid != self.app_pid:
                actions.labels.hide()
                app.notify("Menu labels", "The active application changed.")
                return
            if self.waiting:
                app.notify("Menu labels", "Wait for the menu to finish opening.")
                return
            if self.container is None or self.container.get("AXRole") != "AXMenu":
                app.notify("Menu labels", "Already at the application menu bar.")
                return

            owner = self.container.get("AXParent")
            parent = owner.get("AXParent") if owner is not None else None
            if parent is None or parent.get("AXRole") not in ("AXMenu", "AXMenuBar"):
                app.notify("Menu labels", "No accessible parent menu found.")
                return

            self.back_parent = parent
            self.waiting = True
            self.attempts = 15
            self.selecting = True
            actions.labels.hide()
            # Escape can dismiss the whole menu chain; Left closes only a submenu.
            actions.key("left" if parent.get("AXRole") == "AXMenu" else "esc")
        except (ui.UIErr, ui.ActionFailed):
            _failed("Unable to return to the parent menu.")
        finally:
            self.selecting = False


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

            _session = MenuSession(names, active_app.pid)
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
