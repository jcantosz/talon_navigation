import importlib.util
import itertools
import random
import sys
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "window_hints_core",
    Path(__file__).resolve().parents[1] / "window_hints" / "core.py",
)
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)

R = core.Rect
C = core.Candidate
WINDOW = R(0, 0, 1000, 800)

# Hand-built Outlook-like layout (fixture F1 shape): tools, inboxes, mail, message.
OUTLOOK = {
    "tools": R(0, 0, 60, 800),
    "inboxes": R(60, 0, 240, 800),
    "mail": R(300, 0, 300, 800),
    "message": R(600, 0, 400, 800),
}


def panes_for(layout, role="AXScrollArea", named=True):
    return [C(role, rect, 2, None, named) for rect in layout.values()]


class RectTests(unittest.TestCase):
    def test_as_rect_accepts_dict_sequence_and_object(self):
        class Frame:
            x, y, width, height = 1, 2, 3, 4

        expected = R(1, 2, 3, 4)
        self.assertEqual(
            core.as_rect({"x": 1, "y": 2, "width": 3, "height": 4}), expected
        )
        self.assertEqual(core.as_rect((1, 2, 3, 4)), expected)
        self.assertEqual(core.as_rect(Frame()), expected)

    def test_as_rect_rejects_unusable_frames(self):
        for bad in (
            None,
            (0, 0, 0, 10),
            (0, 0, 10, -1),
            (0, 0, float("nan"), 5),
            (0, 0, float("inf"), 5),
            (1, 2, 3),
            {"x": 1},
            ("a", 0, 1, 1),
        ):
            self.assertIsNone(core.as_rect(bad), bad)

    def test_negative_origin_and_intersection(self):
        clipped = core.intersect(R(-100, -50, 300, 200), WINDOW)
        self.assertEqual(clipped, R(0, 0, 200, 150))
        self.assertIsNone(core.intersect(R(1000, 0, 10, 10), WINDOW))

    def test_iou_identical_disjoint_and_half(self):
        self.assertEqual(core.iou(R(0, 0, 10, 10), R(0, 0, 10, 10)), 1.0)
        self.assertEqual(core.iou(R(0, 0, 10, 10), R(20, 0, 10, 10)), 0.0)
        self.assertAlmostEqual(core.iou(R(0, 0, 10, 10), R(5, 0, 10, 10)), 1 / 3)


class SelectionTests(unittest.TestCase):
    def test_side_by_side_panes_are_ordered_left_to_right(self):
        panes = core.select_candidates(panes_for(OUTLOOK), WINDOW)
        self.assertEqual([p.frame for p in panes], list(OUTLOOK.values()))

    def test_ordering_is_stable_under_shuffling(self):
        source = panes_for(OUTLOOK)
        expected = core.select_candidates(source, WINDOW)
        generator = random.Random(7)
        for _ in range(50):
            shuffled = source[:]
            generator.shuffle(shuffled)
            self.assertEqual(core.select_candidates(shuffled, WINDOW), expected)

    def test_reading_pane_below_orders_top_then_bottom_within_a_column(self):
        layout = {
            "mail": R(300, 0, 700, 400),
            "message": R(300, 400, 700, 400),
        }
        panes = core.select_candidates(panes_for(layout), WINDOW)
        self.assertEqual([p.frame for p in panes], list(layout.values()))

    def test_row_tolerance_treats_near_equal_tops_as_one_row(self):
        panes = core.order_panes(
            [C("AXList", R(500, 3, 100, 100)), C("AXList", R(100, 0, 100, 100))]
        )
        self.assertEqual([p.frame.x for p in panes], [100, 500])

    def test_identical_frames_keep_the_outermost(self):
        outer = C("AXSplitGroup", R(0, 0, 500, 400), depth=1, named=True)
        inner = C("AXScrollArea", R(0, 0, 500, 400), depth=4, named=True)
        for order in itertools.permutations((outer, inner)):
            (kept,) = core.select_candidates(order, WINDOW)
            self.assertEqual(kept.role, "AXSplitGroup")

    def test_whole_window_tiny_unnamed_and_non_pane_roles_are_dropped(self):
        source = [
            C("AXScrollArea", WINDOW, named=True),
            C("AXScrollArea", R(0, 0, 10, 600), named=True),
            C("AXScrollArea", R(100, 0, 200, 600), named=False),
            C("AXButton", R(300, 0, 200, 600), named=True),
        ]
        self.assertEqual(core.select_candidates(source, WINDOW, "named"), [])
        structural = core.select_candidates(source, WINDOW, "structural")
        self.assertEqual([p.frame for p in structural], [R(100, 0, 200, 600)])

    def test_pane_is_clipped_to_the_window(self):
        (pane,) = core.select_candidates(
            [C("AXScrollArea", R(-50, 100, 400, 2000), named=True)], WINDOW
        )
        self.assertEqual(pane.frame, R(0, 100, 350, 700))

    def test_structural_is_a_superset_of_named_even_with_identical_frames(self):
        frame = R(100, 100, 300, 300)
        source = [
            C("AXSplitGroup", frame, depth=1, named=False),
            C("AXScrollArea", frame, depth=4, named=True),
            C("AXToolbar", R(500, 100, 200, 200), depth=2, named=False),
        ]
        named = core.select_candidates(source, WINDOW, "named")
        structural = core.select_candidates(source, WINDOW, "structural")
        self.assertEqual([p.frame for p in named], [frame])
        self.assertTrue(named[0].named)
        self.assertEqual(len(structural), 2)
        self.assertIn(named[0].frame, [p.frame for p in structural])

    def test_element_reference_survives_selection(self):
        marker = object()
        (pane,) = core.select_candidates(
            [C("AXOutline", R(10, 10, 200, 300), 1, None, True, marker)], WINDOW
        )
        self.assertIs(pane.ref, marker)

    def test_unknown_rule_is_an_error(self):
        with self.assertRaises(ValueError):
            core.select_candidates([], WINDOW, "fuzzy")

    def test_multi_display_negative_window_coordinates(self):
        window = R(-1500, -200, 1400, 900)
        (pane,) = core.select_candidates(
            [C("AXOutline", R(-1500, -200, 300, 900), named=True)], window
        )
        self.assertEqual(pane.frame, R(-1500, -200, 300, 900))


