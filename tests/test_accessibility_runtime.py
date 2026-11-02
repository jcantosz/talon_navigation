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
            def tag(self, *args, **kwargs):
                pass

            def setting(self, *args, **kwargs):
                pass

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


class ApplicationLabelTests(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.window = Element(AXRole="AXWindow")
        self.application = Element(AXRole="AXApplication", AXFocusedWindow=self.window)
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
        self.module = load(self.talon, "accessibility/inventory.py")
        self.actions = self.module.Actions

    def assert_session_active(self, active):
        self.assertEqual(ACTIVE_TAG in self.talon.active_tags(), active)

    def test_application_numbers_stop_an_existing_label_session(self):
        for tag in ("user.menu_labels_active", "user.status_labels_active"):
            with self.subTest(tag=tag):
                self.talon.dispatch_labels("hide")
                publisher = self.talon.Context()
                publisher.tags = [tag]
                context = self.talon.Context()
                context.matches = f"tag: {tag}"
                stopped = Mock()

                def hide_foreign():
                    self.talon.next_action()
                    publisher.tags = []
                    stopped()

                self.talon.overrides[(id(context), "labels")] = type(
                    "ForeignLabels", (), {"hide": staticmethod(hide_foreign)}
                )

                self.actions.accessibility_show_application_numbers()

                stopped.assert_called_once()
                self.assertNotIn(tag, self.talon.active_tags())
                self.assert_session_active(True)

    def test_stopped_session_cannot_clear_replacement_session_tag(self):
        self.actions.accessibility_show_application_numbers()
        previous = self.module._session
        self.actions.accessibility_show_application_numbers()
        replacement = self.module._session

        previous.stop()

        self.assertTrue(previous.stopped)
        self.assertIs(self.module._session, replacement)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_stopped_render_does_not_hide_a_replacement_session(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        native_show = self.module.actions.labels.show
        switched = False

        def show_then_replace(targets):
            nonlocal switched
            native_show(targets)
            if not switched:
                switched = True
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()

        with patch.object(
            self.module.actions.labels, "show", side_effect=show_then_replace
        ):
            session.refresh(force=True)

        self.assertTrue(session.stopped)
        self.assertIsNotNone(self.module._session)
        self.assertIsNot(self.module._session, session)
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_stopped_render_hides_its_own_orphaned_labels(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        native_show = self.module.actions.labels.show

        def show_then_stop(targets):
            native_show(targets)
            self.module._stop()

        with patch.object(
            self.module.actions.labels, "show", side_effect=show_then_stop
        ):
            session.refresh(force=True)

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.talon.native_calls[-1], ("hide", ()))

    def test_replaced_session_does_not_select_new_session_label(self):
        self.actions.accessibility_show_application_numbers()
        previous = self.module._session

        def replace_session(target):
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            return target

        with patch.object(
            self.module, "_row_activation_target", side_effect=replace_session
        ):
            self.talon.dispatch_labels("select", 1)

        self.assertTrue(previous.stopped)
        self.assertIsNot(self.module._session, previous)
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_row_activation_does_not_hide_a_replacement_session(self):
        row, _ = self.text_row(frame(x=40, y=25, width=60, height=18))
        self.talon.query_results = [row]
        self.actions.accessibility_show_application_numbers()
        previous = self.module._session

        def replace_session(action):
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            self.talon.native_calls.clear()

        with patch.object(row, "perform", side_effect=replace_session):
            self.talon.dispatch_labels("select", 1)

        self.assertTrue(previous.stopped)
        self.assertIsNot(self.module._session, previous)
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_application_query_uses_configured_depth(self):
        for configured, expected in ((0, -1), (13, 13), (40, 40)):
            with self.subTest(depth=configured):
                self.talon.settings["user.accessibility_query_max_depth"] = configured
                query = Mock(return_value=[self.button])
                with patch.object(self.module.axquery, "query_all", query):
                    self.actions.accessibility_show_application_numbers()
                query.assert_called_once_with(
                    self.module.QUERY,
                    root=self.window,
                    visible_only=True,
                    max_depth=expected,
                    timeout=1,
                )
                self.assertEqual(self.module._session.targets, [self.button])

    def test_application_query_uses_configured_timeout(self):
        self.talon.settings["user.accessibility_query_timeout"] = 3.0
        query = Mock(return_value=[self.button])
        with patch.object(self.module.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()
        self.assertEqual(query.call_args.kwargs["timeout"], 3.0)
        self.assertEqual(self.module._session.targets, [self.button])

    def test_invalid_query_budgets_are_rejected_before_querying(self):
        cases = [
            ("user.accessibility_query_max_depth", -1),
            *(
                ("user.accessibility_query_timeout", value)
                for value in (0, -1, float("nan"), float("inf"))
            ),
        ]
        for setting, value in cases:
            with self.subTest(setting=setting, value=value):
                original = self.talon.settings[setting]
                self.talon.settings[setting] = value
                query = Mock()
                try:
                    with patch.object(self.module.axquery, "query_all", query):
                        with self.assertRaises(RuntimeError):
                            self.module._controls(self.talon.active_app)
                    query.assert_not_called()
                finally:
                    self.talon.settings[setting] = original

    def test_unusable_frames_are_not_numbered(self):
        for invalid_frame in (
            None,
            frame(width=0),
            frame(height=0),
            frame(width=-1),
            frame(height=-1),
            frame(x=float("nan")),
            frame(y=float("inf")),
            frame(width=float("inf")),
            frame(height=float("nan")),
        ):
            with self.subTest(frame=invalid_frame):
                invalid = Element(AXRole="AXButton", AXFrame=invalid_frame)
                self.talon.query_results = [invalid, self.button, self.popup]

                self.actions.accessibility_show_application_numbers()

                self.assertEqual(
                    self.module._session.targets, [self.button, self.popup]
                )
                self.assertEqual(
                    self.talon.native_calls[-1],
                    ("show", ([self.button, self.popup],)),
                )

    def test_explicitly_hidden_and_disabled_targets_are_not_numbered(self):
        hidden = Element(AXRole="AXButton", AXFrame=frame(), AXHidden=True)
        disabled = Element(AXRole="AXButton", AXFrame=frame(), AXEnabled=False)
        self.talon.query_results = [hidden, disabled, self.button]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [self.button])

    def test_pressable_rows_are_numbered(self):
        row = Element(AXRole="AXRow", AXTitle="Threads", AXFrame=frame(y=200))
        disabled = Element(AXRole="AXRow", AXFrame=frame(y=300), AXEnabled=False)
        self.talon.query_results = [row, disabled, self.button]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [row, self.button])

    def test_group_inside_unpressable_row_is_numbered(self):
        row = Element(AXRole="AXRow", AXFrame=frame(y=200))
        row.actions = ["AXShowMenu"]
        cell = Element(AXRole="AXGroup", AXParent=row)
        item = Element(AXRole="AXGroup", AXParent=cell, AXFrame=frame(y=200))
        self.talon.query_results = [item, self.button]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [item, self.button])

    def test_group_inside_pressable_row_is_not_numbered_twice(self):
        row = Element(AXRole="AXRow", AXFrame=frame(y=200))
        content = Element(AXRole="AXGroup", AXParent=row, AXFrame=frame(y=200))
        self.talon.query_results = [row, content]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [row])

    def test_groups_outside_nearby_rows_are_not_numbered(self):
        row = Element(AXRole="AXRow")
        row.actions = []
        distant = row
        for _ in range(3):
            distant = Element(AXRole="AXGroup", AXParent=distant)
        far = Element(AXRole="AXGroup", AXParent=distant, AXFrame=frame(y=200))
        container = Element(AXRole="AXGroup", AXParent=self.window, AXFrame=frame())
        orphan = Element(AXRole="AXGroup", AXFrame=frame(y=300))
        self.talon.query_results = [far, container, orphan, self.button]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [self.button])

    def text_row(self, text_frame):
        text = Element(AXRole="AXStaticText", AXValue="games", AXFrame=text_frame)
        text.actions = ["AXShowMenu"]
        cell = Element(AXRole="AXGroup", AXChildren=[text], AXFrame=frame(width=380))
        cell.actions = []
        row = Element(AXRole="AXRow", AXChildren=[cell], AXFrame=frame(x=0, width=400))
        return row, text

    def test_row_label_is_drawn_on_its_text(self):
        row, text = self.text_row(frame(x=40, y=25, width=60, height=18))
        self.talon.query_results = [row, self.button]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [row, self.button])
        self.assertEqual(self.talon.native_calls[-1], ("show", ([text, self.button],)))

    def test_row_without_text_inside_it_is_labelled_directly(self):
        outside, _ = self.text_row(frame(x=600, y=25, width=60, height=18))
        empty = Element(AXRole="AXRow", AXFrame=frame(y=200, width=400))
        self.talon.query_results = [outside, empty]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.talon.native_calls[-1], ("show", ([outside, empty],)))

    def test_pressable_group_in_row_keeps_its_own_label(self):
        text = Element(AXRole="AXStaticText", AXFrame=frame(x=40, y=25, width=60))
        row = Element(AXRole="AXRow", AXFrame=frame(x=0, width=400))
        row.actions = ["AXShowMenu"]
        item = Element(
            AXRole="AXGroup", AXParent=row, AXChildren=[text], AXFrame=frame()
        )
        self.talon.query_results = [item]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.talon.native_calls[-1], ("show", ([item],)))

    def test_row_text_four_levels_deep_is_used(self):
        text = Element(AXRole="AXStaticText", AXFrame=frame(x=40, y=25, width=60))
        node = text
        for _ in range(3):
            node = Element(AXRole="AXGroup", AXChildren=[node], AXFrame=frame())
            node.actions = []
        row = Element(AXRole="AXRow", AXChildren=[node], AXFrame=frame(x=0, width=400))
        self.talon.query_results = [row]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.talon.native_calls[-1], ("show", ([text],)))

    def test_row_ignores_text_owned_by_a_nested_control(self):
        text = Element(AXRole="AXStaticText", AXFrame=frame(x=40, y=25, width=60))
        popup = Element(AXRole="AXPopUpButton", AXChildren=[text], AXFrame=frame())
        row = Element(AXRole="AXRow", AXChildren=[popup], AXFrame=frame(x=0, width=400))
        self.talon.query_results = [row, popup]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.talon.native_calls[-1], ("show", ([row, popup],)))

    def test_selecting_text_labelled_row_presses_the_row(self):
        row, text = self.text_row(frame(x=40, y=25, width=60, height=18))
        self.talon.query_results = [row, self.button]
        self.actions.accessibility_show_application_numbers()

        self.talon.dispatch_labels("select", 1)

        self.assertEqual(row.performed, ["AXPress"])
        self.assertEqual(text.performed, [])
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIn(("hide", ()), self.talon.native_calls)
        self.assertIsNone(self.module._session)

    def test_selecting_button_still_uses_native_selection(self):
        row, _ = self.text_row(frame(x=40, y=25, width=60, height=18))
        self.talon.query_results = [row, self.button]
        self.actions.accessibility_show_application_numbers()

        self.talon.dispatch_labels("select", 2)

        self.assertIn(("select", (2,)), self.talon.native_calls)
        self.assertEqual(row.performed, [])

    def test_row_activates_single_content_group_at_coverage_boundary(self):
        row, text = self.text_row(frame(x=40, y=25, width=60, height=18))
        child = row.get("AXChildren")[0]
        child.attrs.update(
            AXParent=row, AXFrame=frame(x=20, y=23, width=320, height=24)
        )
        child.actions = ["AXPress"]
        self.talon.query_results = [row, child]
        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [row])
        self.assertEqual(self.module._session.labelled, [text])
        self.talon.dispatch_labels("select", 1)

        self.assertEqual(child.performed, ["AXPress"])
        self.assertEqual(row.performed, [])
        self.assertNotIn(("select", (1,)), self.talon.native_calls)

    def test_row_content_group_is_used_even_without_text_substitution(self):
        child = Element(AXRole="AXGroup", AXFrame=frame(x=20, width=360))
        row = Element(AXRole="AXRow", AXFrame=frame(x=0, width=400), AXChildren=[child])
        child.attrs["AXParent"] = row
        self.talon.query_results = [row, child]
        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.labelled, [row])
        self.talon.dispatch_labels("select", 1)

        self.assertEqual(child.performed, ["AXPress"])
        self.assertEqual(row.performed, [])
        self.assertNotIn(("select", (1,)), self.talon.native_calls)

    def test_row_content_group_requires_unambiguous_contained_coverage(self):
        cases = (
            ("narrow", frame(x=20, width=319.9), {}, "AXGroup"),
            ("short", frame(x=20, y=23, width=320, height=23.9), {}, "AXGroup"),
            ("outside", frame(x=-2, width=400), {}, "AXGroup"),
            ("disabled", frame(x=20, width=360), {"AXEnabled": False}, "AXGroup"),
            ("hidden", frame(x=20, width=360), {"AXHidden": True}, "AXGroup"),
            ("button", frame(x=20, width=360), {}, "AXButton"),
            ("invalid", None, {}, "AXGroup"),
        )
        for name, child_frame, attrs, role in cases:
            with self.subTest(name=name):
                row = Element(AXRole="AXRow", AXFrame=frame(x=0, width=400))
                child = Element(AXRole=role, AXFrame=child_frame, **attrs)
                row.attrs["AXChildren"] = [child]
                self.assertIs(self.module._row_activation_target(row), row)

        row = Element(AXRole="AXRow", AXFrame=frame(x=0, width=400))
        row.attrs["AXChildren"] = [
            Element(AXRole="AXGroup", AXFrame=frame(x=20, width=360)),
            Element(AXRole="AXButton", AXFrame=frame(x=340, width=20)),
        ]
        self.assertIs(self.module._row_activation_target(row), row)

    def test_row_content_group_failure_is_reported_without_pressing_row(self):
        row, _ = self.text_row(frame(x=40, y=25, width=60, height=18))
        child = row.get("AXChildren")[0]
        child.actions = ["AXPress"]
        self.talon.query_results = [row]
        self.actions.accessibility_show_application_numbers()
        with patch.object(child, "perform", side_effect=ActionFailed("press failed")):
            self.talon.dispatch_labels("select", 1)
        self.assertEqual(row.performed, [])
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels", "Unable to activate the selected control."
        )

    def test_transient_query_attribute_error_is_retried_once(self):
        query = Mock(side_effect=[AttributeError("AXRole"), [self.button]])
        with patch.object(self.module.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()

        self.assertEqual(query.call_count, 2)
        self.assertEqual(self.module._session.targets, [self.button])
        self.talon.notify.assert_not_called()

    def test_query_attribute_error_notifies_and_stops_session(self):
        for during_refresh in (False, True):
            with self.subTest(during_refresh=during_refresh):
                self.actions.accessibility_show_application_numbers()
                session = self.module._session
                session.request_refresh()
                query = Mock(side_effect=AttributeError("AXRole"))
                with patch.object(self.module.axquery, "query_all", query):
                    if during_refresh:
                        session.refresh()
                    else:
                        self.actions.accessibility_show_application_numbers()
                self.assertIsNone(self.module._session)
                self.assertTrue(session.stopped)
                self.assert_session_active(False)
                self.talon.notify.assert_called_with(
                    "Application control labels",
                    "Unable to query the focused accessibility window.",
                )

    def test_empty_initial_query_does_not_leave_an_inactive_session(self):
        self.talon.query_results = []
        self.actions.accessibility_show_application_numbers()
        self.assertIsNone(self.module._session)
        self.assert_session_active(False)
        self.talon.notify.assert_called_with(
            "Application control labels",
            "The focused window exposes no visible pressable controls.",
        )

    def staged_window(self):
        self.talon.settings["user.accessibility_defer_web_areas"] = True
        self.close = Element(
            AXRole="AXButton", AXPosition=(0, 0), AXFrame=frame(x=1, width=10)
        )
        self.workbench = Element(AXRole="AXWebArea", AXTitle="Doc", AXFrame=frame())
        self.page = Element(
            AXRole="AXWebArea", AXTitle="Page", AXFrame=frame(width=200, height=200)
        )
        container = Element(AXRole="AXGroup", AXChildren=[self.workbench, self.page])
        container.actions = []
        self.window.attrs.update(AXTitle="Doc", AXChildren=[self.close, container])
        self.button.attrs["AXParent"] = self.workbench
        self.popup.attrs["AXParent"] = self.page
        results = {id(self.workbench): [self.button], id(self.page): [self.popup]}
        return Mock(side_effect=lambda *args, root, **kwargs: results[id(root)])

    def run_deferred(self):
        callback = self.talon.cron.after.call_args.args[1]
        callback()

    def test_deferred_web_areas_append_after_primary_numbers(self):
        query = self.staged_window()
        hit = Element(AXRole="AXStaticText", AXParent=self.page)
        with patch.object(self.module.axquery, "query_all", query):
            with patch.object(self.module.ui, "element_at", return_value=hit) as at:
                self.actions.accessibility_show_application_numbers()
                self.assertEqual(
                    self.talon.native_calls[-1], ("show", ([self.close, self.button],))
                )
                at.assert_not_called()
                self.run_deferred()
        self.assertEqual(
            self.module._session.targets, [self.close, self.button, self.popup]
        )
        self.assertEqual(
            self.talon.native_calls[-1],
            ("show", ([self.close, self.button, self.popup],)),
        )
        self.assertEqual(at.call_count, 1)
        self.assertEqual(query.call_count, 2)

    def test_covered_deferred_web_area_is_not_walked(self):
        query = self.staged_window()
        for hit in (
            Element(AXRole="AXTextArea", AXParent=self.workbench),
            RuntimeError("No element found."),
        ):
            with self.subTest(hit=hit):
                query.reset_mock()
                self.talon.native_calls.clear()
                with patch.object(self.module.axquery, "query_all", query):
                    with patch.object(
                        self.module.ui,
                        "element_at",
                        **(
                            {"side_effect": hit}
                            if isinstance(hit, Exception)
                            else {"return_value": hit}
                        ),
                    ):
                        self.actions.accessibility_show_application_numbers()
                        self.run_deferred()
                self.assertEqual(
                    self.module._session.targets, [self.close, self.button]
                )
                self.assertEqual(
                    self.talon.native_calls,
                    [("hide", ()), ("show", ([self.close, self.button],))],
                )
                self.assertEqual(query.call_count, 1)

    def test_deferred_web_area_errors_are_surfaced(self):
        query = self.staged_window()
        with patch.object(self.module.axquery, "query_all", query):
            with patch.object(
                self.module.ui, "element_at", side_effect=RuntimeError("Provider")
            ):
                self.actions.accessibility_show_application_numbers()
                self.run_deferred()
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels",
            "Unable to query the focused accessibility window.",
        )

    def test_deferred_append_waits_for_window_and_session(self):
        query = self.staged_window()
        with patch.object(self.module.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()
            session = self.module._session
            self.application.attrs["AXFocusedWindow"] = Element(AXRole="AXWindow")
            with patch.object(session, "request_refresh") as refresh:
                self.run_deferred()
            refresh.assert_called_once_with("0ms")
            self.assertEqual(session.targets, [self.close, self.button])

            self.application.attrs["AXFocusedWindow"] = self.window
            self.actions.accessibility_show_application_numbers()
            job = self.module._session.deferred_job
            self.module._stop()
            self.talon.cron.cancel.assert_any_call(job)

    def test_refresh_collects_deferred_web_areas_synchronously(self):
        query = self.staged_window()
        hit = Element(AXRole="AXStaticText", AXParent=self.page)
        with patch.object(self.module.axquery, "query_all", query):
            with patch.object(self.module.ui, "element_at", return_value=hit):
                self.actions.accessibility_show_application_numbers()
                session = self.module._session
                job = session.deferred_job
                session.refresh()
        self.talon.cron.cancel.assert_called_with(job)
        self.assertIsNone(session.deferred_job)
        self.assertEqual(session.targets, [self.close, self.button, self.popup])

    def test_window_without_matching_primary_web_area_is_queried_whole(self):
        query = self.staged_window()
        self.window.attrs["AXTitle"] = "Other"
        with patch.object(self.module.axquery, "query_all", query):
            with patch.object(self.module.ui, "element_at") as at:
                query.side_effect = lambda *args, root, **kwargs: [self.button]
                self.actions.accessibility_show_application_numbers()
        query.assert_called_once()
        self.assertIs(query.call_args.kwargs["root"], self.window)
        at.assert_not_called()
        self.talon.cron.after.assert_not_called()

    def test_deferred_web_areas_are_opt_in(self):
        self.staged_window()
        self.talon.settings["user.accessibility_defer_web_areas"] = False
        with patch.object(self.module.ui, "element_at") as at:
            self.actions.accessibility_show_application_numbers()
        at.assert_not_called()
        self.talon.cron.after.assert_not_called()
        self.assertEqual(self.module._session.targets, [self.button, self.popup])

    def test_surface_clip_replaces_talon_pruning(self):
        self.talon.settings["user.accessibility_clip_to_surface"] = True
        self.window.attrs["AXFrame"] = frame(x=0, y=0, width=500, height=500)
        outside = Element(AXRole="AXButton", AXFrame=frame(x=600))
        touching = Element(AXRole="AXButton", AXFrame=frame(x=500))
        removed = Element(AXRole="AXButton", AXFrame=frame())
        removed.attrs = {}
        query = Mock(return_value=[removed, outside, touching, self.button])
        with patch.object(self.module.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()
        self.assertFalse(query.call_args.kwargs["visible_only"])
        self.assertEqual(self.module._session.targets, [self.button])

    def test_surface_clip_without_frame_is_surfaced(self):
        self.talon.settings["user.accessibility_clip_to_surface"] = True
        query = Mock(return_value=[self.button])
        with patch.object(self.module.axquery, "query_all", query):
            self.actions.accessibility_show_application_numbers()
        query.assert_not_called()
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels",
            "Unable to query the focused accessibility window.",
        )

    def test_deferred_web_areas_use_the_window_clip(self):
        query = self.staged_window()
        self.talon.settings["user.accessibility_clip_to_surface"] = True
        self.window.attrs["AXFrame"] = frame(x=0, y=0, width=500, height=500)
        below = Element(AXRole="AXLink", AXFrame=frame(y=900), AXParent=self.page)
        results = {
            id(self.workbench): [self.button],
            id(self.page): [self.popup, below],
        }
        query.side_effect = lambda *args, root, **kwargs: results[id(root)]
        hit = Element(AXRole="AXStaticText", AXParent=self.page)
        with patch.object(self.module.axquery, "query_all", query):
            with patch.object(self.module.ui, "element_at", return_value=hit):
                self.actions.accessibility_show_application_numbers()
                self.run_deferred()
        self.assertEqual(
            self.module._session.targets, [self.close, self.button, self.popup]
        )
        self.assertTrue(
            all(call.kwargs["visible_only"] is False for call in query.call_args_list)
        )

    def test_web_area_cache_uses_equality_for_unhashable_elements(self):
        class UnhashableElement(Element):
            __hash__ = None

            def __eq__(self, other):
                return (
                    isinstance(other, UnhashableElement) and self.attrs is other.attrs
                )

        area = UnhashableElement(AXRole="AXWebArea")
        child = UnhashableElement(AXParent=area)
        cache = []
        self.assertIs(self.module._web_area(child, cache), area)
        alias = UnhashableElement()
        alias.attrs = child.attrs
        with patch.object(alias, "get", side_effect=AssertionError("not cached")):
            self.assertIs(self.module._web_area(alias, cache), area)
        self.assertIsNone(self.module._web_area(None, cache))

    def test_web_area_ancestry_cycle_surfaces_an_error(self):
        cyclic = Element(AXRole="AXGroup")
        cyclic.attrs["AXParent"] = cyclic
        with self.assertRaisesRegex(RuntimeError, "ancestry"):
            self.module._web_area(cyclic, [])

    def test_selection_rechecks_web_area_after_tab_changes(self):
        self.talon.settings["user.accessibility_defer_web_areas"] = True
        area = Element(AXRole="AXWebArea")
        self.button.attrs["AXParent"] = area
        self.talon.query_results = [self.button]
        with patch.object(self.module.ui, "element_at", return_value=self.button):
            self.actions.accessibility_show_application_numbers()
        unrelated = Element(AXRole="AXWebArea")
        with patch.object(self.module.ui, "element_at", return_value=unrelated):
            self.talon.dispatch_labels("select", 1)
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.assertIn("web area is covered", self.talon.notify.call_args.args[1])

    def test_overlapping_distinct_controls_are_preserved(self):
        overlapping = Element(
            AXRole="AXButton", AXTitle="Other action", AXFrame=frame()
        )
        self.talon.query_results = [self.button, self.button, overlapping]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [self.button, overlapping])

    def test_tag_activates_overrides_and_hide_clears_it(self):
        self.actions.accessibility_show_application_numbers()
        self.assertIn(("show", ([self.button, self.popup],)), self.talon.native_calls)
        self.assert_session_active(True)

        self.talon.modules()[0].actions.labels.select(1)
        self.assertIn(("select", (1,)), self.talon.native_calls)

        self.talon.modules()[0].actions.labels.hide()
        self.assertIn(("hide", ()), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.assert_session_active(False)

    def test_expanding_selection_keeps_session_and_schedules_refresh(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session

        self.talon.modules()[0].actions.labels.select(2)

        self.assertIn(("select", (2,)), self.talon.native_calls)
        self.assertIs(self.module._session, session)
        self.talon.cron.after.assert_called_once()
        self.assert_session_active(True)

    def test_reload_stops_previous_session_and_cancels_refresh(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        session.request_refresh()
        job = session.refresh_job

        load(self.talon, "accessibility/inventory.py", self.module)

        self.assertTrue(session.stopped)
        self.talon.cron.cancel.assert_any_call(job)
        self.assertIsNone(self.module._session)

    def test_selection_after_window_change_is_rejected(self):
        self.actions.accessibility_show_application_numbers()
        self.application.attrs["AXFocusedWindow"] = Element(AXRole="AXWindow")

        self.talon.modules()[0].actions.labels.select(1)

        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.assertIn("focused window changed", self.talon.notify.call_args[0][1])

    def test_stale_target_reports_error_without_raising(self):
        self.actions.accessibility_show_application_numbers()
        self.popup.dead = True

        self.talon.modules()[0].actions.labels.select(2)

        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels",
            "Unable to activate the selected control.",
        )

    def test_activation_failure_is_reported(self):
        self.application.dead = True

        self.actions.accessibility_show_application_numbers()

        self.assertIsNone(self.module._session)
        self.assertIn(
            "Unable to enable accessibility interfaces",
            self.talon.notify.call_args[0][1],
        )

    def test_interface_toggle_failure_is_reported(self):
        self.application.dead = True

        self.actions.accessibility_set_interfaces(True, False)

        self.assertIn(
            "Unable to update accessibility interfaces",
            self.talon.notify.call_args[0][1],
        )

    def test_normal_selection_cleans_up_when_native_labels_hide(self):
        self.talon.hide_after_select = True
        self.actions.accessibility_show_application_numbers()

        self.talon.dispatch_labels("select", 1)

        self.assertIn(("select", (1,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.assert_session_active(False)

    def test_expansion_survives_native_hide_and_refreshes_new_targets(self):
        self.talon.hide_after_select = True
        self.actions.accessibility_show_application_numbers()
        session = self.module._session

        self.talon.dispatch_labels("select", 2)

        self.assertIs(self.module._session, session)
        self.assert_session_active(True)
        self.talon.cron.after.assert_called_once_with(
            "100ms", session._refresh_after_event
        )
        self.talon.query_results = [self.button]
        self.talon.cron.after.call_args.args[1]()
        self.assertEqual(session.targets, [self.button])
        self.assertIsNone(session.refresh_job)
        self.assertEqual(self.talon.native_calls[-1], ("show", ([self.button],)))

    def test_expansion_restores_labels_when_targets_do_not_change(self):
        self.talon.hide_after_select = True
        self.actions.accessibility_show_application_numbers()
        session = self.module._session

        self.talon.dispatch_labels("select", 2)
        self.talon.cron.after.call_args.args[1]()

        self.assertIs(self.module._session, session)
        self.assertEqual(
            self.talon.native_calls[-1], ("show", ([self.button, self.popup],))
        )

    def test_invalid_number_is_rejected_without_native_selection(self):
        self.actions.accessibility_show_application_numbers()

        self.talon.dispatch_labels("select", 99)

        self.assertNotIn(("select", (99,)), self.talon.native_calls)
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Application control labels", "That number no longer matches a control."
        )

    def test_app_change_stops_session_and_cancels_pending_refresh(self):
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        session.request_refresh()
        job = session.refresh_job

        self.module._focus_changed(types.SimpleNamespace(pid=2))

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)
        self.talon.cron.cancel.assert_any_call(job)
        self.assert_session_active(False)

    def test_unsupported_activation_attributes_are_not_an_operational_failure(self):
        with patch.object(Element, "__setitem__", side_effect=UIErr("unsupported")):
            self.actions.accessibility_set_interfaces(True)

        self.talon.notify.assert_called_with(
            "Accessibility interfaces", "Enabled: No supported writable interfaces"
        )


class ApplicationMenuTests(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.window = Element(
            AXRole="AXWindow", AXFrame=frame(x=0, y=0, width=500, height=500)
        )
        self.application = Element(AXRole="AXApplication", AXFocusedWindow=self.window)
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
        self.module = load(self.talon, "accessibility/inventory.py")
        self.actions = self.module.Actions
        self.query = Mock(
            side_effect=lambda *args, root, **kwargs: self.results[id(root)]
        )
        self.module.axquery.query_all = self.query

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

    def test_initially_open_menu_numbers_only_menu_controls(self):
        session = self.start(self.menu)

        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])
        self.assertEqual(self.talon.native_calls[-1], ("show", ([self.item],)))
        self.assertEqual(self.query.call_count, 1)
        self.assertIs(self.query.call_args.kwargs["root"], self.menu)

    def test_menu_text_anchor_labels_and_presses_the_logical_item(self):
        shortcut = Element(AXRole="AXStaticText", AXFrame=frame(x=70))
        title = Element(AXRole="AXStaticText", AXFrame=frame(x=25))
        group = Element(AXRole="AXGroup", AXChildren=[shortcut, title])
        self.item.attrs["AXChildren"] = [group]

        session = self.start(self.menu)

        self.assertEqual(session.targets, [self.item])
        self.assertEqual(session.labelled, [title])
        self.assertEqual(self.talon.native_calls[-1], ("show", ([title],)))
        self.talon.native_calls.clear()
        self.talon.dispatch_labels("select", 1)
        self.assertEqual(self.item.performed, ["AXPress"])
        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertEqual(self.talon.native_calls.count(("hide", ())), 1)

    def test_menu_text_anchor_ignores_nested_controls_and_menus(self):
        nested_text = Element(AXRole="AXStaticText", AXFrame=frame())
        button = Element(AXRole="AXButton", AXChildren=[nested_text])
        submenu = Element(AXRole="AXMenu", AXChildren=[nested_text])
        self.item.attrs["AXChildren"] = [button, submenu]

        session = self.start(self.menu)

        self.assertEqual(session.labelled, [self.item])

    def test_menu_text_anchor_ignores_hidden_and_outside_text(self):
        hidden = Element(AXRole="AXStaticText", AXHidden=True, AXFrame=frame())
        outside = Element(AXRole="AXStaticText", AXFrame=frame(x=500))
        self.item.attrs["AXChildren"] = [hidden, outside]

        session = self.start(self.menu)

        self.assertEqual(session.labelled, [self.item])

    def test_window_menu_item_keeps_native_label_and_selection(self):
        text = Element(AXRole="AXStaticText", AXFrame=frame())
        self.item.attrs["AXChildren"] = [text]
        self.results[id(self.window)] = [self.item]

        session = self.start()

        self.assertEqual(session.labelled, [self.item])
        self.talon.dispatch_labels("select", 1)
        self.assertIn(("select", (1,)), self.talon.native_calls)

    def test_text_anchored_submenu_still_uses_hover_fallback(self):
        title = Element(AXRole="AXStaticText", AXFrame=frame(x=25))
        self.item.attrs.update(AXChildren=[title], AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)

        self.talon.dispatch_labels("select", 1)
        for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
            session._check_menu()

        self.assertEqual(self.item.performed, ["AXPress"])
        self.module.actions.mouse_move.assert_called_once_with(50, 35)

    def test_menu_query_uses_menu_clip_not_window_clip(self):
        self.talon.settings["user.accessibility_clip_to_surface"] = True
        outside = Element(AXRole="AXMenuItem", AXFrame=frame(x=400))
        self.results[id(self.menu)] = [self.item, outside]

        session = self.start(self.menu)

        self.assertEqual(session.targets, [self.item])
        self.assertIs(self.query.call_args.kwargs["root"], self.menu)
        self.assertFalse(self.query.call_args.kwargs["visible_only"])

    def test_diagnostic_surfaces_still_include_window_and_menu(self):
        self.talon.active_menu = self.menu
        self.assertEqual(
            self.module.focused_surfaces(self.talon.active_app),
            [("focused-window", self.window), ("active-menu", self.menu)],
        )

    def test_menu_poll_does_not_repeat_window_queries(self):
        session = self.start()

        self.talon.cron.interval.assert_called_once_with("100ms", session._check_menu)
        for _ in range(10):
            session._check_menu()

        self.assertEqual(self.query.call_count, 1)
        self.talon.cron.after.assert_not_called()

    def test_stopped_menu_poll_does_not_hide_replacement_session(self):
        session = self.start()
        switched = False

        def switch_during_poll():
            nonlocal switched
            if not switched:
                switched = True
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()
                return self.menu
            return None

        with patch.object(
            self.module.ui, "active_menu", side_effect=switch_during_poll
        ):
            session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_stopped_menu_poll_error_does_not_stop_replacement_session(self):
        session = self.start()
        switched = False

        def fail_after_switch():
            nonlocal switched
            if not switched:
                switched = True
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()
                raise UIErr("old session failed")
            return None

        with patch.object(self.module.ui, "active_menu", side_effect=fail_after_switch):
            session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.talon.notify.assert_not_called()

    def test_stopped_refresh_does_not_stop_replacement_on_empty_result(self):
        session = self.start()
        switched = False

        def finish_after_switch(owner, menu, window):
            nonlocal switched
            if not switched:
                switched = True
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()
                return [], []
            return [self.button], []

        with patch.object(self.module, "_controls", side_effect=finish_after_switch):
            session.refresh(force=True)

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertEqual(self.module._session.targets, [self.button])
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.talon.notify.assert_not_called()

    def test_stopped_focus_check_does_not_hide_replacement_session(self):
        for operation in ("select", "back", "refresh"):
            with self.subTest(operation=operation):
                session = self.start(self.menu)
                switched = False

                def change_session_during_focus_check():
                    nonlocal switched
                    if not switched:
                        switched = True
                        self.talon.dispatch_labels("hide")
                        self.actions.accessibility_show_application_numbers()
                        self.talon.native_calls.clear()
                        return types.SimpleNamespace(pid=2)
                    return self.talon.active_app

                with patch.object(
                    self.module.ui,
                    "active_app",
                    side_effect=change_session_during_focus_check,
                ):
                    if operation == "select":
                        self.talon.dispatch_labels("select", 1)
                    elif operation == "back":
                        self.actions.accessibility_application_numbers_back()
                    else:
                        session.refresh()

                self.assertTrue(session.stopped)
                self.assertIsNot(self.module._session, session)
                self.assertNotIn(("hide", ()), self.talon.native_calls)
                self.talon.notify.assert_not_called()

    def test_mouse_opened_menu_replaces_window_and_close_restores_it(self):
        session = self.start()
        self.talon.active_menu = self.menu

        session._check_menu()
        self.assertEqual(self.talon.native_calls[-1], ("hide", ()))
        self.assertIs(self.module._session, session)
        self.assertEqual(self.query.call_count, 1)
        self.finish_refresh()

        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])
        self.assertIs(self.query.call_args.kwargs["root"], self.menu)

        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()

        self.assertIsNone(session.menu)
        self.assertEqual(session.targets, [self.button])
        self.assertIs(self.query.call_args.kwargs["root"], self.window)

    def test_manual_submenu_transition_only_numbers_current_menu(self):
        session = self.start(self.menu)
        submenu, item = self.nested_menu()
        self.talon.active_menu = submenu

        session._check_menu()
        self.finish_refresh()

        self.assertIs(session.menu, submenu)
        self.assertEqual(session.targets, [item])
        self.assertIs(self.query.call_args.kwargs["root"], submenu)

    def test_selection_rejects_stale_window_labels_after_menu_opens(self):
        session = self.start()
        self.talon.active_menu = self.menu

        self.talon.dispatch_labels("select", 1)

        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.assertIs(self.module._session, session)
        self.assertIn("menu changed", self.talon.notify.call_args.args[1].lower())
        self.finish_refresh()
        self.assertEqual(session.targets, [self.item])

    def test_select_and_back_wait_for_in_progress_refresh(self):
        session = self.start(self.menu)
        session.refreshing = True

        self.talon.dispatch_labels("select", 1)
        self.actions.accessibility_application_numbers_back()

        self.assertNotIn(("select", (1,)), self.talon.native_calls)
        self.module.actions.key.assert_not_called()
        self.assertIs(self.module._session, session)
        self.assertEqual(self.talon.notify.call_count, 2)
        self.assertTrue(
            all(
                "refresh" in call.args[1].lower()
                for call in self.talon.notify.call_args_list
            )
        )

    def test_menu_selection_waits_for_delayed_submenu(self):
        self.talon.hide_after_select = True
        session = self.start(self.menu)
        submenu, item = self.nested_menu()

        self.talon.dispatch_labels("select", 1)
        self.assertIs(self.module._session, session)
        session._check_menu()
        self.assertEqual(self.query.call_count, 1)
        self.talon.active_menu = submenu
        session._check_menu()
        self.finish_refresh()

        self.assertIs(session.menu, submenu)
        self.assertEqual(session.targets, [item])

    def test_submenu_selection_hovers_only_after_native_selection_stalls(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        self.talon.hide_after_select = True
        session = self.start(self.menu)
        submenu, item = self.nested_menu()

        self.talon.dispatch_labels("select", 1)

        self.assertIn(("select", (1,)), self.talon.native_calls)
        for _ in range(self.module.MENU_HOVER_DELAY_TICKS - 1):
            session._check_menu()
        self.module.actions.mouse_move.assert_not_called()
        session._check_menu()
        self.module.actions.mouse_move.assert_called_once_with(50, 35)

        self.talon.active_menu = submenu
        session._check_menu()
        self.finish_refresh()
        self.assertIs(session.menu, submenu)
        self.assertEqual(session.targets, [item])

    def test_submenu_selection_does_not_hover_if_native_open_succeeds(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)
        submenu, item = self.nested_menu()

        self.talon.dispatch_labels("select", 1)
        self.talon.active_menu = submenu
        session._check_menu()
        self.finish_refresh()

        self.module.actions.mouse_move.assert_not_called()
        self.assertEqual(session.targets, [item])

    def test_submenu_hover_rejects_stale_or_unsafe_targets(self):
        for case in (
            "leaf",
            "disabled",
            "hidden",
            "outside_menu",
            "invalid_frame",
            "detached",
            "mouse_moved",
            "window_changed",
        ):
            with self.subTest(case=case):
                self.item.attrs.update(
                    AXParent=self.menu,
                    AXHasPopup=case != "leaf",
                    AXEnabled=True,
                    AXHidden=False,
                    AXFrame=frame(),
                )
                self.application.attrs["AXFocusedWindow"] = self.window
                self.talon.mouse_pos.reset_mock(side_effect=True)
                self.talon.mouse_pos.return_value = (30, 40)
                self.module.actions.mouse_move.reset_mock()
                session = self.start(self.menu)
                self.talon.dispatch_labels("select", 1)

                if case == "disabled":
                    self.item.attrs["AXEnabled"] = False
                elif case == "hidden":
                    self.item.attrs["AXHidden"] = True
                elif case == "outside_menu":
                    self.item.attrs["AXFrame"] = frame(x=400)
                elif case == "invalid_frame":
                    self.item.attrs["AXFrame"] = frame(width=float("nan"))
                elif case == "detached":
                    self.item.attrs["AXParent"] = Element(AXRole="AXMenu")
                elif case == "mouse_moved":
                    self.talon.mouse_pos.return_value = (31, 40)
                elif case == "window_changed":
                    self.application.attrs["AXFocusedWindow"] = Element(
                        AXRole="AXWindow"
                    )

                for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
                    session._check_menu()

                self.module.actions.mouse_move.assert_not_called()

    def test_submenu_hover_does_not_move_after_menu_changes_during_validation(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)
        submenu, item = self.nested_menu()
        self.talon.dispatch_labels("select", 1)

        def change_menu(*args):
            self.talon.active_menu = submenu
            return (50, 35)

        with patch.object(self.module, "_submenu_hover_point", side_effect=change_menu):
            for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
                session._check_menu()

        self.module.actions.mouse_move.assert_not_called()
        session._check_menu()
        self.finish_refresh()
        self.assertEqual(session.targets, [item])

    def test_replaced_session_cannot_move_mouse_from_old_submenu_hover(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)
        self.talon.dispatch_labels("select", 1)

        def replace_session(*args):
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            self.talon.native_calls.clear()
            return (50, 35)

        with patch.object(
            self.module, "_submenu_hover_point", side_effect=replace_session
        ):
            for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
                session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.module.actions.mouse_move.assert_not_called()
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.talon.notify.assert_not_called()

    def test_submenu_hover_failure_is_reported(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)
        self.talon.dispatch_labels("select", 1)
        self.module.actions.mouse_move.side_effect = ActionFailed("mouse failed")

        for _ in range(self.module.MENU_HOVER_DELAY_TICKS):
            session._check_menu()

        self.assertTrue(session.stopped)
        self.talon.notify.assert_called_once_with(
            "Application control labels", "Unable to open the selected submenu."
        )

    def test_menu_selection_tolerates_briefly_missing_active_menu(self):
        self.talon.hide_after_select = True
        session = self.start(self.menu)
        submenu, item = self.nested_menu()
        self.talon.dispatch_labels("select", 1)
        self.talon.active_menu = None
        session._check_menu()

        self.assertIs(self.module._session, session)
        self.talon.active_menu = submenu
        session._check_menu()
        self.finish_refresh()
        self.assertEqual(session.targets, [item])

    def test_menu_leaf_selection_exits_without_relabeling_window(self):
        self.talon.hide_after_select = True
        session = self.start(self.menu)

        self.talon.dispatch_labels("select", 1)
        self.talon.active_menu = None
        for _ in range(15):
            session._check_menu()

        self.assertIsNone(self.module._session)
        self.assertTrue(session.stopped)
        self.assertEqual(self.query.call_count, 1)
        self.assertNotIn(("show", ([self.button],)), self.talon.native_calls)

    def test_back_closes_top_menu_and_restores_window(self):
        session = self.start(self.menu)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

        self.actions.accessibility_application_numbers_back()

        self.module.actions.key.assert_called_once_with("esc")
        self.assertEqual(self.menu.performed, [])
        self.assertIs(self.module._session, session)
        self.assertNotIn(ACTIVE_TAG, self.talon.active_tags())
        self.assertIn(SESSION_TAG, self.talon.active_tags())
        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()
        self.assertIsNone(session.menu)
        self.assertEqual(session.targets, [self.button])
        self.assertIn(ACTIVE_TAG, self.talon.active_tags())
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_back_uses_escape_if_top_menu_cannot_be_cancelled(self):
        self.menu.actions = []
        session = self.start(self.menu)

        self.actions.accessibility_application_numbers_back()

        self.module.actions.key.assert_called_once_with("esc")
        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()
        self.assertEqual(session.targets, [self.button])

    def test_back_closes_one_submenu_and_relabels_parent(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)

        self.actions.accessibility_application_numbers_back()

        self.module.actions.key.assert_called_once_with("left")
        self.talon.active_menu = self.menu
        session._check_menu()
        self.finish_refresh()
        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])

    def test_back_recognizes_a_direct_parent_menu(self):
        submenu, _ = self.nested_menu()
        submenu.attrs["AXParent"] = self.menu
        session = self.start(submenu)

        self.actions.accessibility_application_numbers_back()

        self.module.actions.key.assert_called_once_with("left")
        self.talon.active_menu = self.menu
        session._check_menu()
        self.finish_refresh()
        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])

    def test_back_falls_back_to_window_if_parent_cannot_be_restored(self):
        submenu, _ = self.nested_menu()
        submenu.attrs["AXParent"] = self.menu
        session = self.start(submenu)

        self.actions.accessibility_application_numbers_back()
        for _ in range(self.module.MENU_BACK_FALLBACK_TICKS):
            session._check_menu()

        self.assertEqual(
            [call.args for call in self.module.actions.key.call_args_list],
            [("left",), ("esc",)],
        )
        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()

        self.assertIsNone(session.menu)
        self.assertEqual(session.targets, [self.button])
        self.assertIn("application controls", self.talon.notify.call_args.args[1])

    def test_back_fallback_does_not_escape_after_window_changes(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        self.actions.accessibility_application_numbers_back()
        self.application.attrs["AXFocusedWindow"] = Element(AXRole="AXWindow")

        for _ in range(self.module.MENU_BACK_FALLBACK_TICKS):
            session._check_menu()

        self.module.actions.key.assert_called_once_with("left")
        self.assertTrue(session.stopped)
        self.assertIn("window changed", self.talon.notify.call_args.args[1].lower())

    def test_back_fallback_does_not_escape_after_menu_changes_during_validation(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        self.actions.accessibility_application_numbers_back()

        def change_menu():
            self.talon.active_menu = Element(AXRole="AXMenu")
            return True

        with patch.object(session, "_transition_focus_valid", side_effect=change_menu):
            for _ in range(self.module.MENU_BACK_FALLBACK_TICKS):
                session._check_menu()

        self.module.actions.key.assert_called_once_with("left")

    def test_replaced_session_cannot_send_fallback_escape(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        self.actions.accessibility_application_numbers_back()

        def replace_session():
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            self.talon.native_calls.clear()
            return True

        with patch.object(
            session, "_transition_focus_valid", side_effect=replace_session
        ):
            for _ in range(self.module.MENU_BACK_FALLBACK_TICKS):
                session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.module.actions.key.assert_called_once_with("left")
        self.assertNotIn(("hide", ()), self.talon.native_calls)

    def test_back_fallback_escape_failure_is_reported(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        self.actions.accessibility_application_numbers_back()
        self.module.actions.key.side_effect = ActionFailed("escape failed")

        for _ in range(self.module.MENU_BACK_FALLBACK_TICKS):
            session._check_menu()

        self.assertTrue(session.stopped)
        self.talon.notify.assert_called_once_with(
            "Application control labels", "Unable to return to the parent menu."
        )

    def test_submenu_back_uses_verified_parent_menu_opener(self):
        opener = Element(AXRole="AXMenuBarItem", AXChildren=[self.menu], AXEnabled=True)
        self.menu.attrs["AXParent"] = opener
        submenu, _ = self.nested_menu()
        session = self.start(submenu)

        self.actions.accessibility_application_numbers_back()

        self.assertEqual(opener.performed, ["AXPress"])
        self.module.actions.key.assert_not_called()
        self.talon.active_menu = self.menu
        session._check_menu()
        self.finish_refresh()
        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])

    def test_replaced_session_does_not_press_a_menu_opener(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        opener = Element(AXRole="AXMenuBarItem")

        def replace_session(parent):
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            return opener

        with patch.object(self.module, "menu_opener", side_effect=replace_session):
            self.actions.accessibility_application_numbers_back()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertEqual(opener.performed, [])
        self.module.actions.key.assert_not_called()

    def test_back_does_not_send_escape_after_session_is_replaced_while_hiding(self):
        session = self.start(self.menu)
        native_hide = self.module.actions.labels.hide
        switched = False

        def replace_during_hide():
            nonlocal switched
            if not switched:
                switched = True
                native_hide()
                self.module._stop()
                self.actions.accessibility_show_application_numbers()
            else:
                native_hide()

        with patch.object(
            self.module.actions.labels, "hide", side_effect=replace_during_hide
        ):
            self.actions.accessibility_application_numbers_back()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.module.actions.key.assert_not_called()
        self.assertIn(ACTIVE_TAG, self.talon.active_tags())
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_back_at_window_does_not_send_a_key(self):
        session = self.start()
        self.actions.accessibility_application_numbers_back()
        self.assertIs(self.module._session, session)
        self.module.actions.key.assert_not_called()
        self.talon.notify.assert_called_once()

    def test_back_waits_and_reports_an_unchanged_menu(self):
        session = self.start(self.menu)
        self.actions.accessibility_application_numbers_back()
        self.actions.accessibility_application_numbers_back()
        self.module.actions.key.assert_called_once_with("esc")

        for _ in range(15):
            session._check_menu()

        self.assertIsNone(self.module._session)
        self.assertIn("unable to return", self.talon.notify.call_args.args[1].lower())

    def test_menu_monitor_is_cancelled_with_session(self):
        session = self.start()
        job = session.job
        self.talon.dispatch_labels("hide")
        self.assertTrue(session.stopped)
        self.talon.cron.cancel.assert_any_call(job)

    def test_other_label_session_can_hide_during_back_transition(self):
        session = self.start(self.menu)
        self.actions.accessibility_application_numbers_back()

        self.talon.dispatch_labels("hide")

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)

    def test_escape_and_session_overrides_use_separate_tags(self):
        active = (ROOT / "accessibility" / "inventory_active.talon").read_text()
        self.assertIn(f"tag: {ACTIVE_TAG}", active)
        self.assertIn("key(escape):", active)
        self.assertIn(f"tag: {SESSION_TAG}", self.module.labels_ctx.matches)

    def test_app_change_stops_session_during_back_transition(self):
        session = self.start(self.menu)
        self.actions.accessibility_application_numbers_back()
        self.talon.active_app = types.SimpleNamespace(pid=2)

        session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)

    def test_menu_change_prevents_stale_deferred_append(self):
        session = self.start()
        self.talon.active_menu = self.menu
        with patch.object(self.module, "_deferred_controls") as deferred:
            session._append_deferred(self.window, [self.button], [])
        deferred.assert_not_called()
        self.finish_refresh()
        self.assertEqual(session.targets, [self.item])

    def test_menu_change_during_query_never_renders_stale_targets(self):
        session = self.start()
        self.talon.active_menu = self.menu

        def query(*args, root, **kwargs):
            if root is self.menu:
                self.talon.active_menu = None
            return self.results[id(root)]

        self.query.side_effect = query
        session._check_menu()
        self.finish_refresh()

        self.assertNotIn(("show", ([self.item],)), self.talon.native_calls)
        self.finish_refresh()
        self.assertEqual(session.targets, [self.button])

    def test_temporarily_empty_menu_is_retried_without_stopping(self):
        session = self.start()
        self.talon.active_menu = self.menu
        self.results[id(self.menu)] = []
        session._check_menu()
        self.finish_refresh()

        self.assertIs(self.module._session, session)
        self.assertEqual(self.talon.cron.after.call_args.args[0], "100ms")
        self.results[id(self.menu)] = [self.item]
        self.finish_refresh()
        self.assertEqual(session.targets, [self.item])

    def test_transition_hide_preserves_an_existing_hide_guard(self):
        session = self.start()
        session.preserve_hide = True

        session.hide_for_transition()

        self.assertTrue(session.preserve_hide)
        self.assertIs(self.module._session, session)
        session.preserve_hide = False

    def test_menu_monitor_error_stops_and_notifies(self):
        session = self.start()
        with patch.object(self.module.ui, "active_menu", side_effect=UIErr("failed")):
            session._check_menu()
        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)
        self.talon.notify.assert_called_once_with(
            "Application control labels",
            "Unable to query the focused accessibility window.",
        )


class HighlightRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.talon.active_app = types.SimpleNamespace(pid=1, name="Editor")
        self.element = Element(
            AXRole="AXTextArea",
            AXValue="one two one",
            AXSelectedTextRange=Span(0, 0),
            AXSharedCharacterRange=Span(10, 21),
            AXFocused=True,
        )
        self.talon.user.dictation_current_element = lambda: self.element
        self.talon.user.homophones_get = lambda word: None
        self.module = load(self.talon, "accessibility/text_highlight_spike.py")
        self.actions = self.module.Actions

    def test_start_selects_nearest_match_with_shared_offset(self):
        self.actions.text_highlight_spike_start("one")
        selected = self.element.attrs["AXSelectedTextRange"]
        self.assertEqual((selected.left, selected.right), (10, 13))

    def test_non_bmp_character_before_match_uses_utf16_ax_range(self):
        content = "one two one. 🙂 target word. one again."
        self.element.attrs.update(
            AXValue=content,
            AXSelectedTextRange=Span(116, 116),
            AXSharedCharacterRange=Span(100, 100 + len(content) + 1),
        )

        self.actions.text_highlight_spike_start("target")

        selected = self.element.attrs["AXSelectedTextRange"]
        self.assertEqual((selected.left, selected.right), (116, 122))

    def test_shared_range_change_rejects_stale_mapping(self):
        self.actions.text_highlight_spike_start("one")
        self.element.attrs["AXSharedCharacterRange"] = Span(50, 61)

        self.actions.text_highlight_spike_next()

        self.assertIsNone(self.module._session)
        self.assertEqual(self.element.attrs["AXSelectedTextRange"].left, 10)
        self.talon.notify.assert_called_with(
            "Highlight word", "Unable to update the highlighted word."
        )

    def test_window_change_rejects_selection(self):
        self.actions.text_highlight_spike_start("one")
        self.talon.active_window = types.SimpleNamespace(id=2)

        self.actions.text_highlight_spike_next()

        self.assertIsNone(self.module._session)
        self.assertEqual(self.element.attrs["AXSelectedTextRange"].left, 10)

    def test_homophone_failure_is_surfaced_and_exact_matching_continues(self):
        self.talon.user.homophones_get = Mock(side_effect=ActionFailed("missing"))

        self.actions.text_highlight_spike_start("one")

        self.assertIsNotNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Highlight word",
            "Homophone lookup failed; matching the exact word only.",
        )

    def test_missing_homophone_action_is_surfaced(self):
        self.talon.user.homophones_get = Mock(side_effect=KeyError("homophones_get"))

        self.actions.text_highlight_spike_start("one")

        self.assertIsNotNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Highlight word",
            "Homophones are unavailable; matching the exact word only.",
        )

    def test_unavailable_element_is_reported(self):
        self.actions.text_highlight_spike_start("one")
        self.element.dead = True

        self.module._element_changed()

        self.assertIsNone(self.module._session)
        self.assertIn("no longer available", self.talon.notify.call_args[0][1])

    def test_reload_stops_previous_session(self):
        self.actions.text_highlight_spike_start("one")
        session = self.module._session

        load(self.talon, "accessibility/text_highlight_spike.py", self.module)

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)

    def test_navigation_wraps_and_close_preserves_selection(self):
        self.actions.text_highlight_spike_start("one")
        for operation, expected in (
            (self.actions.text_highlight_spike_next, (18, 21)),
            (self.actions.text_highlight_spike_next, (10, 13)),
            (self.actions.text_highlight_spike_previous, (18, 21)),
            (self.actions.text_highlight_spike_first, (10, 13)),
            (self.actions.text_highlight_spike_last, (18, 21)),
            (lambda: self.actions.text_highlight_spike_select(1), (10, 13)),
        ):
            with self.subTest(expected=expected):
                operation()
                selected = self.element.attrs["AXSelectedTextRange"]
                self.assertEqual((selected.left, selected.right), expected)

        selected = self.element.attrs["AXSelectedTextRange"]
        self.actions.text_highlight_spike_hide()
        self.assertIs(self.element.attrs["AXSelectedTextRange"], selected)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.module.tag_ctx.tags, [])
        self.module.highlight_gui.hide.assert_called_once()

    def test_invalid_number_cleans_up_without_changing_selection(self):
        self.actions.text_highlight_spike_start("one")
        selected = self.element.attrs["AXSelectedTextRange"]

        self.actions.text_highlight_spike_select(99)

        self.assertIs(self.element.attrs["AXSelectedTextRange"], selected)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.module.tag_ctx.tags, [])

    def test_selection_write_failure_logs_notifies_and_cleans_up(self):
        self.actions.text_highlight_spike_start("one")
        with (
            patch.object(Element, "__setitem__", side_effect=UIErr("read only")),
            self.assertLogs(level="ERROR") as logged,
        ):
            self.actions.text_highlight_spike_next()

        self.assertIn("read only", "\n".join(logged.output))
        self.talon.notify.assert_called_with(
            "Highlight word", "Unable to update the highlighted word."
        )
        self.assertIsNone(self.module._session)
        self.assertEqual(self.module.tag_ctx.tags, [])

    def test_app_focus_and_text_changes_each_prevent_another_selection(self):
        for change in ("app", "focus", "text"):
            with self.subTest(change=change):
                self.talon.active_app = types.SimpleNamespace(pid=1, name="Editor")
                self.element.attrs.update(AXFocused=True, AXValue="one two one")
                self.actions.text_highlight_spike_start("one")
                selected = self.element.attrs["AXSelectedTextRange"]
                if change == "app":
                    self.talon.active_app = types.SimpleNamespace(pid=2)
                elif change == "focus":
                    self.element.attrs["AXFocused"] = False
                else:
                    self.element.attrs["AXValue"] = "changed"

                with self.assertLogs(level="ERROR"):
                    self.actions.text_highlight_spike_next()

                self.assertIsNone(self.module._session)
                self.assertIs(self.element.attrs["AXSelectedTextRange"], selected)


class DebugRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.talon.active_app = types.SimpleNamespace(pid=1, name="Example")
        self.module = load(self.talon, "accessibility/debug_snapshots.py")

    def test_partial_snapshot_notifies_without_changing_directory_permissions(self):
        with (
            patch.object(self.module, "_inventories", return_value=[]),
            patch.object(
                self.module,
                "write_snapshots",
                return_value=([Path("example.json")], True),
            ),
            patch("builtins.print"),
        ):
            self.module.Actions.accessibility_debug_snapshot()

        self.talon.notify.assert_called_with(
            "Accessibility debug snapshots",
            "Saved PARTIAL snapshots; see the errors and surfaces fields.",
        )

    def test_snapshot_write_failure_logs_and_notifies(self):
        with (
            patch.object(self.module, "_inventories", return_value=[]),
            patch.object(
                self.module, "write_snapshots", side_effect=PermissionError("read only")
            ),
            self.assertLogs(level="ERROR") as logged,
        ):
            self.module.Actions.accessibility_debug_snapshot()

        self.assertIn("PermissionError", "\n".join(logged.output))
        self.talon.notify.assert_called_with(
            "Accessibility debug snapshots",
            "Unable to capture or save accessibility snapshots.",
        )

    def test_inventory_read_failure_logs_and_notifies(self):
        with (
            patch.object(self.module, "_inventories", side_effect=UIErr("unavailable")),
            self.assertLogs(level="ERROR"),
        ):
            self.module.Actions.accessibility_debug_inventory()

        self.talon.notify.assert_called_with(
            "Accessibility debug inventory",
            "Unable to read the focused accessibility surfaces.",
        )

    def test_no_active_app_does_not_attempt_capture(self):
        self.talon.active_app = None
        with patch.object(self.module, "_inventories") as inventories:
            self.module.Actions.accessibility_debug_inventory()
            self.module.Actions.accessibility_debug_snapshot()

        inventories.assert_not_called()
        self.assertEqual(self.talon.notify.call_count, 2)


if __name__ == "__main__":
    unittest.main()
