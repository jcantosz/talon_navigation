import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

REPORTS = Path(__file__).resolve().parents[1] / "reports"


class Module:
    def action_class(self, cls):
        return cls


class CommandReportTests(unittest.TestCase):
    def setUp(self):
        package = types.ModuleType("navigation_report_tests")
        package.__path__ = [str(REPORTS)]
        core = types.ModuleType("navigation_report_tests.command_inventory")
        core.REPORTS = dict.fromkeys(("commands", "prefixes", "conflicts", "active"))
        core.write_report = Mock()
        self.notify = Mock()
        talon = types.SimpleNamespace(
            Module=Module, app=types.SimpleNamespace(notify=self.notify)
        )
        spec = importlib.util.spec_from_file_location(
            "navigation_report_tests.command_reports", REPORTS / "command_reports.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(
            sys.modules,
            {
                "talon": talon,
                "navigation_report_tests": package,
                "navigation_report_tests.command_inventory": core,
            },
        ):
            spec.loader.exec_module(self.module)

    def test_every_report_is_generated_before_browser_opens(self):
        for report_type in self.module.REPORTS:
            with (
                self.subTest(report=report_type),
                tempfile.TemporaryDirectory() as directory,
            ):
                self.module.REPORT_DIRECTORY = Path(directory)
                calls = []
                self.module.write_report = lambda *args: calls.append(("write", args))
                with patch.object(
                    self.module.webbrowser,
                    "open",
                    side_effect=lambda *args, **kwargs: (
                        calls.append(("open", args)) or True
                    ),
                ):
                    result = self.module.generate_and_open(report_type)
                self.assertEqual(result, Path(directory) / f"{report_type}.html")
                self.assertEqual(
                    calls,
                    [
                        ("write", (result, report_type)),
                        ("open", (result.as_uri(),)),
                    ],
                )

    def test_unknown_report_does_not_generate_or_open(self):
        with patch.object(self.module.webbrowser, "open") as browser:
            with self.assertRaises(ValueError):
                self.module.generate_and_open("unknown")
        self.module.write_report.assert_not_called()
        browser.assert_not_called()

    def test_browser_failure_is_explicit(self):
        with patch.object(self.module.webbrowser, "open", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Unable to open"):
                self.module.generate_and_open("commands")

    def test_action_notifies_and_logs_write_failure(self):
        self.module.write_report.side_effect = OSError("Disk full")
        with patch.object(self.module.webbrowser, "open") as browser:
            with self.assertLogs(level="ERROR"):
                self.module.Actions.navigation_command_report("prefixes")
        self.notify.assert_called_once()
        browser.assert_not_called()

    def test_action_notifies_and_logs_browser_failure(self):
        with patch.object(self.module.webbrowser, "open", return_value=False):
            with self.assertLogs(level="ERROR"):
                self.module.Actions.navigation_command_report("conflicts")
        self.notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
