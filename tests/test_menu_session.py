import unittest
from unittest.mock import Mock, patch

if __package__:
    from .menu_support import SOURCE, ActionFailed, Children, MenuLabelsTestCase, UIErr
else:
    from menu_support import SOURCE, ActionFailed, Children, MenuLabelsTestCase, UIErr


class SessionTests(MenuLabelsTestCase):
    def test_entrypoint_supplies_session_context_and_failure_callback(self):
        self.actions.menu_labels_show(False)

        session = self.module._session
        self.assertIsInstance(session, self.menu_session.MenuSession)
        self.assertIs(session.context, self.module.ctx)
        self.assertIs(session._failed, self.module._failed)
        self.assertEqual(self.module.ctx.tags, ["user.menu_labels_active"])

    def test_number_override_keeps_an_exact_rule_separate_from_aliases(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        self.assertRegex(
            grammar,
            r"(?m)^show menu numbers:\n[ \t]+user\.menu_labels_show\(false\)$",
        )
        headers = [
            line[:-1]
            for line in grammar.splitlines()
            if line and not line[0].isspace() and line.endswith(":")
        ]
        for header in headers:
            if header != "show menu numbers":
                self.assertNotIn("show menu numbers", header.split(" | "))

    def test_hide_clears_native_labels_before_removing_override(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        job = session.job
        self.labels.hide()
        self.assertEqual(self.visible, [])
        self.assertEqual(self.module.ctx.tags, [])
        self.assertIsNone(session.job)
        self.cron.cancel.assert_called_with(job)

    def test_stopped_render_preserves_replacement_menu_labels(self):
        self.actions.menu_labels_show(False)
        previous = self.module._session
        native_show = self.labels.show
        switched = False

        def show_then_replace(targets):
            nonlocal switched
            native_show(targets)
            if not switched:
                switched = True
                self.actions.menu_labels_show(False)

        with patch.object(self.labels, "show", side_effect=show_then_replace):
            previous.show_container(self.bar, self.bar.children)

        self.assertTrue(previous.stopped)
        self.assertIsNotNone(self.module._session)
        self.assertIsNot(self.module._session, previous)
        self.assertEqual(self.visible, self.bar.children)

    def test_leaf_selection_exits_without_relabeling_old_menu(self):
        self.menu = self.submenu("Leaf")
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        self.menu = None
        for _ in range(15):
            session.update()
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.notify.assert_not_called()

    def test_unchanged_menu_times_out_with_notification(self):
        self.menu = self.submenu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        for _ in range(15):
            session.update()
        self.assertIsNone(session.job)
        self.notify.assert_called_once_with(
            "Menu labels", "No new selectable submenu appeared."
        )

    def test_app_switch_cancels_pending_relabel(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        self.application.pid = 2
        self.menu = self.submenu()
        session.update()
        self.assertEqual(self.visible, [])
        self.assertFalse(session.waiting)
        self.assertIsNone(session.job)

    def test_app_switch_before_selection_does_not_select_stale_item(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.application.pid = 2
        self.labels.select(1)
        self.assertEqual(self.selected, [])
        self.notify.assert_called_once()
        self.assertIsNone(session.job)

    def test_external_menu_dismissal_clears_labels(self):
        self.menu = self.submenu()
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.menu = None
        session.update()
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)

    def test_missing_menu_reports_accessibility_failure(self):
        self.application.children = Children()
        with self.assertLogs(level="ERROR"):
            self.actions.menu_labels_show(False)
        self.notify.assert_called_once()
        self.assertEqual(self.visible, [])
        self.assertIsNone(self.module._session)

    def test_accessibility_failure_while_waiting_cleans_up(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.labels.select(1)
        self.ui.active_menu = Mock(side_effect=UIErr("Stale element"))
        with self.assertLogs(level="ERROR"):
            session.update()
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.notify.assert_called_once()

    def test_accessibility_failure_before_selection_cleans_up(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        self.ui.active_menu = Mock(side_effect=UIErr("Stale element"))
        with self.assertLogs(level="ERROR"):
            self.labels.select(1)
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.assertEqual(self.selected, [])
        self.notify.assert_called_once()

    def test_failed_accessibility_press_cleans_up(self):
        self.actions.menu_labels_show(False)
        session = self.module._session
        native = self.native

        def fail_select(name, *args):
            if name == "select":
                raise ActionFailed("AXPress failed")
            native(name, *args)

        self.native = fail_select
        with self.assertLogs(level="ERROR"):
            self.labels.select(1)
        self.assertEqual(self.visible, [])
        self.assertIsNone(session.job)
        self.assertFalse(session.selecting)
        self.notify.assert_called_once()

    def test_invalid_numbers_report_error_without_selecting(self):
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_click(0)
        self.actions.menu_labels_move(3)
        self.assertEqual(self.selected, [])
        self.labels.mouse_move.assert_not_called()
        self.assertEqual(self.notify.call_count, 2)

    def test_explicit_number_command_uses_the_same_selection_override(self):
        self.actions.menu_labels_show(False)
        self.actions.menu_labels_click(2)
        self.assertEqual(self.selected, [2])
        self.assertTrue(self.module._session.waiting)

    def test_number_command_in_title_mode_explains_how_to_switch(self):
        self.actions.menu_labels_show()
        self.actions.menu_labels_click(1)
        self.assertEqual(self.selected, [])
        self.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
