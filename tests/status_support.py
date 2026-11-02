import importlib.util
import sys
import types
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "status" / "status_labels.py"


class UIErr(Exception):
    pass


class ActionFailed(Exception):
    pass


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float


class Element:
    def __init__(self, role, title=None, frame=None, children=(), actions=(), **attrs):
        self.attrs = {
            "AXRole": role,
            "AXTitle": title,
            "AXFrame": frame,
            "AXChildren": list(children),
            **attrs,
        }
        self.actions = dict.fromkeys(actions, "")
        self.perform = Mock()
        for child in children:
            child.attrs["AXParent"] = self

    def get(self, key):
        if key == "AXWindows":
            return [
                child
                for child in self.attrs["AXChildren"]
                if child.get("AXRole") == "AXWindow"
            ]
        if key == "AXExtrasMenuBar":
            return next(
                (
                    child
                    for child in self.attrs["AXChildren"]
                    if child.get("AXRole") == "AXMenuBar"
                ),
                None,
            )
        return self.attrs.get(key)


class Owner:
    def __init__(self, pid=2, name="Control Center", bundle="com.apple.controlcenter"):
        self.pid = pid
        self.name = name
        self.bundle = bundle
        self.element = Element("AXApplication")


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


class StatusLabelsTestCase(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.front = Owner(1, "Editor", "editor")
        self.front_bar = Element(
            "AXMenuBar", frame=Rect(0, 0, 1000, 24), AXParent=self.front.element
        )
        self.front.element.attrs["AXMenuBar"] = self.front_bar
        self.icon = Element(
            "AXMenuBarItem",
            frame=Rect(700, 0, 25, 24),
            actions=("AXPress",),
            AXSubrole="AXMenuExtra",
            AXDescription="Control Center",
            AXIdentifier="com.apple.menuextra.controlcenter",
        )
        self.bar = Element("AXMenuBar", children=[self.icon])
        self.bar.attrs["AXParent"] = self.owner.element
        self.owner.element.attrs["AXChildren"] = [self.bar]
        self.menu = None
        self.apps = [self.owner]
        self.visible = []
        self.names = None
        self.stack = []
        self.native_selections = []
        self.on_show = None
        self.mouse_target = None
        self.ui = types.SimpleNamespace(
            Element=Element,
            App=Owner,
            Rect=Rect,
            UIErr=UIErr,
            ActionFailed=ActionFailed,
            active_app=lambda: self.front,
            active_menu=lambda: self.menu,
            element_at=self.element_at,
            apps=lambda: self.apps,
            screens=lambda: [types.SimpleNamespace(rect=Rect(0, 0, 1000, 700))],
        )
        self.cron = types.SimpleNamespace(
            interval=Mock(return_value=object()), cancel=Mock()
        )
        self.notify = Mock()
        self.labels = types.SimpleNamespace(
            show=lambda elements: self.show(elements, False),
            show_names=lambda elements: self.show(elements, True),
            hide=lambda: self.dispatch("hide"),
            select=lambda label: self.dispatch("select", label),
            rect=self.label_rect,
            mouse_move=lambda label: setattr(self, "mouse_target", self.resolve(label)),
        )
        self.actions = types.SimpleNamespace(
            labels=self.labels,
            next=self.next_action,
            key=Mock(),
            mouse_click=lambda: self.mouse_target.perform("AXPress"),
        )
        talon = types.SimpleNamespace(
            Module=Module,
            Context=Context,
            actions=self.actions,
            app=types.SimpleNamespace(notify=self.notify),
            cron=self.cron,
            ui=self.ui,
        )
        root_package = types.ModuleType("talon_navigation_under_test")
        root_package.__path__ = [str(SOURCE.parents[1])]
        package = types.ModuleType("talon_navigation_under_test.status")
        package.__path__ = [str(SOURCE.parent)]
        spec = importlib.util.spec_from_file_location(
            "talon_navigation_under_test.status.status_labels", SOURCE
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
        self.commands = self.module.StatusLabelsActions

    def element_at(self, x, y):
        def hit(element):
            if element.get("AXHidden"):
                return None
            for child in element.get("AXChildren") or ():
                found = hit(child)
                if found is not None:
                    return found
            frame = element.get("AXFrame")
            if (
                frame is not None
                and frame.x <= x < frame.x + frame.width
                and frame.y <= y < frame.y + frame.height
            ):
                return element
            return None

        roots = [self.menu] if self.menu is not None else []
        for owner in self.apps:
            roots.extend(
                root
                for root in owner.element.attrs["AXChildren"]
                if root.get("AXRole") == "AXWindow"
            )
            for bar in owner.element.attrs["AXChildren"]:
                if bar.get("AXRole") == "AXMenuBar":
                    roots.extend(
                        root
                        for element in bar.get("AXChildren")
                        for root in element.get("AXChildren") or ()
                        if root.get("AXRole") == "AXMenu"
                        and self.module.surfaces.visible_frame(root) is not None
                    )
        for root in roots:
            found = hit(root)
            if found is not None:
                return found
        for owner in self.apps:
            for bar in owner.element.attrs["AXChildren"]:
                if bar.get("AXRole") != "AXMenuBar":
                    continue
                bar.attrs["AXParent"] = owner.element
                if bar.get("AXFrame") is None:
                    bar.attrs["AXFrame"] = self.front_bar.get("AXFrame")
                for element in bar.get("AXChildren"):
                    element.attrs["AXParent"] = bar
                    frame = element.get("AXFrame")
                    if (
                        frame is not None
                        and not element.get("AXHidden")
                        and frame.x <= x < frame.x + frame.width
                        and frame.y <= y < frame.y + frame.height
                    ):
                        return element
        if self.front_bar.get("AXFrame").x <= x < 1000 and 0 <= y < 24:
            return self.front_bar
        return self.front.element

    def show(self, elements, names):
        self.visible = list(elements)
        self.names = names
        if self.on_show is not None:
            self.on_show()

    def resolve(self, label):
        if isinstance(label, int):
            return self.visible[label - 1]
        return next(
            element
            for element in self.visible
            if label in (element.get("AXTitle"), element.get("AXDescription"))
        )

    def label_rect(self, label):
        element = self.resolve(label)
        frame = element.get("AXFrame")
        if element.get("AXRole") == "AXSlider":
            return Rect(frame.x + 1, frame.y + 1, frame.width - 2, frame.height - 2)
        return frame

    def dispatch(self, name, *args):
        if self.module.ctx.tags:
            self.stack.append(name)
            try:
                getattr(self.module.StatusLabelOverrides, name)(*args)
            finally:
                self.stack.pop()
        else:
            self.native(name, *args)

    def native(self, name, *args):
        if name == "select":
            target = self.resolve(args[0])
            self.native_selections.append(target)
            target.perform("AXPress")
            self.labels.hide()
        else:
            self.visible = []

    def next_action(self, *args):
        self.assertTrue(self.module.ctx.tags)
        self.native(self.stack[-1], *args)

    def button(self, title="Sound", role="AXButton", **attrs):
        return Element(
            role, title, Rect(700, 60, 80, 30), actions=("AXPress",), **attrs
        )

    def panel(self, *controls):
        return Element(
            "AXWindow",
            "Control Center",
            Rect(600, 30, 400, 400),
            children=[Element("AXGroup", children=controls)],
            AXSubrole="AXSystemDialog",
        )

    def add_window_group_icon(self):
        icon = Element(
            "AXMenuBarItem",
            frame=Rect(750, 0, 25, 24),
            actions=("AXPress",),
            AXSubrole="AXMenuExtra",
            AXDescription="Clock",
            AXIdentifier="com.apple.menuextra.clock",
        )
        group = Element("AXGroup", children=[icon])
        window = Element(
            "AXWindow",
            frame=Rect(750, 0, 25, 24),
            children=[group],
            AXParent=self.owner.element,
        )
        self.owner.element.attrs["AXChildren"].append(window)
        return icon, group

    def open_panel(self, names=False, controls=None):
        panel = self.panel(*(controls or [self.button()]))

        def toggle(action):
            roots = self.owner.element.attrs["AXChildren"]
            if panel in roots:
                roots.remove(panel)
            else:
                roots.append(panel)

        self.icon.perform.side_effect = toggle
        self.commands.status_labels_show(names)
        self.labels.select("Control Center" if names else 1)
        session = self.module._session
        self.tick(session, 3)
        self.assertIs(session.surface.root, panel)
        return session, panel

    def tick(self, session, count=1):
        for _ in range(count):
            session.update()
