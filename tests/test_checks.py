import importlib.util
import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "repository_checks", ROOT / "scripts" / "check.py"
)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class CheckRunnerTests(unittest.TestCase):
    def test_talon_discovery_excludes_dependencies_and_finds_nested_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = root / "menus" / "example.talon"
            expected.parent.mkdir()
            expected.write_text("example: key(escape)\n")
            for name in checks.EXCLUDED_DIRECTORIES:
                excluded = root / name
                excluded.mkdir()
                (excluded / "ignored.talon").write_text("not repository source")
            self.assertEqual(checks.talon_files(root), [expected])

    def run_checks(self, arguments=(), returncodes=(0, 0, 0, 0)):
        with (
            patch.object(checks.importlib.util, "find_spec", return_value=object()),
            patch.object(Path, "is_file", return_value=True),
            patch.object(checks, "talon_files", return_value=[ROOT / "test.talon"]),
            patch.object(
                checks.subprocess,
                "run",
                side_effect=[
                    types.SimpleNamespace(returncode=code) for code in returncodes
                ],
            ) as run,
            patch("builtins.print"),
        ):
            status = checks.main(arguments)
        return status, run.call_args_list

    def test_default_checks_are_non_mutating_and_include_tests(self):
        status, calls = self.run_checks()
        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 4)
        self.assertNotIn("--fix", calls[0].args[0])
        self.assertIn("--check", calls[1].args[0])
        self.assertNotIn("--fix", calls[2].args[0])
        self.assertIn("unittest", calls[3].args[0])
        self.assertTrue(all(call.kwargs["cwd"] == ROOT for call in calls))

    def test_fix_mode_is_explicit(self):
        status, calls = self.run_checks(["--fix"])
        self.assertEqual(status, 0)
        self.assertIn("--fix", calls[0].args[0])
        self.assertNotIn("--check", calls[1].args[0])
        self.assertIn("--fix", calls[2].args[0])

    def test_lint_failure_still_runs_tests_and_returns_failure(self):
        status, calls = self.run_checks(returncodes=(0, 0, 1, 0))
        self.assertEqual(status, 1)
        self.assertEqual(len(calls), 4)
        self.assertIn("unittest", calls[-1].args[0])

    def test_missing_ruff_is_an_explicit_failure(self):
        with (
            patch.object(checks.importlib.util, "find_spec", return_value=None),
            patch.object(checks.subprocess, "run") as run,
            patch("builtins.print") as output,
        ):
            self.assertEqual(checks.main([]), 1)
        run.assert_not_called()
        self.assertIn("Ruff is missing", output.call_args.args[0])


@unittest.skipUnless(
    shutil.which("node")
    and (ROOT / "node_modules" / "@cursorless" / "talon-tools").is_dir(),
    "Node and npm ci are required for Talon linter integration tests",
)
class TalonLinterTests(unittest.TestCase):
    def lint(self, file, fix=False):
        return subprocess.run(
            [
                "node",
                str(ROOT / "scripts" / "lint_talon.mjs"),
                *(["--fix"] if fix else []),
                str(file),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_invalid_talon_is_rejected_and_not_rewritten_even_in_fix_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            source = "broken:\n    key(\n"
            file = Path(directory) / "broken.talon"
            file.write_text(source)
            for fix in (False, True):
                result = self.lint(file, fix)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid Talon syntax", result.stderr)
                self.assertEqual(file.read_text(), source)

    def test_formatting_check_is_read_only_and_fix_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "example.talon"
            source = "example:    key(escape)\n"
            file.write_text(source)
            result = self.lint(file)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(file.read_text(), source)
            result = self.lint(file, fix=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            formatted = file.read_text()
            self.assertNotEqual(formatted, source)
            result = self.lint(file)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(file.read_text(), formatted)

    def test_fix_removes_empty_header_in_one_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "global.talon"
            file.write_text("-\n\nexample:\n    key(escape)\n")
            result = self.lint(file, fix=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.lint(file)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
