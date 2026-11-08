import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "general" / "targeted_sleep.py"
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
            with (
                self.subTest(names=names),
                self.assertRaisesRegex(ValueError, "comma-separated list"),
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

    def test_refresh_keeps_targets_while_settings_are_unregistered(self):
        def unregistered(name):
            raise KeyError(name)

        before = self.module.ctx.lists["user.targeted_sleep_target"]
        with patch.object(
            self.module, "settings", types.SimpleNamespace(get=unregistered)
        ):
            self.module.refresh_targeted_sleep_targets()
        self.assertIs(self.module.ctx.lists["user.targeted_sleep_target"], before)

    def test_commands_are_anchored_and_available_awake_and_asleep(self):
        source = TALON_FILE.read_text()
        for mode in ("command", "dictation", "sleep"):
            with self.subTest(mode=mode):
                self.assertIn(f"mode: {mode}\n", source)
        for rule, command in (
            (
                "^ sleep {user.targeted_sleep_target} | "
                "stop listening {user.targeted_sleep_target} $",
                "speech.disable()",
            ),
            (
                "^ {user.targeted_sleep_target} sleep | "
                "{user.targeted_sleep_target} stop listening $",
                "speech.disable()",
            ),
            (
                "^ (wake | listen) [up] {user.targeted_sleep_target} | "
                "start listening {user.targeted_sleep_target} $",
                "speech.enable()",
            ),
            (
                "^ {user.targeted_sleep_target} (listen | wake) [up] | "
                "{user.targeted_sleep_target} start listening $",
                "speech.enable()",
            ),
        ):
            with self.subTest(rule=rule):
                self.assertIn(f"{rule}:\n    {command}\n", source)


if __name__ == "__main__":
    unittest.main()
