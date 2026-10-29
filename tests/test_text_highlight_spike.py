import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "text_highlight_spike_core",
    Path(__file__).resolve().parents[1]
    / "accessibility"
    / "text_highlight_spike_core.py",
)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class TextHighlightSpikeTests(unittest.TestCase):
    def test_finds_whole_word_matches_for_exact_terms_and_homophones(self):
        matches = core.find_matches(
            "Their project is over there, not in the theater.",
            ("there", "their"),
        )

        self.assertEqual(
            [(match.start, match.end, match.text) for match in matches],
            [(0, 5, "Their"), (22, 27, "there")],
        )

    def test_nearest_match_uses_the_caret_position(self):
        matches = core.find_matches("one two one three one", ("one",))

        self.assertEqual(core.nearest_match_index(matches, 9), 1)
        self.assertEqual(core.nearest_match_index(matches, 20), 2)

    def test_context_snippet_marks_match_and_limits_surrounding_words(self):
        content = "zero one two three target four five six seven"
        match = core.find_matches(content, ("target",))[0]

        self.assertEqual(
            core.context_snippet(content, match, surrounding_words=2),
            "… two three [target] four five …",
        )

    def test_display_window_tracks_current_match(self):
        self.assertEqual(
            core.displayed_match_indices(total=20, current=10, limit=5),
            (8, 9, 10, 11, 12),
        )
        self.assertEqual(
            core.displayed_match_indices(total=20, current=19, limit=5),
            (15, 16, 17, 18, 19),
        )


if __name__ == "__main__":
    unittest.main()
