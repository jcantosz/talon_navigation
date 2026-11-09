import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        Element,
        FakeTalon,
        UIErr,
        load,
    )
else:
    from accessibility_support import (
        Element,
        FakeTalon,
        UIErr,
        load,
    )


class DebugRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.talon = FakeTalon()
        self.talon.active_app = types.SimpleNamespace(pid=1, name="Example")
        self.module = load(self.talon, "diagnostics/debug_snapshots.py")

    def test_debug_import_does_not_register_application_numbering(self):
        self.assertEqual(self.talon.contexts, [])
        self.assertEqual(self.talon.declared_settings, {})
        self.assertEqual(self.talon.declared_tags, [])
        self.module.ui.register.assert_not_called()

    def test_diagnostic_surfaces_still_include_window_and_menu(self):
        window = Element(AXRole="AXWindow")
        menu = Element(AXRole="AXMenu")
        self.talon.active_app.element = Element(AXFocusedWindow=window)
        self.talon.active_menu = menu
        with patch.object(self.module, "collect", side_effect=[window, menu]):
            self.assertEqual(
                self.module._inventories(self.talon.active_app),
                [("focused-window", window), ("active-menu", menu)],
            )

    def test_partial_snapshot_notifies_without_changing_directory_permissions(self):
        with (
            patch.object(self.module, "_inventories", return_value=[]),
            patch.object(
                self.module,
                "write_snapshots",
                return_value=([Path("example.json")], True),
            ),
            patch("builtins.print"),
        ):
            self.module.Actions.accessibility_debug_snapshot()

        self.talon.notify.assert_called_with(
            "Accessibility debug snapshots",
            "Saved PARTIAL snapshots; see the errors and surfaces fields.",
        )

    def test_snapshot_write_failure_logs_and_notifies(self):
        with (
            patch.object(self.module, "_inventories", return_value=[]),
            patch.object(
                self.module, "write_snapshots", side_effect=PermissionError("read only")
            ),
            self.assertLogs(level="ERROR") as logged,
        ):
            self.module.Actions.accessibility_debug_snapshot()

        self.assertIn("PermissionError", "\n".join(logged.output))
        self.talon.notify.assert_called_with(
            "Accessibility debug snapshots",
            "Unable to capture or save accessibility snapshots.",
        )

    def test_inventory_read_failure_logs_and_notifies(self):
        with (
            patch.object(self.module, "_inventories", side_effect=UIErr("unavailable")),
            self.assertLogs(level="ERROR"),
        ):
            self.module.Actions.accessibility_debug_inventory()

        self.talon.notify.assert_called_with(
            "Accessibility debug inventory",
            "Unable to read the focused accessibility surfaces.",
        )

    def test_no_active_app_does_not_attempt_capture(self):
        self.talon.active_app = None
        with patch.object(self.module, "_inventories") as inventories:
            self.module.Actions.accessibility_debug_inventory()
            self.module.Actions.accessibility_debug_snapshot()

        inventories.assert_not_called()
        self.assertEqual(self.talon.notify.call_count, 2)


if __name__ == "__main__":
    unittest.main()