class AnchorTests(unittest.TestCase):
    def test_anchor_is_inside_pane_and_rule_spans_the_width(self):
        rect = R(60, 10, 240, 780)
        anchor = core.hint_anchor(rect)
        self.assertEqual((anchor.x, anchor.y), (64, 14))
        self.assertEqual(anchor.underline_start, (60, 10))
        self.assertEqual(anchor.underline_end, (300, 10))

    def test_anchor_never_leaves_a_tiny_pane(self):
        rect = R(10, 10, 4, 4)
        anchor = core.hint_anchor(rect, inset=50)
        self.assertTrue(rect.x <= anchor.x <= rect.right)
        self.assertTrue(rect.y <= anchor.y <= rect.bottom)

    def test_overlapping_hints_are_reported_not_moved(self):
        close = [
            core.hint_anchor(R(0, 0, 100, 100)),
            core.hint_anchor(R(30, 0, 100, 100)),
        ]
        self.assertEqual(core.hint_overlaps(close), [(0, 1)])
        anchors = [core.hint_anchor(OUTLOOK[name]) for name in OUTLOOK]
        self.assertEqual(core.hint_overlaps(anchors, (50, 20)), [])

    def test_narrow_sidebar_collides_with_a_wide_hint(self):
        # The 60 px tools pane and its neighbour are 60 px apart: an 80 px wide
        # hint overlaps, a 50 px one does not. Hint width is a WH4 constraint.
        anchors = [core.hint_anchor(OUTLOOK[name]) for name in OUTLOOK]
        self.assertEqual(core.hint_overlaps(anchors, (80, 20)), [(0, 1)])


class ScoreTests(unittest.TestCase):
    def test_perfect_match_has_full_precision_and_recall(self):
        panes = core.select_candidates(panes_for(OUTLOOK), WINDOW)
        result = core.score(OUTLOOK, panes)
        self.assertEqual((result.precision, result.recall), (1.0, 1.0))

    def test_missing_pane_is_named(self):
        layout = dict(OUTLOOK)
        del layout["inboxes"]
        panes = core.select_candidates(panes_for(layout), WINDOW)
        result = core.score(OUTLOOK, panes)
        self.assertEqual(result.missed, ("inboxes",))
        self.assertEqual(result.recall, 0.75)
        self.assertEqual(result.precision, 1.0)

    def test_extra_pane_lowers_precision(self):
        source = panes_for(OUTLOOK) + [C("AXList", R(310, 10, 200, 100), named=True)]
        panes = core.select_candidates(source, WINDOW)
        result = core.score(OUTLOOK, panes)
        self.assertEqual(result.recall, 1.0)
        self.assertEqual(result.precision, 0.8)

    def test_split_truth_matches_only_one_candidate(self):
        truth = {"mail": R(300, 0, 300, 800)}
        halves = [
            C("AXList", R(300, 0, 300, 400)),
            C("AXList", R(300, 400, 300, 400)),
        ]
        result = core.score(truth, halves)
        self.assertEqual(result.matched, ())
        self.assertEqual(result.missed, ("mail",))

    def test_input_order_does_not_change_the_score(self):
        panes = core.select_candidates(panes_for(OUTLOOK), WINDOW)
        forward = core.score(OUTLOOK, panes)
        backward = core.score(OUTLOOK, panes[::-1])
        self.assertEqual(
            [name for name, _ in forward.matched],
            [name for name, _ in backward.matched],
        )
        self.assertEqual(
            [panes[i].frame for _, i in forward.matched],
            [panes[::-1][i].frame for _, i in backward.matched],
        )

    def test_empty_truth_and_panes(self):
        result = core.score({}, [])
        self.assertEqual((result.precision, result.recall), (1.0, 1.0))


if __name__ == "__main__":
    unittest.main()
