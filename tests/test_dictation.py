import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "dictation" / "dictation.py"


class Context:
    def __init__(self):
        self.tags = []
        self.settings = {}


class Module:
    def tag(self, *args, **kwargs):
        pass

    def action_class(self, cls):
        return cls


class DictationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("dictation_under_test", SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        self.actions = Mock()
        talon = types.SimpleNamespace(
            Context=Context, Module=Module, actions=self.actions, app=Mock()
        )
        with patch.dict(sys.modules, {"talon": talon}):
            spec.loader.exec_module(self.module)

    def test_long_timeout_is_scoped_to_its_tag(self):
        self.assertEqual(self.module.ctx.matches, "os: mac")
        self.assertEqual(self.module.ctx.tags, ["user.navigation_dictation"])
        self.assertIn(
            "tag: user.navigation_dictation_long", self.module.long_ctx.matches
        )
        self.assertEqual(self.module.long_ctx.settings, {"speech.timeout": 2.0})

    def test_long_and_short_are_repeatable_and_restore_normal_settings(self):
        for _ in range(2):
            self.module.Actions.navigation_dictation_long()
            self.assertEqual(
                self.module.ctx.tags,
                ["user.navigation_dictation", "user.navigation_dictation_long"],
            )
        for _ in range(2):
            self.module.Actions.navigation_dictation_short()
            self.assertEqual(self.module.ctx.tags, ["user.navigation_dictation"])
        self.assertEqual(self.module.ctx.settings, {})

    def test_prose_command_inserts_and_records_history_like_phrase(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        self.assertIn(
            "prose <user.prose>$:\n"
            "    user.add_phrase_to_history(prose)\n"
            "    insert(prose)\n",
            grammar,
        )

    def test_default_type_literal_say_commands_are_not_overridden(self):
        rules = [
            line
            for line in SOURCE.with_suffix(".talon").read_text().splitlines()
            if line and not line.startswith(("#", " "))
        ]
        for prefix in ("type", "literal", "say"):
            with self.subTest(prefix=prefix):
                self.assertFalse(any(rule.startswith(prefix) for rule in rules))

    def test_existing_formatter_commands_are_not_overridden(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        self.assertNotIn("{user.prose_formatter}", grammar)
