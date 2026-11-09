import importlib
import json
import random
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

package = types.ModuleType("hints_profile_under_test")
package.__path__ = [str(Path(__file__).resolve().parents[1])]
with patch.dict(sys.modules, {"talon": None, package.__name__: package}):
    profile_module = importlib.import_module(
        f"{package.__name__}.window_hints.profiles"
    )
    base = importlib.import_module(f"{package.__name__}.window_hints.core")

P = profile_module
Rect = base.Rect
FIXTURE = Path(__file__).parent / "fixtures" / "vscode_grid.json"
VSCODE = P.load_profile("vscode")


def load_fixture():
    data = json.loads(FIXTURE.read_text())
    return [
        P.Node(
            tuple(item["path"]),
            base.as_rect(item["frame"]),
            dom=item["dom"],
            classes=frozenset(item["classes"]),
        )
        for item in data["nodes"]
    ]


def names(panes):
    return [pane.name for pane in panes]


WINDOW = Rect(0, 0, 1000, 800)
MARKERS = {
    "title bar": {"classes": {"titlebar-container"}},
    "activity bar": {"classes": {"codicon-accounts-view-bar-icon"}},
    "sidebar": {"classes": {"composite", "viewlet"}},
    "panel": {"classes": {"composite", "panel"}},
    "auxiliary bar": {"classes": {"composite", "auxiliarybar"}},
    "editor": {"dom": "workbench.parts.editor"},
    "status bar": {"dom": "workbench.parts.statusbar"},
    "mystery": {},
}


def layout(cells, hidden=()):
    """A synthetic workbench: one grid whose leaf cells hold a marker two levels down."""
    nodes = [
        P.Node((), WINDOW),
        P.Node((0,), WINDOW, classes=frozenset({"monaco-grid-view"})),
    ]
    for index, (name, rect) in enumerate(cells):
        classes = {"split-view-view"}
        if name not in hidden:
            classes.add("visible")
        path = (0, index)
        marker = MARKERS[name]
        nodes += [
            P.Node(path, rect, classes=frozenset(classes)),
            P.Node(path + (0,), rect),
            P.Node(
                path + (0, 0),
                rect,
                dom=marker.get("dom", ""),
                classes=frozenset(marker.get("classes", ())),
            ),
        ]
    return nodes


STANDARD = [
    ("title bar", Rect(0, 0, 1000, 40)),
    ("activity bar", Rect(0, 40, 50, 720)),
    ("sidebar", Rect(50, 40, 250, 720)),
    ("editor", Rect(300, 40, 450, 720)),
    ("auxiliary bar", Rect(750, 40, 250, 720)),
    ("status bar", Rect(0, 760, 1000, 40)),
]


def frames(panes):
    return {pane.name: pane.frame for pane in panes}


