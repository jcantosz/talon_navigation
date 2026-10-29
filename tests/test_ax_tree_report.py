import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ax_tree_report",
    Path(__file__).resolve().parents[1] / "scripts" / "ax_tree_report.py",
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def record(path, role, actions=(), title=""):
    return {
        "surface": "focused-window",
        "path": path,
        "attributes": {"AXRole": role, "AXTitle": title},
        "actions": list(actions),
    }


class AxTreeReportTests(unittest.TestCase):
    def test_collapses_scaffolding_but_preserves_branching_container(self):
        records = [
            record([], "AXWindow"),
            record([0], "AXGroup"),
            record([0, 0], "AXGroup"),
            record([0, 0, 0], "AXButton", ("AXPress",), "One"),
            record([0, 0, 1], "AXButton", ("AXPress",), "Two"),
        ]

        root = report.build_surfaces(records)[0][1]
        result = report.prune(root, root=True)[0]

        self.assertEqual(len(result.children), 1)
        container = result.children[0]
        self.assertEqual(container.attributes["AXRole"], "AXGroup")
        self.assertEqual([child.name for child in container.children], ["One", "Two"])

    def test_ignores_scroll_only_nodes_and_escapes_names(self):
        snapshot = {
            "application": {"name": "Example"},
            "captured_at": "now",
            "nodes": [
                record([], "AXWindow"),
                record([0], "AXStaticText", ("AXScrollToVisible",), "Skip"),
                record([1], "AXButton", ("AXPress",), "<Open>"),
            ],
        }

        rendered = report.render(snapshot)

        self.assertNotIn(">Skip<", rendered)
        self.assertIn("&lt;Open&gt;", rendered)
        self.assertIn('class="control"', rendered)
        self.assertIn('class="action">Press</span>', rendered)

    def test_collapses_actionable_group_with_one_control_branch(self):
        records = [
            record([], "AXWindow"),
            record([0], "AXGroup", ("AXPress",), "Redundant wrapper"),
            record([0, 0], "AXGroup", ("AXPress",), "Nested wrapper"),
            record([0, 0, 0], "AXButton", ("AXPress",), "Useful control"),
        ]

        root = report.build_surfaces(records)[0][1]
        result = report.prune(root, root=True)[0]

        self.assertEqual(len(result.children), 1)
        self.assertEqual(result.children[0].name, "Useful control")

    def test_spatial_view_uses_frames_and_dom_class_group_names(self):
        root = record([], "AXWindow", title="Window")
        root["attributes"]["AXFrame"] = {
            "x": 100,
            "y": 50,
            "width": 800,
            "height": 600,
        }
        group = record([0], "AXGroup")
        group["attributes"].update(
            {
                "AXDOMClassList": ["p-channel_sidebar__link"],
                "AXFrame": {"x": 100, "y": 50, "width": 200, "height": 600},
            }
        )
        control = record([0, 0], "AXButton", ("AXPress",), "Browse")
        control["attributes"]["AXFrame"] = {
            "x": 120,
            "y": 80,
            "width": 80,
            "height": 30,
        }
        sibling = record([0, 1], "AXButton", ("AXPress",), "Search")
        sibling["attributes"]["AXFrame"] = {
            "x": 120,
            "y": 120,
            "width": 80,
            "height": 30,
        }
        background = record([1], "AXGroup", ("AXShowMenu",))
        background["attributes"].update(
            {
                "AXDOMClassList": ["p-theme_background"],
                "AXFrame": {"x": 100, "y": 50, "width": 800, "height": 600},
            }
        )
        snapshot = {
            "application": {"name": "Example"},
            "captured_at": "now",
            "nodes": [root, group, control, sibling, background],
        }

        rendered = report.render(snapshot)

        self.assertIn('id="spatial-view" class="view active"', rendered)
        self.assertIn('class="spatial-group', rendered)
        self.assertIn(
            'class="spatial-group depth-1 searchable" '
            'style="left:0.000%;top:0.000%;width:100.000%;height:100.000%',
            rendered,
        )
        self.assertIn("channel sidebar", rendered)
        self.assertIn("theme background", rendered)
        self.assertIn("left:2.500%;top:5.000%", rendered)
        self.assertNotIn('class="path"', rendered)


if __name__ == "__main__":
    unittest.main()
