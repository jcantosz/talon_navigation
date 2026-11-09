import sys
import types
import unittest
from unittest.mock import Mock, patch

if __package__:
    from .accessibility_support import Element, FakeTalon, frame, load
else:
    from accessibility_support import Element, FakeTalon, frame, load


class SectionActionsTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeTalon()
        labels = types.SimpleNamespace(spoken_name=lambda value: value)
        with patch.dict(
            sys.modules, {"talon_navigation_runtime.window_hints.labels": labels}
        ):
            self.module = load(self.fake, "window_hints/section_actions.py")
        self.root = Element(
            AXRole="AXGroup", AXFrame=frame(x=0, y=0, width=100, height=80)
        )
        self.module.ctrl.mouse_move = Mock()
        self.module.ctrl.mouse_scroll = Mock()
        self.fake.settings.update(
            {
                "user.mouse_wheel_down_amount": 120,
                "user.mouse_wheel_horizontal_amount": 40,
            }
        )
        self.fake.mouse_pos.return_value = (50, 40)
        self.module.actions.user.accessibility_invalidate_numbers_for_scroll = Mock()
        self.resolve = Mock(return_value=self.root)
        window = Element()
        self.fake.active_app = types.SimpleNamespace(
            element=Element(AXFocusedWindow=window)
        )
        self.root.attrs["AXWindow"] = window
        preference = patch.object(
            self.module.subprocess,
            "run",
            return_value=types.SimpleNamespace(stdout="1\n"),
        )
        self.preference = preference.start()
        self.addCleanup(preference.stop)

    def test_visual_directions_follow_both_native_scroll_preferences(self):
        for preference in ("0", "1"):
            self.module.refresh_scroll_direction()
            self.preference.return_value.stdout = preference
            for direction in ("up", "down", "left", "right"):
                expected = (
                    direction if preference == "1" else self.module.OPPOSITE[direction]
                )
                self.assertEqual(self.module._wheel_direction(direction), expected)

    def test_preference_read_once_until_explicit_section_refresh(self):
        for _ in range(10):
            self.module.scroll(self.resolve, "down", 1)
        self.preference.assert_called_once()
        self.module.refresh_scroll_direction()
        self.module.scroll(self.resolve, "down", 1)
        self.assertEqual(self.preference.call_count, 2)

    def test_warmed_scroll_work_budget(self):
        self.module.scroll(self.resolve, "down", 1)
        self.preference.reset_mock()
        self.resolve.reset_mock()
        self.module.ctrl.mouse_scroll.reset_mock()
        for _ in range(20):
            self.module.scroll(self.resolve, "down", 1)
        self.preference.assert_not_called()
        self.assertEqual(self.resolve.call_count, 20)
        self.assertEqual(self.module.ctrl.mouse_scroll.call_count, 20)
        self.module.ctrl.mouse_move.assert_not_called()
        self.module.actions.sleep.assert_not_called()

    def test_horizontal_distance_and_natural_direction(self):
        self.preference.return_value.stdout = "0"
        self.module.scroll(self.resolve, "right", 3)
        self.module.ctrl.mouse_scroll.assert_called_once_with(y=0, x=-120, pos=(50, 40))

    def test_focus_change_during_menu_check_refuses_all_input(self):
        def changed(*_):
            self.fake.active_app = None
            return None

        with (
            patch.object(self.module.ui, "active_menu", side_effect=changed),
            self.assertRaisesRegex(RuntimeError, "focused window changed"),
        ):
            self.module.scroll(self.resolve, "down", 1)
        self.module.ctrl.mouse_move.assert_not_called()
        self.module.ctrl.mouse_scroll.assert_not_called()

    def test_focus_change_during_resolution_cannot_retarget_another_window(self):
        def changed():
            self.fake.active_app = types.SimpleNamespace(
                element=Element(AXFocusedWindow=Element())
            )
            return self.root

        with self.assertRaisesRegex(RuntimeError, "focused window changed"):
            self.module.scroll(changed, "down", 1)
        self.module.ctrl.mouse_move.assert_not_called()
        self.module.ctrl.mouse_scroll.assert_not_called()

    def test_invalid_distance_refuses_input(self):
        for distance in (0, -1, float("nan"), float("inf")):
            self.fake.settings["user.mouse_wheel_down_amount"] = distance
            with self.assertRaises(ValueError):
                self.module.scroll(self.resolve, "down", 1)
        self.module.ctrl.mouse_move.assert_not_called()
        self.module.ctrl.mouse_scroll.assert_not_called()

    def test_missing_or_unexpected_scroll_preference_blocks_input(self):
        self.preference.return_value.stdout = ""
        with self.assertRaisesRegex(RuntimeError, "boolean"):
            self.module.scroll(self.resolve, "down", 1)
        self.preference.side_effect = self.module.subprocess.CalledProcessError(
            1, "defaults"
        )
        with self.assertRaisesRegex(RuntimeError, "preference"):
            self.module.scroll(self.resolve, "down", 1)
        self.module.ctrl.mouse_move.assert_not_called()
        self.module.ctrl.mouse_scroll.assert_not_called()

    def test_scroll_without_clicking_uses_native_wheel_and_existing_distance(self):
        invalidate = (
            self.module.actions.user.accessibility_invalidate_numbers_for_scroll
        )
        self.module.scroll(self.resolve, "down", 2)
        self.module.actions.sleep.assert_not_called()
        self.module.ctrl.mouse_move.assert_not_called()
        self.module.ctrl.mouse_scroll.assert_called_once_with(y=240, x=0, pos=(50, 40))
        self.resolve.assert_called_once_with()
        invalidate.assert_called_once()
        self.assertEqual(self.root.performed, [])

    def test_repeated_scroll_uses_normal_wheel_semantics_without_ax_hit_tests(self):
        self.module.ui.element_at.side_effect = AssertionError("Unreliable AX hit")
        for _ in range(20):
            self.module.scroll(self.resolve, "down", 1)
        self.module.ctrl.mouse_move.assert_not_called()
        self.assertEqual(self.module.ctrl.mouse_scroll.call_count, 20)
        self.module.ui.element_at.assert_not_called()

    def test_async_pointer_move_uses_explicit_scroll_position_without_wait(self):
        self.fake.mouse_pos.return_value = (0, 0)
        self.module.scroll(self.resolve, "down", 1)
        self.module.ctrl.mouse_move.assert_called_once_with(50, 40)
        self.module.ctrl.mouse_scroll.assert_called_once_with(y=120, x=0, pos=(50, 40))
        self.module.actions.sleep.assert_not_called()

    def test_menu_blocks_scroll(self):
        self.fake.active_menu = Element()
        with self.assertRaisesRegex(RuntimeError, "menu"):
            self.module.scroll(self.resolve, "down", 1)
        self.module.ctrl.mouse_move.assert_not_called()

    def test_bad_arguments_are_reported_before_resolving(self):
        for direction, amount in (("elsewhere", 1), ("up", 0), ("down", 21)):
            with self.assertRaises(ValueError):
                self.module.scroll(self.resolve, direction, amount)
        self.resolve.assert_not_called()

    def test_failure_logs_and_notifies(self):
        with self.assertLogs(level="ERROR"):
            self.module.run(lambda: self.module.scroll(self.resolve, "down", 0))
        self.fake.notify.assert_called_once()
