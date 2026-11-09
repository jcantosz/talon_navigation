import sys
import types
import unittest
from unittest.mock import patch

if __package__:
    from .accessibility_support import Element, FakeTalon, frame, load
else:
    from accessibility_support import Element, FakeTalon, frame, load


class ActiveSectionTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeTalon()
        labels = types.SimpleNamespace(
            spoken_name=lambda name: name.replace(" 1", " one")
        )
        with patch.dict(
            sys.modules, {"talon_navigation_runtime.window_hints.labels": labels}
        ):
            self.module = load(self.fake, "window_hints/sections.py")
        self.window = Element()
        self.owner = types.SimpleNamespace(element=Element(AXFocusedWindow=self.window))
        self.fake.active_app = self.owner
        self.root = Element(AXWindow=self.window, AXFrame=frame())
        self.sections = self.module.ActiveSections()
        self.sections.publish(
            self.owner,
            self.window,
            "example",
            [types.SimpleNamespace(name="compose 1", ref=self.root)],
        )

    def test_reuses_real_root_for_both_names_without_discovery(self):
        for _ in range(10):
            self.assertIs(self.sections.resolve("compose one", "example"), self.root)
            self.assertIs(self.sections.resolve("compose 1", "example"), self.root)

    def test_focus_profile_window_and_explicit_invalidation_reject_old_sections(self):
        for change in ("app", "window", "profile", "clear"):
            with self.subTest(change=change):
                self.setUp()
                profile = "example"
                if change == "app":
                    self.fake.active_app = None
                elif change == "window":
                    self.owner.element.attrs["AXFocusedWindow"] = Element()
                elif change == "profile":
                    profile = "other"
                else:
                    self.sections.clear()
                with self.assertRaisesRegex(RuntimeError, "Show sections again"):
                    self.sections.resolve("compose one", profile)

    def test_dead_hidden_missing_and_invalid_geometry_fail_not_guess(self):
        with self.assertRaisesRegex(RuntimeError, "absent"):
            self.sections.resolve("compose", "example")
        for key, value in (("AXWindow", None), ("AXHidden", True), ("AXFrame", None)):
            self.root.attrs[key] = value
            with self.assertRaisesRegex(RuntimeError, "Show sections again"):
                self.sections.resolve("compose one", "example")
            self.setUp()
        self.root.dead = True
        with self.assertRaises(self.module.ui.UIErr):
            self.sections.resolve("compose one", "example")
