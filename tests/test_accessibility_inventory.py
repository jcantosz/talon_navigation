import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

package = types.ModuleType("inventory_under_test")
package.__path__ = [str(Path(__file__).resolve().parents[1])]
with patch.dict(sys.modules, {"talon": None, package.__name__: package}):
    inventory_core = importlib.import_module(
        f"{package.__name__}.accessibility.inventory_core"
    )
    roles = importlib.import_module(f"{package.__name__}.lib.roles")


class UIError(Exception):
    pass


class Element:
    def __init__(self, attributes=None, actions=(), children=()):
        self.values = attributes or {}
        self.attrs = self.values
        self.actions = actions
        self.values["AXChildren"] = children

    def get(self, name):
        return self.values.get(name)


class BrokenElement(Element):
    @property
    def attrs(self):
        raise UIError("unavailable")

    @attrs.setter
    def attrs(self, value):
        pass


class Rect:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class AccessibilityInventoryTests(unittest.TestCase):
    def test_inventory_uses_shared_roles_without_requiring_talon(self):
        self.assertIs(inventory_core.CONTROL_ROLES, roles.CONTROL_ROLES)
        self.assertEqual(
            roles.CONTROL_ROLES,
            {
                "AXButton",
                "AXCheckBox",
                "AXComboBox",
                "AXDisclosureTriangle",
                "AXLink",
                "AXMenuButton",
                "AXMenuItem",
                "AXPopUpButton",
                "AXRadioButton",
                "AXSearchField",
                "AXSlider",
                "AXSwitch",
                "AXTab",
                "AXTextArea",
                "AXTextField",
            },
        )

    def test_identifies_the_show_numbers_predicate(self):
        button = Element(
            {"AXRole": "AXButton", "AXPosition": (10, 20)},
            {"AXPress": "press"},
        )
        unpressable = Element({"AXRole": "AXButton", "AXPosition": (20, 20)})
        root = Element({"AXRole": "AXWindow"}, children=(button, unpressable))

        result = inventory_core.collect(root, UIError)

        self.assertEqual(len(result.nodes), 3)
        self.assertTrue(result.nodes[1].matches_show_numbers)
        self.assertFalse(result.nodes[2].matches_show_numbers)
        self.assertTrue(result.nodes[2].is_control)

    def test_reports_unreadable_nodes_without_hiding_other_controls(self):
        button = Element(
            {"AXRole": "AXButton", "AXPosition": (10, 20)},
            ("AXPress",),
        )
        root = Element(
            {"AXRole": "AXWindow"},
            children=(BrokenElement(), button),
        )

        result = inventory_core.collect(root, UIError)

        self.assertEqual(len(result.nodes), 2)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("root/0", result.errors[0])

    def test_node_limit_is_reported(self):
        root = Element(
            {"AXRole": "AXWindow"},
            children=(Element({"AXRole": "AXButton"}),),
        )

        result = inventory_core.collect(root, UIError, limit=1)

        self.assertTrue(result.truncated)
        self.assertEqual(len(result.nodes), 1)

    def test_visible_number_targets_exclude_layout_and_offscreen_nodes(self):
        bounds = [Rect(0, 0, 100, 100)]
        elements = (
            Element(
                {
                    "AXRole": "AXButton",
                    "AXPosition": (10, 10),
                    "AXFrame": Rect(10, 10, 20, 20),
                    "AXEnabled": True,
                },
                ("AXPress",),
            ),
            Element(
                {
                    "AXRole": "AXGroup",
                    "AXPosition": (10, 10),
                    "AXFrame": Rect(10, 10, 20, 20),
                },
                ("AXPress",),
            ),
            Element(
                {
                    "AXRole": "AXButton",
                    "AXPosition": (200, 200),
                    "AXFrame": Rect(200, 200, 20, 20),
                },
                ("AXPress",),
            ),
        )
        result = inventory_core.collect(
            Element({"AXRole": "AXWindow"}, children=elements), UIError
        )

        self.assertTrue(result.nodes[1].is_visible_number_target(bounds))
        self.assertFalse(result.nodes[2].is_visible_number_target(bounds))
        self.assertFalse(result.nodes[3].is_visible_number_target(bounds))


if __name__ == "__main__":
    unittest.main()
