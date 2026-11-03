import unittest
from unittest.mock import Mock

if __package__:
    from .status_support import ActionFailed, Element, Rect, StatusLabelsTestCase
else:
    from status_support import ActionFailed, Element, Rect, StatusLabelsTestCase


class StatusControlTests(StatusLabelsTestCase):
    def test_panel_role_policy_keeps_existing_controls_and_exclusions(self):
        included = (
            "AXButton",
            "AXCheckBox",
            "AXComboBox",
            "AXDisclosureTriangle",
            "AXLink",
            "AXMenuButton",
            "AXPopUpButton",
            "AXRadioButton",
            "AXSearchField",
            "AXSlider",
            "AXSwitch",
            "AXTextField",
        )
        excluded = (
            "AXMenuItem",
            "AXTab",
            "AXTextArea",
            "AXRow",
            "AXGroup",
            "AXStaticText",
        )
        controls = [self.button(role, role=role) for role in (*included, *excluded)]
        panel = Element("AXWindow", children=controls)

        targets = self.module.surfaces.panel_targets(panel, self.owner)

        self.assertEqual(self.module.surfaces.PANEL_ROLES, set(included))
        self.assertEqual(
            [target.element for target in targets], controls[: len(included)]
        )

    def test_panel_role_policy_keeps_nonpressable_editable_controls(self):
        included = ("AXSlider", "AXTextField", "AXSearchField", "AXComboBox")
        controls = [
            Element(role, role, Rect(700, 60, 80, 30))
            for role in (*included, "AXButton", "AXTextArea", "AXTab")
        ]
        panel = Element("AXWindow", children=controls)

        targets = self.module.surfaces.panel_targets(panel, self.owner)

        self.assertEqual(
            [target.element for target in targets], controls[: len(included)]
        )

    def test_slider_selection_does_not_change_value(self):
        slider = self.button("Volume", role="AXSlider")
        self.open_panel(controls=[slider])
        self.labels.select(1)
        slider.perform.assert_not_called()
        self.assertEqual(self.visible, [slider])
        self.notify.assert_called_once()

    def test_explicit_slider_adjustment_uses_accessibility_increment(self):
        slider = self.button("Volume", role="AXSlider")
        slider.actions = {"AXIncrement": "increment", "AXDecrement": "decrement"}
        session, _ = self.open_panel(controls=[slider])
        self.commands.status_labels_adjust(1, "increase")
        slider.perform.assert_called_once_with("AXIncrement")
        self.tick(session, 3)
        self.assertEqual(self.visible, [slider])

    def test_repeated_adjustments_keep_labels_visible_without_waiting_for_a_transition(
        self,
    ):
        for names in (False, True):
            with self.subTest(names=names):
                self.labels.hide()
                self.owner.element.attrs["AXChildren"] = [self.bar]
                slider = self.button("Volume", role="AXSlider", AXValue=5)
                slider.actions = {
                    "AXIncrement": "increment",
                    "AXDecrement": "decrement",
                }

                def adjust(action):
                    slider.attrs["AXValue"] += 1 if action == "AXIncrement" else -1

                slider.perform.side_effect = adjust
                session, _ = self.open_panel(names, [slider])
                label = "Volume" if names else 1
                for operation in ("increase", "increase", "decrease"):
                    self.commands.status_labels_adjust(label, operation)
                    self.assertEqual(self.visible, [slider])
                    self.assertFalse(session.waiting)
                    self.assertIs(self.module._session, session)
                    self.tick(session)
                    self.assertEqual(self.visible, [slider])
                self.assertEqual(slider.get("AXValue"), 6)
                self.assertEqual(slider.perform.call_count, 3)
                self.notify.assert_not_called()

    def test_slider_resolution_uses_current_geometry_with_native_inset_rectangles(self):
        for names in (False, True):
            with self.subTest(names=names):
                self.labels.hide()
                self.owner.element.attrs["AXChildren"] = [self.bar]
                slider = self.button("Volume", role="AXSlider")
                slider.actions = {"AXIncrement": "increment"}
                session, _ = self.open_panel(names, [slider])
                slider.attrs["AXFrame"] = Rect(702.1, 60.2, 80, 6)
                self.commands.status_labels_adjust("Volume" if names else 1, "increase")
                slider.perform.assert_called_once_with("AXIncrement")
                self.assertEqual(self.visible, [slider])
                self.assertIs(self.module._session, session)
                self.notify.assert_not_called()

    def test_title_resolution_chooses_slider_not_a_larger_overlapping_button(self):
        slider = self.button("Volume", role="AXSlider")
        slider.actions = {"AXIncrement": "increment"}
        parent = Element(
            "AXButton",
            "Sound",
            Rect(680, 40, 150, 100),
            children=[slider],
            actions=("AXPress",),
        )
        self.open_panel(True, [parent])
        self.commands.status_labels_adjust("Volume", "increase")
        slider.perform.assert_called_once_with("AXIncrement")
        parent.perform.assert_not_called()
        self.notify.assert_not_called()

    def test_value_changes_do_not_rerender_or_hide_the_overlay(self):
        slider = self.button("Volume", role="AXSlider", AXValue=5)
        session, _ = self.open_panel(controls=[slider])
        session.show = Mock(wraps=session.show)
        for value in (6, 7, 8):
            slider.attrs["AXValue"] = value
            self.tick(session)
        session.show.assert_not_called()
        self.assertEqual(self.visible, [slider])

    def test_subpixel_frame_jitter_does_not_rerender_or_hide_the_overlay(self):
        control = self.button()
        session, _ = self.open_panel(controls=[control])
        session.show = Mock(wraps=session.show)
        for shift in (0.02, -0.03, 0.04):
            control.attrs["AXFrame"] = Rect(700 + shift, 60 + shift, 80 + shift, 30)
            self.tick(session)
        session.show.assert_not_called()
        self.assertEqual(self.visible, [control])

    def test_meaningful_geometry_change_updates_labels_without_explicit_hide(self):
        control = self.button()
        session, _ = self.open_panel(controls=[control])
        hide = self.labels.hide
        self.labels.hide = Mock(wraps=hide)
        session.show = Mock(wraps=session.show)
        control.attrs["AXFrame"] = Rect(720, 60, 80, 30)
        self.tick(session)
        session.show.assert_called_once()
        self.labels.hide.assert_not_called()
        self.assertEqual(self.visible, [control])

    def test_unsupported_adjustment_does_not_hide_labels_or_press_a_toggle(self):
        control = self.button("Wi-Fi", role="AXCheckBox")
        session, _ = self.open_panel(controls=[control])
        self.commands.status_labels_adjust(1, "increase")
        self.assertEqual(self.visible, [control])
        self.assertFalse(session.waiting)
        control.perform.assert_not_called()
        self.notify.assert_called_once()

    def test_repeated_adjustments_at_a_limit_do_not_time_out_or_hide_labels(self):
        slider = self.button("Volume", role="AXSlider", AXValue=0)
        slider.actions = {"AXDecrement": "decrement"}
        session, _ = self.open_panel(controls=[slider])
        for _ in range(2):
            self.commands.status_labels_adjust(1, "decrease")
            self.assertEqual(self.visible, [slider])
        self.tick(session, 25)
        self.assertIs(self.module._session, session)
        self.assertEqual(self.visible, [slider])
        self.assertFalse(session.waiting)
        self.notify.assert_not_called()

    def test_failed_adjustment_is_reported_and_cleans_up(self):
        slider = self.button("Volume", role="AXSlider")
        slider.actions = {"AXIncrement": "increment"}
        self.open_panel(controls=[slider])
        slider.perform.side_effect = ActionFailed("Cannot adjust")
        with self.assertLogs(level="ERROR"):
            self.commands.status_labels_adjust(1, "increase")
        self.assertIsNone(self.module._session)
        self.assertEqual(self.visible, [])
        self.notify.assert_called_once()

    def test_explicit_details_uses_only_the_advertised_action(self):
        control = self.button("Wi-Fi", role="AXCheckBox")
        control.actions["custom-details"] = "show details"
        self.open_panel(controls=[control])
        self.commands.status_labels_adjust(1, "details")
        control.perform.assert_called_once_with("custom-details")

    def test_details_without_a_real_panel_change_times_out_explicitly(self):
        control = self.button("Wi-Fi", role="AXCheckBox")
        control.actions["custom-details"] = "show details"
        session, _ = self.open_panel(controls=[control])
        self.commands.status_labels_adjust(1, "details")
        self.tick(session, 17)
        self.assertIsNone(self.module._session)
        self.notify.assert_called_once()

    def test_unsupported_details_does_not_guess_or_toggle_control(self):
        control = self.button("Wi-Fi", role="AXCheckBox")
        self.open_panel(controls=[control])
        self.commands.status_labels_adjust(1, "details")
        control.perform.assert_not_called()
        self.notify.assert_called_once()
        self.assertEqual(self.visible, [control])

    def test_accessibility_press_failure_cleans_up_and_notifies(self):
        self.commands.status_labels_show(False)
        self.icon.perform.side_effect = ActionFailed()
        with self.assertLogs(level="ERROR"):
            self.labels.select(1)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.visible, [])
        self.notify.assert_called_once()

    def test_unmatched_label_bounds_is_an_explicit_stale_label_error(self):
        self.commands.status_labels_show(False)
        self.labels.rect = lambda label: Rect(1, 1, 1, 1)
        with self.assertLogs(level="ERROR"):
            self.labels.select(1)
        self.assertIsNone(self.module._session)
        self.icon.perform.assert_not_called()
        self.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
