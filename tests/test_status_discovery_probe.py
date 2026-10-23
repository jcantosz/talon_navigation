import importlib.util
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "status" / "discovery.py"


@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float

    def contains(self, x, y):
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


class Element:
    def __init__(self, role, frame=None, parent=None, **attrs):
        self.attrs = {"AXRole": role, "AXFrame": frame, "AXParent": parent, **attrs}

    def get(self, key):
        return self.attrs.get(key)


class DiscoveryProbeTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "discovery_probe_under_test", SOURCE
        )
        self.probe = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.probe
        spec.loader.exec_module(self.probe)
        self.addCleanup(sys.modules.pop, spec.name)
        self.screens = [SimpleNamespace(rect=Rect(0, 0, 100, 80))]
        self.front = Element("AXApplication")
        self.main_bars = [Element("AXMenuBar", Rect(0, 0, 100, 24), self.front)]
        self.front.attrs["AXMenuBar"] = self.main_bars[0]
        self.bars = []
        self.covered = []
        self.empty = []
        self.hidden_bar = False
        self.window = Element("AXWindow")
        self.ui = SimpleNamespace(
            screens=lambda: self.screens,
            element_at=self.hit,
            active_app=lambda: SimpleNamespace(element=self.front),
            apps=lambda: self.fail("Parent discovery must not enumerate applications"),
        )

    def add_bar(self):
        owner = Element("AXApplication")
        bar = Element("AXMenuBar", Rect(0, 0, 100, 24), owner, AXChildren=[])
        self.bars.append(bar)
        return bar

    def add_icon(self, bar, frame, **attrs):
        icon = Element("AXMenuBarItem", frame, bar, AXSubrole="AXMenuExtra", **attrs)
        bar.get("AXChildren").append(icon)
        return icon

    def hit(self, x, y):
        if any(rect.contains(x, y) for rect in self.empty):
            raise RuntimeError("No element found.")
        if self.hidden_bar or any(rect.contains(x, y) for rect in self.covered):
            return self.window
        for bar in reversed(self.bars):
            for item in bar.get("AXChildren"):
                frame = item.get("AXFrame")
                if (
                    not item.get("AXHidden")
                    and frame is not None
                    and frame.contains(x, y)
                ):
                    return item.get("hit_child") or item
        for bar in self.main_bars:
            if bar.get("AXFrame").contains(x, y):
                return bar
        raise RuntimeError("No element found.")

    def visible_frame(self, element):
        frame = element.get("AXFrame")
        if (
            element.get("AXHidden")
            or frame is None
            or frame.width <= 0
            or frame.height <= 0
        ):
            return None
        return (
            frame
            if any(
                frame.x < screen.rect.x + screen.rect.width
                and frame.x + frame.width > screen.rect.x
                and frame.y < screen.rect.y + screen.rect.height
                and frame.y + frame.height > screen.rect.y
                for screen in self.screens
            )
            else None
        )

    def is_unobstructed(self, element, frame):
        try:
            hit = self.hit(frame.x + frame.width / 2, frame.y + frame.height / 2)
        except RuntimeError as error:
            if str(error) != "No element found.":
                raise
            return False
        for _ in range(12):
            if hit is None:
                return False
            if hit == element:
                return True
            hit = hit.get("AXParent")
        return False

    def baseline(self):
        items = [
            item
            for bar in self.bars
            for item in bar.get("AXChildren")
            if (
                item.get("AXRole") == "AXMenuExtra"
                or item.get("AXSubrole") == "AXMenuExtra"
            )
            and item.get("AXEnabled") is not False
            and (frame := self.visible_frame(item)) is not None
            and self.is_unobstructed(item, frame)
        ]
        return sorted(
            items, key=lambda item: (item.get("AXFrame").x, item.get("AXFrame").y)
        )

    def scan(self, step=1):
        return self.probe.discover(
            self.ui, self.visible_frame, self.is_unobstructed, step=step
        )

    def test_matches_all_provider_contents_and_owners_without_enumerating_apps(self):
        first, second = self.add_bar(), self.add_bar()
        self.add_icon(first, Rect(70, 4, 10, 16))
        self.add_icon(first, Rect(90, 4, 10, 16))
        self.add_icon(second, Rect(50, 4, 10, 16))
        result = self.scan()
        self.assertEqual([item.element for item in result.items], self.baseline())
        self.assertEqual(len(result.bars), 2)
        self.assertTrue(
            all(item.application == item.bar.get("AXParent") for item in result.items)
        )

    def test_single_point_icon_is_found_but_sparse_scan_can_miss_its_parent(self):
        self.add_icon(self.add_bar(), Rect(37.2, 4, 1, 16))
        self.assertEqual([item.element for item in self.scan().items], self.baseline())
        self.assertEqual(len(self.baseline()), 1)
        self.assertEqual(self.scan(8).items, [])

    def test_one_row_can_miss_vertically_offset_custom_accessibility_bounds(self):
        icon = self.add_icon(self.add_bar(), Rect(70, 1, 6, 4))
        self.assertEqual(self.baseline(), [icon])
        self.assertEqual(self.scan().items, [])

    def test_hidden_disabled_offscreen_and_zero_size_items_are_excluded(self):
        bar = self.add_bar()
        self.add_icon(bar, Rect(70, 4, 10, 16))
        self.add_icon(bar, Rect(40, 4, 10, 16), AXHidden=True)
        self.add_icon(bar, Rect(50, 4, 10, 16), AXEnabled=False)
        self.add_icon(bar, Rect(110, 4, 10, 16))
        self.add_icon(bar, Rect(0, 0, 0, 0))
        bar.get("AXChildren").append(Element("AXMenuBarItem", Rect(10, 0, 10, 24), bar))
        self.assertEqual([item.element for item in self.scan().items], self.baseline())
        self.assertEqual(len(self.baseline()), 1)

    def test_covered_items_are_excluded_even_when_their_parent_is_discovered(self):
        bar = self.add_bar()
        self.add_icon(bar, Rect(60, 4, 10, 16))
        self.add_icon(bar, Rect(80, 4, 10, 16))
        self.covered.append(Rect(80, 0, 10, 24))
        self.assertEqual([item.element for item in self.scan().items], self.baseline())
        self.assertEqual(len(self.baseline()), 1)

    def test_accessibility_children_can_identify_the_status_item_parent(self):
        icon = self.add_icon(self.add_bar(), Rect(70, 4, 10, 16))
        icon.attrs["hit_child"] = Element("AXImage", icon.get("AXFrame"), icon)
        self.assertEqual([item.element for item in self.scan().items], [icon])

    def test_multiple_monitors_with_different_bar_heights_and_offsets(self):
        self.screens.append(SimpleNamespace(rect=Rect(200, 100, 100, 100)))
        self.main_bars.append(Element("AXMenuBar", Rect(200, 100, 100, 48), self.front))
        bar = self.add_bar()
        self.add_icon(bar, Rect(70, 8, 10, 8))
        self.add_icon(bar, Rect(270, 120, 10, 8))
        result = self.scan()
        self.assertEqual(result.rows, [12, 124])
        self.assertEqual([item.element for item in result.items], self.baseline())
        self.assertEqual(len(result.bars), 1)

    def test_empty_hit_regions_do_not_abort_discovery(self):
        self.add_icon(self.add_bar(), Rect(70, 4, 10, 16))
        self.empty.append(Rect(40, 0, 5, 24))
        result = self.scan()
        self.assertEqual([item.element for item in result.items], self.baseline())
        self.assertGreater(result.empty_hits, 0)

    def test_hidden_bar_matches_empty_reference(self):
        self.add_icon(self.add_bar(), Rect(70, 4, 10, 16))
        self.hidden_bar = True
        self.assertEqual(self.scan().items, [])
        self.assertEqual(self.baseline(), [])

    def test_unknown_menu_bar_height_is_an_explicit_validation_failure(self):
        self.hidden_bar = True
        self.front.attrs["AXMenuBar"] = None
        with self.assertRaisesRegex(RuntimeError, "Cannot determine"):
            self.scan()

    def test_unexpected_hit_errors_are_not_silently_ignored(self):
        def failed(x, y):
            raise RuntimeError("Unexpected accessibility failure")

        self.ui.element_at = failed
        with self.assertRaisesRegex(RuntimeError, "Unexpected accessibility failure"):
            self.scan()

    def test_invalid_stride_is_rejected(self):
        for step in (0, -1, float("nan")):
            with self.subTest(step=step), self.assertRaises(ValueError):
                self.scan(step)


if __name__ == "__main__":
    unittest.main()
