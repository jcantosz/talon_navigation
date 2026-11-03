import types
import unittest
from unittest.mock import patch

if __package__:
    from .menu_support import ActionFailed, Element, MenuLabelsTestCase
else:
    from menu_support import ActionFailed, Element, MenuLabelsTestCase


class HoverTests(MenuLabelsTestCase):
    def test_numbered_submenu_hovers_only_if_native_selection_stalls(self):
        self.hoverable_menu()
        self.actions.menu_labels_show(False)
        session = self.module._session

        self.labels.select(1)

        self.assertEqual(self.selected, [1])
        for _ in range(self.menu_session.MENU_HOVER_DELAY_TICKS - 1):
            session.update()
        self.module.actions.mouse_move.assert_not_called()
        session.update()
        self.module.actions.mouse_move.assert_called_once_with(50, 35)
        self.assertTrue(session.waiting)

        self.menu = self.submenu("Submenu item")
        session.update()
        self.assertIs(session.container, self.menu)
        self.assertEqual(self.visible, self.menu.children)

    def test_numbered_submenu_does_not_hover_if_native_selection_succeeds(self):
        self.hoverable_menu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)

        self.menu = self.submenu("Submenu item")
        session.update()

        self.module.actions.mouse_move.assert_not_called()
        self.assertIs(session.container, self.menu)

    def test_named_submenu_hovers_when_its_title_uniquely_identifies_it(self):
        self.hoverable_menu()
        self.actions.menu_labels_show()
        session = self.module._session
        self.labels.select("Tools")

        for _ in range(self.menu_session.MENU_HOVER_DELAY_TICKS):
            session.update()

        self.assertEqual(self.selected, ["Tools"])
        self.module.actions.mouse_move.assert_called_once_with(50, 35)

    def test_named_submenu_does_not_guess_between_duplicate_titles(self):
        menu, _ = self.hoverable_menu()
        menu.children.append(Element("AXMenuItem", "Tools"))
        self.actions.menu_labels_show()
        session = self.module._session
        self.labels.select("Tools")

        for _ in range(self.menu_session.MENU_HOVER_DELAY_TICKS):
            session.update()

        self.assertEqual(self.selected, ["Tools"])
        self.module.actions.mouse_move.assert_not_called()

    def test_menu_number_hover_rejects_stale_or_unsafe_targets(self):
        for case in ("mouse_moved", "window_changed", "hidden", "outside"):
            with self.subTest(case=case):
                self.labels.hide()
                self.mouse_pos.return_value = (30, 40)
                self.application_element.attrs["AXFocusedWindow"] = self.window
                self.module.actions.mouse_move.reset_mock()
                _, target = self.hoverable_menu()
                self.actions.menu_labels_show(False)
                session = self.module._session
                self.labels.select(1)
                if case == "mouse_moved":
                    self.mouse_pos.return_value = (31, 40)
                elif case == "window_changed":
                    self.application_element.attrs["AXFocusedWindow"] = Element(
                        "AXWindow"
                    )
                elif case == "hidden":
                    target.attrs["AXHidden"] = True
                else:
                    target.attrs["AXFrame"] = types.SimpleNamespace(
                        x=400, y=20, width=80, height=30
                    )

                for _ in range(self.menu_session.MENU_HOVER_DELAY_TICKS):
                    session.update()

                self.module.actions.mouse_move.assert_not_called()

    def test_menu_number_hover_does_not_move_after_session_replacement(self):
        _, target = self.hoverable_menu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)

        get = target.get

        def replace_session(attribute):
            if attribute == "AXHasPopup":
                self.labels.hide()
                self.actions.menu_labels_show(False)
            return get(attribute)

        with patch.object(target, "get", side_effect=replace_session):
            for _ in range(self.menu_session.MENU_HOVER_DELAY_TICKS):
                session.update()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.module.actions.mouse_move.assert_not_called()

    def test_menu_hover_failure_is_reported_and_cleans_up(self):
        self.hoverable_menu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        self.module.actions.mouse_move.side_effect = ActionFailed("mouse failed")

        with self.assertLogs(level="ERROR"):
            for _ in range(self.menu_session.MENU_HOVER_DELAY_TICKS):
                session.update()

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)
        self.notify.assert_called_once_with(
            "Menu labels", "Unable to open the selected submenu."
        )


if __name__ == "__main__":
    unittest.main()
