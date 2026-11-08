import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "general" / "sleep_captions.py"


class CaptionItem:
    def __init__(self, checked):
        self.attrs = {"name": "Show Subtitles"}
        self.checked = checked
        self.calls = 0

    def __call__(self):
        self.checked = not self.checked
        self.calls += 1


class SleepCaptionsTests(unittest.TestCase):
    def setUp(self):
        mod = Mock()
        mod.action_class.side_effect = lambda cls: cls
        self.app = Mock()
        self.actions = Mock()
        self.actions.speech.enabled.return_value = False
        self.cron = Mock()
        self.scope = Mock()
        self.speech_system = types.SimpleNamespace(ready=False)
        self.item = CaptionItem(True)
        self.menu = types.SimpleNamespace(
            menu=types.SimpleNamespace(items=[self.item]),
        )
        talon = types.ModuleType("talon")
        talon.Module = Mock(return_value=mod)
        talon.actions = self.actions
        talon.app = self.app
        talon.cron = self.cron
        talon.menu = self.menu
        talon.scope = self.scope
        talon.speech_system = self.speech_system
        spec = importlib.util.spec_from_file_location(
            "sleep_captions_under_test", SOURCE
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"talon": talon}):
            spec.loader.exec_module(self.module)

    def test_ready_syncs_without_starting_a_timer(self):
        self.app.register.assert_called_once_with("ready", self.module.on_ready)
        self.scope.register.assert_called_once_with(
            "change", self.module.on_scope_change
        )
        self.module.on_ready()
        self.assertFalse(self.item.checked)
        self.cron.interval.assert_not_called()

    def test_mode_events_sync_but_unrelated_events_do_not(self):
        self.speech_system.ready = True
        self.module.on_scope_change({"app"})
        self.assertEqual(self.item.calls, 0)
        self.module.on_scope_change({"mode"})
        self.assertFalse(self.item.checked)
        self.actions.speech.enabled.return_value = True
        self.module.on_scope_change({"mode"})
        self.assertTrue(self.item.checked)

    def test_scope_events_wait_until_speech_system_is_ready(self):
        self.menu.menu.items = []
        self.module.on_scope_change({"mode"})
        self.cron.interval.assert_not_called()

    def test_reload_syncs_immediately_when_speech_system_is_ready(self):
        self.speech_system.ready = True
        spec = importlib.util.spec_from_file_location("caption_reload", SOURCE)
        reloaded = importlib.util.module_from_spec(spec)
        talon = types.SimpleNamespace(
            Module=Mock(return_value=self.module.mod),
            actions=self.actions,
            app=self.app,
            menu=self.menu,
            scope=self.scope,
            speech_system=self.speech_system,
            cron=self.cron,
        )
        with patch.dict(sys.modules, {"talon": talon}):
            spec.loader.exec_module(reloaded)
        self.assertFalse(self.item.checked)
        self.cron.interval.assert_not_called()

    def test_waking_enables_and_sleeping_disables_actual_menu_state(self):
        self.module.sync_captions()
        self.actions.speech.enabled.return_value = True
        self.module.sync_captions()
        self.assertTrue(self.item.checked)
        self.actions.speech.enabled.return_value = False
        self.module.sync_captions()
        self.assertFalse(self.item.checked)

    def test_matching_state_is_not_toggled_repeatedly(self):
        self.module.sync_captions()
        self.module.sync_captions()
        self.assertEqual(self.item.calls, 1)

    def test_hidden_enables_automatic_sleep_control(self):
        self.actions.speech.enabled.return_value = True
        self.item.checked = False
        self.module.Actions.sleep_captions_hidden()
        self.assertTrue(self.item.checked)

    def test_default_restores_original_state_and_stops_enforcement(self):
        self.module.sync_captions()
        self.module.Actions.sleep_captions_default()
        self.assertTrue(self.item.checked)
        self.item.checked = False
        self.module.sync_captions()
        self.assertFalse(self.item.checked)
        self.module.Actions.sleep_captions_default()
        self.assertFalse(self.item.checked)

    def test_reenable_captures_new_manual_baseline(self):
        self.module.sync_captions()
        self.module.Actions.sleep_captions_default()
        self.item.checked = False
        self.module.Actions.sleep_captions_hidden()
        self.actions.speech.enabled.return_value = True
        self.module.sync_captions()
        self.module.Actions.sleep_captions_default()
        self.assertFalse(self.item.checked)

    def test_global_caption_commands_set_state_and_disable_sleep_enforcement(self):
        self.module.sync_captions()
        self.module.Actions.captions_disable()
        self.assertFalse(self.item.checked)
        self.actions.speech.enabled.return_value = True
        self.module.sync_captions()
        self.assertFalse(self.item.checked)

        self.module.Actions.captions_enable()
        self.assertTrue(self.item.checked)
        self.actions.speech.enabled.return_value = False
        self.module.sync_captions()
        self.assertTrue(self.item.checked)

    def test_missing_native_control_fails_explicitly(self):
        self.menu.menu.items = []
        with self.assertRaisesRegex(RuntimeError, "Show Subtitles"):
            self.module.sync_captions()

    def test_finds_caption_control_in_native_submenu(self):
        submenu = types.SimpleNamespace(items=[self.item])
        self.menu.menu.items = [
            types.SimpleNamespace(attrs={"name": "Speech", "submenu": submenu})
        ]
        self.assertIs(self.module.caption_item(), self.item)

    def test_commands_are_anchored_and_available_awake_and_asleep(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        for mode in ("command", "dictation", "sleep"):
            self.assertIn(f"mode: {mode}\n", grammar)
        for word, action in (("hidden", "hidden"), ("default", "default")):
            self.assertIn(
                f"^sleep captions {word}$:\n    user.sleep_captions_{action}()\n",
                grammar,
            )
        for rule, action in (
            ("(enable | on)", "enable"),
            ("(disable | off)", "disable"),
        ):
            self.assertIn(
                f"^captions {rule}$:\n    user.captions_{action}()\n",
                grammar,
            )
