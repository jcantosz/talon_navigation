import types
import unittest
from unittest.mock import Mock

if __package__:
    from .status_support import Element, Owner, Rect, StatusLabelsTestCase
else:
    from status_support import Element, Owner, Rect, StatusLabelsTestCase


class StatusPanelTests(StatusLabelsTestCase):
    def test_selection_replaces_icons_with_panel_controls_in_both_modes(self):
        for names in (False, True):
            with self.subTest(names=names):
                self.owner.element.attrs["AXChildren"] = [self.bar]
                self.labels.hide()
                session, panel = self.open_panel(names)
                self.assertEqual(
                    self.visible, [panel.get("AXChildren")[0].get("AXChildren")[0]]
                )
                self.assertEqual(self.names, names)
                self.assertFalse(session.waiting)
                self.assertFalse(session.internal)

    def test_leaves_without_children_do_not_raise(self):
        control = self.button()
        del control.attrs["AXChildren"]
        _, _ = self.open_panel(controls=[control])
        self.assertEqual(self.visible, [control])

    def test_hidden_and_disabled_panel_controls_are_excluded(self):
        enabled = self.button()
        disabled = self.button("Disabled", AXEnabled=False)
        hidden = self.button("Hidden", AXHidden=True)
        self.open_panel(controls=[enabled, disabled, hidden])
        self.assertEqual(self.visible, [enabled])

    def test_panel_scan_reads_screen_bounds_once(self):
        screens = Mock(return_value=[types.SimpleNamespace(rect=Rect(0, 0, 1000, 700))])
        self.ui.screens = screens
        panel = self.panel(self.button("One"), self.button("Two"), self.button("Three"))
        self.module.surfaces.panel_targets(panel, self.owner)
        screens.assert_called_once_with()

    def test_existing_application_windows_are_not_labeled_as_status_panels(self):
        old = self.panel(self.button("Old document"))
        old.attrs["AXSubrole"] = "AXStandardWindow"
        self.owner.element.attrs["AXChildren"].append(old)
        session, new = self.open_panel()
        self.assertIs(session.surface.root, new)
        self.assertNotEqual(self.visible[0].get("AXTitle"), "Old document")

    def test_show_switches_style_on_the_current_panel_without_resetting_navigation(
        self,
    ):
        session, panel = self.open_panel()
        for names in (True, False):
            self.commands.status_labels_show(names)
            self.assertIs(self.module._session, session)
            self.assertIs(session.surface.root, panel)
            self.assertEqual(self.names, names)
            self.assertEqual(self.visible, [session.targets[0].element])
            self.assertIs(session.opener, self.icon)
        self.cron.interval.assert_called_once()
        self.icon.perform.assert_called_once()
        self.commands.status_labels_back()
        self.tick(session, 3)
        self.assertEqual(self.visible, [self.icon])

    def test_icon_render_uses_the_current_discovered_parent_cache(self):
        self.commands.status_labels_show(False)
        session = self.module._session
        other = Owner(3, "Other", "other")
        extra = Element("AXMenuExtra", "Other", Rect(650, 0, 20, 20))
        other.element.attrs["AXChildren"] = [Element("AXMenuBar", children=[extra])]
        self.apps.append(other)

        targets = self.module._icons()
        session.show(targets)

        self.assertEqual(self.visible, [extra, self.icon])
        self.assertEqual({owner.pid for parent, owner in session.icon_parents}, {2, 3})

    def test_show_during_opening_changes_style_without_cancelling_the_transition(self):
        panel = self.panel(self.button())
        self.icon.perform.side_effect = lambda action: self.owner.element.attrs[
            "AXChildren"
        ].append(panel)
        self.commands.status_labels_show(False)
        self.labels.select(1)
        session = self.module._session
        self.commands.status_labels_show(True)
        self.assertIs(self.module._session, session)
        self.assertTrue(session.waiting)
        self.tick(session, 3)
        self.assertIs(session.surface.root, panel)
        self.assertTrue(self.names)

    def test_show_after_hiding_labels_adopts_the_still_open_panel(self):
        old_session, panel = self.open_panel()
        self.labels.hide()
        self.commands.status_labels_show(True)
        session = self.module._session
        self.assertIsNot(session, old_session)
        self.assertIs(session.surface.root, panel)
        self.assertIs(session.opener, self.icon)
        self.assertNotIn(panel, session.baseline)
        self.assertTrue(self.names)
        self.commands.status_labels_back()
        self.tick(session, 3)
        self.assertEqual(self.visible, [self.icon])

    def test_show_adopts_an_already_open_native_status_menu(self):
        entry = Element("AXMenuItem", "About", Rect(700, 60, 80, 30))
        self.menu = Element("AXMenu", children=[entry], AXParent=self.icon)
        self.commands.status_labels_show(False)
        self.assertIs(self.module._session.surface.root, self.menu)
        self.assertEqual(self.visible, [entry])
        self.icon.perform.assert_not_called()
        session = self.module._session
        self.commands.status_labels_show(True)
        self.assertIs(self.module._session, session)
        self.assertEqual(self.visible, [entry])
        self.assertTrue(self.names)

    def test_show_adopts_a_visible_direct_status_menu_without_active_menu(self):
        entry = Element("AXMenuItem", "About", Rect(700, 60, 80, 30))
        menu = Element("AXMenu", frame=Rect(690, 30, 200, 150), children=[entry])
        self.icon.attrs["AXChildren"] = [menu]
        self.commands.status_labels_show(False)
        self.assertIs(self.module._session.surface.root, menu)
        self.assertEqual(self.visible, [entry])

    def test_show_does_not_adopt_a_regular_application_menu(self):
        entry = Element("AXMenuItem", "Open", Rect(30, 60, 80, 30))
        self.menu = Element("AXMenu", children=[entry], AXParent=self.front.element)
        self.commands.status_labels_show(False)
        self.assertIsNone(self.module._session.surface)
        self.assertEqual(self.visible, [self.icon])

    def test_show_adopts_an_open_clock_panel_from_notification_center(self):
        notification_center = Owner(
            3, "Notification Center", "com.apple.notificationcenterui"
        )
        self.apps.append(notification_center)
        self.icon.attrs["AXIdentifier"] = "com.apple.menuextra.clock"
        panel = self.panel(self.button("Notifications"))
        notification_center.element.attrs["AXChildren"] = [panel]
        self.commands.status_labels_show(False)
        session = self.module._session
        self.assertIs(session.surface.root, panel)
        self.assertIs(session.surface.owner, notification_center)
        self.assertIs(session.opener, self.icon)
        self.assertEqual({provider.pid for provider in session.providers}, {2, 3})

    def test_unknown_adopted_panel_opener_does_not_guess_a_toggle_for_back(self):
        panel = self.panel(self.button())
        panel.attrs["AXTitle"] = "Unknown panel"
        self.owner.element.attrs["AXChildren"].append(panel)
        self.commands.status_labels_show(False)
        session = self.module._session
        self.commands.status_labels_back()
        self.assertIsNone(session.opener)
        self.assertFalse(session.waiting)
        self.assertTrue(self.visible)
        self.icon.perform.assert_not_called()
        self.notify.assert_called_once()

    def test_unrelated_third_party_system_dialog_is_not_adopted(self):
        other = Owner(3, "Other app", "other")
        extra = Element("AXMenuExtra", "Other app", Rect(650, 0, 20, 20))
        panel = self.panel(self.button("Confirm"))
        panel.attrs["AXTitle"] = "Unrelated alert"
        other.element.attrs["AXChildren"] = [
            Element("AXMenuBar", children=[extra]),
            panel,
        ]
        self.apps.append(other)
        self.commands.status_labels_show(False)
        self.assertIsNone(self.module._session.surface)
        self.assertEqual(self.visible, [extra, self.icon])

    def test_adopted_panel_without_opener_can_use_its_own_close_action(self):
        for method in ("cancel", "close_button"):
            with self.subTest(method=method):
                self.labels.hide()
                panel = self.panel(self.button())
                panel.attrs["AXTitle"] = "Unknown panel"
                self.owner.element.attrs["AXChildren"] = [self.bar, panel]
                close = Element("AXButton", "Close", actions=("AXPress",))
                if method == "cancel":
                    panel.actions = {"AXCancel": "cancel"}
                    action = panel.perform
                else:
                    panel.attrs["AXCloseButton"] = close
                    action = close.perform
                action.side_effect = lambda operation: self.owner.element.attrs[
                    "AXChildren"
                ].remove(panel)
                self.commands.status_labels_show(False)
                session = self.module._session
                self.commands.status_labels_back()
                self.tick(session, 3)
                self.assertEqual(self.visible, [self.icon])
                action.assert_called_once()
                self.icon.perform.assert_not_called()
                self.notify.assert_not_called()

    def test_direct_icon_menu_is_found_even_when_active_menu_is_unavailable(self):
        entry = Element("AXMenuItem", "About", Rect(700, 60, 80, 30))
        menu = Element("AXMenu", children=[entry])
        menu.attrs["AXParent"] = self.icon
        self.icon.perform.side_effect = lambda action: self.icon.attrs.update(
            AXChildren=[menu]
        )
        self.commands.status_labels_show(False)
        self.labels.select(1)
        self.tick(self.module._session, 3)
        self.assertEqual(self.visible, [entry])

    def test_menu_surface_only_labels_the_current_level(self):
        child = Element("AXMenu", children=[self.button("Deeper")])
        entry = Element(
            "AXMenuItem", "Submenu", Rect(700, 60, 80, 30), children=[child]
        )
        menu = Element("AXMenu", children=[entry])
        menu.attrs["AXParent"] = self.icon
        self.icon.perform.side_effect = lambda action: setattr(self, "menu", menu)
        self.commands.status_labels_show(False)
        self.labels.select(1)
        self.tick(self.module._session, 3)
        self.assertEqual(self.visible, [entry])


if __name__ == "__main__":
    unittest.main()
