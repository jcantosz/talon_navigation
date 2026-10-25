import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = (
    Path(__file__).resolve().parents[1] / "general" / "targeted_sleep.py"
)
TALON_FILE = SOURCE.with_suffix(".talon")


class Context:
    def __init__(self):
        self.lists = {}


class Module:
    def setting(self, *_args, **_kwargs):
        pass

    def list(self, *_args, **_kwargs):
        pass


class TargetedSleepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.interval = unittest.mock.Mock()

        def setting_value(name):
            return {
                "user.targeted_sleep_name": "office mac",
                "user.targeted_sleep_names": "",
            }[name]

        talon = types.SimpleNamespace(
            Context=Context,
            Module=Module,
            cron=types.SimpleNamespace(interval=cls.interval),
            settings=types.SimpleNamespace(get=setting_value),
        )
        spec = importlib.util.spec_from_file_location(
            "targeted_sleep_under_test", SOURCE
        )
        cls.module = importlib.util.module_from_spec(spec)
        with (
            patch.dict(sys.modules, {"talon": talon}),
            patch("socket.gethostname", return_value="Office-Mac.local"),
            patch("platform.system", return_value="Darwin"),
        ):
            spec.loader.exec_module(cls.module)

    def test_hostname_is_converted_to_a_spoken_form(self):
        self.assertEqual(
            self.module.spoken_form("Jesses-MacBook-Pro.local"),
            "jesses macbook pro local",
        )

    def test_machine_and_current_os_are_the_only_targets(self):
        self.assertEqual(
            self.module.targeted_sleep_targets("Office Mac", "Darwin"),
            {
                "office mac": "machine",
                "mac": "operating-system",
                "mac os": "operating-system",
            },
        )
        self.assertEqual(
            self.module.targeted_sleep_targets("Desk-PC", "Windows"),
            {
                "desk pc": "machine",
                "windows": "operating-system",
                "microsoft": "operating-system",
                "win": "operating-system",
            },
        )

    def test_multiple_machine_names_are_supported(self):
        self.assertEqual(
            self.module.targeted_sleep_targets("Office, Desk-PC", "Linux"),
            {
                "office": "machine",
                "desk pc": "machine",
                "linux": "operating-system",
            },
        )

    def test_empty_machine_name_is_rejected(self):
        for names in ("", "office,"):
            with self.subTest(names=names), self.assertRaisesRegex(
                ValueError, "comma-separated list"
            ):
                self.module.targeted_sleep_targets(names, "Linux")

    def test_context_list_is_initialized_and_periodically_refreshed(self):
        self.assertEqual(
            self.module.ctx.lists["user.targeted_sleep_target"],
            {
                "office mac": "machine",
                "mac": "operating-system",
                "mac os": "operating-system",
            },
        )
        self.interval.assert_called_once_with(
            "1s", self.module.refresh_targeted_sleep_targets
        )

    def test_commands_are_anchored_and_available_awake_and_asleep(self):
        source = TALON_FILE.read_text()
        for mode in ("command", "dictation", "sleep"):
            with self.subTest(mode=mode):
                self.assertIn(f"mode: {mode}\n", source)
        self.assertIn(
            "^sleep {user.targeted_sleep_target}$:\n    speech.disable()\n",
            source,
        )
        self.assertIn(
            "^{user.targeted_sleep_target} sleep$:\n    speech.disable()\n",
            source,
        )
        self.assertIn(
            "^wake [up] {user.targeted_sleep_target}$:\n    speech.enable()\n",
            source,
        )
        self.assertIn(
            "^{user.targeted_sleep_target} wake [up]$:\n    speech.enable()\n",
            source,
        )


if __name__ == "__main__":
    unittest.main()
