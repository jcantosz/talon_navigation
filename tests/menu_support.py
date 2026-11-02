import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "menus" / "menu_labels.py"


class UIErr(Exception):
    pass


class ActionFailed(Exception):
    pass


class Element:
    def __init__(self, role, title="", children=(), enabled=True):
        self.attrs = {"AXRole": role, "AXTitle": title, "AXEnabled": enabled}
        self.children = list(children)
        self.actions = ["AXPress"]
        self.performed = []

    def get(self, key):
        if key == "AXChildren":
            return self.children
        return self.attrs.get(key)

    def perform(self, action):
        self.performed.append(action)


class Children(list):
    def find_one(self, **query):
        for child in self:
            if child.get("AXRole") == query["AXRole"]:
                return child
        raise UIErr("No menu bar")


class Context:
    def __init__(self):
        self.tags = []

    def action_class(self, namespace):
        return lambda cls: cls


class Module(Context):
    def tag(self, *args, **kwargs):
        pass

    def action_class(self, cls):
        return cls


class MenuLabelsTestCase(unittest.TestCase):
    def setUp(self):
        self.file = Element("AXMenuBarItem", "File")
        self.edit = Element("AXMenuBarItem", "Edit")
        self.bar = Element("AXMenuBar", children=[self.file, self.edit])
        self.window = Element("AXWindow")
        self.application_element = Element("AXApplication")
        self.application_element.attrs["AXFocusedWindow"] = self.window
        self.application = types.SimpleNamespace(
            pid=1, children=Children([self.bar]), element=self.application_element
        )
        self.menu = None
        self.visible = []
        self.style = None
        self.dispatch_stack = []
        self.selected = []
        self.notify = Mock()
        self.mouse_pos = Mock(return_value=(30, 40))
        self.cron = types.SimpleNamespace(
            interval=Mock(return_value=object()), cancel=Mock()
        )
        self.ui = types.SimpleNamespace(
            UIErr=UIErr,
            ActionFailed=ActionFailed,
            active_app=lambda: self.application,
            active_menu=lambda: self.menu,
        )
        self.labels = types.SimpleNamespace(
            show=lambda targets: self.show(targets, "numbers"),
            show_names=lambda targets: self.show(targets, "names"),
            hide=lambda: self.dispatch("hide"),
            select=lambda label: self.dispatch("select", label),
            mouse_move=Mock(),
        )
        talon = types.SimpleNamespace(
            Module=Module,
            Context=Context,
            actions=types.SimpleNamespace(labels=self.labels, next=self.next_action),
            app=types.SimpleNamespace(notify=self.notify),
            cron=self.cron,
            ctrl=types.SimpleNamespace(mouse_pos=self.mouse_pos),
            ui=self.ui,
        )
        root_package = types.ModuleType("talon_navigation_under_test")
        root_package.__path__ = [str(SOURCE.parents[1])]
        package = types.ModuleType("talon_navigation_under_test.menus")
        package.__path__ = [str(SOURCE.parent)]
        spec = importlib.util.spec_from_file_location(
            "talon_navigation_under_test.menus.menu_labels", SOURCE
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(
            sys.modules,
            {
                "talon": talon,
                root_package.__name__: root_package,
                package.__name__: package,
                spec.name: self.module,
            },
        ):
            spec.loader.exec_module(self.module)
            self.menu_session = sys.modules[
                f"{spec.name.rpartition('.')[0]}.menu_session"
            ]
        self.actions = self.module.MenuLabelsActions
        self.module.actions.key = Mock()
        self.module.actions.mouse_move = Mock()

    def prepare_back(self, parent):
        self.menu = self.submenu()
        owner = Element("AXMenuItem", "Owner")
        owner.attrs["AXParent"] = parent
        self.menu.attrs["AXParent"] = owner

    def show(self, targets, style):
        self.visible = list(targets)
        self.style = style

    def native(self, name, *args):
        if name == "select":
            self.selected.append(args[0])
        self.visible = []

    def dispatch(self, name, *args):
        if self.module.ctx.tags:
            self.dispatch_stack.append(name)
            try:
                getattr(self.module.MenuLabelOverrides, name)(*args)
            finally:
                self.dispatch_stack.pop()
        else:
            self.native(name, *args)

    def next_action(self, *args):
        # Talon resolves the next action against the currently active contexts.
        if not self.module.ctx.tags:
            raise IndexError("The override was removed before actions.next()")
        self.native(self.dispatch_stack[-1], *args)

    def submenu(self, title="Open Recent"):
        return Element("AXMenu", children=[Element("AXMenuItem", title)])

    def hoverable_menu(self):
        target = Element("AXMenuItem", "Tools")
        menu = Element("AXMenu", children=[target])
        menu.attrs["AXFrame"] = types.SimpleNamespace(x=0, y=0, width=300, height=300)
        target.attrs.update(
            AXParent=menu,
            AXHasPopup=True,
            AXFrame=types.SimpleNamespace(x=10, y=20, width=80, height=30),
        )
        self.menu = menu
        return menu, target