class VSCodeProfileTests(unittest.TestCase):
    def test_named_profile_targets_split_editors_and_separate_rail_sections(self):
        profile = P.load_profile("vscode_named")
        nodes = [
            P.Node((), WINDOW),
            P.Node(
                (0,),
                Rect(0, 40, 50, 720),
                classes=frozenset({"split-view-view", "visible"}),
            ),
            P.Node(
                (0, 0),
                Rect(8, 44, 36, 300),
                classes=frozenset({"monaco-action-bar", "vertical"}),
            ),
            P.Node(
                (0, 0, 0),
                Rect(8, 44, 36, 300),
                role="AXTabGroup",
                description="Active View Switcher",
            ),
            P.Node(
                (0, 1), Rect(8, 680, 36, 80), role="AXToolbar", description="Manage"
            ),
            P.Node(
                (1,),
                Rect(50, 40, 200, 720),
                classes=frozenset({"split-view-view", "visible"}),
            ),
            P.Node(
                (1, 0),
                Rect(50, 80, 200, 680),
                classes=frozenset({"composite", "viewlet"}),
            ),
            P.Node((2,), Rect(250, 40, 750, 720), dom="workbench.parts.editor"),
            P.Node(
                (2, 0), Rect(250, 40, 350, 32), classes=frozenset({"tabs-container"})
            ),
            P.Node(
                (2, 1), Rect(250, 100, 350, 660), classes=frozenset({"editor-instance"})
            ),
            P.Node(
                (2, 2), Rect(600, 40, 400, 32), classes=frozenset({"tabs-container"})
            ),
            P.Node(
                (2, 3), Rect(600, 100, 400, 660), classes=frozenset({"editor-instance"})
            ),
            P.Node(
                (3,),
                Rect(500, 5, 200, 25),
                role="AXButton",
                description="Open Quick Access",
            ),
            P.Node(
                (4,),
                Rect(900, 40, 50, 32),
                role="AXTabGroup",
                description="Active View Switcher",
            ),
        ]
        panes = P.find_panes(nodes, profile)
        self.assertEqual(
            names(panes),
            [
                "search",
                "activity bar",
                "manage",
                "files",
                "tabs 1",
                "tabs 2",
                "editor 1",
                "editor 2",
            ],
        )
        found = frames(panes)
        self.assertEqual(found["activity bar"], nodes[2].frame)
        self.assertEqual(found["manage"], nodes[4].frame)
        self.assertNotEqual(found["editor 1"], found["editor 2"])
        self.assertEqual(found["editor 2"], nodes[11].frame)
        self.assertNotIn("activity bar 2", found)
        moved = [
            P.Node(
                node.path,
                Rect(
                    node.frame.x - 1000,
                    node.frame.y,
                    node.frame.width,
                    node.frame.height,
                ),
                node.role,
                node.subrole,
                node.dom,
                node.classes,
                node.title,
                node.description,
                node.ref,
            )
            for node in nodes
        ]
        self.assertEqual(names(P.find_panes(moved, profile)), names(panes))

    def test_real_window_yields_the_six_visible_parts_in_profile_order(self):
        panes = P.find_panes(load_fixture(), VSCODE)
        self.assertEqual(
            names(panes),
            [
                "title bar",
                "activity bar",
                "sidebar",
                "editor",
                "auxiliary bar",
                "status bar",
            ],
        )

    def test_real_window_tiles_the_workbench(self):
        panes = P.find_panes(load_fixture(), VSCODE)
        window = base.as_rect((0, 30, 1920, 960))
        result = P.report(panes, window, tiles=True)
        self.assertEqual(result["overlaps"], [])
        self.assertAlmostEqual(result["coverage"], 1.0, places=2)
        self.assertTrue(result["ok"])

    def test_profile_uses_no_view_ids_or_paths(self):
        text = (P.PROFILE_DIRECTORY / "vscode.json").read_text()
        self.assertNotIn("workbench.view.", text)
        self.assertNotIn("workbench.panel.", text)
        self.assertNotIn('"path"', text)

    def test_standard_layout(self):
        panes = P.find_panes(layout(STANDARD), VSCODE)
        self.assertEqual(frames(panes), dict(STANDARD))
        self.assertTrue(P.report(panes, WINDOW, tiles=True)["ok"])

    def test_moving_the_sidebar_right_keeps_names_and_follows_frames(self):
        moved = [
            ("title bar", Rect(0, 0, 1000, 40)),
            ("activity bar", Rect(950, 40, 50, 720)),
            ("editor", Rect(0, 40, 450, 720)),
            ("sidebar", Rect(450, 40, 500, 720)),
            ("status bar", Rect(0, 760, 1000, 40)),
        ]
        panes = P.find_panes(layout(moved), VSCODE)
        self.assertEqual(frames(panes), dict(moved))
        self.assertTrue(P.report(panes, WINDOW, tiles=True)["ok"])

    def test_bottom_panel_is_found(self):
        cells = [
            ("title bar", Rect(0, 0, 1000, 40)),
            ("sidebar", Rect(0, 40, 250, 720)),
            ("editor", Rect(250, 40, 750, 420)),
            ("panel", Rect(250, 460, 750, 300)),
            ("status bar", Rect(0, 760, 1000, 40)),
        ]
        panes = P.find_panes(layout(cells), VSCODE)
        self.assertEqual(frames(panes), dict(cells))

    def test_hidden_and_zero_size_cells_are_ignored(self):
        hidden = P.find_panes(layout(STANDARD, hidden=("auxiliary bar",)), VSCODE)
        self.assertNotIn("auxiliary bar", names(hidden))
        zero = P.find_panes(layout(STANDARD + [("panel", Rect(0, 0, 0, 0))]), VSCODE)
        self.assertNotIn("panel", names(zero))

    def test_node_order_does_not_change_the_result(self):
        nodes = layout(STANDARD)
        expected = P.find_panes(nodes, VSCODE)
        generator = random.Random(3)
        for _ in range(30):
            shuffled = nodes[:]
            generator.shuffle(shuffled)
            self.assertEqual(P.find_panes(shuffled, VSCODE), expected)

    def test_a_pane_that_is_not_in_the_profile_is_not_guessed(self):
        cells = [("mystery", Rect(0, 0, 500, 800)), ("editor", Rect(500, 0, 500, 800))]
        self.assertEqual(names(P.find_panes(layout(cells), VSCODE)), ["editor"])

    def test_missing_part_fails_the_tiling_report(self):
        panes = P.find_panes(layout(STANDARD[:-1]), VSCODE)
        self.assertFalse(P.report(panes, WINDOW, tiles=True)["ok"])

    def test_overlap_is_reported(self):
        cells = [("editor", Rect(0, 0, 600, 800)), ("sidebar", Rect(500, 0, 400, 800))]
        panes = P.find_panes(layout(cells), VSCODE)
        self.assertEqual(P.report(panes, WINDOW)["overlaps"], [("sidebar", "editor")])


