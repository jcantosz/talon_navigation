import types
import unittest
from unittest.mock import Mock, patch

if __package__:
    from .accessibility_support import ActionFailed, FakeTalon, UIErr, load
else:
    from accessibility_support import ActionFailed, FakeTalon, UIErr, load


class SharedHoverTests(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.labels = load(self.talon, "lib/labels.py")
        self.session = self.labels.LabelSession(
            types.SimpleNamespace(tags=[]), "test.labels", False
        )
        self.target = object()
        self.menu = object()
        self.talon.active_menu = self.menu
        self.position = self.talon.mouse_pos.return_value
        self.focus_valid = Mock(return_value=True)
        patcher = patch.object(
            self.labels, "submenu_hover_point", return_value=(50, 35)
        )
        self.point = patcher.start()
        self.addCleanup(patcher.stop)

    def hover(self):
        self.session.hover_submenu_if_current(
            self.target, self.menu, self.position, self.focus_valid
        )

    def test_hover_revalidates_focus_before_moving(self):
        self.hover()

        self.point.assert_called_once_with(self.target, self.menu)
        self.assertEqual(self.focus_valid.call_count, 2)
        self.labels.actions.mouse_move.assert_called_once_with(50, 35)

    def test_stopped_session_does_not_query_or_move(self):
        self.session.stop()
        self.hover()

        self.talon.mouse_pos.assert_not_called()
        self.focus_valid.assert_not_called()
        self.point.assert_not_called()
        self.labels.actions.mouse_move.assert_not_called()

    def test_moved_pointer_does_not_query_target(self):
        self.talon.mouse_pos.return_value = (31, 40)
        self.hover()

        self.focus_valid.assert_not_called()
        self.point.assert_not_called()
        self.labels.actions.mouse_move.assert_not_called()

    def test_invalid_focus_does_not_query_target(self):
        self.focus_valid.return_value = False
        self.hover()

        self.point.assert_not_called()
        self.labels.actions.mouse_move.assert_not_called()

    def test_missing_hover_point_does_not_move(self):
        self.point.return_value = None
        self.hover()

        self.assertEqual(self.focus_valid.call_count, 1)
        self.labels.actions.mouse_move.assert_not_called()

    def test_pointer_movement_during_target_query_prevents_hover(self):
        def move_pointer(*_args):
            self.talon.mouse_pos.return_value = (31, 40)
            return (50, 35)

        self.point.side_effect = move_pointer
        self.hover()

        self.labels.actions.mouse_move.assert_not_called()

    def test_focus_change_during_target_query_prevents_hover(self):
        self.focus_valid.side_effect = [True, False]
        self.hover()

        self.labels.actions.mouse_move.assert_not_called()

    def test_menu_change_during_target_query_prevents_hover(self):
        def change_menu(*_args):
            self.talon.active_menu = object()
            return (50, 35)

        self.point.side_effect = change_menu
        self.hover()

        self.labels.actions.mouse_move.assert_not_called()

    def test_session_stopped_during_target_query_cannot_move(self):
        def stop_session(*_args):
            self.session.stop()
            return (50, 35)

        self.point.side_effect = stop_session
        self.hover()

        self.assertEqual(self.focus_valid.call_count, 1)
        self.labels.actions.mouse_move.assert_not_called()

    def test_session_stopped_during_menu_query_cannot_move(self):
        def stop_session():
            self.session.stop()
            return self.menu

        with patch.object(self.labels.ui, "active_menu", side_effect=stop_session):
            self.hover()

        self.labels.actions.mouse_move.assert_not_called()

    def test_query_errors_propagate_to_the_feature_error_handler(self):
        for error in (UIErr("gone"), ActionFailed("failed"), RuntimeError("error")):
            with self.subTest(error=type(error).__name__):
                self.point.side_effect = error
                with self.assertRaises(type(error)):
                    self.hover()

        self.labels.actions.mouse_move.assert_not_called()


if __name__ == "__main__":
    unittest.main()
