import unittest
from unittest.mock import Mock

if __package__:
    from .status_support import Element, Rect, StatusLabelsTestCase
else:
    from status_support import Element, Rect, StatusLabelsTestCase


class StatusBackTests(StatusLabelsTestCase):
    def test_back_closes_panel_and_relabels_icons_without_escape(self):
        session, _ = self.open_panel()
        self.commands.status_labels_back()
        self.tick(session, 3)
        self.assertEqual(self.visible, [self.icon])
        self.assertIsNone(session.surface)
        self.assertFalse(session.waiting)
        self.assertEqual(self.icon.perform.call_count, 2)
        self.actions.key.assert_not_called()

    def test_submenu_back_uses_verified_parent_menu_opener(self):
        parent = Element("AXMenu")
        opener = Element("AXMenuBarItem", children=[parent], actions=("AXPress",))
        item = Element("AXMenuItem", AXParent=parent)
        submenu = Element("AXMenu", AXParent=item)
        self.commands.status_labels_show(False)
        session = self.module._session
        session.surface = self.module.surfaces.Surface(submenu, self.owner, [])
        session.owner = self.owner
        self.menu = submenu

        self.commands.status_labels_back()

        opener.perform.assert_called_once_with("AXPress")
        self.actions.key.assert_not_called()

    def test_submenu_back_recognizes_a_direct_parent_menu(self):
        parent = Element("AXMenu")
        submenu = Element("AXMenu", AXParent=parent)
        self.commands.status_labels_show(False)
        session = self.module._session
        session.surface = self.module.surfaces.Surface(submenu, self.owner, [])
        session.owner = self.owner
        self.menu = submenu

        self.commands.status_labels_back()

        self.actions.key.assert_called_once_with("left")
        self.assertFalse(session.returning)
        self.assertTrue(session.requires_change)

    def test_submenu_back_does_not_press_the_status_icon_opener(self):
        parent = Element("AXMenu", AXParent=self.icon)
        self.icon.attrs["AXChildren"] = [parent]
        item = Element("AXMenuItem", AXParent=parent)
        submenu = Element("AXMenu", AXParent=item)
        self.commands.status_labels_show(False)
        session = self.module._session
        session.surface = self.module.surfaces.Surface(submenu, self.owner, [])
        session.owner = self.owner
        session.opener = self.icon
        self.menu = submenu

        self.commands.status_labels_back()

        self.icon.perform.assert_not_called()
        self.actions.key.assert_called_once_with("left")

    def test_back_reuses_known_icon_providers_without_rescanning_every_app(self):
        session, _ = self.open_panel()
        self.commands.status_labels_back()
        self.ui.apps = Mock(side_effect=AssertionError("Unexpected full app scan"))
        self.tick(session, 3)
        self.assertEqual(self.visible, [self.icon])

    def test_back_at_icons_is_explicit_and_does_not_press_anything(self):
        self.commands.status_labels_show()
        self.commands.status_labels_back()
        self.icon.perform.assert_not_called()
        self.notify.assert_called_once()

    def test_top_menu_back_uses_menu_cancel_and_restores_icons(self):
        entry = Element("AXMenuItem", "About", Rect(700, 60, 80, 30))
        menu = Element("AXMenu", children=[entry], actions=("AXCancel",))
        menu.attrs["AXParent"] = self.icon
        menu.perform.side_effect = lambda action: setattr(self, "menu", None)
        self.icon.perform.side_effect = lambda action: setattr(self, "menu", menu)
        self.commands.status_labels_show(False)
        self.labels.select(1)
        session = self.module._session
        self.tick(session, 3)
        self.commands.status_labels_back()
        self.tick(session, 3)
        menu.perform.assert_called_once_with("AXCancel")
        self.assertEqual(self.visible, [self.icon])


if __name__ == "__main__":
    unittest.main()
