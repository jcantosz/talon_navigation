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

    def test_nested_numbered_row_keeps_its_text_and_selection(self):
        channel, text = self.text_row(frame(x=40, y=20, width=60, height=1))
        channel.attrs["AXFrame"] = frame(x=0, y=20, width=400, height=1)
        content = channel.get("AXChildren")[0]
        content.attrs.update(AXFrame=channel.get("AXFrame"), AXParent=channel)
        content.actions = ["AXPress"]
        wrapper = Element(AXRole="AXGroup", AXChildren=[channel])
        wrapper.actions = []
        section = Element(
            AXRole="AXRow",
            AXChildren=[wrapper],
            AXFrame=channel.get("AXFrame"),
        )
        self.talon.query_results = [section, channel, self.button]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [section, channel, self.button])
        self.assertEqual(self.module._session.labelled, [section, text, self.button])
        self.talon.dispatch_labels("select", 2)

        self.assertEqual(content.performed, ["AXPress"])
        self.assertEqual(channel.performed, [])
        self.assertEqual(section.performed, [])

    def test_badge_search_traverses_unnumbered_nested_row(self):
        nested, text = self.text_row(frame(x=40, y=25, width=60, height=18))
        nested.actions = []
        row = Element(
            AXRole="AXRow", AXChildren=[nested], AXFrame=frame(x=0, width=400)
        )
        self.talon.query_results = [row]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.labelled, [text])

    def test_shared_text_anchors_fall_back_without_losing_targets(self):
        row, text = self.text_row(frame(x=40, y=25, width=60, height=18))
        other = Element(
            AXRole="AXRow",
            AXChildren=row.get("AXChildren"),
            AXFrame=row.get("AXFrame"),
        )
        self.talon.query_results = [row, other, self.button]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [row, other, self.button])
        self.assertEqual(self.module._session.labelled, [row, other, self.button])
        self.talon.dispatch_labels("select", 3)
        self.assertIn(("select", (3,)), self.talon.native_calls)
        self.assertEqual(text.performed, [])

    def test_anchor_cannot_borrow_a_separately_numbered_text_element(self):
        row, text = self.text_row(frame(x=40, y=25, width=60, height=18))
        labels = self.session_module.label_elements([row, text])

        self.assertEqual(labels, [row, text])

    def test_equal_but_distinct_text_proxies_are_colliding_anchors(self):
        class TextProxy(Element):
            def __eq__(self, other):
                return isinstance(other, TextProxy)

        rows = [
            Element(
                AXRole="AXRow",
                AXChildren=[
                    TextProxy(
                        AXRole="AXStaticText",
                        AXFrame=frame(x=40, y=25, width=60, height=18),
                    )
                ],
                AXFrame=frame(x=0, width=400),
            )
            for _ in range(2)
        ]
        self.talon.query_results = rows

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.labelled, rows)

    def test_unchanged_anchors_do_not_use_ax_equality(self):
        class NoComparison(Element):
            def __eq__(self, other):
                raise AssertionError("Unchanged anchors should not need AX equality")

        targets = [NoComparison(AXRole="AXButton", AXFrame=frame()) for _ in range(100)]

        anchors = self.session_module.label_elements(targets)

        self.assertTrue(all(a is b for a, b in zip(anchors, targets)))

    def test_combo_arrow_badge_uses_combo_bounds_but_presses_arrow(self):
        arrow = Element(AXRole="AXButton", AXTitle="", AXFrame=frame(x=85, width=15))
        arrow.actions = ["AXPress", "AXShowMenu"]
        combo = Element(
            AXRole="AXComboBox",
            AXFrame=frame(x=0, width=100),
            AXChildren=[arrow],
        )
        combo.actions = ["AXConfirm", "AXShowMenu"]
        arrow.attrs["AXParent"] = combo
        self.talon.query_results = [arrow]

        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.module._session.targets, [arrow])
        self.assertEqual(self.module._session.labelled, [combo])
        self.talon.dispatch_labels("select", 1)
        self.assertEqual(arrow.performed, ["AXPress"])
        self.assertEqual(combo.performed, [])
        self.assertIsNotNone(self.module._session)

    def test_combo_arrow_anchor_requires_containment_and_unique_pressable_child(self):
        arrow = Element(AXRole="AXButton", AXFrame=frame(x=85, width=15))
        combo = Element(
            AXRole="AXComboBox",
            AXFrame=frame(x=0, width=100),
            AXChildren=[arrow],
        )
        combo.actions = ["AXShowMenu"]
        arrow.attrs["AXParent"] = combo
        other = Element(AXRole="AXButton", AXFrame=frame())
        for children, bounds in (
            ([arrow, other], frame(x=0, width=100)),
            ([arrow], frame(x=0, width=50)),
        ):
            combo.attrs.update(AXChildren=children, AXFrame=bounds)
            self.assertIs(self.session_module.label_elements([arrow])[0], arrow)

    def test_distinct_text_frames_do_not_use_ax_equality(self):
        class NoComparison(Element):
            def __eq__(self, other):
                raise AssertionError("Different frames should not need AX equality")

        rows = [
            Element(
                AXRole="AXRow",
                AXChildren=[
                    NoComparison(
                        AXRole="AXStaticText",
                        AXFrame=frame(x=40, y=25 + index, width=60, height=18),
                    )
                ],
                AXFrame=frame(x=0, height=200, width=400),
            )
            for index in range(100)
        ]

        anchors = self.session_module.label_elements(rows)

        self.assertTrue(
            all(
                anchor is row.get("AXChildren")[0] for anchor, row in zip(anchors, rows)
            )
        )

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
