import unittest
from unittest.mock import patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        ActionFailed,
        ApplicationMenuTestCase,
        Element,
        frame,
    )
else:
    from accessibility_support import (
        ActionFailed,
        ApplicationMenuTestCase,
        Element,
        frame,
    )


class ApplicationMenuSelectionTests(ApplicationMenuTestCase):
    def test_text_anchored_submenu_still_uses_hover_fallback(self):
        title = Element(AXRole="AXStaticText", AXFrame=frame(x=25))
        self.item.attrs.update(AXChildren=[title], AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)

        self.talon.dispatch_labels("select", 1)
        for _ in range(self.session_module.MENU_HOVER_DELAY_TICKS):
            session._check_menu()

        self.assertEqual(self.item.performed, ["AXPress"])
        self.module.actions.mouse_move.assert_called_once_with(50, 35)

    def test_menu_selection_waits_for_delayed_submenu(self):
        self.talon.hide_after_select = True
        session = self.start(self.menu)
        submenu, item = self.nested_menu()

        self.talon.dispatch_labels("select", 1)
        self.assertIs(self.module._session, session)
        session._check_menu()
        self.assertEqual(self.query.call_count, 1)
        self.talon.active_menu = submenu
        session._check_menu()
        self.finish_refresh()

        self.assertIs(session.menu, submenu)
        self.assertEqual(session.targets, [item])

    def test_submenu_selection_hovers_only_after_native_selection_stalls(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        self.talon.hide_after_select = True
        session = self.start(self.menu)
        submenu, item = self.nested_menu()

        self.talon.dispatch_labels("select", 1)

        self.assertIn(("select", (1,)), self.talon.native_calls)
        for _ in range(self.session_module.MENU_HOVER_DELAY_TICKS - 1):
            session._check_menu()
        self.module.actions.mouse_move.assert_not_called()
        session._check_menu()
        self.module.actions.mouse_move.assert_called_once_with(50, 35)

        self.talon.active_menu = submenu
        session._check_menu()
        self.finish_refresh()
        self.assertIs(session.menu, submenu)
        self.assertEqual(session.targets, [item])

    def test_submenu_selection_does_not_hover_if_native_open_succeeds(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)
        submenu, item = self.nested_menu()

        self.talon.dispatch_labels("select", 1)
        self.talon.active_menu = submenu
        session._check_menu()
        self.finish_refresh()

        self.module.actions.mouse_move.assert_not_called()
        self.assertEqual(session.targets, [item])

    def test_submenu_hover_rejects_stale_or_unsafe_targets(self):
        for case in (
            "leaf",
            "disabled",
            "hidden",
            "outside_menu",
            "invalid_frame",
            "detached",
            "mouse_moved",
            "window_changed",
        ):
            with self.subTest(case=case):
                self.item.attrs.update(
                    AXParent=self.menu,
                    AXHasPopup=case != "leaf",
                    AXEnabled=True,
                    AXHidden=False,
                    AXFrame=frame(),
                )
                self.application.attrs["AXFocusedWindow"] = self.window
                self.talon.mouse_pos.reset_mock(side_effect=True)
                self.talon.mouse_pos.return_value = (30, 40)
                self.module.actions.mouse_move.reset_mock()
                session = self.start(self.menu)
                self.talon.dispatch_labels("select", 1)

                if case == "disabled":
                    self.item.attrs["AXEnabled"] = False
                elif case == "hidden":
                    self.item.attrs["AXHidden"] = True
                elif case == "outside_menu":
                    self.item.attrs["AXFrame"] = frame(x=400)
                elif case == "invalid_frame":
                    self.item.attrs["AXFrame"] = frame(width=float("nan"))
                elif case == "detached":
                    self.item.attrs["AXParent"] = Element(AXRole="AXMenu")
                elif case == "mouse_moved":
                    self.talon.mouse_pos.return_value = (31, 40)
                elif case == "window_changed":
                    self.application.attrs["AXFocusedWindow"] = Element(
                        AXRole="AXWindow"
                    )

                for _ in range(self.session_module.MENU_HOVER_DELAY_TICKS):
                    session._check_menu()

                self.module.actions.mouse_move.assert_not_called()

    def test_submenu_hover_does_not_move_after_menu_changes_during_validation(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)
        submenu, item = self.nested_menu()
        self.talon.dispatch_labels("select", 1)

        get = self.item.get

        def change_menu(attribute):
            if attribute == "AXHasPopup":
                self.talon.active_menu = submenu
            return get(attribute)

        with patch.object(self.item, "get", side_effect=change_menu):
            for _ in range(self.session_module.MENU_HOVER_DELAY_TICKS):
                session._check_menu()

        self.module.actions.mouse_move.assert_not_called()
        session._check_menu()
        self.finish_refresh()
        self.assertEqual(session.targets, [item])

    def test_replaced_session_cannot_move_mouse_from_old_submenu_hover(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)
        self.talon.dispatch_labels("select", 1)

        get = self.item.get

        def replace_session(attribute):
            if attribute == "AXHasPopup":
                self.talon.dispatch_labels("hide")
                self.actions.accessibility_show_application_numbers()
                self.talon.native_calls.clear()
            return get(attribute)

        with patch.object(self.item, "get", side_effect=replace_session):
            for _ in range(self.session_module.MENU_HOVER_DELAY_TICKS):
                session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.module.actions.mouse_move.assert_not_called()
        self.assertNotIn(("hide", ()), self.talon.native_calls)
        self.talon.notify.assert_not_called()

    def test_submenu_hover_failure_is_reported(self):
        self.item.attrs.update(AXParent=self.menu, AXHasPopup=True)
        session = self.start(self.menu)
        self.talon.dispatch_labels("select", 1)
        self.module.actions.mouse_move.side_effect = ActionFailed("mouse failed")

        for _ in range(self.session_module.MENU_HOVER_DELAY_TICKS):
            session._check_menu()

        self.assertTrue(session.stopped)
        self.talon.notify.assert_called_once_with(
            "Application control labels", "Unable to open the selected submenu."
        )

    def test_menu_selection_tolerates_briefly_missing_active_menu(self):
        self.talon.hide_after_select = True
        session = self.start(self.menu)
        submenu, item = self.nested_menu()
        self.talon.dispatch_labels("select", 1)
        self.talon.active_menu = None
        session._check_menu()

        self.assertIs(self.module._session, session)
        self.talon.active_menu = submenu
        session._check_menu()
        self.finish_refresh()
        self.assertEqual(session.targets, [item])

    def test_menu_leaf_selection_exits_without_relabeling_window(self):
        self.talon.hide_after_select = True
        session = self.start(self.menu)

        self.talon.dispatch_labels("select", 1)
        self.talon.active_menu = None
        for _ in range(15):
            session._check_menu()

        self.assertIsNone(self.module._session)
        self.assertTrue(session.stopped)
        self.assertEqual(self.query.call_count, 1)
        self.assertNotIn(("show", ([self.button],)), self.talon.native_calls)


if __name__ == "__main__":
    unittest.main()
