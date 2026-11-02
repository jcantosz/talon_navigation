import unittest
from unittest.mock import patch

if __package__:
    from .status_support import Owner, StatusLabelsTestCase
else:
    from status_support import Owner, StatusLabelsTestCase


class StatusSessionTests(StatusLabelsTestCase):
    def test_hide_stops_job_and_removes_override_after_native_hide(self):
        self.commands.status_labels_show(False)
        session = self.module._session
        self.labels.hide()
        self.assertIsNone(self.module._session)
        self.assertTrue(session.stopped)
        self.assertEqual(self.visible, [])
        self.assertFalse(self.module.ctx.tags)
        self.cron.cancel.assert_called_once()

    def test_stopped_callback_cannot_resurrect_labels(self):
        self.commands.status_labels_show(False)
        session = self.module._session
        self.labels.hide()
        self.tick(session)
        session.show(
            [
                self.module.surfaces.Target(
                    self.icon, self.owner, self.icon.get("AXFrame")
                )
            ]
        )
        self.assertEqual(self.visible, [])

    def test_cancellation_during_label_rendering_does_not_resurrect_labels(self):
        session, panel = self.open_panel()
        self.on_show = self.module._stop
        session.show(session.targets, session.surface)
        self.assertEqual(self.visible, [])
        self.assertTrue(session.stopped)
        self.assertFalse(self.module.ctx.tags)

    def test_focus_change_cancels_selection_before_any_press(self):
        self.commands.status_labels_show(False)
        self.front = Owner(99, "Other app", "other")
        self.labels.select(1)
        self.icon.perform.assert_not_called()
        self.assertIsNone(self.module._session)
        self.notify.assert_called_once()

    def test_owner_can_take_focus_without_canceling_panel(self):
        session, _ = self.open_panel()
        self.front = self.owner
        self.tick(session)
        self.assertIs(self.module._session, session)

    def test_external_panel_dismissal_stops_labels(self):
        session, panel = self.open_panel()
        self.owner.element.attrs["AXChildren"].remove(panel)
        self.tick(session)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.visible, [])

    def test_no_panel_transition_times_out_with_a_notification(self):
        self.commands.status_labels_show(False)
        self.labels.select(1)
        session = self.module._session
        self.tick(session, 17)
        self.assertIsNone(self.module._session)
        self.notify.assert_called_once()

    def test_panel_update_failure_stops_and_notifies(self):
        session, _ = self.open_panel()
        with (
            patch.object(session, "find_surface", side_effect=RuntimeError("Failed")),
            self.assertLogs(level="ERROR"),
        ):
            self.tick(session)

        self.assertIsNone(self.module._session)
        self.assertTrue(session.stopped)
        self.assertEqual(self.visible, [])
        self.notify.assert_called_once_with(
            "Status labels", "Unable to read the status panel."
        )

    def test_leaf_action_closing_panel_finishes_without_false_error(self):
        control = self.button("Done")
        session, panel = self.open_panel(controls=[control])
        control.perform.side_effect = lambda action: self.owner.element.attrs[
            "AXChildren"
        ].remove(panel)
        self.labels.select(1)
        self.tick(session, 17)
        self.assertIsNone(self.module._session)
        self.notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
