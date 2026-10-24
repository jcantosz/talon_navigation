import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

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
        self.actions.dictate.replace_words.side_effect = lambda words: list(words)
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

    def test_each_prefix_inserts_prose_and_records_history_like_phrase(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        for prefix in ("type", "literal", "say"):
            with self.subTest(prefix=prefix):
                self.assertIn(
                    f"{prefix} <user.prose>$:\n"
                    "    user.add_phrase_to_history(prose)\n"
                    "    insert(prose)\n",
                    grammar,
                )

    def test_default_rule_is_overridden_with_the_exact_original_grammar(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        self.assertIn(
            "type <phrase> | literal <phrase> | say <phrase>:\n"
            "    user.navigation_dictation_insert_words(phrase)\n",
            grammar,
        )

    def test_default_phrase_list_inserts_and_records_the_same_text(self):
        self.module.Actions.navigation_dictation_insert_words(["hello", "world"])
        self.assertEqual(
            self.actions.mock_calls,
            [
                call.dictate.replace_words(["hello", "world"]),
                call.user.add_phrase_to_history("hello world"),
                call.insert("hello world"),
            ],
        )

    def test_default_phrase_preserves_existing_word_replacements(self):
        self.actions.dictate.replace_words.side_effect = None
        self.actions.dictate.replace_words.return_value = ["January", "first"]
        self.module.Actions.navigation_dictation_insert_words(["january", "first"])
        self.actions.user.add_phrase_to_history.assert_called_once_with("January first")
        self.actions.insert.assert_called_once_with("January first")

    def test_existing_formatter_commands_are_not_overridden(self):
        grammar = SOURCE.with_suffix(".talon").read_text()
        self.assertNotIn("{user.prose_formatter}", grammar)
