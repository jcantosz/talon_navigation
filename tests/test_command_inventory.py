import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "inventory",
    Path(__file__).resolve().parents[1] / "reports" / "command_inventory.py",
)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class Literal:
    def __init__(self, name):
        self.name = name


class RuleRef:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"<{self.name}>"


class Seq:
    def __init__(self, *children):
        self.children = children


class Alt(Seq):
    pass


class Opt(Seq):
    pass


class Rep(Seq):
    pass


class InventoryTests(unittest.TestCase):
    def report_data(self):
        return {
            "commands": [],
            "duplicates": [],
            "overlaps": [],
            "possible": [],
            "prefixes": [],
        }

    def embedded_data(self, html):
        marker = '<script id="inventory-data" type="application/json">'
        return json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])

    def test_each_report_starts_in_its_own_view(self):
        for report_type, (title, section, status) in inventory.REPORTS.items():
            with self.subTest(report=report_type):
                html = inventory.render_report(self.report_data(), report_type)
                data = self.embedded_data(html)
                self.assertEqual(data["report"], {"section": section, "status": status})
                self.assertIn(f"<title>{title}</title>", html)
                self.assertNotIn("__DATA__", html)
                self.assertNotIn("__TITLE__", html)

    def test_render_does_not_mutate_snapshot(self):
        data = self.report_data()
        inventory.render_report(data, "active")
        self.assertNotIn("report", data)

    def test_script_closing_tags_in_command_titles_are_not_executable(self):
        data = self.report_data()
        dangerous = '</script><script>alert("injected")</script>'
        data["commands"] = [{"rule": dangerous}]
        html = inventory.render_report(data)
        self.assertNotIn(dangerous, html)
        self.assertEqual(self.embedded_data(html)["commands"][0]["rule"], dangerous)

    def test_unknown_report_is_rejected(self):
        with self.assertRaises(KeyError):
            inventory.render_report(self.report_data(), "unknown")

    def test_write_report_creates_directory_and_refreshes_content(self):
        data = self.report_data()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "reports" / "commands.html"
            with (
                patch.object(inventory, "snapshot", return_value=data),
                patch("builtins.print"),
            ):
                inventory.write_report(output, "prefixes")
                self.assertEqual(
                    self.embedded_data(output.read_text())["report"]["section"],
                    "prefixes",
                )
                inventory.write_report(output, "active")
                self.assertEqual(
                    self.embedded_data(output.read_text())["report"]["status"], "active"
                )

    def test_failed_report_replacement_preserves_existing_snapshot_and_cleans_temp(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "commands.html"
            output.write_text("previous snapshot")
            with patch.object(inventory, "snapshot", return_value=self.report_data()):
                with patch.object(
                    Path, "replace", side_effect=OSError("Cannot replace")
                ):
                    with self.assertRaises(OSError):
                        inventory.write_report(output)
            self.assertEqual(output.read_text(), "previous snapshot")
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_aliases_and_optional_words(self):
        node = Seq(
            Alt(Literal("show"), Literal("open")),
            Literal("commands"),
            Opt(Literal("window")),
        )
        self.assertEqual(
            inventory.variants(node),
            {
                ("show", "commands"),
                ("open", "commands"),
                ("show", "commands", "window"),
                ("open", "commands", "window"),
            },
        )

    def test_optional_leading_word_prefixes(self):
        self.assertEqual(
            inventory.first_tokens(Seq(Opt(Literal("show")), Literal("menu"))),
            ({"show", "menu"}, False),
        )

    def test_reference_is_symbolic_not_invented(self):
        self.assertEqual(
            inventory.variants(Seq(Literal("menu"), RuleRef("user.target"))),
            {("menu", "<user.target>")},
        )

    def test_repetition_is_explicitly_limited_but_indexed(self):
        node = Rep(Literal("word"))
        with self.assertRaises(inventory.ExpansionLimit):
            inventory.variants(node)
        self.assertEqual(inventory.first_tokens(node), ({"word"}, False))

    def test_combinatorial_limit(self):
        node = Seq(*(Opt(Literal(str(i))) for i in range(9)))
        with self.assertRaises(inventory.ExpansionLimit):
            inventory.variants(node)

    def test_reference_overlap_requires_nonempty_words(self):
        self.assertTrue(inventory.could_match(("menu", "<target>"), ("menu", "back")))
        self.assertTrue(
            inventory.could_match(
                ("help", "<text>", "please"), ("help", "many", "words", "please")
            )
        )
        self.assertFalse(inventory.could_match(("menu", "<target>"), ("menu",)))
        self.assertFalse(inventory.could_match(("menu", "<target>"), ("show", "back")))
        self.assertFalse(
            inventory.could_match(("menu", "<target>", "end"), ("menu", "back"))
        )

    def commands(self, *rules):
        return [
            {
                "id": i,
                "grammar": grammar,
                "anchor": "",
                "prefixes": prefixes,
                "file": f"{i}.talon",
                "package": f"package{i}",
                "active": active,
            }
            for i, (grammar, prefixes, active) in enumerate(rules)
        ]

    def test_literal_overlap_across_different_grammar_patterns(self):
        commands = self.commands(
            ("show menu", ["show"], True),
            ("(show | open) menu", ["show", "open"], True),
        )
        result = inventory.build_analysis(
            commands,
            [{("show", "menu")}, {("show", "menu"), ("open", "menu")}],
        )
        self.assertEqual(result["duplicates"], [])
        self.assertEqual(result["overlaps"][0]["label"], "show menu")
        self.assertEqual(result["overlaps"][0]["active"], 2)

    def test_same_grammar_is_not_double_counted_as_phrase_overlap(self):
        commands = self.commands(
            ("show menu", ["show"], True),
            ("show menu", ["show"], False),
        )
        result = inventory.build_analysis(
            commands, [{("show", "menu")}, {("show", "menu")}]
        )
        self.assertEqual(len(result["duplicates"]), 1)
        self.assertEqual(result["duplicates"][0]["active"], 1)
        self.assertEqual(result["overlaps"], [])

    def test_potential_overlap_is_not_mislabeled_as_confirmed(self):
        commands = self.commands(
            ("menu back", ["menu"], True),
            ("menu <target>", ["menu"], True),
        )
        result = inventory.build_analysis(
            commands, [{("menu", "back")}, {("menu", "<target>")}]
        )
        self.assertEqual(result["duplicates"], [])
        self.assertEqual(result["overlaps"], [])
        self.assertEqual(len(result["possible"]), 1)
        self.assertEqual(result["possible"][0]["active"], 2)

    def test_unknown_leading_capture_is_not_scanned_as_matching_everything(self):
        commands = self.commands(
            ("menu back", ["menu"], True),
            ("<text>", ["<text>"], True),
        )
        result = inventory.build_analysis(commands, [{("menu", "back")}, {("<text>",)}])
        self.assertEqual(result["possible"], [])
        self.assertIn("<text>", [row["label"] for row in result["prefixes"]])

    def test_anchors_distinguish_duplicate_grammar_groups(self):
        commands = self.commands(("help", ["help"], True), ("help", ["help"], True))
        commands[1]["anchor"] = "$"
        result = inventory.build_analysis(commands, [{("help",)}, {("help",)}])
        self.assertEqual(result["duplicates"], [])


if __name__ == "__main__":
    unittest.main()
