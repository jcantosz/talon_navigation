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
        del self.application.attrs["AXManualAccessibility"]
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

        load(self.talon, "application_controls/inventory.py", self.module)

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

    def settle_calls(self, session):
        return [
            call
            for call in self.talon.cron.after.call_args_list
            if call.args[1] == session._settle
        ]

    def test_already_enabled_app_is_scanned_once(self):
        self.actions.accessibility_show_application_numbers()

        self.assertEqual(self.settle_calls(self.module._session), [])

    def test_just_enabled_app_rescans_until_tree_settles(self):
        for attribute in ("AXEnhancedUserInterface", "AXManualAccessibility"):
            self.application.attrs[attribute] = False
        self.talon.query_results = [self.button]
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        self.assertEqual(self.talon.native_calls[-1], ("show", ([self.button],)))
        self.assertEqual(len(self.settle_calls(session)), 1)

        self.talon.query_results = [self.button, self.popup]
        session._settle()
        self.assertEqual(
            self.talon.native_calls[-1], ("show", ([self.button, self.popup],))
        )
        shown = len(self.talon.native_calls)
        session._settle()
        session._settle()

        self.assertEqual(len(self.talon.native_calls), shown)
        self.assertEqual(len(self.settle_calls(session)), 3)
        self.assertIsNone(session.settle_job)

    def test_settle_rescans_are_bounded_and_cancelled_on_stop(self):
        self.application.attrs["AXEnhancedUserInterface"] = False
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        for _ in range(self.session_module.SETTLE_SCANS):
            session._settle()
        self.assertIsNone(session.settle_job)
        self.assertEqual(
            len(self.settle_calls(session)), self.session_module.SETTLE_SCANS
        )

        self.application.attrs["AXEnhancedUserInterface"] = False
        self.actions.accessibility_show_application_numbers()
        session = self.module._session
        job = session.settle_job
        self.assertIsNotNone(job)

        self.actions.accessibility_show_application_numbers()

        self.assertTrue(session.stopped)
        self.talon.cron.cancel.assert_any_call(job)


if __name__ == "__main__":
    unittest.main()
