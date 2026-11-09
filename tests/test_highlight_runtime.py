import types
import unittest
from unittest.mock import Mock, patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        ActionFailed,
        Element,
        FakeTalon,
        Span,
        UIErr,
        load,
    )
else:
    from accessibility_support import (
        ActionFailed,
        Element,
        FakeTalon,
        Span,
        UIErr,
        load,
    )


class HighlightRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.talon.active_app = types.SimpleNamespace(pid=1, name="Editor")
        self.element = Element(
            AXRole="AXTextArea",
            AXValue="one two one",
            AXSelectedTextRange=Span(0, 0),
            AXSharedCharacterRange=Span(10, 21),
            AXFocused=True,
        )
        self.talon.user.dictation_current_element = lambda: self.element
        self.talon.user.homophones_get = lambda word: None
        self.module = load(
            self.talon, "experiments/text_highlight/text_highlight_spike.py"
        )
        self.actions = self.module.Actions

    def test_start_selects_nearest_match_with_shared_offset(self):
        self.actions.text_highlight_spike_start("one")
        selected = self.element.attrs["AXSelectedTextRange"]
        self.assertEqual((selected.left, selected.right), (10, 13))

    def test_non_bmp_character_before_match_uses_utf16_ax_range(self):
        content = "one two one. 🙂 target word. one again."
        self.element.attrs.update(
            AXValue=content,
            AXSelectedTextRange=Span(116, 116),
            AXSharedCharacterRange=Span(100, 100 + len(content) + 1),
        )

        self.actions.text_highlight_spike_start("target")

        selected = self.element.attrs["AXSelectedTextRange"]
        self.assertEqual((selected.left, selected.right), (116, 122))

    def test_shared_range_change_rejects_stale_mapping(self):
        self.actions.text_highlight_spike_start("one")
        self.element.attrs["AXSharedCharacterRange"] = Span(50, 61)

        self.actions.text_highlight_spike_next()

        self.assertIsNone(self.module._session)
        self.assertEqual(self.element.attrs["AXSelectedTextRange"].left, 10)
        self.talon.notify.assert_called_with(
            "Highlight word", "Unable to update the highlighted word."
        )

    def test_window_change_rejects_selection(self):
        self.actions.text_highlight_spike_start("one")
        self.talon.active_window = types.SimpleNamespace(id=2)

        self.actions.text_highlight_spike_next()

        self.assertIsNone(self.module._session)
        self.assertEqual(self.element.attrs["AXSelectedTextRange"].left, 10)

    def test_homophone_failure_is_surfaced_and_exact_matching_continues(self):
        self.talon.user.homophones_get = Mock(side_effect=ActionFailed("missing"))

        self.actions.text_highlight_spike_start("one")

        self.assertIsNotNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Highlight word",
            "Homophone lookup failed; matching the exact word only.",
        )

    def test_missing_homophone_action_is_surfaced(self):
        self.talon.user.homophones_get = Mock(side_effect=KeyError("homophones_get"))

        self.actions.text_highlight_spike_start("one")

        self.assertIsNotNone(self.module._session)
        self.talon.notify.assert_called_with(
            "Highlight word",
            "Homophones are unavailable; matching the exact word only.",
        )

    def test_unavailable_element_is_reported(self):
        self.actions.text_highlight_spike_start("one")
        self.element.dead = True

        self.module._element_changed()

        self.assertIsNone(self.module._session)
        self.assertIn("no longer available", self.talon.notify.call_args[0][1])

    def test_reload_stops_previous_session(self):
        self.actions.text_highlight_spike_start("one")
        session = self.module._session

        load(
            self.talon,
            "experiments/text_highlight/text_highlight_spike.py",
            self.module,
        )

        self.assertTrue(session.stopped)
        self.assertIsNone(self.module._session)

    def test_navigation_wraps_and_close_preserves_selection(self):
        self.actions.text_highlight_spike_start("one")
        for operation, expected in (
            (self.actions.text_highlight_spike_next, (18, 21)),
            (self.actions.text_highlight_spike_next, (10, 13)),
            (self.actions.text_highlight_spike_previous, (18, 21)),
            (self.actions.text_highlight_spike_first, (10, 13)),
            (self.actions.text_highlight_spike_last, (18, 21)),
            (lambda: self.actions.text_highlight_spike_select(1), (10, 13)),
        ):
            with self.subTest(expected=expected):
                operation()
                selected = self.element.attrs["AXSelectedTextRange"]
                self.assertEqual((selected.left, selected.right), expected)

        selected = self.element.attrs["AXSelectedTextRange"]
        self.actions.text_highlight_spike_hide()
        self.assertIs(self.element.attrs["AXSelectedTextRange"], selected)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.module.tag_ctx.tags, [])
        self.module.highlight_gui.hide.assert_called_once()

    def test_invalid_number_cleans_up_without_changing_selection(self):
        self.actions.text_highlight_spike_start("one")
        selected = self.element.attrs["AXSelectedTextRange"]

        self.actions.text_highlight_spike_select(99)

        self.assertIs(self.element.attrs["AXSelectedTextRange"], selected)
        self.assertIsNone(self.module._session)
        self.assertEqual(self.module.tag_ctx.tags, [])

    def test_selection_write_failure_logs_notifies_and_cleans_up(self):
        self.actions.text_highlight_spike_start("one")
        with (
            patch.object(Element, "__setitem__", side_effect=UIErr("read only")),
            self.assertLogs(level="ERROR") as logged,
        ):
            self.actions.text_highlight_spike_next()

        self.assertIn("read only", "\n".join(logged.output))
        self.talon.notify.assert_called_with(
            "Highlight word", "Unable to update the highlighted word."
        )
        self.assertIsNone(self.module._session)
        self.assertEqual(self.module.tag_ctx.tags, [])

    def test_app_focus_and_text_changes_each_prevent_another_selection(self):
        for change in ("app", "focus", "text"):
            with self.subTest(change=change):
                self.talon.active_app = types.SimpleNamespace(pid=1, name="Editor")
                self.element.attrs.update(AXFocused=True, AXValue="one two one")
                self.actions.text_highlight_spike_start("one")
                selected = self.element.attrs["AXSelectedTextRange"]
                if change == "app":
                    self.talon.active_app = types.SimpleNamespace(pid=2)
                elif change == "focus":
                    self.element.attrs["AXFocused"] = False
                else:
                    self.element.attrs["AXValue"] = "changed"

                with self.assertLogs(level="ERROR"):
                    self.actions.text_highlight_spike_next()

                self.assertIsNone(self.module._session)
                self.assertIs(self.element.attrs["AXSelectedTextRange"], selected)


if __name__ == "__main__":
    unittest.main()
