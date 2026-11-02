import unittest
from unittest.mock import patch

# Talon imports packages; unittest discovery can load these modules top-level.
if __package__:
    from .accessibility_support import (
        ApplicationTestCase,
        Element,
        UIErr,
        load,
    )
else:
    from accessibility_support import (
        ApplicationTestCase,
        Element,
        UIErr,
        load,
    )


class ApplicationActivationTests(ApplicationTestCase):
    def test_manual_disable_is_preserved_until_explicit_enable(self):
        self.actions.accessibility_set_interfaces(False)

        self.assertFalse(self.actions.accessibility_prepare_active_app())
        self.assertIs(self.application.get("AXManualAccessibility"), False)
        self.assertIs(self.application.get("AXEnhancedUserInterface"), False)

        self.actions.accessibility_set_interfaces(True)

        self.assertTrue(self.actions.accessibility_prepare_active_app())
        self.assertIs(self.application.get("AXManualAccessibility"), True)
        self.assertIs(self.application.get("AXEnhancedUserInterface"), True)

    def test_manual_override_distinguishes_reused_process_ids(self):
        self.actions.accessibility_set_interfaces(False)
        self.talon.active_app.created_at = 1

        self.assertTrue(self.actions.accessibility_prepare_active_app())
        self.assertIs(self.application.get("AXManualAccessibility"), True)

    def test_disallowed_bundle_is_not_enabled_without_force(self):
        self.talon.settings["user.accessibility_activation_disallowed_bundles"] = (
            "com.other, com.example , "
        )

        self.assertFalse(self.actions.accessibility_prepare_active_app())
        self.actions.accessibility_set_interfaces(True)

        self.assertIsNone(self.application.get("AXManualAccessibility"))
        self.assertEqual(self.module._activation_overrides, {})
        self.talon.notify.assert_called_with(
            "Accessibility interfaces", "Activation is disallowed for com.example."
        )

        self.actions.accessibility_set_interfaces(True, force=True)

        self.assertIs(self.application.get("AXManualAccessibility"), True)

    def test_disallowed_bundle_can_still_be_disabled(self):
        self.talon.settings["user.accessibility_activation_disallowed_bundles"] = (
            "com.example"
        )
        self.application.attrs["AXManualAccessibility"] = True

        self.actions.accessibility_set_interfaces(False)

        self.assertIs(self.application.get("AXManualAccessibility"), False)

    def test_reload_resets_manual_activation_overrides(self):
        self.actions.accessibility_set_interfaces(False)

        load(self.talon, "accessibility/inventory.py", self.module)

        self.assertEqual(self.module._activation_overrides, {})
        self.assertTrue(self.module.Actions.accessibility_prepare_active_app())

    def test_activation_failure_is_reported(self):
        self.application.dead = True

        self.actions.accessibility_show_application_numbers()

        self.assertIsNone(self.module._session)
        self.assertIn(
            "Unable to enable accessibility interfaces",
            self.talon.notify.call_args[0][1],
        )

    def test_interface_toggle_failure_is_reported(self):
        self.application.dead = True

        self.actions.accessibility_set_interfaces(True, False)

        self.assertIn(
            "Unable to update accessibility interfaces",
            self.talon.notify.call_args[0][1],
        )

    def test_unsupported_activation_attributes_are_not_an_operational_failure(self):
        with patch.object(Element, "__setitem__", side_effect=UIErr("unsupported")):
            self.actions.accessibility_set_interfaces(True)

        self.talon.notify.assert_called_with(
            "Accessibility interfaces", "Enabled: No supported writable interfaces"
        )


if __name__ == "__main__":
    unittest.main()
