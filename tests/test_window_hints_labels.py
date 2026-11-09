import importlib.util
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Rect:
    def __init__(self, x, y, width, height):
        self.x, self.y, self.width, self.height = x, y, width, height
        self.pos = (x, y)


class Element:
    def __init__(self, ref):
        self._ref = ref

    def copy(self):
        return Element(self._ref)

    def get(self, key, default=None):
        return self._ref.get(key, default)

    def perform(self, action):
        self._ref["perform"](action)


class UIErr(Exception):
    pass


class PaneLabels(unittest.TestCase):
    def setUp(self):
        self.actions = types.SimpleNamespace(
            labels=types.SimpleNamespace(show_names=Mock(), show=Mock(), hide=Mock())
        )
        self.app = types.SimpleNamespace(notify=Mock())
        talon = types.ModuleType("talon")
        talon.actions, talon.app = self.actions, self.app
        talon.ui = types.SimpleNamespace(Element=Element, UIErr=UIErr)
        talon.Module = lambda: types.SimpleNamespace(
            setting=Mock(), tag=Mock(), list=Mock(), action_class=lambda cls: cls
        )
        talon.Context = lambda: types.SimpleNamespace(
            lists={}, tags=[], action_class=lambda _: lambda cls: cls
        )
        talon.cron = types.SimpleNamespace(after=Mock(), cancel=Mock())
        talon.ctrl = types.SimpleNamespace(mouse_move=Mock())
        talon.ui.register = Mock()
        talon.ui.ActionFailed = UIErr
        talon.settings = types.SimpleNamespace(
            get=Mock(return_value="com.microsoft.VSCode=vscode")
        )
        talon.ui.active_app = Mock(
            return_value=types.SimpleNamespace(bundle="com.microsoft.VSCode")
        )
        self.talon = talon
        talon_types = types.ModuleType("talon.types")
        talon_types.Rect = Rect
        talon_types.Size2d = lambda **kwargs: types.SimpleNamespace(**kwargs)
        path = Path(__file__).parents[1] / "window_hints/labels.py"
        spec = importlib.util.spec_from_file_location("pane_label_under_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"talon": talon, "talon.types": talon_types}):
            spec.loader.exec_module(self.module)
        self.ref = {
            "AXFrame": Rect(100, 200, 400, 300),
            "AXRole": "AXGroup",
            "AXTitle": "Original",
            "perform": Mock(),
        }
        self.original = Element(self.ref)
        self.pane = types.SimpleNamespace(ref=self.original, name="editor")

    def _runtime(self):
        root = types.ModuleType("hints_runtime_test")
        root.__path__ = [str(Path(__file__).parents[1])]
        package = types.ModuleType(f"{root.__name__}.window_hints")
        package.__path__ = [str(Path(__file__).parents[1] / "window_hints")]
        name = f"{package.__name__}.window_hints"
        spec = importlib.util.spec_from_file_location(
            name, Path(package.__path__[0]) / "window_hints.py"
        )
        runtime = importlib.util.module_from_spec(spec)
        with patch.dict(
            "sys.modules",
            {
                "talon": self.talon,
                root.__name__: root,
                package.__name__: package,
                f"{package.__name__}.labels": self.module,
                f"{package.__name__}.section_actions": types.SimpleNamespace(
                    refresh_scroll_direction=Mock()
                ),
            },
        ):
            spec.loader.exec_module(runtime)
        return runtime

    def test_profile_walk_bounds_content_without_changing_generic_walk(self):
        runtime = self._runtime()
        owner, root = object(), object()
        with (
            patch.object(runtime.ui, "active_app", return_value=owner, create=True),
            patch.object(runtime, "focused_surfaces", return_value=[("window", root)]),
            patch.object(runtime, "collect") as collect,
        ):
            runtime._walk({"max_depth": 7})
            collect.assert_called_once_with(
                root,
                UIErr,
                max_depth=7,
                stop_roles=("AXTable", "AXOutline", "AXTextField", "AXTextArea"),
            )
            collect.reset_mock()
            runtime._walk()
            collect.assert_called_once_with(root, UIErr)

    def test_unreadable_root_reports_runtime_error_not_index_error(self):
        runtime = self._runtime()
        with self.assertRaisesRegex(RuntimeError, "no readable AX tree"):
            runtime._check_window(types.SimpleNamespace(nodes=[]))

    def test_profile_nodes_include_native_help_and_identifier(self):
        runtime = self._runtime()
        self.ref["AXHelp"] = "Mail"
        node = types.SimpleNamespace(
            path=(0,),
            frame=self.ref["AXFrame"],
            role="AXButton",
            title="",
            description="",
            identifier="Search Bar",
            element=self.original,
        )
        result = runtime._profile_nodes(types.SimpleNamespace(nodes=[node]))
        self.assertEqual(result[0].identifier, "Search Bar")
        self.assertEqual(result[0].help, "Mail")
        self.assertIs(result[0].ref, self.original)

    def test_command_rendering_choice_reaches_same_profile_targets(self):
        runtime = self._runtime()
        inventory = types.SimpleNamespace(
            truncated=False,
            errors=[],
            nodes=[types.SimpleNamespace(element=self.original)],
        )
        with (
            patch.object(runtime, "_walk", return_value=(inventory, 0)),
            patch.object(runtime, "_profile_nodes", return_value=[]),
            patch.object(runtime, "_window_rect", return_value=None),
            patch.object(runtime, "_check_window"),
            patch.object(
                runtime.ui,
                "active_app",
                return_value=types.SimpleNamespace(bundle="com.microsoft.VSCode"),
            ),
            patch.object(runtime.profiles, "load_profile", return_value={}),
            patch.object(runtime.profiles, "find_panes", return_value=[self.pane]),
            patch.object(
                runtime.profiles,
                "report",
                return_value={"coverage": 0, "overlaps": [], "ok": True},
            ),
            patch.object(runtime.pane_labels, "show") as show,
            patch("builtins.print"),
        ):
            self.pane.frame = self.ref["AXFrame"]
            for names in (True, False):
                runtime.Actions.window_hints_show(names=names)
                show.assert_called_with([self.pane], names=names)
            runtime.profiles.load_profile.assert_called_with("vscode")

    def test_dismissal_or_new_focus_during_walk_prevents_late_hint_render(self):
        for cancel in ("hide", "focus"):
            runtime = self._runtime()
            inventory = types.SimpleNamespace(truncated=False, errors=[])

            def finish_walk(_):
                if cancel == "hide":
                    runtime._session.stop()
                else:
                    runtime._session.focus_changed()
                return (inventory, 0)

            with (
                patch.object(runtime, "_walk", side_effect=finish_walk),
                patch.object(runtime, "_profile_nodes", return_value=[]),
                patch.object(runtime.profiles, "load_profile", return_value={}),
                patch.object(runtime.profiles, "find_panes", return_value=[self.pane]),
                patch.object(runtime.pane_labels, "show") as show,
            ):
                runtime.Actions.window_hints_show()
            show.assert_not_called()

    def test_number_startup_does_not_preresolve_or_hide_twice(self):
        runtime = self._runtime()
        start = Mock(side_effect=lambda resolve: resolve())
        self.actions.user = types.SimpleNamespace(
            accessibility_show_section_numbers=start
        )
        with (
            patch.object(
                runtime.section_actions, "run", side_effect=lambda op: op(), create=True
            ),
            patch.object(
                runtime, "_resolve_section", return_value=self.original
            ) as resolve,
        ):
            runtime.Actions.window_section_number("editor")
        start.assert_called_once()
        resolve.assert_called_once_with("editor")
        self.actions.labels.hide.assert_not_called()

    def test_active_reference_lookup_never_loads_profiles_or_walks(self):
        runtime = self._runtime()
        with (
            patch.object(
                runtime._sections, "resolve", return_value=self.original
            ) as resolve,
            patch.object(
                runtime, "_walk", side_effect=AssertionError("Unnecessary walk")
            ),
            patch.object(
                runtime.profiles,
                "load_profile",
                side_effect=AssertionError("Unnecessary profile load"),
            ),
        ):
            for _ in range(20):
                self.assertIs(runtime._resolve_section("editor"), self.original)
        self.assertEqual(resolve.call_count, 20)

    def test_focus_invalidates_section_references_even_after_hints_are_hidden(self):
        runtime = self._runtime()
        runtime._sections.targets["editor"] = self.original
        runtime.ctx.lists["user.window_sections"] = {"editor": "editor"}
        runtime._session.stop()
        runtime._focus_changed()
        self.assertEqual(runtime._sections.targets, {})
        self.assertEqual(runtime.ctx.lists["user.window_sections"], {})

    def test_profile_selection_tracks_active_bundle_and_mapping_changes(self):
        runtime = self._runtime()
        self.talon.settings.get.return_value = (
            "com.microsoft.VSCode=vscode, mail=outlook"
        )
        self.assertEqual(runtime._current_profile(), "vscode")
        self.talon.ui.active_app.return_value = types.SimpleNamespace(bundle="mail")
        self.assertEqual(runtime._current_profile(), "outlook")
        self.talon.settings.get.return_value = "mail=slack"
        self.assertEqual(runtime._current_profile(), "slack")
        self.talon.ui.active_app.return_value = types.SimpleNamespace(bundle="unknown")
        self.assertEqual(runtime._current_profile(), "")
        self.talon.ui.active_app.return_value = None
        self.assertEqual(runtime._current_profile(), "")

    def test_invalid_mapping_reports_error_without_generic_fallback(self):
        runtime = self._runtime()
        self.talon.settings.get.return_value = "bundle=slack,bundle=outlook"
        with (
            patch.object(runtime, "_show_generic") as generic,
            self.assertLogs(level="ERROR"),
        ):
            runtime.Actions.window_hints_show()
        generic.assert_not_called()
        self.assertIsNone(runtime._session.mode)
        self.app.notify.assert_called_once()

    def test_name_and_centre_geometry_without_native_mutation(self):
        proxy = self.module.PaneLabel(self.original, "editor")
        self.assertIsInstance(proxy, Element)
        self.assertEqual(proxy.get("AXTitle"), "editor")
        self.assertEqual(proxy["AXDescription"], "editor")
        self.assertEqual(proxy.AXPosition, (294, 344))
        size = proxy.get("AXSize")
        self.assertEqual((size.width, size.height), (12, 12))
        self.assertEqual(self.ref["AXTitle"], "Original")
        self.assertEqual(self.ref["AXFrame"].width, 400)
        self.assertEqual(proxy.get("AXRole"), "AXGroup")

    def test_actions_are_performed_on_real_reference(self):
        proxy = self.module.PaneLabel(self.original, "editor")
        proxy.perform("AXPress")
        self.ref["perform"].assert_called_once_with("AXPress")
        self.assertIs(proxy._ref, self.original._ref)

    def test_numeric_suffixes_are_speakable_names(self):
        for name, expected in (
            ("tabs", "tabs"),
            ("tabs 1", "tabs one"),
            ("tabs 2", "tabs two"),
            ("editor 12", "editor twelve"),
            ("tabs 21", "tabs twenty one"),
            ("tabs 100", "tabs one hundred"),
            ("tabs 102", "tabs one hundred two"),
            ("tabs 1000", "tabs one thousand"),
        ):
            with self.subTest(name=name):
                proxy = self.module.PaneLabel(self.original, name)
                self.assertEqual(proxy.get("AXTitle"), expected)

    def test_geometry_tracks_group_and_negative_coordinates(self):
        proxy = self.module.PaneLabel(self.original, "editor")
        self.ref["AXFrame"] = Rect(-1000, -300, 200, 100)
        self.assertEqual(proxy.get("AXPosition"), (-906, -256))

    def test_geometry_failure_reports_and_falls_back(self):
        proxy = self.module.PaneLabel(self.original, "editor")
        with patch.object(self.module, "Rect", side_effect=ValueError("bad geometry")):
            with self.assertLogs(level="ERROR"):
                self.assertIs(proxy.get("AXFrame"), self.ref["AXFrame"])
        self.app.notify.assert_called_once()
        self.assertIs(proxy.get("AXFrame"), self.ref["AXFrame"])

    def test_renderer_failure_uses_original_group(self):
        self.actions.labels.show_names.side_effect = [TypeError("unsupported"), None]
        with self.assertLogs(level="ERROR"):
            self.module.show([self.pane])
        self.assertEqual(self.actions.labels.show_names.call_count, 2)
        self.assertEqual(
            self.actions.labels.show_names.call_args.args[0], [self.original]
        )
        self.app.notify.assert_called_once()
        self.actions.labels.hide.assert_called_once()

    def test_numbers_use_the_same_centred_element_and_real_reference(self):
        self.module.show([self.pane], names=False)
        self.actions.labels.show_names.assert_not_called()
        proxy = self.actions.labels.show.call_args.args[0][0]
        self.assertIs(proxy._ref, self.original._ref)
        self.assertEqual(proxy.get("AXPosition"), (294, 344))

    def test_numeric_renderer_failure_uses_original_group(self):
        self.actions.labels.show.side_effect = [TypeError("unsupported"), None]
        with self.assertLogs(level="ERROR"):
            self.module.show([self.pane], names=False)
        self.assertEqual(self.actions.labels.show.call_args.args[0], [self.original])
        self.actions.labels.show_names.assert_not_called()

    def test_fallback_failure_is_not_swallowed(self):
        self.actions.labels.show_names.side_effect = TypeError("unsupported")
        with self.assertLogs(level="ERROR"), self.assertRaises(TypeError):
            self.module.show([self.pane])


if __name__ == "__main__":
    unittest.main()
