"""Shared Talon doubles and setup for accessibility runtime tests."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_TAG = "user.application_labels_active"
SESSION_TAG = "user.application_labels_session"


class UIErr(Exception):
    pass


class ActionFailed(Exception):
    pass


class Span:
    def __init__(self, left, right):
        self.left = left
        self.right = right


def frame(x=10, y=20, width=80, height=30):
    return types.SimpleNamespace(x=x, y=y, width=width, height=height)


class Element:
    def __init__(self, **attrs):
        self.attrs = attrs
        self.actions = ["AXPress"]
        self.dead = False
        self.performed = []

    def get(self, key):
        if self.dead:
            raise UIErr("element is gone")
        return self.attrs.get(key)

    def perform(self, action):
        if self.dead:
            raise UIErr("element is gone")
        self.performed.append(action)

    def __setitem__(self, key, value):
        if self.dead:
            raise UIErr("element is gone")
        self.attrs[key] = value


class FakeTalon:
    """Minimal Talon double that resolves context tags like Talon does."""

    def __init__(self):
        self.contexts = []
        self.notify = Mock()
        self.native_calls = []
        self.hide_after_select = False
        self.overrides = {}
        self.dispatching = []
        self.declared_tags = []
        self.declared_settings = {}
        self.cron = types.SimpleNamespace(
            after=Mock(side_effect=lambda *_: object()),
            interval=Mock(side_effect=lambda *_: object()),
            cancel=Mock(),
        )
        self.settings = {
            "user.accessibility_query_max_depth": 0,
            "user.accessibility_query_timeout": 1.0,
            "user.accessibility_defer_web_areas": False,
            "user.accessibility_clip_to_surface": False,
            "user.accessibility_activation_disallowed_bundles": "",
        }
        self.query_results = []
        self.mouse_pos = Mock(return_value=(30, 40))
        self.active_app = None
        self.active_window = types.SimpleNamespace(id=1)
        self.active_menu = None
        self.user = types.SimpleNamespace()
        fake = self

        class Context:
            def __init__(self):
                self.matches = ""
                self.tags = []
                fake.contexts.append(self)

            def action_class(self, namespace):
                def register(cls):
                    fake.overrides[(id(self), namespace)] = cls
                    return cls

                return register

        class Module:
            def tag(self, name, **kwargs):
                fake.declared_tags.append(name)

            def setting(self, name, **kwargs):
                fake.declared_settings[name] = kwargs

            def action_class(self, cls):
                return cls

        self.Context = Context
        self.Module = Module

    def active_tags(self):
        tags = set()
        while True:
            updated = set(tags)
            for context in self.contexts:
                if self.requirements(context) <= tags:
                    updated.update(context.tags)
            if updated == tags:
                return tags
            tags = updated

    def requirements(self, context):
        return {
            line.split(":", 1)[1].strip()
            for line in context.matches.splitlines()
            if line.strip().startswith("tag:")
        }

    def dispatch_labels(self, name, *args):
        tags = self.active_tags()
        for (context_id, namespace), cls in self.overrides.items():
            context = next(c for c in self.contexts if id(c) == context_id)
            if namespace == "labels" and self.requirements(context) <= tags:
                self.dispatching.append((name, args))
                try:
                    return getattr(cls, name)(*args)
                finally:
                    self.dispatching.pop()
        return self.native(name, *args)

    def native(self, name, *args):
        self.native_calls.append((name, args))
        if name == "select" and self.hide_after_select:
            self.dispatch_labels("hide")

    def next_action(self, *args):
        name, _ = self.dispatching[-1]
        return self.native(name, *args)

    def modules(self):
        labels = types.SimpleNamespace(
            show=lambda targets: self.native("show", list(targets)),
            show_names=lambda targets: self.native("show_names", list(targets)),
            hide=lambda: self.dispatch_labels("hide"),
            select=lambda label: self.dispatch_labels("select", label),
        )
        ui = types.SimpleNamespace(
            UIErr=UIErr,
            ActionFailed=ActionFailed,
            active_app=lambda: self.active_app,
            active_window=lambda: self.active_window,
            active_menu=lambda: self.active_menu,
            element_at=Mock(),
            register=Mock(),
        )
        talon = types.SimpleNamespace(
            Module=self.Module,
            Context=self.Context,
            actions=types.SimpleNamespace(
                labels=labels,
                next=self.next_action,
                key=Mock(),
                mouse_move=Mock(),
                sleep=Mock(),
                user=self.user,
            ),
            app=types.SimpleNamespace(notify=self.notify),
            axquery=types.SimpleNamespace(
                query_all=lambda *args, **kwargs: list(self.query_results)
            ),
            cron=self.cron,
            ctrl=types.SimpleNamespace(mouse_pos=self.mouse_pos),
            imgui=types.SimpleNamespace(
                GUI=object,
                open=lambda: (
                    lambda function: types.SimpleNamespace(show=Mock(), hide=Mock())
                ),
            ),
            settings=types.SimpleNamespace(get=lambda name: self.settings[name]),
            ui=ui,
        )
        return talon, types.SimpleNamespace(Span=Span)


def load(fake, relative, module=None):
    source = ROOT / relative
    talon, talon_types = fake.modules()
    root = types.ModuleType("talon_navigation_runtime")
    root.__path__ = [str(ROOT)]
    package = types.ModuleType(f"{root.__name__}.{source.parent.name}")
    package.__path__ = [str(source.parent)]
    name = f"{package.__name__}.{source.stem}"
    spec = importlib.util.spec_from_file_location(name, source)
    module = module or importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "talon": talon,
            "talon.types": talon_types,
            root.__name__: root,
            package.__name__: package,
            name: module,
        },
    ):
        spec.loader.exec_module(module)
    return module


class ApplicationTestCase(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.window = Element(AXRole="AXWindow")
        self.application = Element(
            AXRole="AXApplication",
            AXFocusedWindow=self.window,
            AXEnhancedUserInterface=True,
            AXManualAccessibility=True,
        )
        self.talon.active_app = types.SimpleNamespace(
            pid=1,
            name="Example",
            bundle="com.example",
            created_at=0,
            element=self.application,
        )
        self.button = Element(AXRole="AXButton", AXTitle="OK", AXFrame=frame())
        self.popup = Element(
            AXRole="AXPopUpButton", AXTitle="Choose", AXFrame=frame(x=100)
        )
        self.talon.query_results = [self.button, self.popup]
        self.module = load(self.talon, "application_controls/inventory.py")
        self.session_module = self.module.application_session
        self.collection = self.session_module.controls
        self.actions = self.module.Actions

    def assert_session_active(self, active):
        self.assertEqual(ACTIVE_TAG in self.talon.active_tags(), active)

    def text_row(self, text_frame):
        text = Element(AXRole="AXStaticText", AXValue="games", AXFrame=text_frame)
        text.actions = ["AXShowMenu"]
        cell = Element(AXRole="AXGroup", AXChildren=[text], AXFrame=frame(width=380))
        cell.actions = []
        row = Element(AXRole="AXRow", AXChildren=[cell], AXFrame=frame(x=0, width=400))
        return row, text


class ApplicationMenuTestCase(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.window = Element(
            AXRole="AXWindow", AXFrame=frame(x=0, y=0, width=500, height=500)
        )
        self.application = Element(
            AXRole="AXApplication",
            AXFocusedWindow=self.window,
            AXEnhancedUserInterface=True,
            AXManualAccessibility=True,
        )
        self.talon.active_app = types.SimpleNamespace(
            pid=1,
            name="Example",
            bundle="com.example",
            created_at=0,
            element=self.application,
        )
        self.button = Element(AXRole="AXButton", AXTitle="Window", AXFrame=frame())
        self.item = Element(AXRole="AXMenuItem", AXTitle="Menu", AXFrame=frame())
        self.menu = Element(
            AXRole="AXMenu", AXFrame=frame(x=0, y=0, width=300, height=300)
        )
        self.menu.actions = ["AXCancel"]
        self.results = {id(self.window): [self.button], id(self.menu): [self.item]}
        self.module = load(self.talon, "application_controls/inventory.py")
        self.session_module = self.module.application_session
        self.collection = self.session_module.controls
        self.actions = self.module.Actions
        self.query = Mock(
            side_effect=lambda *args, root, **kwargs: self.results[id(root)]
        )
        self.collection.axquery.query_all = self.query

    def start(self, menu=None):
        self.talon.active_menu = menu
        self.actions.accessibility_show_application_numbers()
        return self.module._session

    def finish_refresh(self):
        self.talon.cron.after.call_args.args[1]()

    def nested_menu(self):
        owner = Element(AXRole="AXMenuItem", AXParent=self.menu)
        submenu = Element(
            AXRole="AXMenu",
            AXParent=owner,
            AXFrame=frame(x=300, y=0, width=150, height=200),
        )
        item = Element(AXRole="AXMenuItem", AXTitle="Submenu", AXFrame=frame())
        self.results[id(submenu)] = [item]
        return submenu, item
