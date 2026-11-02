import types
import unittest
from unittest.mock import patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        ACTIVE_TAG,
        ROOT,
        SESSION_TAG,
        ActionFailed,
        ApplicationMenuTestCase,
        Element,
    )
else:
    from accessibility_support import (
        ACTIVE_TAG,
        ROOT,
        SESSION_TAG,
        ActionFailed,
        ApplicationMenuTestCase,
        Element,
    )


class ApplicationMenuBackTests(ApplicationMenuTestCase):
    def test_back_closes_top_menu_and_restores_window(self):
        session = self.start(self.menu)
        self.assertIn(SESSION_TAG, self.talon.active_tags())

        self.actions.accessibility_application_numbers_back()

        self.module.actions.key.assert_called_once_with("esc")
        self.assertEqual(self.menu.performed, [])
        self.assertIs(self.module._session, session)
        self.assertNotIn(ACTIVE_TAG, self.talon.active_tags())
        self.assertIn(SESSION_TAG, self.talon.active_tags())
        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()
        self.assertIsNone(session.menu)
        self.assertEqual(session.targets, [self.button])
        self.assertIn(ACTIVE_TAG, self.talon.active_tags())
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_back_uses_escape_if_top_menu_cannot_be_cancelled(self):
        self.menu.actions = []
        session = self.start(self.menu)

        self.actions.accessibility_application_numbers_back()

        self.module.actions.key.assert_called_once_with("esc")
        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()
        self.assertEqual(session.targets, [self.button])

    def test_back_closes_one_submenu_and_relabels_parent(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)

        self.actions.accessibility_application_numbers_back()

        self.module.actions.key.assert_called_once_with("left")
        self.talon.active_menu = self.menu
        session._check_menu()
        self.finish_refresh()
        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])

    def test_back_recognizes_a_direct_parent_menu(self):
        submenu, _ = self.nested_menu()
        submenu.attrs["AXParent"] = self.menu
        session = self.start(submenu)

        self.actions.accessibility_application_numbers_back()

        self.module.actions.key.assert_called_once_with("left")
        self.talon.active_menu = self.menu
        session._check_menu()
        self.finish_refresh()
        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])

    def test_back_falls_back_to_window_if_parent_cannot_be_restored(self):
        submenu, _ = self.nested_menu()
        submenu.attrs["AXParent"] = self.menu
        session = self.start(submenu)

        self.actions.accessibility_application_numbers_back()
        for _ in range(self.session_module.MENU_BACK_FALLBACK_TICKS):
            session._check_menu()

        self.assertEqual(
            [call.args for call in self.module.actions.key.call_args_list],
            [("left",), ("esc",)],
        )
        self.talon.active_menu = None
        session._check_menu()
        self.finish_refresh()

        self.assertIsNone(session.menu)
        self.assertEqual(session.targets, [self.button])
        self.assertIn("application controls", self.talon.notify.call_args.args[1])

    def test_back_fallback_does_not_escape_after_window_changes(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        self.actions.accessibility_application_numbers_back()
        self.application.attrs["AXFocusedWindow"] = Element(AXRole="AXWindow")

        for _ in range(self.session_module.MENU_BACK_FALLBACK_TICKS):
            session._check_menu()

        self.module.actions.key.assert_called_once_with("left")
        self.assertTrue(session.stopped)
        self.assertIn("window changed", self.talon.notify.call_args.args[1].lower())

    def test_back_fallback_does_not_escape_after_menu_changes_during_validation(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        self.actions.accessibility_application_numbers_back()

        def change_menu():
            self.talon.active_menu = Element(AXRole="AXMenu")
            return True

        with patch.object(session, "_transition_focus_valid", side_effect=change_menu):
            for _ in range(self.session_module.MENU_BACK_FALLBACK_TICKS):
                session._check_menu()

        self.module.actions.key.assert_called_once_with("left")

    def test_replaced_session_cannot_send_fallback_escape(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        self.actions.accessibility_application_numbers_back()

        def replace_session():
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            self.talon.native_calls.clear()
            return True

        with patch.object(
            session, "_transition_focus_valid", side_effect=replace_session
        ):
            for _ in range(self.session_module.MENU_BACK_FALLBACK_TICKS):
                session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.module.actions.key.assert_called_once_with("left")
        self.assertNotIn(("hide", ()), self.talon.native_calls)

    def test_back_fallback_escape_failure_is_reported(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        self.actions.accessibility_application_numbers_back()
        self.module.actions.key.side_effect = ActionFailed("escape failed")

        for _ in range(self.session_module.MENU_BACK_FALLBACK_TICKS):
            session._check_menu()

        self.assertTrue(session.stopped)
        self.talon.notify.assert_called_once_with(
            "Application control labels", "Unable to return to the parent menu."
        )

    def test_submenu_back_uses_verified_parent_menu_opener(self):
        opener = Element(AXRole="AXMenuBarItem", AXChildren=[self.menu], AXEnabled=True)
        self.menu.attrs["AXParent"] = opener
        submenu, _ = self.nested_menu()
        session = self.start(submenu)

        self.actions.accessibility_application_numbers_back()

        self.assertEqual(opener.performed, ["AXPress"])
        self.module.actions.key.assert_not_called()
        self.talon.active_menu = self.menu
        session._check_menu()
        self.finish_refresh()
        self.assertIs(session.menu, self.menu)
        self.assertEqual(session.targets, [self.item])

    def test_replaced_session_does_not_press_a_menu_opener(self):
        submenu, _ = self.nested_menu()
        session = self.start(submenu)
        opener = Element(AXRole="AXMenuBarItem")

        def replace_session(parent):
            self.talon.dispatch_labels("hide")
            self.actions.accessibility_show_application_numbers()
            return opener

        with patch.object(
            self.session_module, "menu_opener", side_effect=replace_session
        ):
            self.actions.accessibility_application_numbers_back()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.assertEqual(opener.performed, [])
        self.module.actions.key.assert_not_called()

    def test_back_does_not_send_escape_after_session_is_replaced_while_hiding(self):
        session = self.start(self.menu)
        native_hide = self.module.actions.labels.hide
        switched = False

        def replace_during_hide():
            nonlocal switched
            if not switched:
                switched = True
                native_hide()
                self.module._stop()
                self.actions.accessibility_show_application_numbers()
            else:
                native_hide()

        with patch.object(
            self.module.actions.labels, "hide", side_effect=replace_during_hide
        ):
            self.actions.accessibility_application_numbers_back()

        self.assertTrue(session.stopped)
        self.assertIsNot(self.module._session, session)
        self.module.actions.key.assert_not_called()
        self.assertIn(ACTIVE_TAG, self.talon.active_tags())
        self.assertIn(SESSION_TAG, self.talon.active_tags())

    def test_back_at_window_does_not_send_a_key(self):
        session = self.start()
        self.actions.accessibility_application_numbers_back()
        self.assertIs(self.module._session, session)
        self.module.actions.key.assert_not_called()
        self.talon.notify.assert_called_once()

    def test_back_waits_and_reports_an_unchanged_menu(self):
        session = self.start(self.menu)
        self.actions.accessibility_application_numbers_back()
        self.actions.accessibility_application_numbers_back()
        self.module.actions.key.assert_called_once_with("esc")

        for _ in range(15):
            session._check_menu()

        self.assertIsNone(self.module._session)
        self.assertIn("unable to return", self.talon.notify.call_args.args[1].lower())

    def test_other_label_session_can_hide_during_back_transition(self):
        session = self.start(self.menu)
        self.actions.accessibility_application_numbers_back()

        self.talon.dispatch_labels("hide")

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)

    def test_escape_and_session_overrides_use_separate_tags(self):
        active = (ROOT / "accessibility" / "inventory_active.talon").read_text()
        self.assertIn(f"tag: {ACTIVE_TAG}", active)
        self.assertIn("key(escape):", active)
        self.assertIn(f"tag: {SESSION_TAG}", self.module.labels_ctx.matches)

    def test_app_change_stops_session_during_back_transition(self):
        session = self.start(self.menu)
        self.actions.accessibility_application_numbers_back()
        self.talon.active_app = types.SimpleNamespace(pid=2)

        session._check_menu()

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)


if __name__ == "__main__":
    unittest.main()
