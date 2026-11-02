import unittest
from unittest.mock import Mock, patch

if __package__:
    from .menu_support import Element, MenuLabelsTestCase
else:
    from menu_support import Element, MenuLabelsTestCase


class BackTests(MenuLabelsTestCase):
    def test_back_to_parent_preserves_both_label_styles(self):
        for names in (True, False):
            with self.subTest(names=names):
                self.labels.hide()
                parent = self.submenu("Parent item")
                self.prepare_back(parent)
                self.actions.menu_labels_show(names)
                self.actions.menu_labels_back()
                self.assertEqual(self.visible, [])
                self.module.actions.key.assert_called_with("left")
                self.module._session.update()
                self.assertTrue(self.module._session.waiting)
                self.menu = parent
                self.module._session.update()
                self.assertEqual(self.visible, parent.children)
                self.assertEqual(self.style, "names" if names else "numbers")
                self.assertIsNone(self.module._session.back_parent)

    def test_back_from_top_menu_relabels_menu_bar(self):
        self.prepare_back(self.bar)
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_back()
        self.module.actions.key.assert_called_with("esc")
        self.menu = None
        self.module._session.update()
        self.assertEqual(self.visible, self.bar.children)
        self.assertEqual(self.style, "numbers")
        self.assertIs(self.module._session.container, self.bar)

    def test_back_recognizes_direct_menu_and_menu_bar_parents(self):
        for parent in (self.submenu("Parent item"), self.bar):
            with self.subTest(role=parent.get("AXRole")):
                self.labels.hide()
                self.menu = self.submenu()
                self.menu.attrs["AXParent"] = parent
                self.actions.menu_labels_show(False)

                self.actions.menu_labels_back()

                is_bar = parent.get("AXRole") == "AXMenuBar"
                self.module.actions.key.assert_called_with("esc" if is_bar else "left")
                self.menu = None if is_bar else parent
                self.module._session.update()
                self.assertEqual(self.visible, parent.children)
                self.assertIs(self.module._session.container, parent)

    def test_back_falls_back_to_menu_bar_when_parent_does_not_respond(self):
        parent = self.submenu("Parent")
        self.menu = self.submenu()
        self.menu.attrs["AXParent"] = parent
        self.actions.menu_labels_show(False)
        session = self.module._session

        self.actions.menu_labels_back()
        for _ in range(self.menu_session.MENU_BACK_FALLBACK_TICKS):
            session.update()

        self.assertEqual(
            [call.args for call in self.module.actions.key.call_args_list],
            [("left",), ("esc",)],
        )
        self.menu = None
        session.update()
        self.assertIs(session.container, self.bar)
        self.assertEqual(self.visible, self.bar.children)
        self.assertEqual(self.style, "numbers")
        self.assertIn("menu bar", self.notify.call_args.args[1])

    def test_back_fallback_does_not_escape_after_window_changes(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.actions.menu_labels_back()
        self.application_element.attrs["AXFocusedWindow"] = Element("AXWindow")

        for _ in range(self.menu_session.MENU_BACK_FALLBACK_TICKS):
            session.update()

        self.module.actions.key.assert_called_once_with("left")
        self.assertTrue(session.stopped)
        self.assertIn("window changed", self.notify.call_args.args[1].lower())

    def test_back_fallback_does_not_escape_after_menu_changes(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.actions.menu_labels_back()
        self.menu = self.submenu("Unrelated")

        for _ in range(self.menu_session.MENU_BACK_FALLBACK_TICKS):
            session.update()

        self.module.actions.key.assert_called_once_with("left")

    def test_back_rejects_stale_labels_after_menu_changes(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.menu = self.submenu("Another menu")

        self.actions.menu_labels_back()

        self.assertTrue(session.stopped)
        self.module.actions.key.assert_not_called()
        self.assertIn("menu changed", self.notify.call_args.args[1].lower())

    def test_replaced_session_cannot_press_a_parent_opener(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        opener = Element("AXMenuBarItem", "File")

        def replace_session(*args):
            self.actions.menu_labels_show(False)
            return opener

        with patch.object(
            self.menu_session, "menu_opener", side_effect=replace_session
        ):
            self.actions.menu_labels_back()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertEqual(opener.performed, [])
        self.module.actions.key.assert_not_called()

    def test_back_does_not_press_an_opener_after_the_menu_changes(self):
        parent = self.submenu("Parent")
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)
        session = self.module._session
        opener = Element("AXMenuBarItem", "File")

        def change_menu(*args):
            self.menu = self.submenu("Another menu")
            return opener

        with patch.object(self.menu_session, "menu_opener", side_effect=change_menu):
            self.actions.menu_labels_back()

        self.assertTrue(session.stopped)
        self.assertEqual(opener.performed, [])
        self.module.actions.key.assert_not_called()
        self.assertIn("menu changed", self.notify.call_args.args[1].lower())

    def test_submenu_back_uses_verified_parent_menu_opener(self):
        parent = self.submenu("Parent item")
        opener = Element("AXMenuBarItem", "File", children=[parent])
        opener.actions = ["AXPress"]
        opener.perform = Mock()
        parent.attrs["AXParent"] = opener
        self.prepare_back(parent)
        self.actions.menu_labels_show(False)

        self.actions.menu_labels_back()

        opener.perform.assert_called_once_with("AXPress")
        self.module.actions.key.assert_not_called()
        self.menu = parent
        self.module._session.update()
        self.assertEqual(self.visible, parent.children)

    def test_menu_opener_rejects_unsafe_or_unrelated_owners(self):
        cases = (
            ("disabled", "AXMenuItem", False, False, ["AXPress"], True),
            ("hidden", "AXMenuItem", True, True, ["AXPress"], True),
            ("wrong role", "AXButton", True, False, ["AXPress"], True),
            ("not pressable", "AXMenuItem", True, False, [], True),
            ("not its child", "AXMenuItem", True, False, ["AXPress"], False),
        )
        for name, role, enabled, hidden, actions, has_child in cases:
            with self.subTest(name=name):
                menu = self.submenu()
                owner = Element(
                    role, children=[menu] if has_child else [], enabled=enabled
                )
                owner.attrs["AXHidden"] = hidden
                owner.actions = actions
                menu.attrs["AXParent"] = owner

                self.assertIsNone(self.menu_session.menu_opener(menu))
        self.assertIsNone(self.menu_session.menu_opener(self.submenu()))

    def test_back_at_bar_does_not_send_escape(self):
        self.actions.menu_labels_show()
        self.actions.menu_labels_back()
        self.module.actions.key.assert_not_called()
        self.assertEqual(self.visible, self.bar.children)
        self.notify.assert_called_once()

    def test_back_timeout_reports_failure_and_cleans_up(self):
        self.prepare_back(self.bar)
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_back()
        session = self.module._session
        for _ in range(15):
            session.update()
        self.assertIsNone(session.job)
        self.assertIsNone(session.back_parent)
        self.notify.assert_called_once_with(
            "Menu labels", "Unable to return to the parent menu."
        )

    def test_back_without_accessible_parent_does_not_close_menu(self):
        self.menu = self.submenu()
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_back()
        self.module.actions.key.assert_not_called()
        self.assertEqual(self.visible, self.menu.children)
        self.notify.assert_called_once()

    def test_back_while_waiting_does_not_send_escape(self):
        self.actions.menu_labels_show(False)
        self.labels.select(1)
        self.actions.menu_labels_back()
        self.module.actions.key.assert_not_called()
        self.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
