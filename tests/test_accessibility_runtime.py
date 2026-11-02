import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_TAG = "user.application_labels_active"


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

    def get(self, key):
        if self.dead:
            raise UIErr("element is gone")
        return self.attrs.get(key)

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
            after=Mock(side_effect=lambda *_: object()), cancel=Mock()
        )
        self.settings = {
            "user.accessibility_query_max_depth": 0,
            "user.accessibility_query_timeout": 1.0,
            "user.accessibility_defer_web_areas": False,
            "user.accessibility_clip_to_surface": False,
            "user.accessibility_activation_disallowed_bundles": "",
        }
        self.query_results = []
        self.active_app = None
        self.active_window = types.SimpleNamespace(id=1)
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
            active_menu=lambda: None,
            element_at=Mock(),
            register=Mock(),
        )
        talon = types.SimpleNamespace(
            Module=self.Module,
            Context=self.Context,
            actions=types.SimpleNamespace(
                labels=labels,
                next=self.next_action,
                sleep=Mock(),
                user=self.user,
            ),
            app=types.SimpleNamespace(notify=self.notify),
            axquery=types.SimpleNamespace(
                query_all=lambda *args, **kwargs: list(self.query_results)
            ),
            cron=self.cron,
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
                self.assertEqual(len(self.talon.native_calls), 1)
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
            refresh.assert_called_once_with()
            self.assertEqual(session.targets, [self.close, self.button])

            self.application.attrs["AXFocusedWindow"] = self.window
            self.actions.accessibility_show_application_numbers()
            job = self.module._session.deferred_job
            self.module._stop()
            self.talon.cron.cancel.assert_called_with(job)

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
        self.talon.cron.cancel.assert_called_with(job)
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
        self.talon.cron.cancel.assert_called_once_with(job)
        self.assert_session_active(False)

    def test_unsupported_activation_attributes_are_not_an_operational_failure(self):
        with patch.object(Element, "__setitem__", side_effect=UIErr("unsupported")):
            self.actions.accessibility_set_interfaces(True)

        self.talon.notify.assert_called_with(
            "Accessibility interfaces", "Enabled: No supported writable interfaces"
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