class GenericMatcherTests(unittest.TestCase):
    def nodes(self):
        return [
            P.Node((), Rect(0, 0, 100, 100), role="AXWindow"),
            P.Node((0,), Rect(0, 0, 40, 100), role="AXOutline", title="Folders"),
            P.Node((1,), Rect(40, 0, 60, 100), role="AXTable", subrole="AXList"),
            P.Node((1, 0), Rect(40, 0, 60, 10), role="AXRow"),
        ]

    def test_matches_on_role_title_subrole_and_requires_every_key(self):
        n = self.nodes()
        self.assertTrue(P.matches(n[1], {"role": "AXOutline", "title": "Folders"}))
        self.assertFalse(P.matches(n[1], {"role": "AXOutline", "title": "Other"}))
        self.assertTrue(P.matches(n[2], {"subrole": "AXList"}))

    def test_self_scope_uses_the_node_and_ancestor_scope_uses_the_ancestor(self):
        n = self.nodes()
        own = {"panes": [{"name": "rows", "match": {"role": "AXRow"}}]}
        self.assertEqual(P.find_panes(n, own)[0].frame, Rect(40, 0, 60, 10))
        parent = {
            "panes": [
                {
                    "name": "rows",
                    "match": {"role": "AXRow"},
                    "scope": {"ancestor": {"role": "AXTable"}},
                }
            ]
        }
        self.assertEqual(P.find_panes(n, parent)[0].frame, Rect(40, 0, 60, 100))

    def test_no_matching_ancestor_means_no_pane(self):
        profile = {
            "panes": [
                {
                    "name": "rows",
                    "match": {"role": "AXRow"},
                    "scope": {"ancestor": {"role": "AXSplitGroup"}},
                }
            ]
        }
        self.assertEqual(P.find_panes(self.nodes(), profile), [])

    def test_max_depth_ignores_deeper_markers(self):
        deep = {"panes": [{"name": "rows", "match": {"role": "AXRow"}, "max_depth": 1}]}
        shallow = {
            "panes": [{"name": "rows", "match": {"role": "AXRow"}, "max_depth": 2}]
        }
        self.assertEqual(P.find_panes(self.nodes(), deep), [])
        self.assertEqual(len(P.find_panes(self.nodes(), shallow)), 1)

    def test_same_name_with_different_frames_is_suffixed_and_same_frame_collapses(self):
        n = [
            P.Node((0,), Rect(0, 0, 10, 10), role="AXList"),
            P.Node((1,), Rect(20, 0, 10, 10), role="AXList"),
            P.Node((2,), Rect(20, 0, 10, 10), role="AXList"),
        ]
        panes = P.find_panes(
            n, {"panes": [{"name": "list", "match": {"role": "AXList"}}]}
        )
        self.assertEqual(names(panes), ["list 1", "list 2"])
        singleton = P.find_panes(
            n[1:], {"panes": [{"name": "list", "match": {"role": "AXList"}}]}
        )
        self.assertEqual(names(singleton), ["list"])

    def test_class_suffix_and_all_classes_semantics(self):
        node = P.Node((0,), Rect(0, 0, 1, 1), classes=frozenset({"a-icon", "b"}))
        self.assertTrue(P.matches(node, {"class_suffix": "-icon"}))
        self.assertTrue(P.matches(node, {"classes": ["a-icon", "b"]}))
        self.assertFalse(P.matches(node, {"classes": ["a-icon", "c"]}))


