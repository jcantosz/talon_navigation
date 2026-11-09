import types
import unittest
from unittest.mock import Mock

if __package__:
    from .accessibility_support import FakeTalon, UIErr, load
else:
    from accessibility_support import FakeTalon, UIErr, load


class HintLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeTalon()
        self.module = load(self.fake, "window_hints/lifecycle.py")
        self.context = types.SimpleNamespace(tags=[])
        self.render = Mock()
        self.session = self.module.HintSession(self.context, self.render)

    def tick(self):
        self.fake.cron.after.call_args.args[1]()

    def test_focus_refresh_preserves_names_and_coalesces_events(self):
        self.session.show("named", False)
        self.session.focus_changed(object())
        first = self.session.job
        self.session.focus_changed(object())
        self.fake.cron.cancel.assert_called_with(first)
        self.render.assert_called_once_with("named", False)
        self.tick()
        self.assertEqual(self.render.call_count, 2)
        self.render.assert_called_with("named", False)
        self.assertEqual(self.context.tags, ["user.window_hints_active"])

    def test_hide_or_replacement_cancels_pending_refresh(self):
        self.session.show("named", True)
        self.session.focus_changed()
        job = self.session.job
        self.session.replaced()
        self.fake.cron.cancel.assert_called_with(job)
        self.tick()
        self.assertEqual(self.render.call_count, 1)
        self.assertIsNone(self.session.mode)
        self.assertEqual(self.context.tags, [])

    def test_internal_renderer_hide_does_not_stop_session(self):
        def draw(*_):
            with self.session.drawing():
                self.session.replaced()

        self.render.side_effect = draw
        self.session.show("structural", False)
        self.assertEqual(self.session.mode, ("structural", False))
        self.session.focus_changed()
        self.tick()
        self.assertEqual(self.render.call_count, 2)

    def test_focus_events_before_show_do_nothing(self):
        self.session.focus_changed()
        self.fake.cron.after.assert_not_called()
        self.render.assert_not_called()

    def test_failed_query_stops_and_notifies_no_stale_retry(self):
        self.render.side_effect = UIErr("failed")
        with self.assertLogs(level="ERROR"):
            self.session.show("named", True)
        self.assertIsNone(self.session.mode)
        self.fake.notify.assert_called_once()
        self.session.focus_changed()
        self.fake.cron.after.assert_not_called()

    def test_focus_race_retries_current_application_instead_of_stopping(self):
        self.render.side_effect = [self.module.FocusChanged(), None]
        self.session.show("named", True)
        self.assertIsNotNone(self.session.job)
        self.tick()
        self.assertEqual(self.render.call_count, 2)
        self.assertIsNotNone(self.session.mode)
        self.fake.notify.assert_not_called()
