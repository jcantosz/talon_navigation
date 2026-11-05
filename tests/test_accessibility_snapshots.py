import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "snapshots",
    Path(__file__).resolve().parents[1] / "diagnostics" / "snapshots.py",
)
snapshots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshots)


class UIError(Exception):
    pass


class Element:
    def dump(self):
        return {
            "AXRole": "AXButton",
            "AXTitle": "Private channel",
            "AXValue": "Private message",
            "AXChildren": ["not serialized"],
        }


class SnapshotTests(unittest.TestCase):
    def surfaces(self, errors=(), truncated=False):
        node = SimpleNamespace(
            element=Element(),
            path=(0, 1),
            actions=("AXPress",),
            matches_show_numbers=True,
        )
        inventory = SimpleNamespace(nodes=(node,), errors=errors, truncated=truncated)
        return [("focused-window", inventory)]

    def test_redacted_snapshot_preserves_structure_and_removes_text(self):
        application = SimpleNamespace(name="Slack", bundle="com.example", pid=42)

        data = snapshots.snapshot_data(
            application, self.surfaces(), UIError, redacted=True
        )

        self.assertEqual(data["application"]["name"], "<redacted>")
        attributes = data["nodes"][0]["attributes"]
        self.assertEqual(attributes["AXRole"], "AXButton")
        self.assertEqual(attributes["AXTitle"], "<redacted>")
        self.assertEqual(attributes["AXValue"], "<redacted>")
        self.assertNotIn("AXChildren", attributes)

    def test_writes_full_and_redacted_files_per_bundle(self):
        application = SimpleNamespace(name="Slack", bundle="com.example", pid=42)
        with tempfile.TemporaryDirectory() as directory:
            paths, partial = snapshots.write_snapshots(
                Path(directory), application, self.surfaces(), UIError
            )

            self.assertFalse(partial)

            self.assertEqual(
                {path.name for path in paths},
                {"com.example.full.json", "com.example.redacted.json"},
            )
            full = json.loads((Path(directory) / "com.example.full.json").read_text())
            redacted = json.loads(
                (Path(directory) / "com.example.redacted.json").read_text()
            )
            self.assertEqual(
                full["nodes"][0]["attributes"]["AXTitle"], "Private channel"
            )
            self.assertEqual(
                redacted["nodes"][0]["attributes"]["AXTitle"], "<redacted>"
            )
            self.assertEqual(full["captured_at"], redacted["captured_at"])

    def test_collection_errors_and_truncation_mark_snapshot_partial(self):
        application = SimpleNamespace(name="Slack", bundle="com.example", pid=42)
        surfaces = self.surfaces(errors=("root/3: UIError: gone",), truncated=True)
        with tempfile.TemporaryDirectory() as directory:
            _, partial = snapshots.write_snapshots(
                Path(directory), application, surfaces, UIError
            )
            redacted = json.loads(
                (Path(directory) / "com.example.redacted.json").read_text()
            )

        self.assertTrue(partial)
        self.assertEqual(
            redacted["surfaces"],
            [
                {
                    "surface": "focused-window",
                    "nodes": 1,
                    "errors": ["root/3: UIError: gone"],
                    "truncated": True,
                }
            ],
        )

    def test_full_and_redacted_share_one_element_dump(self):
        application = SimpleNamespace(name="Example", bundle="com.example", pid=42)
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                Element, "dump", autospec=True, return_value={"AXTitle": "one"}
            ) as dump,
        ):
            snapshots.write_snapshots(
                Path(directory), application, self.surfaces(), UIError
            )

        dump.assert_called_once()

    def test_dump_failure_is_preserved_and_marks_capture_partial(self):
        application = SimpleNamespace(name="Example", bundle="com.example", pid=42)
        with patch.object(Element, "dump", side_effect=UIError("unavailable")):
            data = snapshots.snapshot_data(application, self.surfaces(), UIError)

        self.assertTrue(snapshots.is_partial(data))
        self.assertIn("UIError: unavailable", data["errors"][0])
        self.assertEqual(data["nodes"][0]["attributes"], {})


if __name__ == "__main__":
    unittest.main()