class ProfileValidationTests(unittest.TestCase):
    def check_invalid(self, profile, text):
        with self.assertRaises(P.ProfileError) as caught:
            P.validate(profile)
        self.assertIn(text, str(caught.exception))

    def pane(self, **changes):
        return {"name": "a", "match": {"role": "AXList"}, **changes}

    def test_bundled_profile_is_valid(self):
        self.assertIs(P.validate(VSCODE), VSCODE)

    def test_rejects_malformed_profiles_explicitly(self):
        self.check_invalid([], "object")
        self.check_invalid({"panes": []}, "panes")
        self.check_invalid({"panes": [self.pane()], "extra": 1}, "unknown profile")
        self.check_invalid({"panes": [self.pane(match={})]}, "non-empty")
        self.check_invalid(
            {"panes": [self.pane(match={"colour": "x"})]}, "unknown match"
        )
        self.check_invalid({"panes": [self.pane(match={"classes": "a"})]}, "classes")
        self.check_invalid({"panes": [self.pane(name="")]}, "name")
        self.check_invalid({"panes": [self.pane(), self.pane()]}, "duplicate")
        self.check_invalid({"panes": [self.pane(scope="parent")]}, "scope")
        self.check_invalid({"panes": [self.pane(max_depth=0)]}, "max_depth")
        self.check_invalid({"panes": [self.pane(max_depth=True)]}, "max_depth")
        self.check_invalid({"panes": [self.pane(typo=1)]}, "unknown keys")
        self.check_invalid({"panes": [self.pane()], "tiles": "yes"}, "tiles")

    def test_load_rejects_bad_names_missing_files_and_bad_json(self):
        for bad in ("", "../vscode", "VSCode", "a/b", None):
            with self.assertRaises(P.ProfileError):
                P.load_profile(bad)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(P.ProfileError):
                P.load_profile("absent", directory)
            (Path(directory) / "broken.json").write_text("{")
            with self.assertRaises(P.ProfileError):
                P.load_profile("broken", directory)


class CoreContractTests(unittest.TestCase):
    def test_core_modules_contain_no_application_names(self):
        root = Path(__file__).resolve().parents[1] / "window_hints"
        for name in ("profiles.py", "core.py"):
            text = (root / name).read_text().lower()
            for word in ("vscode", "outlook", "slack", "com.microsoft"):
                self.assertNotIn(word, text, f"{name} mentions {word}")


if __name__ == "__main__":
    unittest.main()
