import unittest
from unittest.mock import patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        ActionFailed,
        ApplicationTestCase,
        Element,
        frame,
    )
else:
    from accessibility_support import (
        ActionFailed,
        ApplicationTestCase,
        Element,
        frame,
    )


class ApplicationRowsTests(ApplicationTestCase):
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
                self.assertIs(self.collection.row_activation_target(row), row)

        row = Element(AXRole="AXRow", AXFrame=frame(x=0, width=400))
        row.attrs["AXChildren"] = [
            Element(AXRole="AXGroup", AXFrame=frame(x=20, width=360)),
            Element(AXRole="AXButton", AXFrame=frame(x=340, width=20)),
        ]
        self.assertIs(self.collection.row_activation_target(row), row)

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


if __name__ == "__main__":
    unittest.main()
