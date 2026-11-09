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
            labels=types.SimpleNamespace(show_names=Mock(), hide=Mock())
        )
        self.app = types.SimpleNamespace(notify=Mock())
        talon = types.ModuleType("talon")
        talon.actions, talon.app = self.actions, self.app
        talon.ui = types.SimpleNamespace(Element=Element, UIErr=UIErr)
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

    def test_fallback_failure_is_not_swallowed(self):
        self.actions.labels.show_names.side_effect = TypeError("unsupported")
        with self.assertLogs(level="ERROR"), self.assertRaises(TypeError):
            self.module.show([self.pane])


if __name__ == "__main__":
    unittest.main()
