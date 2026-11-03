"""Menu targets and the application menu navigation state machine."""

from talon import actions, app, ctrl, ui

from ..lib.labels import (
    MENU_BACK_FALLBACK_TICKS,
    MENU_HOVER_DELAY_TICKS,
    MENU_WAIT_TICKS,
    LabelSession,
    label_element,
    menu_opener,
    menu_parent,
)


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
    def __init__(self, names, app_pid, context, failed):
        super().__init__(context, "user.menu_labels_active", names)
        self._failed = failed
        self.app_pid = app_pid
        self.targets = []
        self.labelled = []
        self.container = None
        self.waiting = False
        self.previous_menu = None
        self.attempts = 0
        self.selecting = False
        self.back_parent = None
        self.hover_target = None
        self.hover_position = None
        self.hover_window = None
        self.back_window = None
        self.back_fallback = False

    def show_container(self, container, targets):
        self.targets = targets
        in_menu = not self.names and container.get("AXRole") == "AXMenu"
        self.labelled = [
            label_element(target, in_menu=True) if in_menu else target
            for target in targets
        ]
        self.container = container
        self.waiting = False
        self.back_parent = None
        self.hover_target = None
        self.hover_position = None
        self.hover_window = None
        self.back_window = None
        self.back_fallback = False
        self.render(self.labelled)

    def stop(self):
        super().stop()
        self.targets = []
        self.labelled = []
        self.container = None
        self.waiting = False
        self.previous_menu = None
        self.back_parent = None
        self.hover_target = None
        self.hover_position = None
        self.hover_window = None
        self.back_window = None
        self.back_fallback = False

    def transition_focus_valid(self, window):
        active = ui.active_app()
        if self.stopped:
            return False
        if active is None or active.pid != self.app_pid:
            actions.labels.hide()
            return False
        focused_window = active.element.get("AXFocusedWindow")
        if self.stopped:
            return False
        if focused_window != window:
            actions.labels.hide()
            app.notify(
                "Menu labels", "The focused window changed. Show menu labels again."
            )
            return False
        return True

    def hover_submenu(self):
        target = self.hover_target
        position = self.hover_position
        window = self.hover_window
        self.hover_target = None
        self.hover_position = None
        self.hover_window = None
        try:
            self.hover_submenu_if_current(
                target,
                self.previous_menu,
                position,
                lambda: self.transition_focus_valid(window),
            )
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if not self.stopped:
                self._failed("Unable to open the selected submenu.")

    def fallback_back(self):
        try:
            if (
                self.back_window is None
                or not self.transition_focus_valid(self.back_window)
                or ui.active_menu() != self.container
                or self.stopped
            ):
                return
            self.back_fallback = True
            self.attempts = MENU_WAIT_TICKS
            self.selecting = True
            try:
                actions.key("esc")
            finally:
                self.selecting = False
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if not self.stopped:
                self._failed("Unable to return to the parent menu.")

    def update(self):
        if self.selecting or self.stopped:
            return
        try:
            active = ui.active_app()
            if self.stopped:
                return
            if active is None or active.pid != self.app_pid:
                actions.labels.hide()
                return

            menu = ui.active_menu()
            if self.stopped:
                return
            if self.waiting:
                if self.back_parent is not None:
                    parent_is_bar = self.back_parent.get("AXRole") == "AXMenuBar"
                    if self.stopped:
                        return
                    if menu == self.back_parent or (parent_is_bar and menu is None):
                        targets = _targets_in(self.back_parent)
                        if self.stopped:
                            return
                        if targets:
                            self.show_container(self.back_parent, targets)
                            return
                    if self.back_fallback and menu is None:
                        bar = ui.active_app().children.find_one(
                            AXRole="AXMenuBar", max_depth=0
                        )
                        targets = _targets_in(bar)
                        if self.stopped:
                            return
                        if not targets:
                            actions.labels.hide()
                            app.notify(
                                "Menu labels",
                                "No selectable application menu items found.",
                            )
                            return
                        self.show_container(bar, targets)
                        app.notify(
                            "Menu labels",
                            "The parent menu did not respond; showing the "
                            "application menu bar instead.",
                        )
                        return
                    self.attempts -= 1
                    if (
                        not self.back_fallback
                        and not parent_is_bar
                        and menu == self.container
                        and self.attempts <= MENU_WAIT_TICKS - MENU_BACK_FALLBACK_TICKS
                    ):
                        self.fallback_back()
                        if self.stopped:
                            return
                    if self.attempts <= 0:
                        actions.labels.hide()
                        app.notify(
                            "Menu labels", "Unable to return to the parent menu."
                        )
                    return
                # AXPress returns before macOS publishes the newly opened menu.
                if menu is not None and menu != self.previous_menu:
                    targets = _targets_in(menu)
                    if self.stopped:
                        return
                    if targets:
                        self.show_container(menu, targets)
                        return
                self.attempts -= 1
                if (
                    self.hover_target is not None
                    and menu == self.previous_menu
                    and self.attempts <= MENU_WAIT_TICKS - MENU_HOVER_DELAY_TICKS
                ):
                    self.hover_submenu()
                    if self.stopped:
                        return
                if self.attempts <= 0:
                    actions.labels.hide()
                    if menu is not None:
                        app.notify("Menu labels", "No new selectable submenu appeared.")
            elif self.container.get("AXRole") == "AXMenu" and menu != self.container:
                actions.labels.hide()
        except ui.UIErr:
            if not self.stopped:
                self._failed("Unable to read the active menu.")

    def select(self, label):
        try:
            active = ui.active_app()
            if self.stopped:
                return
            if active is None or active.pid != self.app_pid:
                actions.labels.hide()
                app.notify(
                    "Menu labels",
                    "The active application changed. Show menu labels again.",
                )
                return

            if self.waiting:
                app.notify("Menu labels", "Wait for the menu to finish opening.")
                return
            self.previous_menu = ui.active_menu()
            if self.stopped:
                return
            expected = (
                self.container if self.container.get("AXRole") == "AXMenu" else None
            )
            if self.stopped:
                return
            if self.previous_menu != expected:
                actions.labels.hide()
                app.notify("Menu labels", "The active menu changed. Show labels again.")
                return
            target = None
            window = None
            candidate = None
            if self.previous_menu is not None and self.previous_menu == self.container:
                if (
                    not self.names
                    and isinstance(label, int)
                    and 1 <= label <= len(self.targets)
                ):
                    candidate = self.targets[label - 1]
                elif self.names and isinstance(label, str):
                    matches = [
                        item
                        for item in self.targets
                        if (item.get("AXTitle") or "").casefold() == label.casefold()
                    ]
                    if len(matches) == 1:
                        candidate = matches[0]
                if candidate is not None and (
                    candidate.get("AXRole") == "AXMenuItem"
                    and candidate.get("AXHasPopup") is True
                ):
                    window = active.element.get("AXFocusedWindow")
                    if window is not None:
                        target = candidate
            if self.stopped:
                return
            self.waiting = True
            self.attempts = MENU_WAIT_TICKS
            self.selecting = True
            if (
                not self.names
                and isinstance(label, int)
                and 1 <= label <= len(self.targets)
                and self.labelled[label - 1] is not self.targets[label - 1]
            ):
                menu = ui.active_menu()
                if self.stopped:
                    return
                if menu != self.previous_menu:
                    self.selecting = False
                    actions.labels.hide()
                    app.notify(
                        "Menu labels", "The active menu changed. Show labels again."
                    )
                    return
                active = ui.active_app()
                if self.stopped:
                    return
                if active is None or active.pid != self.app_pid:
                    self.selecting = False
                    actions.labels.hide()
                    app.notify(
                        "Menu labels",
                        "The active application changed. Show labels again.",
                    )
                    return
                self.targets[label - 1].perform("AXPress")
                if not self.stopped:
                    actions.labels.hide()
            else:
                actions.next(label)
            if not self.stopped and target is not None:
                self.hover_position = ctrl.mouse_pos()
                self.hover_window = window
                self.hover_target = target
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if not self.stopped:
                self._failed("Unable to select the menu item.")
        finally:
            self.selecting = False

    def back(self):
        try:
            active = ui.active_app()
            if self.stopped:
                return
            if active is None or active.pid != self.app_pid:
                actions.labels.hide()
                app.notify("Menu labels", "The active application changed.")
                return
            if self.waiting:
                app.notify("Menu labels", "Wait for the menu to finish opening.")
                return
            container = self.container
            role = container.get("AXRole") if container is not None else None
            if self.stopped:
                return
            if role != "AXMenu":
                app.notify("Menu labels", "Already at the application menu bar.")
                return

            menu = ui.active_menu()
            if self.stopped:
                return
            if menu != self.container:
                actions.labels.hide()
                app.notify("Menu labels", "The active menu changed. Show labels again.")
                return
            parent = menu_parent(self.container)
            if self.stopped:
                return
            if parent is None or parent.get("AXRole") not in ("AXMenu", "AXMenuBar"):
                app.notify("Menu labels", "No accessible parent menu found.")
                return

            self.back_parent = parent
            self.back_window = (
                active.element.get("AXFocusedWindow")
                if parent.get("AXRole") == "AXMenu"
                else None
            )
            if self.stopped:
                return
            self.back_fallback = False
            self.waiting = True
            self.attempts = MENU_WAIT_TICKS
            self.selecting = True
            actions.labels.hide()
            if self.stopped:
                return
            opener = menu_opener(parent) if parent.get("AXRole") == "AXMenu" else None
            if self.stopped:
                return
            current_menu = ui.active_menu()
            if self.stopped:
                return
            if current_menu != menu:
                self.selecting = False
                actions.labels.hide()
                app.notify("Menu labels", "The active menu changed. Show labels again.")
                return
            active = ui.active_app()
            if self.stopped:
                return
            if active is None or active.pid != self.app_pid:
                self.selecting = False
                actions.labels.hide()
                app.notify("Menu labels", "The active application changed.")
                return
            if opener is not None:
                opener.perform("AXPress")
            else:
                actions.key("left" if parent.get("AXRole") == "AXMenu" else "esc")
        except (AttributeError, RuntimeError, ui.UIErr, ui.ActionFailed):
            if not self.stopped:
                self._failed("Unable to return to the parent menu.")
        finally:
            self.selecting = False
