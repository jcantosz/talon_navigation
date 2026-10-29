import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "snapshots",
    Path(__file__).resolve().parents[1] / "accessibility" / "snapshots.py",
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
    def surfaces(self):
        node = SimpleNamespace(
            element=Element(),
            path=(0, 1),
            actions=("AXPress",),
            matches_show_numbers=True,
        )
        return [("focused-window", SimpleNamespace(nodes=(node,)))]

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
            paths = snapshots.write_snapshots(
                Path(directory), application, self.surfaces(), UIError
            )

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


if __name__ == "__main__":
    unittest.main()
