import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

SOURCE = Path(__file__).resolve().parents[1] / "general" / "sleep_warning.py"


class DurationMatch:
    def __init__(self, number, unit):
        self.number = number
        self.unit = unit

    def __getitem__(self, index):
        return self.unit


class SleepWarningTests(unittest.TestCase):
    def setUp(self):
        self.actions = Mock()
        self.actions.speech.enabled.return_value = False
        self.app = Mock()
        self.cron = Mock()
        self.cron.after.side_effect = lambda *args: object()
        self.gui = Mock()

        def decorate_gui(fn):
            self.draw_gui = fn
            return self.gui

        self.mod = Mock()
        self.mod.action_class.side_effect = lambda cls: cls
        self.mod.capture.side_effect = lambda **kwargs: lambda fn: fn
        self.settings = Mock()
        self.setting_values = {
            "user.sleep_warning": True,
            "user.sleep_warning_use_overlay": False,
        }
        self.settings.get.side_effect = self.setting_values.__getitem__
        self.speech_system = Mock()
        talon = types.SimpleNamespace(
            Module=Mock(return_value=self.mod),
            actions=self.actions,
            app=self.app,
            cron=self.cron,
            imgui=types.SimpleNamespace(open=lambda: decorate_gui, GUI=Mock),
            settings=self.settings,
            speech_system=self.speech_system,
        )
        spec = importlib.util.spec_from_file_location(
            "sleep_warning_under_test", SOURCE
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"talon": talon}):
            spec.loader.exec_module(self.module)
        self.clock = patch.object(self.module.time, "monotonic", return_value=100.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.ignored = {
            "phrase": ["say", "hello"],
            "parsed": [types.SimpleNamespace(_name="___ltphrase_gt__")],
        }

    def test_registers_phrase_listener(self):
        self.speech_system.register.assert_called_once_with(
            "phrase", self.module.on_phrase
        )

    def test_warns_when_sleep_catch_all_ignores_speech(self):
        self.module.on_phrase(self.ignored)
        self.app.notify.assert_called_once_with(
            "Talon sleep warnings",
            'Talon is asleep. Say "wake up" to enable commands.',
        )
        self.gui.show.assert_not_called()
        self.cron.after.assert_not_called()
        self.assertEqual(self.actions.mock_calls, [call.speech.enabled()])

    def test_does_not_warn_while_awake(self):
        self.actions.speech.enabled.return_value = True
        self.module.on_phrase(self.ignored)
        self.app.notify.assert_not_called()
        self.gui.show.assert_not_called()

    def test_does_not_warn_for_wake_up_or_other_sleep_commands(self):
        for name in ("wake_up", "microphone_off"):
            with self.subTest(name=name):
                self.module.on_phrase(
                    {
                        "phrase": ["wake", "up"],
                        "parsed": [types.SimpleNamespace(_name=name)],
                    }
                )
        self.gui.show.assert_not_called()
        self.app.notify.assert_not_called()

    def test_does_not_warn_without_recognized_words_or_sleep_catch_all(self):
        for event in (
            {},
            {"phrase": []},
            {"phrase": ["hello"]},
            {"phrase": ["hello"], "parsed": []},
            {"phrase": ["hello"], "parsed": self.ignored["parsed"] * 2},
        ):
            with self.subTest(event=event):
                self.module.on_phrase(event)
        self.gui.show.assert_not_called()
        self.app.notify.assert_not_called()

    def test_can_be_disabled(self):
        self.setting_values["user.sleep_warning"] = False
        self.module.on_phrase(self.ignored)
        self.gui.show.assert_not_called()
        self.app.notify.assert_not_called()

    def test_limits_warnings_to_once_every_five_seconds(self):
        self.module.on_phrase(self.ignored)
        self.now.return_value = 104.99
        self.module.on_phrase(self.ignored)
        self.app.notify.assert_called_once()
        self.now.return_value = 105.0
        self.module.on_phrase(self.ignored)
        self.assertEqual(self.app.notify.call_count, 2)

    def test_awake_speech_resets_throttle(self):
        self.module.on_phrase(self.ignored)
        self.actions.speech.enabled.return_value = True
        self.module.on_phrase({"phrase": ["wake", "up"]})
        self.actions.speech.enabled.return_value = False
        self.module.on_phrase(self.ignored)
        self.assertEqual(self.app.notify.call_count, 2)

    def test_overlay_hides_after_timer_fires(self):
        self.setting_values["user.sleep_warning_use_overlay"] = True
        self.module.on_phrase(self.ignored)
        self.gui.show.assert_called_once_with()
        self.app.notify.assert_not_called()
        self.cron.after.assert_called_once_with("3s", self.module.hide_warning)
        self.cron.after.call_args.args[1]()
        self.gui.hide.assert_called_once_with()
        self.assertIsNone(self.module._hide_job)

    def test_replacing_overlay_cancels_previous_hide_timer(self):
        self.setting_values["user.sleep_warning_use_overlay"] = True
        self.module.show_warning("first")
        first_job = self.module._hide_job
        self.module.show_warning("second")
        self.cron.cancel.assert_called_once_with(first_job)
        self.assertEqual(self.module._message, "second")
        drawing = Mock()
        self.draw_gui(drawing)
        drawing.text.assert_called_once_with("second")

    def test_voice_enable_overrides_disabled_startup_setting(self):
        self.setting_values["user.sleep_warning"] = False
        self.module.Actions.sleep_warning_enable()
        self.app.notify.assert_called_once_with(
            "Talon sleep warnings", "Sleep warnings on"
        )
        self.app.notify.reset_mock()
        self.module.on_phrase(self.ignored)
        self.app.notify.assert_called_once()

    def test_voice_disable_stops_warnings_and_confirms(self):
        self.module.Actions.sleep_warning_disable()
        self.app.notify.assert_called_once_with(
            "Talon sleep warnings", "Sleep warnings off"
        )
        self.app.notify.reset_mock()
        self.module.on_phrase(self.ignored)
        self.app.notify.assert_not_called()
        self.assertIsNone(self.module._last_warning)

    def test_switching_to_native_hides_pending_overlay(self):
        self.setting_values["user.sleep_warning_use_overlay"] = True
        self.module.show_warning("overlay")
        job = self.module._hide_job
        self.setting_values["user.sleep_warning_use_overlay"] = False
        self.module.show_warning("native")
        self.cron.cancel.assert_called_once_with(job)
        self.gui.hide.assert_called_once_with()
        self.assertIsNone(self.module._hide_job)
        self.app.notify.assert_called_once_with("Talon sleep warnings", "native")

    def test_voice_commands_are_anchored_and_available_in_sleep(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        for mode in ("command", "dictation", "sleep"):
            self.assertIn(f"mode: {mode}\n", grammar)
        for word, action in (("on", "enable"), ("off", "disable")):
            self.assertIn(
                f"^sleep warnings {word}$:\n    user.sleep_warning_{action}()\n",
                grammar,
            )

    def test_duration_capture_converts_singular_and_plural_units(self):
        for amount, unit, seconds in (
            (30, "minutes", 1800),
            (1, "hour", 3600),
            (2, "hours", 7200),
            (1, "minute", 60),
            (10, "seconds", 10),
            (1, "second", 1),
        ):
            with self.subTest(amount=amount, unit=unit):
                match = DurationMatch(amount, unit)
                self.assertEqual(self.module.sleep_warning_duration(match), seconds)

    def test_timed_disable_suppresses_warnings_then_enables_them(self):
        self.module.Actions.sleep_warning_disable_for(1800)
        self.cron.after.assert_called_once_with("1800s", self.module.resume_warnings)
        self.app.notify.assert_called_once_with(
            "Talon sleep warnings", "Sleep warnings off for 30 minutes"
        )
        self.app.notify.reset_mock()
        self.module.on_phrase(self.ignored)
        self.app.notify.assert_not_called()
        self.cron.after.call_args.args[1]()
        self.assertTrue(self.module._enabled_override)
        self.assertIsNone(self.module._resume_job)
        self.app.notify.assert_called_once_with(
            "Talon sleep warnings", "Sleep warnings on"
        )

    def test_hour_duration_confirmation(self):
        self.module.Actions.sleep_warning_disable_for(3600)
        self.app.notify.assert_called_once_with(
            "Talon sleep warnings", "Sleep warnings off for 1 hour"
        )

    def test_new_timer_replaces_previous_timer(self):
        self.module.Actions.sleep_warning_disable_for(60)
        first_job = self.module._resume_job
        self.module.Actions.sleep_warning_disable_for(120)
        self.cron.cancel.assert_called_once_with(first_job)
        self.assertIsNot(self.module._resume_job, first_job)
        self.assertEqual(self.cron.after.call_args.args[0], "120s")

    def test_manual_on_or_off_cancels_pending_resume(self):
        for action in ("sleep_warning_enable", "sleep_warning_disable"):
            with self.subTest(action=action):
                self.module.Actions.sleep_warning_disable_for(60)
                job = self.module._resume_job
                self.cron.cancel.reset_mock()
                getattr(self.module.Actions, action)()
                self.cron.cancel.assert_called_once_with(job)
                self.assertIsNone(self.module._resume_job)

    def test_invalid_duration_does_not_cancel_existing_timer(self):
        self.module.Actions.sleep_warning_disable_for(60)
        job = self.module._resume_job
        for seconds in (0, -1):
            with self.subTest(seconds=seconds):
                with self.assertRaisesRegex(ValueError, "greater than zero"):
                    self.module.Actions.sleep_warning_disable_for(seconds)
                self.assertIs(self.module._resume_job, job)
        self.cron.cancel.assert_not_called()

    def test_timed_command_uses_existing_number_capture_and_is_anchored(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        self.assertIn(
            "^sleep warnings off [for] <user.sleep_warning_duration>$:\n"
            "    user.sleep_warning_disable_for(sleep_warning_duration)\n",
            grammar,
        )
