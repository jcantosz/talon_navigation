import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

package = types.ModuleType("inventory_under_test")
package.__path__ = [str(Path(__file__).resolve().parents[1])]
with patch.dict(sys.modules, {"talon": None, package.__name__: package}):
    inventory_core = importlib.import_module(f"{package.__name__}.ax.inventory")
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


class BoundaryElement(Element):
    def get(self, name):
        if name == "AXChildren":
            raise AssertionError("Boundary children must not be fetched")
        return super().get(name)


class AccessibilityInventoryTests(unittest.TestCase):
    def test_depth_bound_stops_repeated_search_field_children(self):
        class RepeatedElement(Element):
            def get(self, name):
                if name == "AXChildren":
                    return (RepeatedElement({"AXRole": "AXTextField"}),)
                return super().get(name)

        root = RepeatedElement({"AXRole": "AXWindow"})
        result = inventory_core.collect(root, UIError, max_depth=2)
        self.assertFalse(result.truncated)
        self.assertEqual(len(result.nodes), 3)

    def test_depth_boundary_includes_marker_but_not_its_children(self):
        marker = BoundaryElement({"AXRole": "AXGroup"})
        root = Element({"AXRole": "AXWindow"}, children=(marker,))
        result = inventory_core.collect(root, UIError, max_depth=1)
        self.assertEqual([n.path for n in result.nodes], [(), (0,)])
        self.assertFalse(result.truncated)
        with self.assertRaisesRegex(AssertionError, "must not be fetched"):
            inventory_core.collect(root, UIError)

    def test_content_pruning_keeps_following_sibling_panes(self):
        table = BoundaryElement({"AXRole": "AXTable"})
        message = Element({"AXRole": "AXWebArea"})
        root = Element({"AXRole": "AXWindow"}, children=(table, message))
        result = inventory_core.collect(root, UIError, stop_roles=("AXTable",))
        self.assertEqual(
            [n.role for n in result.nodes], ["AXWindow", "AXTable", "AXWebArea"]
        )
        self.assertFalse(result.errors)

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


if __name__ == "__main__":
    unittest.main()
